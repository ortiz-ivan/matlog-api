"""Datos iniciales: turnos de la academia y una biblioteca base de técnicas.

Es idempotente: solo inserta lo que no existe (comparando por nombre), así que
puede ejecutarse varias veces y no pisa cambios hechos desde la app.
"""

from datetime import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Categoria as C
from app.models import Posicion as P
from app.models import Tecnica, Turno

TURNOS = [
    ("Turno 1", time(19, 30), time(20, 30)),
    ("Turno 2", time(20, 30), time(21, 30)),
]

TECNICAS = [
    # Guardia cerrada
    ("Armbar desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Triángulo desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Omoplata", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Kimura desde guardia cerrada", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Guillotina", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Estrangulación cruzada desde guardia", C.FINALIZACION, P.GUARDIA_CERRADA),
    ("Barrida de tijera", C.BARRIDA, P.GUARDIA_CERRADA),
    ("Barrida de cadera (hip bump)", C.BARRIDA, P.GUARDIA_CERRADA),
    ("Barrida de péndulo (flower sweep)", C.BARRIDA, P.GUARDIA_CERRADA),
    ("Apertura de guardia cerrada de pie", C.PASAJE, P.GUARDIA_CERRADA),
    ("Apertura de guardia cerrada de rodillas", C.PASAJE, P.GUARDIA_CERRADA),
    # Guardia abierta
    ("Torreando", C.PASAJE, P.GUARDIA_ABIERTA),
    ("Knee cut", C.PASAJE, P.GUARDIA_ABIERTA),
    ("Leg drag", C.PASAJE, P.GUARDIA_ABIERTA),
    ("Pasaje de doble underhook", C.PASAJE, P.GUARDIA_ABIERTA),
    ("Retención de guardia", C.GUARDIA, P.GUARDIA_ABIERTA),
    ("Barrida de mariposa", C.BARRIDA, P.GUARDIA_ABIERTA),
    ("Barrida de De La Riva", C.BARRIDA, P.GUARDIA_ABIERTA),
    ("Barrida de araña (spider)", C.BARRIDA, P.GUARDIA_ABIERTA),
    ("Berimbolo", C.TRANSICION, P.GUARDIA_ABIERTA),
    # Media guardia
    ("Knee shield", C.GUARDIA, P.MEDIA_GUARDIA),
    ("Barrida old school", C.BARRIDA, P.MEDIA_GUARDIA),
    ("Toma de espalda desde media guardia", C.TRANSICION, P.MEDIA_GUARDIA),
    ("Pasaje de media guardia con crossface", C.PASAJE, P.MEDIA_GUARDIA),
    # Control lateral
    ("Kimura desde control lateral", C.FINALIZACION, P.CONTROL_LATERAL),
    ("Americana", C.FINALIZACION, P.CONTROL_LATERAL),
    ("Transición a montada", C.TRANSICION, P.CONTROL_LATERAL),
    ("Rodilla en el abdomen (knee on belly)", C.CONTROL, P.CONTROL_LATERAL),
    ("Escape de control lateral a guardia", C.ESCAPE, P.CONTROL_LATERAL),
    # Montada
    ("Armbar desde montada", C.FINALIZACION, P.MONTADA),
    ("Estrangulación cruzada desde montada", C.FINALIZACION, P.MONTADA),
    ("Ezequiel", C.FINALIZACION, P.MONTADA),
    ("S-mount", C.CONTROL, P.MONTADA),
    ("Escape de montada con puente (upa)", C.ESCAPE, P.MONTADA),
    ("Escape de montada codo-rodilla", C.ESCAPE, P.MONTADA),
    # Espalda
    ("Mata león", C.FINALIZACION, P.ESPALDA),
    ("Bow and arrow", C.FINALIZACION, P.ESPALDA),
    ("Control de espalda con ganchos", C.CONTROL, P.ESPALDA),
    ("Escape de espalda", C.ESCAPE, P.ESPALDA),
    # Norte-sur
    ("Estrangulación norte-sur", C.FINALIZACION, P.NORTE_SUR),
    # Tortuga
    ("Toma de espalda desde tortuga", C.TRANSICION, P.TORTUGA),
    ("Clock choke", C.FINALIZACION, P.TORTUGA),
    # De pie
    ("Double leg", C.DERRIBO, P.DE_PIE),
    ("Single leg", C.DERRIBO, P.DE_PIE),
    ("O-soto-gari", C.DERRIBO, P.DE_PIE),
    ("Ippon seoi nage", C.DERRIBO, P.DE_PIE),
    ("Puxada (pull guard)", C.GUARDIA, P.DE_PIE),
]


def _existentes(db: Session, columna) -> set[str]:
    return {nombre.lower() for nombre in db.scalars(select(columna))}


def cargar_datos_iniciales(db: Session) -> tuple[int, int]:
    """Inserta los turnos y técnicas que falten. Devuelve (turnos, técnicas) creados."""
    turnos = _existentes(db, Turno.nombre)
    nuevos_turnos = [
        Turno(nombre=nombre, hora_inicio=inicio, hora_fin=fin)
        for nombre, inicio, fin in TURNOS
        if nombre.lower() not in turnos
    ]

    tecnicas = _existentes(db, Tecnica.nombre)
    nuevas_tecnicas = [
        Tecnica(nombre=nombre, categoria=categoria, posicion=posicion)
        for nombre, categoria, posicion in TECNICAS
        if nombre.lower() not in tecnicas
    ]

    db.add_all(nuevos_turnos + nuevas_tecnicas)
    db.commit()
    return len(nuevos_turnos), len(nuevas_tecnicas)
