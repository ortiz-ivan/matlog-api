from fastapi import APIRouter, HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.orm import joinedload

from app.deps import DB, UsuarioActual
from app.models import Cinturon, EstadoParticipacion, Participacion, Torneo, Usuario
from app.schemas import Companero, CompaneroLista, FichaCompanero, Medallero

router = APIRouter(prefix="/api/companeros", tags=["companeros"])

# Del cinturón más alto al más bajo; sin cinturón, al final.
_RANGO = case(
    {c: i for i, c in enumerate(reversed(Cinturon))},
    value=Usuario.cinturon,
    else_=len(Cinturon),
)

_APROBADA = Participacion.estado == EstadoParticipacion.APROBADA


def _medalleros(db: DB, *filtros) -> dict[int, Medallero]:
    """Medallas y torneos de cada usuario, contando solo participaciones aprobadas."""
    medalleros: dict[int, Medallero] = {}
    filas = db.execute(
        select(
            Participacion.usuario_id,
            Participacion.medalla,
            func.count(),
        )
        .where(_APROBADA, Participacion.medalla.is_not(None), *filtros)
        .group_by(Participacion.usuario_id, Participacion.medalla)
    )
    for usuario_id, medalla, total in filas:
        setattr(medalleros.setdefault(usuario_id, Medallero()), medalla.value.lower(), total)
    filas = db.execute(
        select(Participacion.usuario_id, func.count(func.distinct(Participacion.torneo_id)))
        .where(_APROBADA, *filtros)
        .group_by(Participacion.usuario_id)
    )
    for usuario_id, torneos in filas:
        medalleros.setdefault(usuario_id, Medallero()).torneos = torneos
    return medalleros


@router.get("", response_model=list[CompaneroLista])
def listar(db: DB, _: UsuarioActual):
    """Las cuentas activas de la academia, con solo sus datos públicos y su medallero.

    Sin paginar: una academia tiene decenas de alumnos, no miles, y la vitrina los
    agrupa por cinturón.
    """
    usuarios = db.scalars(
        select(Usuario)
        .where(Usuario.activo)
        .order_by(
            _RANGO,
            Usuario.grado.desc(),
            Usuario.fecha_ingreso.asc().nulls_last(),
            func.lower(Usuario.nombre),
            Usuario.id,
        )
    ).all()
    medalleros = _medalleros(db)
    return [
        CompaneroLista(
            **Companero.model_validate(u).model_dump(),
            medallero=medalleros.get(u.id, Medallero()),
        )
        for u in usuarios
    ]


@router.get("/{usuario_id}", response_model=FichaCompanero)
def ficha(usuario_id: int, db: DB, _: UsuarioActual):
    usuario = db.get(Usuario, usuario_id)
    # Las cuentas desactivadas no aparecen en la vitrina.
    if usuario is None or not usuario.activo:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Compañero no encontrado")
    participaciones = db.scalars(
        select(Participacion)
        .join(Participacion.torneo)
        .options(joinedload(Participacion.torneo))
        .where(Participacion.usuario_id == usuario_id, _APROBADA)
        .order_by(Torneo.fecha.desc(), Participacion.id.desc())
    ).all()
    return FichaCompanero(
        **Companero.model_validate(usuario).model_dump(),
        medallero=_medalleros(db, Participacion.usuario_id == usuario_id).get(
            usuario_id, Medallero()
        ),
        participaciones=participaciones,
    )
