from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.auditoria import foto, registrar
from app.deps import DB, Admin, UsuarioActual
from app.models import Accion, Participacion, Torneo
from app.schemas import BUSQUEDA_MAX, TorneoIn, TorneoOut

router = APIRouter(prefix="/api/torneos", tags=["torneos"])


def _obtener(db: DB, torneo_id: int) -> Torneo:
    torneo = db.get(Torneo, torneo_id)
    if torneo is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Torneo no encontrado")
    return torneo


def _validar_unico(db: DB, datos: TorneoIn, excluir_id: int | None = None) -> None:
    # Mismo nombre el mismo día: casi seguro que alguien ya lo dio de alta.
    consulta = select(Torneo.id).where(
        func.lower(Torneo.nombre) == datos.nombre.lower(), Torneo.fecha == datos.fecha
    )
    if excluir_id is not None:
        consulta = consulta.where(Torneo.id != excluir_id)
    if db.scalar(consulta):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese torneo ya está registrado en esa fecha")


@router.get("", response_model=list[TorneoOut])
def listar(
    db: DB,
    _: UsuarioActual,
    q: Annotated[str | None, Query(max_length=BUSQUEDA_MAX)] = None,
):
    consulta = select(Torneo).order_by(Torneo.fecha.desc(), Torneo.nombre)
    if q and q.strip():
        consulta = consulta.where(Torneo.nombre.icontains(q.strip(), autoescape=True))
    return db.scalars(consulta).all()


@router.get("/{torneo_id}", response_model=TorneoOut)
def detalle(torneo_id: int, db: DB, _: UsuarioActual):
    return _obtener(db, torneo_id)


@router.post("", response_model=TorneoOut, status_code=status.HTTP_201_CREATED)
def crear(datos: TorneoIn, db: DB, usuario: UsuarioActual):
    _validar_unico(db, datos)
    torneo = Torneo(**datos.model_dump(), creado_por=usuario)
    db.add(torneo)
    registrar(db, usuario, Accion.CREAR, torneo)
    db.commit()
    return torneo


@router.put("/{torneo_id}", response_model=TorneoOut)
def actualizar(torneo_id: int, datos: TorneoIn, db: DB, admin: Admin):
    torneo = _obtener(db, torneo_id)
    _validar_unico(db, datos, excluir_id=torneo_id)
    antes = foto(torneo)
    for campo, valor in datos.model_dump().items():
        setattr(torneo, campo, valor)
    registrar(db, admin, Accion.ACTUALIZAR, torneo, antes)
    db.commit()
    return torneo


@router.delete("/{torneo_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(torneo_id: int, db: DB, admin: Admin):
    torneo = _obtener(db, torneo_id)
    # Borrarlo se llevaría medallas por delante: primero hay que quitar sus participaciones.
    if db.scalar(select(Participacion.id).where(Participacion.torneo_id == torneo_id).limit(1)):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "El torneo tiene participaciones: bórralas antes"
        )
    registrar(db, admin, Accion.ELIMINAR, torneo)
    db.delete(torneo)
    db.commit()
