import enum
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    JSON,
    Enum,
    ForeignKey,
    Index,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    false,
    func,
    true,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Cinturon(str, enum.Enum):
    BLANCO = "BLANCO"
    AZUL = "AZUL"
    MORADO = "MORADO"
    MARRON = "MARRON"
    NEGRO = "NEGRO"


class Modalidad(str, enum.Enum):
    GI = "GI"
    NO_GI = "NO_GI"


class Categoria(str, enum.Enum):
    GUARDIA = "GUARDIA"
    PASAJE = "PASAJE"
    BARRIDA = "BARRIDA"
    FINALIZACION = "FINALIZACION"
    ESCAPE = "ESCAPE"
    DERRIBO = "DERRIBO"
    TRANSICION = "TRANSICION"
    CONTROL = "CONTROL"
    OTRA = "OTRA"


class Accion(str, enum.Enum):
    CREAR = "CREAR"
    ACTUALIZAR = "ACTUALIZAR"
    ELIMINAR = "ELIMINAR"


class Posicion(str, enum.Enum):
    GUARDIA_CERRADA = "GUARDIA_CERRADA"
    GUARDIA_ABIERTA = "GUARDIA_ABIERTA"
    MEDIA_GUARDIA = "MEDIA_GUARDIA"
    CONTROL_LATERAL = "CONTROL_LATERAL"
    MONTADA = "MONTADA"
    ESPALDA = "ESPALDA"
    NORTE_SUR = "NORTE_SUR"
    TORTUGA = "TORTUGA"
    DE_PIE = "DE_PIE"
    OTRA = "OTRA"


def _enum(tipo: type[enum.Enum]) -> Enum:
    # VARCHAR + CHECK en lugar de ENUM nativo: portable entre SQLite y PostgreSQL
    # y más fácil de migrar si la taxonomía cambia.
    return Enum(tipo, native_enum=False, length=32, create_constraint=True)


class Timestamps:
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


clase_tecnicas = Table(
    "clase_tecnicas",
    Base.metadata,
    Column("clase_id", ForeignKey("clases.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "tecnica_id",
        ForeignKey("tecnicas.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    ),
)


# Grados (stripes) que admite cada cinturón: 4 en los de color y hasta 6 en el negro
# (después llega el coral). La base solo acota a 0-6; el límite por cinturón lo valida la API.
GRADO_MAXIMO = 6


def grado_maximo(cinturon: Cinturon | None) -> int:
    if cinturon is None:
        return 0
    return GRADO_MAXIMO if cinturon is Cinturon.NEGRO else 4


class Usuario(Timestamps, Base):
    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(f"grado BETWEEN 0 AND {GRADO_MAXIMO}", name="grado_valido"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    # Identificador para iniciar sesión; siempre en minúsculas.
    username: Mapped[str] = mapped_column(String(30), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # Cinturón, grado y fecha de ingreso solo los cambia un admin: se muestran a todos en
    # "Compañeros" y nadie debe poder subirse de cinturón a sí mismo.
    cinturon: Mapped[Cinturon | None] = mapped_column(_enum(Cinturon))
    grado: Mapped[int] = mapped_column(default=0, server_default="0")
    fecha_ingreso: Mapped[date | None] = mapped_column(Date)
    # Puede gestionar usuarios y borrar registros. El resto de acciones son de todos.
    es_admin: Mapped[bool] = mapped_column(default=False, server_default=false())
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())
    # Va dentro de cada token; incrementarla invalida todos los tokens ya emitidos.
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")


class Turno(Timestamps, Base):
    __tablename__ = "turnos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    activo: Mapped[bool] = mapped_column(default=True, server_default=true())

    # Días de la semana en que hay clase en este turno, con su modalidad.
    dias: Mapped[list["TurnoDia"]] = relationship(
        cascade="all, delete-orphan", order_by="TurnoDia.dia"
    )


class TurnoDia(Base):
    """Un día de la semana en que se entrena en un turno (0 = lunes ... 6 = domingo)."""

    __tablename__ = "turno_dias"
    __table_args__ = (CheckConstraint("dia BETWEEN 0 AND 6", name="dia_valido"),)

    turno_id: Mapped[int] = mapped_column(
        ForeignKey("turnos.id", ondelete="CASCADE"), primary_key=True
    )
    dia: Mapped[int] = mapped_column(primary_key=True)
    modalidad: Mapped[Modalidad] = mapped_column(_enum(Modalidad))


class Tecnica(Timestamps, Base):
    __tablename__ = "tecnicas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True)
    categoria: Mapped[Categoria] = mapped_column(_enum(Categoria))
    posicion: Mapped[Posicion] = mapped_column(_enum(Posicion))
    descripcion: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(500))

    clases: Mapped[list["Clase"]] = relationship(
        secondary=clase_tecnicas,
        back_populates="tecnicas",
        order_by="Clase.fecha.desc()",
    )


class Clase(Timestamps, Base):
    __tablename__ = "clases"

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    turno_id: Mapped[int] = mapped_column(ForeignKey("turnos.id"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    hora_inicio: Mapped[time] = mapped_column(Time)
    hora_fin: Mapped[time] = mapped_column(Time)
    modalidad: Mapped[Modalidad] = mapped_column(_enum(Modalidad))
    tema: Mapped[str] = mapped_column(String(200))
    # Quién dio la clase; texto libre porque no tiene por qué tener cuenta.
    instructor: Mapped[str | None] = mapped_column(String(100))
    notas: Mapped[str | None] = mapped_column(Text)
    video_url: Mapped[str | None] = mapped_column(String(500))

    creado_por: Mapped[Usuario] = relationship()
    turno: Mapped[Turno] = relationship()
    tecnicas: Mapped[list[Tecnica]] = relationship(
        secondary=clase_tecnicas, back_populates="clases", order_by="Tecnica.nombre"
    )


class Medalla(str, enum.Enum):
    ORO = "ORO"
    PLATA = "PLATA"
    BRONCE = "BRONCE"


class EstadoParticipacion(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class Torneo(Timestamps, Base):
    """Un campeonato. Lo da de alta cualquiera al registrar su participación; corregirlo
    o borrarlo es de admins."""

    __tablename__ = "torneos"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150))
    fecha: Mapped[date] = mapped_column(Date, index=True)
    lugar: Mapped[str | None] = mapped_column(String(150))
    creado_por_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)

    creado_por: Mapped[Usuario] = relationship()


class Participacion(Timestamps, Base):
    """Lo que hizo un alumno en un torneo y, si la ganó, su medalla.

    La registra el propio alumno y queda PENDIENTE: no se ve en Compañeros hasta que un
    admin la aprueba. Las que registra un admin nacen aprobadas.
    """

    __tablename__ = "participaciones"
    __table_args__ = (
        # Se puede competir en Gi y No-Gi, o en peso y absoluto, en el mismo torneo.
        UniqueConstraint("usuario_id", "torneo_id", "modalidad", "categoria"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuarios.id"), index=True)
    # Sin borrado en cascada: un torneo con participaciones no se puede borrar.
    torneo_id: Mapped[int] = mapped_column(ForeignKey("torneos.id"), index=True)
    modalidad: Mapped[Modalidad] = mapped_column(_enum(Modalidad))
    # Texto libre como lo nombra el torneo: "Adulto azul pluma", "Absoluto"...
    categoria: Mapped[str] = mapped_column(String(100))
    medalla: Mapped[Medalla | None] = mapped_column(_enum(Medalla))
    estado: Mapped[EstadoParticipacion] = mapped_column(
        _enum(EstadoParticipacion),
        default=EstadoParticipacion.PENDIENTE,
        server_default=EstadoParticipacion.PENDIENTE.value,
        index=True,
    )
    motivo_rechazo: Mapped[str | None] = mapped_column(String(200))
    # El admin que la aprobó o rechazó.
    revisado_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"))

    usuario: Mapped[Usuario] = relationship(foreign_keys=[usuario_id])
    torneo: Mapped[Torneo] = relationship()


class Auditoria(Base):
    """Un cambio en los datos: quién, cuándo, sobre qué y cómo estaba antes.

    Solo se añaden filas; ningún endpoint las modifica ni las borra.
    """

    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_entidad", "entidad", "entidad_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    # Quién hizo el cambio. Nulo: desde la línea de comandos (app.cli).
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuarios.id"), index=True)
    accion: Mapped[Accion] = mapped_column(_enum(Accion))
    # "clase", "tecnica", "turno", "usuario", "torneo" o "participacion". Sin FK: la
    # fila puede haberse borrado.
    entidad: Mapped[str] = mapped_column(String(32))
    entidad_id: Mapped[int]
    # CREAR y ELIMINAR: todos los campos. ACTUALIZAR: {campo: [antes, después]}.
    cambios: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))

    usuario: Mapped[Usuario | None] = relationship()
