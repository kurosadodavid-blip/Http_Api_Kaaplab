
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Annotated

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Float, Integer, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "No se encontro la variable de entorno DATABASE_URL."
    )

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


class Base(DeclarativeBase):
    pass


class Medicion(Base):
    __tablename__ = "mediciones"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        index=True
    )
    colmena: Mapped[str] = mapped_column(String(50), nullable=False)
    nodo: Mapped[str] = mapped_column(String(50), nullable=False)
    temperatura: Mapped[float] = mapped_column(Float, nullable=False)
    humedad: Mapped[float] = mapped_column(Float, nullable=False)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )


class MedicionCrear(BaseModel):
    colmena: str = Field(min_length=1, max_length=50)
    nodo: str = Field(min_length=1, max_length=50)
    temperatura: float = Field(ge=-50, le=100)
    humedad: float = Field(ge=0, le=100)


class MedicionRespuesta(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    colmena: str
    nodo: str
    temperatura: float
    humedad: float
    fecha: datetime


def obtener_sesion():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


SesionDB = Annotated[Session, Depends(obtener_sesion)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


app = FastAPI(
    title="KAABLAB API",
    description="API para registrar y consultar mediciones de colmenas.",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/")
def inicio():
    return {
        "mensaje": "KAABLAB API funcionando",
        "documentacion": "/docs"
    }


@app.get("/health")
def verificar_estado():
    return {"estado": "activo"}


@app.post(
    "/mediciones",
    response_model=MedicionRespuesta,
    status_code=status.HTTP_201_CREATED
)
def crear_medicion(datos: MedicionCrear, db: SesionDB):
    nueva_medicion = Medicion(
        colmena=datos.colmena,
        nodo=datos.nodo,
        temperatura=datos.temperatura,
        humedad=datos.humedad
    )

    db.add(nueva_medicion)
    db.commit()
    db.refresh(nueva_medicion)

    return nueva_medicion


@app.get(
    "/mediciones",
    response_model=list[MedicionRespuesta]
)
def listar_mediciones(
    db: SesionDB,
    colmena: str | None = None,
    nodo: str | None = None,
    limite: int = Query(default=100, ge=1, le=1000)
):
    consulta = select(Medicion)

    if colmena is not None:
        consulta = consulta.where(Medicion.colmena == colmena)

    if nodo is not None:
        consulta = consulta.where(Medicion.nodo == nodo)

    consulta = consulta.order_by(Medicion.id.desc()).limit(limite)

    return db.scalars(consulta).all()


@app.get(
    "/mediciones/{medicion_id}",
    response_model=MedicionRespuesta
)
def obtener_medicion(medicion_id: int, db: SesionDB):
    consulta = select(Medicion).where(Medicion.id == medicion_id)
    medicion = db.scalars(consulta).first()

    if medicion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontro la medicion."
        )

    return medicion
@app.get("/mediciones/fecha/{fecha}")
def obtener_registro_deLa_fecha_exacta(fecha: date):
    with SessionLocal() as db:
        consulta = select(Medicion).where(
            Medicion.fecha.cast(DateTime).date() == fecha
        )
        registros = db.scalars(consulta).all()

    if not registros:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron registros para la fecha especificada."
        )

    return registros

@app.get("/mediciones/fecha/rango/{fecha_inicio}/{fecha_fin}")
def obtener_registros_por_rango_de_fecha(
    fecha_inicio: date,
    fecha_fin: date
):
    with SessionLocal() as db:
        consulta = select(Medicion).where(
            Medicion.fecha.cast(DateTime).date().between(fecha_inicio, fecha_fin)
        )
        registros = db.scalars(consulta).all()

    if not registros:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron registros para el rango de fechas especificado."
        )

    return registros

@app.get("/mediciones/fecha/apartir/{fecha}")
def obtener_registros_apartir_de_fecha(fecha: date):
    with SessionLocal() as db:
        consulta = select(Medicion).where(
            Medicion.fecha.cast(DateTime).date() >= fecha
        )
        registros = db.scalars(consulta).all()

    if not registros:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No se encontraron registros a partir de la fecha especificada."
        )

    return registros

@app.get("/mediciones/all")
def obtener_todos_los_registros():
    with SessionLocal() as db:
        consulta = select(Medicion)
        registros = db.scalars(consulta).all()
        return registros