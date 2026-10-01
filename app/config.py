import re
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _origen_valido(origen: str) -> str:
    # El navegador manda el Origin como esquema://host[:puerto] y CORS lo compara
    # literalmente: una barra final o una ruta harían que nunca coincidiera. "*" se
    # rechaza porque permitiría a cualquier web llamar a la API.
    if not re.fullmatch(r"https?://[^/*\s]+", origen):
        raise ValueError(
            f"Origen CORS inválido: {origen!r}. Formato: http(s)://host[:puerto], "
            "sin barra final ni comodines"
        )
    return origen


OrigenCors = Annotated[str, AfterValidator(_origen_valido)]


class Settings(BaseSettings):
    """Configuración leída de variables de entorno o del archivo .env.

    Los valores sin default son obligatorios: la app no arranca si faltan.
    Ver .env.example.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: PostgresDsn
    # Solo la usa pytest; nunca debe apuntar a la base de desarrollo o producción.
    test_database_url: PostgresDsn | None = None

    jwt_secret: SecretStr = Field(min_length=32)
    # Solo HMAC: el mismo secreto firma y verifica. Nunca "none".
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    # Vida de cada token. El frontend lo renueva mientras se usa la app, así que en la
    # práctica es el tiempo de inactividad tras el que hay que volver a iniciar sesión.
    jwt_expire_minutes: int = Field(default=60 * 24, gt=0)
    # Duración máxima de una sesión desde el login, por mucho que se renueve el token.
    sesion_max_dias: int = Field(default=7, gt=0)

    # Código que hay que presentar para registrarse (se comparte con los compañeros).
    codigo_invitacion: SecretStr = Field(min_length=8)

    # Fallos permitidos (login o código de invitación) dentro de la ventana; después, 429.
    limite_fallos_usuario: int = Field(default=5, gt=0)
    limite_fallos_ip: int = Field(default=20, gt=0)
    limite_ventana_minutos: int = Field(default=15, gt=0)

    # /docs, /redoc y /openapi.json. Sin valor por defecto: hay que decidirlo en cada
    # entorno (true en desarrollo, false en producción).
    docs_habilitadas: bool

    # Orígenes exactos del frontend que pueden llamar a la API desde el navegador.
    cors_origins: list[OrigenCors] = Field(min_length=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  (los valores vienen del entorno)


settings = get_settings()
