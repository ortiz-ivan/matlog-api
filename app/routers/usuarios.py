from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app.cuentas import crear_cuenta
from app.deps import DB, Admin
from app.models import Usuario
from app.schemas import Pagina, UsuarioActualizar, UsuarioNuevo, UsuarioOut
from app.security import hash_password

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


def _obtener(db: DB, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return usuario


@router.get("", response_model=Pagina[UsuarioOut])
def listar(
    db: DB,
    _: Admin,
    q: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filtros = []
    if q and q.strip():
        patron = f"%{q.strip()}%"
        filtros.append(or_(Usuario.nombre.ilike(patron), Usuario.username.ilike(patron)))

    total = db.scalar(select(func.count(Usuario.id)).where(*filtros))
    usuarios = db.scalars(
        select(Usuario)
        .where(*filtros)
        .order_by(func.lower(Usuario.nombre), Usuario.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Pagina(items=usuarios, total=total)


@router.get("/{usuario_id}", response_model=UsuarioOut)
def detalle(usuario_id: int, db: DB, _: Admin):
    return _obtener(db, usuario_id)


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioNuevo, db: DB, _: Admin):
    return crear_cuenta(db, datos, es_admin=datos.es_admin)


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def actualizar(usuario_id: int, datos: UsuarioActualizar, db: DB, admin: Admin):
    usuario = _obtener(db, usuario_id)

    # null solo tiene sentido en el cinturón (quitarlo); en el resto se ignora.
    cambios = {
        campo: valor
        for campo, valor in datos.model_dump(exclude_unset=True).items()
        if valor is not None or campo == "cinturon"
    }
    if usuario.id == admin.id and (
        cambios.get("es_admin") is False or cambios.get("activo") is False
    ):
        # Evita que la plataforma se quede sin nadie capaz de administrarla.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No puedes quitarte el admin ni desactivarte a ti mismo"
        )

    if password := cambios.pop("password", None):
        usuario.password_hash = hash_password(password)
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    db.commit()
    return usuario
