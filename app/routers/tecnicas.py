from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, Admin, UsuarioActual
from app.models import Categoria, Clase, Posicion, Tecnica
from app.schemas import TecnicaDetalle, TecnicaIn, TecnicaOut

router = APIRouter(prefix="/api/tecnicas", tags=["tecnicas"])


def _obtener(db: DB, tecnica_id: int) -> Tecnica:
    tecnica = db.get(
        Tecnica,
        tecnica_id,
        options=[selectinload(Tecnica.clases).selectinload(Clase.turno)],
    )
    if tecnica is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Técnica no encontrada")
    return tecnica


def _validar_nombre_unico(db: DB, nombre: str, excluir_id: int | None = None) -> None:
    consulta = select(Tecnica.id).where(func.lower(Tecnica.nombre) == nombre.lower())
    if excluir_id is not None:
        consulta = consulta.where(Tecnica.id != excluir_id)
    if db.scalar(consulta):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una técnica con ese nombre")


@router.get("", response_model=list[TecnicaOut])
def listar(
    db: DB,
    _: UsuarioActual,
    q: str | None = None,
    categoria: Categoria | None = None,
    posicion: Posicion | None = None,
):
    consulta = select(Tecnica).order_by(Tecnica.nombre)
    if q:
        consulta = consulta.where(Tecnica.nombre.ilike(f"%{q.strip()}%"))
    if categoria:
        consulta = consulta.where(Tecnica.categoria == categoria)
    if posicion:
        consulta = consulta.where(Tecnica.posicion == posicion)
    return db.scalars(consulta).all()


@router.get("/{tecnica_id}", response_model=TecnicaDetalle)
def detalle(tecnica_id: int, db: DB, _: UsuarioActual):
    return _obtener(db, tecnica_id)


@router.post("", response_model=TecnicaOut, status_code=status.HTTP_201_CREATED)
def crear(datos: TecnicaIn, db: DB, _: UsuarioActual):
    _validar_nombre_unico(db, datos.nombre)
    tecnica = Tecnica(**datos.model_dump())
    db.add(tecnica)
    db.commit()
    return tecnica


@router.put("/{tecnica_id}", response_model=TecnicaOut)
def actualizar(tecnica_id: int, datos: TecnicaIn, db: DB, _: UsuarioActual):
    tecnica = _obtener(db, tecnica_id)
    _validar_nombre_unico(db, datos.nombre, excluir_id=tecnica_id)
    for campo, valor in datos.model_dump().items():
        setattr(tecnica, campo, valor)
    db.commit()
    return tecnica


@router.delete("/{tecnica_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(tecnica_id: int, db: DB, _: Admin):
    db.delete(_obtener(db, tecnica_id))
    db.commit()
