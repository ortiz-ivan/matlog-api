import enum
from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Table,
    Text,
    Time,
    false,
    func,
    true,
)
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


class Usuario(Timestamps, Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(100))
    # Identificador para iniciar sesión; siempre en minúsculas.
    username: Mapped[str] = mapped_column(String(30), unique=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    cinturon: Mapped[Cinturon | None] = mapped_column(_enum(Cinturon))
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
