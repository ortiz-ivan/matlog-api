from datetime import date, time
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BeforeValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    model_validator,
)

from app.models import Categoria, Cinturon, Modalidad, Posicion

# Se valida como URL pero se guarda como texto plano.
Url = Annotated[HttpUrl, AfterValidator(str)]
Password = Annotated[str, Field(min_length=8, max_length=128)]
# Se normaliza a minúsculas antes de validar: "Ivan.Ortiz" y "ivan.ortiz" son el mismo.
Username = Annotated[
    str,
    BeforeValidator(lambda v: v.strip().lower() if isinstance(v, str) else v),
    Field(
        min_length=3,
        max_length=30,
        pattern=r"^[a-z0-9._-]+$",
        description="3-30 caracteres: letras, números, punto, guion o guion bajo",
    ),
]


class Esquema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Pagina[T](BaseModel):
    items: list[T]
    total: int


# --- Auth ---


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# --- Usuarios ---


class UsuarioResumen(Esquema):
    id: int
    nombre: str


class UsuarioOut(UsuarioResumen):
    username: str
    email: str
    cinturon: Cinturon | None
    es_admin: bool
    activo: bool


class Registro(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    username: Username
    email: EmailStr
    password: Password
    cinturon: Cinturon | None = None
    codigo_invitacion: str


class UsuarioActualizar(BaseModel):
    """Cambios que puede hacer un admin sobre cualquier usuario."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    password: Password | None = None
    cinturon: Cinturon | None = None
    es_admin: bool | None = None
    activo: bool | None = None


# --- Turnos ---


class _ConHorario(BaseModel):
    @model_validator(mode="after")
    def _horario_valido(self) -> Self:
        inicio, fin = getattr(self, "hora_inicio", None), getattr(self, "hora_fin", None)
        if inicio and fin and fin <= inicio:
            raise ValueError("hora_fin debe ser posterior a hora_inicio")
        return self


class TurnoIn(_ConHorario):
    nombre: str = Field(min_length=1, max_length=100)
    hora_inicio: time
    hora_fin: time


class TurnoResumen(Esquema):
    id: int
    nombre: str


class TurnoOut(TurnoResumen):
    hora_inicio: time
    hora_fin: time
    activo: bool


# --- Técnicas ---


class TecnicaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    categoria: Categoria
    posicion: Posicion
    descripcion: str | None = None
    video_url: Url | None = None


class TecnicaResumen(Esquema):
    id: int
    nombre: str
    categoria: Categoria
    posicion: Posicion


class TecnicaOut(TecnicaResumen):
    descripcion: str | None
    video_url: str | None


# --- Clases ---


class ClaseIn(_ConHorario):
    fecha: date
    turno_id: int
    # Si no se indican, se toman del turno.
    hora_inicio: time | None = None
    hora_fin: time | None = None
    modalidad: Modalidad = Modalidad.GI
    tema: str = Field(min_length=1, max_length=200)
    instructor: str | None = Field(default=None, max_length=100)
    notas: str | None = None
    video_url: Url | None = None
    tecnica_ids: list[int] = []


class ClaseResumen(Esquema):
    id: int
    fecha: date
    hora_inicio: time
    hora_fin: time
    modalidad: Modalidad
    tema: str
    instructor: str | None
    turno: TurnoResumen


class ClaseOut(ClaseResumen):
    creado_por: UsuarioResumen
    notas: str | None
    video_url: str | None
    tecnicas: list[TecnicaResumen]


class TecnicaDetalle(TecnicaOut):
    clases: list[ClaseResumen]
