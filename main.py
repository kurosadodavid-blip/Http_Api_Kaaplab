from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Float, DateTime, Integer, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

DATABASE_URL = "postgresql+psycopg://kaablab_db_user:aybuVIPBT9DOroxDAmrjQ0J9JYTm4vCQ@dpg-db8313mq1p3s739cj4mg-a/kaablab_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Medicion(Base):
    __tablename__ = "mediciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    colmena_id: Mapped[str] = mapped_column(String(50), index=True)
    temperatura: Mapped[float] = mapped_column(Float)
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Base.metadata.create_all(bind=engine)

app = FastAPI(title="API de monitoreo de colmenas")


class MedicionEntrada(BaseModel):
    temperatura: float = Field(ge=-20, le=80)


def obtener_db():
    with SessionLocal() as db:
        yield db


@app.post("/colmenas/{colmena_id}/temperatura", status_code=201)
def guardar_temperatura(
    colmena_id: str,
    datos: MedicionEntrada,
    db: Session = Depends(obtener_db)
):
    medicion = Medicion(
        colmena_id=colmena_id,
        temperatura=datos.temperatura,
        fecha=datetime.now(timezone.utc)
    )

    db.add(medicion)
    db.commit()
    db.refresh(medicion)

    return {
        "mensaje": "Temperatura guardada",
        "id": medicion.id,
        "colmena_id": medicion.colmena_id,
        "temperatura": medicion.temperatura,
        "fecha": medicion.fecha
    }


@app.get("/colmenas/{colmena_id}/temperatura")
def consultar_historial(
    colmena_id: str,
    db: Session = Depends(obtener_db)
):
    consulta = (
        select(Medicion)
        .where(Medicion.colmena_id == colmena_id)
        .order_by(Medicion.fecha.desc())
    )

    mediciones = db.scalars(consulta).all()

    return [
        {
            "id": m.id,
            "temperatura": m.temperatura,
            "fecha": m.fecha
        }
        for m in mediciones
    ]


@app.get("/mediciones")
def consultar_todas(db: Session = Depends(obtener_db)):
    consulta = select(Medicion).order_by(Medicion.fecha.desc())
    mediciones = db.scalars(consulta).all()

    return [
        {
            "id": m.id,
            "colmena_id": m.colmena_id,
            "temperatura": m.temperatura,
            "fecha": m.fecha
        }
        for m in mediciones
    ]