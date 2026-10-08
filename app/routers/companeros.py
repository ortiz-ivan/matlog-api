from fastapi import APIRouter
from sqlalchemy import case, func, select

from app.deps import DB, UsuarioActual
from app.models import Cinturon, Usuario
from app.schemas import Companero

router = APIRouter(prefix="/api/companeros", tags=["companeros"])

# Del cinturón más alto al más bajo; sin cinturón, al final.
_RANGO = case(
    {c: i for i, c in enumerate(reversed(Cinturon))},
    value=Usuario.cinturon,
    else_=len(Cinturon),
)


@router.get("", response_model=list[Companero])
def listar(db: DB, _: UsuarioActual):
    """Las cuentas activas de la academia, con solo sus datos públicos.

    Sin paginar: una academia tiene decenas de alumnos, no miles, y la vitrina los
    agrupa por cinturón.
    """
    return db.scalars(
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
