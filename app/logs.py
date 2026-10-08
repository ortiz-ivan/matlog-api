"""Log de eventos de seguridad: inicios de sesión, bloqueos, accesos denegados y cambios.

Sale por stdout, que es lo que guarda Railway, así que queda fuera de la base de datos:
si alguien la manipulara, aquí seguiría el rastro. Nunca se registran contraseñas,
tokens ni el contenido de los cambios (eso está en la tabla de auditoría).
"""

import json
import logging
import sys

_log = logging.getLogger("matlog.seguridad")


def configurar() -> None:
    """Manda los logs de la app a stdout. Idempotente: se puede llamar varias veces."""
    raiz = logging.getLogger("matlog")
    if raiz.handlers:
        return
    salida = logging.StreamHandler(sys.stdout)
    salida.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    raiz.addHandler(salida)
    raiz.setLevel(logging.INFO)


def evento(nombre: str, nivel: int = logging.INFO, **datos: object) -> None:
    """Una línea `evento=<nombre> clave=valor ...`, fácil de buscar y filtrar.

    Los valores van en JSON: un username con saltos de línea o comillas queda escapado
    y no puede inventar líneas de log falsas.
    """
    campos = (f"{k}={json.dumps(v, ensure_ascii=False, default=str)}" for k, v in datos.items())
    _log.log(nivel, " ".join([f"evento={nombre}", *campos]))


def aviso(nombre: str, **datos: object) -> None:
    evento(nombre, logging.WARNING, **datos)
