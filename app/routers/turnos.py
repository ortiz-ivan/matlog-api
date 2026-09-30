from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, Admin, UsuarioActual
from app.models import Turno
from app.schemas import TurnoIn, TurnoOut

router = APIRouter(prefix="/api/turnos", tags=["turnos"])


def _obtener(db: DB, turno_id: int) -> Turno:
    turno = db.get(Turno, turno_id)
    if turno is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turno no encontrado")
    return turno


@router.get("", response_model=list[TurnoOut])
def listar(db: DB, _: UsuarioActual, incluir_inactivos: bool = False):
    consulta = select(Turno).order_by(Turno.hora_inicio)
    if not incluir_inactivos:
        consulta = consulta.where(Turno.activo)
    return db.scalars(consulta).all()


@router.post("", response_model=TurnoOut, status_code=status.HTTP_201_CREATED)
def crear(datos: TurnoIn, db: DB, _: UsuarioActual):
    turno = Turno(**datos.model_dump())
    db.add(turno)
    db.commit()
    return turno


@router.put("/{turno_id}", response_model=TurnoOut)
def actualizar(turno_id: int, datos: TurnoIn, db: DB, _: UsuarioActual):
    turno = _obtener(db, turno_id)
    for campo, valor in datos.model_dump().items():
        setattr(turno, campo, valor)
    turno.activo = True
    db.commit()
    return turno


@router.delete("/{turno_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar(turno_id: int, db: DB, _: Admin):
    # Se desactiva en lugar de borrar para no perder las clases asociadas.
    _obtener(db, turno_id).activo = False
    db.commit()
