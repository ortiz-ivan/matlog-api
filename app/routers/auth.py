import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select

from app.config import settings
from app.deps import DB, UsuarioActual
from app.models import Usuario
from app.schemas import Registro, Token, UsuarioOut
from app.security import crear_token, hash_password, verificar_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/registro", response_model=Token, status_code=status.HTTP_201_CREATED)
def registro(datos: Registro, db: DB):
    codigo_valido = secrets.compare_digest(
        datos.codigo_invitacion.encode(), settings.codigo_invitacion.get_secret_value().encode()
    )
    if not codigo_valido:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Código de invitación incorrecto")

    email = datos.email.lower()
    if db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Ya existe un usuario con ese email")

    usuario = Usuario(
        nombre=datos.nombre,
        email=email,
        password_hash=hash_password(datos.password),
        cinturon=datos.cinturon,
    )
    db.add(usuario)
    db.commit()
    return Token(access_token=crear_token(usuario.id))


@router.post("/login", response_model=Token)
def login(db: DB, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    # OAuth2 llama "username" al campo; aquí es el email.
    usuario = db.scalar(
        select(Usuario).where(func.lower(Usuario.email) == form.username.lower())
    )
    if (
        usuario is None
        or not usuario.activo
        or not verificar_password(form.password, usuario.password_hash)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email o contraseña incorrectos")
    return Token(access_token=crear_token(usuario.id))


@router.get("/me", response_model=UsuarioOut)
def me(usuario: UsuarioActual):
    return usuario
