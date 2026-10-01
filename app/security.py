import secrets
from datetime import UTC, datetime, timedelta
from typing import NamedTuple

import jwt
from pwdlib import PasswordHash

from app.config import settings
from app.models import Usuario

_hasher = PasswordHash.recommended()
# Hash de una contraseña aleatoria que nadie conoce; ver verificar_password.
_HASH_FICTICIO = _hasher.hash(secrets.token_urlsafe(32))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verificar_password(password: str, password_hash: str | None) -> bool:
    """Sin hash (el usuario no existe) se verifica igual contra uno ficticio y da False.

    Así la respuesta tarda lo mismo exista o no la cuenta, y el tiempo no revela
    qué usernames están registrados.
    """
    if password_hash is None:
        _hasher.verify(password, _HASH_FICTICIO)
        return False
    return _hasher.verify(password, password_hash)


class DatosToken(NamedTuple):
    usuario_id: int
    version: int
    # Cuándo se inició sesión con la contraseña; se conserva al renovar el token.
    inicio_sesion: datetime


def crear_token(usuario: Usuario, inicio_sesion: datetime | None = None) -> str:
    """Token de JWT_EXPIRE_MINUTES, sin pasar nunca de SESION_MAX_DIAS desde el login.

    Sin inicio_sesion es un login nuevo; al renovar se pasa el del token anterior.
    """
    ahora = datetime.now(UTC)
    inicio = inicio_sesion or ahora
    expira = min(
        ahora + timedelta(minutes=settings.jwt_expire_minutes),
        inicio + timedelta(days=settings.sesion_max_dias),
    )
    return jwt.encode(
        {
            "sub": str(usuario.id),
            "ver": usuario.token_version,
            "auth_time": int(inicio.timestamp()),
            "iat": ahora,
            "exp": expira,
        },
        settings.jwt_secret.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


def leer_token(token: str) -> DatosToken | None:
    """Devuelve los datos del token, o None si no es válido o ha caducado."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            # PyJWT valida exp e iat si vienen, pero no exige que estén: un token sin exp
            # no caducaría nunca.
            options={"require": ["sub", "ver", "auth_time", "iat", "exp"]},
        )
        return DatosToken(
            int(payload["sub"]),
            int(payload["ver"]),
            datetime.fromtimestamp(int(payload["auth_time"]), UTC),
        )
    except (jwt.PyJWTError, KeyError, TypeError, ValueError, OverflowError, OSError):
        return None


def invalidar_tokens(usuario: Usuario) -> None:
    """Cierra todas las sesiones abiertas del usuario (surte efecto al hacer commit)."""
    usuario.token_version += 1
