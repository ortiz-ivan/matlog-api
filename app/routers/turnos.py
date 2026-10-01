from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB, Admin, UsuarioActual
from app.models import Turno, TurnoDia
from app.schemas import TurnoIn, TurnoOut

router = APIRouter(prefix="/api/turnos", tags=["turnos"])

# Los turnos definen el horario oficial que todos ven en el calendario:
# consultarlos es libre, cambiarlos es de admins.


def _obtener(db: DB, turno_id: int) -> Turno:
    turno = db.get(Turno, turno_id, options=[selectinload(Turno.dias)])
    if turno is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Turno no encontrado")
    return turno


def _aplicar(turno: Turno, datos: TurnoIn) -> None:
    turno.nombre = datos.nombre
    turno.hora_inicio = datos.hora_inicio
    turno.hora_fin = datos.hora_fin
    # Se actualiza en su sitio: crear objetos nuevos con la misma clave (turno, día)
    # que los existentes chocaría en la sesión. delete-orphan borra los días quitados.
    actuales = {d.dia: d for d in turno.dias}
    nuevos = {d.dia: d.modalidad for d in datos.dias}
    for dia, existente in actuales.items():
        if dia in nuevos:
            existente.modalidad = nuevos[dia]
        else:
            turno.dias.remove(existente)
    for dia, modalidad in nuevos.items():
        if dia not in actuales:
            turno.dias.append(TurnoDia(dia=dia, modalidad=modalidad))
    turno.dias.sort(key=lambda d: d.dia)


@router.get("", response_model=list[TurnoOut])
def listar(db: DB, _: UsuarioActual, incluir_inactivos: bool = False):
    consulta = select(Turno).options(selectinload(Turno.dias)).order_by(Turno.hora_inicio)
    if not incluir_inactivos:
        consulta = consulta.where(Turno.activo)
    return db.scalars(consulta).all()


@router.get("/{turno_id}", response_model=TurnoOut)
def detalle(turno_id: int, db: DB, _: UsuarioActual):
    return _obtener(db, turno_id)


@router.post("", response_model=TurnoOut, status_code=status.HTTP_201_CREATED)
def crear(datos: TurnoIn, db: DB, _: Admin):
    turno = Turno()
    _aplicar(turno, datos)
    db.add(turno)
    db.commit()
    return _obtener(db, turno.id)


@router.put("/{turno_id}", response_model=TurnoOut)
def actualizar(turno_id: int, datos: TurnoIn, db: DB, _: Admin):
    turno = _obtener(db, turno_id)
    _aplicar(turno, datos)
    turno.activo = True
    db.commit()
    return _obtener(db, turno_id)


@router.delete("/{turno_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar(turno_id: int, db: DB, _: Admin):
    # Se desactiva en lugar de borrar para no perder las clases asociadas.
    _obtener(db, turno_id).activo = False
    db.commit()
