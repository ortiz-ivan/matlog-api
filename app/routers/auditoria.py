from typing import Annotated, Literal

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.deps import DB, Admin
from app.models import Accion, Auditoria
from app.schemas import AuditoriaOut, Pagina

router = APIRouter(prefix="/api/auditoria", tags=["auditoria"])


@router.get("", response_model=Pagina[AuditoriaOut])
def listar(
    db: DB,
    _: Admin,
    entidad: Literal["clase", "tecnica", "turno", "usuario"] | None = None,
    entidad_id: int | None = None,
    usuario_id: Annotated[int | None, Query(description="autor del cambio")] = None,
    accion: Accion | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """Historial de cambios, del más reciente al más antiguo. Solo lectura."""
    filtros = []
    if entidad:
        filtros.append(Auditoria.entidad == entidad)
    if entidad_id is not None:
        filtros.append(Auditoria.entidad_id == entidad_id)
    if usuario_id is not None:
        filtros.append(Auditoria.usuario_id == usuario_id)
    if accion:
        filtros.append(Auditoria.accion == accion)

    total = db.scalar(select(func.count(Auditoria.id)).where(*filtros))
    registros = db.scalars(
        select(Auditoria)
        .where(*filtros)
        .options(selectinload(Auditoria.usuario))
        .order_by(Auditoria.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return Pagina(items=registros, total=total)
