"""Registro de cambios en la tabla auditoria.

Uso en un endpoint, siempre antes del commit para que el cambio y su registro se
guarden juntos (o ninguno):

    antes = foto(clase)              # solo al actualizar
    ...modificar clase...
    registrar(db, usuario, Accion.ACTUALIZAR, clase, antes)
    db.commit()

Al eliminar se llama antes de db.delete(): se guarda la fila entera, para poder
recuperarla.
"""

import enum
from datetime import date, time

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app import logs
from app.models import Accion, Auditoria, Clase, Participacion, Tecnica, Torneo, Turno, Usuario

Auditable = Clase | Tecnica | Turno | Usuario | Torneo | Participacion

_ENTIDADES: dict[type, str] = {
    Clase: "clase",
    Tecnica: "tecnica",
    Turno: "turno",
    Usuario: "usuario",
    Torneo: "torneo",
    Participacion: "participacion",
}
# El hash de la contraseña nunca se copia: un cambio de contraseña se anota sin valores.
# Las marcas de tiempo ya están en la propia fila de auditoría.
_OCULTOS = {"password_hash", "token_version", "creado_en", "actualizado_en"}


def _json(valor: object) -> object:
    if isinstance(valor, enum.Enum):
        return valor.value
    if isinstance(valor, (date, time)):
        return valor.isoformat()
    return valor


def foto(obj: Auditable) -> dict[str, object]:
    """Los campos de la fila (y sus relaciones propias) como dict apto para JSON."""
    datos = {
        attr.key: _json(getattr(obj, attr.key))
        for attr in inspect(obj).mapper.column_attrs
        if attr.key not in _OCULTOS
    }
    if isinstance(obj, Clase):
        datos["tecnica_ids"] = sorted(t.id for t in obj.tecnicas)
    elif isinstance(obj, Turno):
        datos["dias"] = {str(d.dia): d.modalidad.value for d in obj.dias}
    return datos


def registrar(
    db: Session,
    autor: Usuario | None,
    accion: Accion,
    obj: Auditable,
    antes: dict[str, object] | None = None,
    extra: dict[str, object] | None = None,
) -> None:
    """Añade a la sesión la fila de auditoría del cambio. autor None: desde app.cli.

    En ACTUALIZAR solo se guardan los campos que cambian ({campo: [antes, después]});
    si no cambia ninguno no se registra nada. `extra` añade datos que no están en la
    fila, p. ej. {"password": "cambiada"}.
    """
    # Al flush las relaciones asignadas pasan a sus columnas (clase.turno -> turno_id)
    # y un objeto nuevo recibe su id.
    db.flush()
    if accion is Accion.ACTUALIZAR:
        if antes is None:
            raise ValueError("ACTUALIZAR necesita la foto de antes del cambio")
        cambios = {k: [antes.get(k), v] for k, v in foto(obj).items() if antes.get(k) != v}
    else:
        cambios = foto(obj)
    cambios |= extra or {}
    if not cambios:
        return

    entidad = _ENTIDADES[type(obj)]
    db.add(
        Auditoria(
            usuario_id=autor.id if autor else None,
            accion=accion,
            entidad=entidad,
            entidad_id=obj.id,
            cambios=cambios,
        )
    )
    # En el log solo los nombres de los campos: los valores pueden ser datos personales.
    logs.evento(
        "cambio",
        accion=accion.value,
        entidad=entidad,
        id=obj.id,
        autor=autor.id if autor else "cli",
        campos=sorted(cambios),
    )
