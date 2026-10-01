"""Alta de cuentas: compartida por el registro público y el alta desde un admin."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Usuario
from app.schemas import UsuarioCrear
from app.security import hash_password


def crear_cuenta(db: Session, datos: UsuarioCrear, es_admin: bool = False) -> Usuario:
    """Crea el usuario o responde 409 si el username o el email ya están en uso."""
    email = datos.email.lower()
    if db.scalar(select(Usuario.id).where(Usuario.username == datos.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ese nombre de usuario ya está en uso")
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe una cuenta con ese email")

    usuario = Usuario(
        nombre=datos.nombre,
        username=datos.username,
        email=email,
        password_hash=hash_password(datos.password),
        cinturon=datos.cinturon,
        es_admin=es_admin,
    )
    db.add(usuario)
    db.commit()
    return usuario
