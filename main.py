
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    String,
    Index,
    create_engine,
    select,
    text
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    sessionmaker
)

load_dotenv()

# ==========================================
# CONFIGURACION DE BASE DE DATOS
# ==========================================

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("No se encontro DATABASE_URL.")

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgres://",
        "postgresql+psycopg://",
        1
    )
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1
    )

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False
)


# ==========================================
# MIGRACION AUTOMATICA DE BASE DE DATOS
# ==========================================

def migrar_base_datos():

    with engine.begin() as conexion:

        # Agregar identificador de paquete si no existe
        conexion.execute(text("""
            ALTER TABLE mediciones
            ADD COLUMN IF NOT EXISTS id_paquete VARCHAR(100);
        """))

        # Crear indice unico para identificadores no nulos
        conexion.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_mediciones_id_paquete
            ON mediciones (id_paquete)
            WHERE id_paquete IS NOT NULL;
        """))

        # Evitar alertas activas duplicadas para el mismo nodo,
        # sensor y tipo de alerta.
        conexion.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS
            uq_alerta_activa_por_sensor
            ON alertas (nodo, dispositivo_id, tipo_alerta)
            WHERE estado = 'ACTIVA';
        """))


# ==========================================
# MODELO ORM
# ==========================================

class Base(DeclarativeBase):
    pass


class Medicion(Base):

    __tablename__ = "mediciones"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    id_paquete: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True
    )

    colmena: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    nodo: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    temperatura: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    humedad: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class Alerta(Base):

    __tablename__ = "alertas"

    id_alerta: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )

    nodo: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    dispositivo_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    tipo_alerta: Mapped[str] = mapped_column(
        String(50),
        nullable=False
    )

    descripcion: Mapped[str] = mapped_column(
        String,
        nullable=False
    )

    fecha_hora: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    estado: Mapped[str] = mapped_column(
        String(20),
        default="ACTIVA",
        nullable=False
    )

    fecha_cierre: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    __table_args__ = (
        Index(
            "uq_alerta_activa_por_sensor",
            "nodo",
            "dispositivo_id",
            "tipo_alerta",
            unique=True,
            postgresql_where=text("estado = 'ACTIVA'")
        ),
    )


# ==========================================
# ESQUEMAS PYDANTIC
# ==========================================

class MedicionCrear(BaseModel):

    id_paquete: str | None = Field(
        default=None,
        min_length=1,
        max_length=100
    )

    colmena: str = Field(
        min_length=1,
        max_length=50
    )

    nodo: str = Field(
        min_length=1,
        max_length=50
    )

    temperatura: float = Field(
        ge=-50,
        le=100
    )

    humedad: float = Field(
        ge=0,
        le=100
    )


class MedicionRespuesta(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id: int
    id_paquete: str | None = None
    colmena: str
    nodo: str
    temperatura: float
    humedad: float
    fecha: datetime


class AlertaCrear(BaseModel):

    nodo: str = Field(min_length=1, max_length=50)
    dispositivo_id: str = Field(min_length=1, max_length=50)
    tipo_alerta: str = Field(min_length=1, max_length=50)
    descripcion: str = Field(min_length=1)


class AlertaRespuesta(BaseModel):

    model_config = ConfigDict(from_attributes=True)

    id_alerta: int
    nodo: str
    dispositivo_id: str
    tipo_alerta: str
    descripcion: str
    fecha_hora: datetime
    estado: str
    fecha_cierre: datetime | None


# ==========================================
# SESIONES DE BASE DE DATOS
# ==========================================

def obtener_sesion():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


SesionDB = Annotated[
    Session,
    Depends(obtener_sesion)
]


# ==========================================
# INICIO Y CIERRE DE LA API
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    Base.metadata.create_all(bind=engine)

    migrar_base_datos()

    yield

    engine.dispose()


app = FastAPI(
    title="KAABLAB API",
    description="API para el monitoreo de colmenas.",
    version="1.2.0",
    lifespan=lifespan
)


# ==========================================
# ENDPOINT PRINCIPAL
# ==========================================

@app.get("/")
def inicio():

    return {
        "mensaje": "Bienvenido a KAABLAB API",
        "estado": "Funcionando"
    }


# ==========================================
# ESTADO DE LA API
# ==========================================

@app.get("/health")
def verificar_estado():

    return {
        "estado": "saludable",
        "servicio": "KAABLAB API"
    }


# ==========================================
# REGISTRAR MEDICION
# ==========================================

@app.post(
    "/mediciones",
    response_model=MedicionRespuesta,
    status_code=status.HTTP_201_CREATED
)
def crear_medicion(
    datos: MedicionCrear,
    db: SesionDB
):

    nueva_medicion = Medicion(
        id_paquete=datos.id_paquete,
        colmena=datos.colmena,
        nodo=datos.nodo,
        temperatura=datos.temperatura,
        humedad=datos.humedad
    )

    try:

        db.add(nueva_medicion)

        db.commit()

        db.refresh(nueva_medicion)

        return nueva_medicion

    except IntegrityError:

        db.rollback()

        if datos.id_paquete is not None:

            existente = db.scalar(
                select(Medicion.id).where(
                    Medicion.id_paquete == datos.id_paquete
                )
            )

            if existente is not None:

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Este paquete ya fue registrado."
                )

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No fue posible registrar la medicion."
        )


# ==========================================
# OBTENER MEDICIONES
# ==========================================

@app.get(
    "/mediciones",
    response_model=list[MedicionRespuesta]
)
def obtener_mediciones(
    db: SesionDB,
    colmena: str | None = None,
    nodo: str | None = None,
    limite: int = Query(
        default=100,
        ge=1,
        le=1000
    )
):

    consulta = select(Medicion)

    if colmena:
        consulta = consulta.where(
            Medicion.colmena == colmena
        )

    if nodo:
        consulta = consulta.where(
            Medicion.nodo == nodo
        )

    consulta = consulta.order_by(
        Medicion.id.desc()
    ).limit(limite)

    return db.scalars(consulta).all()


# ==========================================
# OBTENER TODAS LAS MEDICIONES
# ==========================================

@app.get(
    "/mediciones/all",
    response_model=list[MedicionRespuesta]
)
def obtener_todas_las_mediciones(
    db: SesionDB
):

    consulta = select(Medicion).order_by(
        Medicion.id.desc()
    )

    return db.scalars(consulta).all()


# ==========================================
# OBTENER MEDICIONES POR FECHA
# ==========================================

@app.get(
    "/mediciones/fecha/{fecha}",
    response_model=list[MedicionRespuesta]
)
def obtener_mediciones_fecha(
    fecha: date,
    db: SesionDB
):

    inicio = datetime.combine(
        fecha,
        time.min,
        tzinfo=timezone.utc
    )

    fin = inicio + timedelta(days=1)

    consulta = select(Medicion).where(
        Medicion.fecha >= inicio,
        Medicion.fecha < fin
    ).order_by(Medicion.fecha.desc())

    return db.scalars(consulta).all()


# ==========================================
# OBTENER MEDICIONES POR RANGO DE FECHAS
# ==========================================

@app.get(
    "/mediciones/fecha/rango/{fecha_inicio}/{fecha_fin}",
    response_model=list[MedicionRespuesta]
)
def obtener_mediciones_rango(
    fecha_inicio: date,
    fecha_fin: date,
    db: SesionDB
):

    if fecha_inicio > fecha_fin:

        raise HTTPException(
            status_code=400,
            detail="La fecha inicial no puede ser posterior a la fecha final."
        )

    inicio = datetime.combine(
        fecha_inicio,
        time.min,
        tzinfo=timezone.utc
    )

    fin = datetime.combine(
        fecha_fin + timedelta(days=1),
        time.min,
        tzinfo=timezone.utc
    )

    consulta = select(Medicion).where(
        Medicion.fecha >= inicio,
        Medicion.fecha < fin
    ).order_by(Medicion.fecha.desc())

    return db.scalars(consulta).all()


# ==========================================
# OBTENER MEDICIONES A PARTIR DE UNA FECHA
# ==========================================

@app.get(
    "/mediciones/fecha/apartir/{fecha}",
    response_model=list[MedicionRespuesta]
)
def obtener_mediciones_a_partir(
    fecha: datetime,
    db: SesionDB
):

    if fecha.tzinfo is None:
        fecha = fecha.replace(
            tzinfo=timezone.utc
        )

    consulta = select(Medicion).where(
        Medicion.fecha >= fecha
    ).order_by(Medicion.fecha.desc())

    return db.scalars(consulta).all()


# ==========================================
# REGISTRAR ALERTA
# ==========================================

@app.post(
    "/alertas",
    response_model=AlertaRespuesta,
    status_code=status.HTTP_201_CREATED
)
def registrar_alerta(
    datos: AlertaCrear,
    db: SesionDB,
    response: Response
):
    nodo = datos.nodo.strip()
    dispositivo_id = datos.dispositivo_id.strip()
    tipo_alerta = datos.tipo_alerta.strip().upper()
    descripcion = datos.descripcion.strip()

    if not nodo or not dispositivo_id or not tipo_alerta or not descripcion:
        raise HTTPException(
            status_code=400,
            detail="Los campos de la alerta no pueden estar vacios."
        )

    # Si ya existe una alerta activa idéntica, se devuelve la existente.
    alerta_existente = db.scalar(
        select(Alerta).where(
            Alerta.nodo == nodo,
            Alerta.dispositivo_id == dispositivo_id,
            Alerta.tipo_alerta == tipo_alerta,
            Alerta.estado == "ACTIVA"
        )
    )

    if alerta_existente is not None:
        response.status_code = status.HTTP_200_OK
        return alerta_existente

    nueva_alerta = Alerta(
        nodo=nodo,
        dispositivo_id=dispositivo_id,
        tipo_alerta=tipo_alerta,
        descripcion=descripcion,
        estado="ACTIVA"
    )

    try:
        db.add(nueva_alerta)
        db.commit()
        db.refresh(nueva_alerta)
        return nueva_alerta

    except IntegrityError:
        db.rollback()

        # Protege también ante dos solicitudes simultáneas.
        alerta_existente = db.scalar(
            select(Alerta).where(
                Alerta.nodo == nodo,
                Alerta.dispositivo_id == dispositivo_id,
                Alerta.tipo_alerta == tipo_alerta,
                Alerta.estado == "ACTIVA"
            )
        )

        if alerta_existente is not None:
            response.status_code = status.HTTP_200_OK
            return alerta_existente

        raise HTTPException(
            status_code=500,
            detail="No fue posible registrar la alerta."
        )


# ==========================================
# DEVOLVER ALERTAS
# ==========================================

@app.get(
    "/alertas",
    response_model=list[AlertaRespuesta]
)
def devolver_alertas(
    db: SesionDB,
    nodo: str | None = None,
    dispositivo_id: str | None = None,
    tipo_alerta: str | None = None,
    estado: str | None = None,
    limite: int = Query(default=100, ge=1, le=1000)
):
    consulta = select(Alerta)

    if nodo:
        consulta = consulta.where(Alerta.nodo == nodo)

    if dispositivo_id:
        consulta = consulta.where(
            Alerta.dispositivo_id == dispositivo_id
        )

    if tipo_alerta:
        consulta = consulta.where(
            Alerta.tipo_alerta == tipo_alerta.upper()
        )

    if estado:
        estado = estado.upper()

        if estado not in ("ACTIVA", "CERRADA"):
            raise HTTPException(
                status_code=400,
                detail="El estado debe ser ACTIVA o CERRADA."
            )

        consulta = consulta.where(Alerta.estado == estado)

    consulta = consulta.order_by(
        Alerta.fecha_hora.desc()
    ).limit(limite)

    return db.scalars(consulta).all()


# ==========================================
# DEVOLVER UNA ALERTA POR SU ID
# ==========================================

@app.get(
    "/alertas/{id_alerta}",
    response_model=AlertaRespuesta
)
def devolver_alerta(
    id_alerta: int,
    db: SesionDB
):
    alerta = db.get(Alerta, id_alerta)

    if alerta is None:
        raise HTTPException(
            status_code=404,
            detail="Alerta no encontrada."
        )

    return alerta


# ==========================================
# CERRAR ALERTA
# ==========================================

@app.post(
    "/alertas/{id_alerta}/cerrar",
    response_model=AlertaRespuesta
)
def cerrar_alerta(
    id_alerta: int,
    db: SesionDB
):
    alerta = db.get(Alerta, id_alerta)

    if alerta is None:
        raise HTTPException(
            status_code=404,
            detail="Alerta no encontrada."
        )

    if alerta.estado == "CERRADA":
        return alerta

    alerta.estado = "CERRADA"
    alerta.fecha_cierre = datetime.now(timezone.utc)

    db.commit()
    db.refresh(alerta)

    return alerta



# ==========================================
# OBTENER MEDICION POR ID
# ==========================================

@app.get(
    "/mediciones/{medicion_id}",
    response_model=MedicionRespuesta
)
def obtener_medicion(
    medicion_id: int,
    db: SesionDB
):

    medicion = db.get(
        Medicion,
        medicion_id
    )

    if medicion is None:

        raise HTTPException(
            status_code=404,
            detail="Medicion no encontrada."
        )

    return medicion



