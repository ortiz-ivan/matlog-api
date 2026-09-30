from functools import lru_cache

from pydantic import Field, PostgresDsn, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = Field(default=60 * 24 * 7, gt=0)

    # Código que hay que presentar para registrarse (se comparte con los compañeros).
    codigo_invitacion: SecretStr = Field(min_length=8)

    cors_origins: list[str]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  (los valores vienen del entorno)


settings = get_settings()
