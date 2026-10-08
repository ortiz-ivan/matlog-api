"""Alta de cuentas: compartida por el registro público y el alta desde un admin."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auditoria import registrar
from app.models import Accion, Usuario
from app.schemas import CAMPOS_ACADEMIA, UsuarioCrear
from app.security import hash_password


def crear_cuenta(
    db: Session, datos: UsuarioCrear, autor: Usuario | None = None, es_admin: bool = False
) -> Usuario:
    """Crea el usuario o responde 409 si el username o el email ya están en uso.

    autor: el admin que la da de alta; sin él es un registro público y en la auditoría
    figura como autora la propia cuenta.
    """
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
        es_admin=es_admin,
        # Solo el alta de un admin los trae (UsuarioNuevo); en el registro no existen.
        **datos.model_dump(include=CAMPOS_ACADEMIA),
    )
    db.add(usuario)
    registrar(db, autor or usuario, Accion.CREAR, usuario)
    db.commit()
    return usuario
