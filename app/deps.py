from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Usuario
from app.security import leer_token

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

DB = Annotated[Session, Depends(get_db)]


def usuario_actual(db: DB, token: Annotated[str, Depends(oauth2)]) -> Usuario:
    datos = leer_token(token)
    usuario = db.get(Usuario, datos.usuario_id) if datos else None
    # Una versión distinta significa que el token fue invalidado (cambio de contraseña, etc.).
    if usuario is None or not usuario.activo or usuario.token_version != datos.version:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Credenciales inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return usuario


def solo_admin(usuario: Annotated[Usuario, Depends(usuario_actual)]) -> Usuario:
    if not usuario.es_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo para administradores")
    return usuario


UsuarioActual = Annotated[Usuario, Depends(usuario_actual)]
Admin = Annotated[Usuario, Depends(solo_admin)]
