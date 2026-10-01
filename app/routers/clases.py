from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, Admin, UsuarioActual
from app.models import Clase, Modalidad, Tecnica, Turno, clase_tecnicas
from app.schemas import BUSQUEDA_MAX, ClaseIn, ClaseOut, Pagina

router = APIRouter(prefix="/api/clases", tags=["clases"])

_CARGAR_RELACIONES = [
    selectinload(Clase.turno),
    selectinload(Clase.creado_por),
    selectinload(Clase.tecnicas),
]


def _obtener(db: DB, clase_id: int) -> Clase:
    clase = db.get(Clase, clase_id, options=_CARGAR_RELACIONES)
    if clase is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clase no encontrada")
    return clase


def _aplicar(db: DB, clase: Clase, datos: ClaseIn) -> None:
    turno = db.get(Turno, datos.turno_id)
    if turno is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El turno no existe")

    ids = set(datos.tecnica_ids)
    tecnicas = db.scalars(select(Tecnica).where(Tecnica.id.in_(ids))).all() if ids else []
    if len(tecnicas) != len(ids):
        faltan = sorted(ids - {t.id for t in tecnicas})
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"Técnicas inexistentes: {faltan}"
        )

    hora_inicio = datos.hora_inicio or turno.hora_inicio
    hora_fin = datos.hora_fin or turno.hora_fin
    if hora_fin <= hora_inicio:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "hora_fin debe ser posterior a hora_inicio",
        )

    clase.turno = turno
    clase.fecha = datos.fecha
    clase.hora_inicio = hora_inicio
    clase.hora_fin = hora_fin
    clase.modalidad = datos.modalidad
    clase.tema = datos.tema
    clase.instructor = datos.instructor
    clase.notas = datos.notas
    clase.video_url = datos.video_url
    clase.tecnicas = list(tecnicas)


@router.get("", response_model=Pagina[ClaseOut])
def listar(
    db: DB,
    _: UsuarioActual,
    desde: date | None = None,
    hasta: date | None = None,
    turno_id: int | None = None,
    modalidad: Modalidad | None = None,
    instructor: Annotated[str | None, Query(max_length=BUSQUEDA_MAX)] = None,
    tecnica_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filtros = []
    if desde:
        filtros.append(Clase.fecha >= desde)
    if hasta:
        filtros.append(Clase.fecha <= hasta)
    if turno_id:
        filtros.append(Clase.turno_id == turno_id)
    if modalidad:
        filtros.append(Clase.modalidad == modalidad)
    if instructor:
        filtros.append(Clase.instructor.icontains(instructor.strip(), autoescape=True))
    if tecnica_id:
        filtros.append(
            Clase.id.in_(
                select(clase_tecnicas.c.clase_id).where(
                    clase_tecnicas.c.tecnica_id == tecnica_id
                )
            )
        )

    total = db.scalar(select(func.count(Clase.id)).where(*filtros))
    clases = db.scalars(
        select(Clase)
        .where(*filtros)
        .options(*_CARGAR_RELACIONES)
        .order_by(Clase.fecha.desc(), Clase.hora_inicio.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Pagina(items=clases, total=total)


@router.get("/{clase_id}", response_model=ClaseOut)
def detalle(clase_id: int, db: DB, _: UsuarioActual):
    return _obtener(db, clase_id)


@router.post("", response_model=ClaseOut, status_code=status.HTTP_201_CREATED)
def crear(datos: ClaseIn, db: DB, admin: Admin):
    # Registrar clases es solo de admins; editarlas puede hacerlo cualquiera (p. ej. para
    # añadir una técnica que faltó) y borrarlas vuelve a ser solo de admins.
    clase = Clase(creado_por=admin)
    _aplicar(db, clase, datos)
    db.add(clase)
    db.commit()
    return _obtener(db, clase.id)


@router.put("/{clase_id}", response_model=ClaseOut)
def actualizar(clase_id: int, datos: ClaseIn, db: DB, _: UsuarioActual):
    clase = _obtener(db, clase_id)
    _aplicar(db, clase, datos)
    db.commit()
    return _obtener(db, clase_id)


@router.delete("/{clase_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(clase_id: int, db: DB, _: Admin):
    db.delete(_obtener(db, clase_id))
    db.commit()
