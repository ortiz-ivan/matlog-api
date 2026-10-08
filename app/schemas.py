from datetime import date, datetime, time
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

from app.models import (
    GRADO_MAXIMO,
    Accion,
    Categoria,
    Cinturon,
    Modalidad,
    Posicion,
    grado_maximo,
)

# Límites de lo que se acepta: acotan lo que cabe en la base de datos y lo que cuesta
# procesar cada petición. TEXTO_LARGO es para notas y descripciones (columnas Text).
URL_MAX = 500  # como las columnas video_url
TEXTO_LARGO = 5000
BUSQUEDA_MAX = 100
PASSWORD_MAX = 128


def _url_texto(url: HttpUrl) -> str:
    # Se mide ya normalizada: un dominio con tildes pasa a punycode y crece.
    texto = str(url)
    if len(texto) > URL_MAX:
        raise ValueError(f"La URL no puede superar {URL_MAX} caracteres")
    return texto


# Se valida como URL pero se guarda como texto plano.
Url = Annotated[HttpUrl, AfterValidator(_url_texto)]
Password = Annotated[str, Field(min_length=8, max_length=PASSWORD_MAX)]
TextoLargo = Annotated[str, Field(max_length=TEXTO_LARGO)]
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


class Companero(UsuarioResumen):
    """Lo que ve cualquier usuario de los demás. Sin username ni email: el username es
    la mitad de las credenciales y el email es un dato personal."""

    cinturon: Cinturon | None
    grado: int
    fecha_ingreso: date | None


class UsuarioOut(Companero):
    username: str
    email: str
    es_admin: bool
    activo: bool


# Datos de la academia: solo los asigna un admin (ver models.Usuario).
CAMPOS_ACADEMIA = {"cinturon", "grado", "fecha_ingreso"}
FECHA_INGRESO_MIN = date(1950, 1, 1)


def _fecha_ingreso_valida(fecha: date | None) -> date | None:
    if fecha is not None and not FECHA_INGRESO_MIN <= fecha <= date.today():
        raise ValueError("La fecha de ingreso no puede ser futura ni anterior a 1950")
    return fecha


FechaIngreso = Annotated[date | None, AfterValidator(_fecha_ingreso_valida)]
Grado = Annotated[int, Field(ge=0, le=GRADO_MAXIMO)]


def comprobar_grado(cinturon: Cinturon | None, grado: int) -> None:
    """ValueError si el cinturón no admite tantos grados."""
    maximo = grado_maximo(cinturon)
    if grado <= maximo:
        return
    if cinturon is None:
        raise ValueError("Sin cinturón no puede haber grados")
    raise ValueError(f"Ese cinturón admite como mucho {maximo} grados")


class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    username: Username
    email: EmailStr
    password: Password


class Registro(UsuarioCrear):
    """Alta pública: exige el código de invitación, nunca da admin y no asigna cinturón."""

    codigo_invitacion: str = Field(max_length=128)


class UsuarioNuevo(UsuarioCrear):
    """Alta hecha por un admin."""

    cinturon: Cinturon | None = None
    grado: Grado = 0
    fecha_ingreso: FechaIngreso = None
    es_admin: bool = False

    @model_validator(mode="after")
    def _grado_del_cinturon(self) -> Self:
        comprobar_grado(self.cinturon, self.grado)
        return self


class PerfilActualizar(BaseModel):
    """Lo que cada usuario puede cambiar de sí mismo. El cinturón no: lo asigna un admin."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)


class CambioPassword(BaseModel):
    actual: str = Field(max_length=PASSWORD_MAX)
    nueva: Password


class UsuarioActualizar(BaseModel):
    """Cambios que puede hacer un admin sobre cualquier usuario."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    password: Password | None = None
    cinturon: Cinturon | None = None
    grado: Grado | None = None
    fecha_ingreso: FechaIngreso = None
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


class TurnoDiaSchema(Esquema):
    dia: int = Field(ge=0, le=6, description="0 = lunes ... 6 = domingo")
    modalidad: Modalidad = Modalidad.GI


class TurnoIn(_ConHorario):
    nombre: str = Field(min_length=1, max_length=100)
    hora_inicio: time
    hora_fin: time
    dias: list[TurnoDiaSchema] = Field(default=[], max_length=7)

    @model_validator(mode="after")
    def _dias_sin_repetir(self) -> Self:
        if len({d.dia for d in self.dias}) != len(self.dias):
            raise ValueError("Hay días repetidos")
        return self


class TurnoResumen(Esquema):
    id: int
    nombre: str


class TurnoOut(TurnoResumen):
    hora_inicio: time
    hora_fin: time
    activo: bool
    dias: list[TurnoDiaSchema]


# --- Técnicas ---


class TecnicaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=150)
    categoria: Categoria
    posicion: Posicion
    descripcion: TextoLargo | None = None
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
    notas: TextoLargo | None = None
    video_url: Url | None = None
    tecnica_ids: list[int] = Field(default=[], max_length=50)


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



# --- Auditoría ---


class AuditoriaOut(Esquema):
    id: int
    creado_en: datetime
    # None: cambio hecho desde la línea de comandos.
    usuario: UsuarioResumen | None
    accion: Accion
    entidad: str
    entidad_id: int
    cambios: dict
