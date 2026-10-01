"""Límite de intentos fallidos (login y código de invitación) contra fuerza bruta.

Se guarda en memoria: vale para un único proceso. Con varios workers o réplicas,
cada uno llevaría su propia cuenta y habría que moverlo a Redis o similar.
"""

import math
import threading
import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException, Request, status

from app.config import settings

# Por encima de este número de claves se purgan las caducadas, para que alguien
# probando miles de usernames distintos no haga crecer la memoria sin límite.
_MAX_CLAVES = 10_000


class LimiteFallos:
    """Cuenta intentos por clave en una ventana deslizante."""

    def __init__(
        self, maximo: int, ventana_segundos: float, reloj: Callable[[], float] = time.monotonic
    ):
        self.maximo = maximo
        self.ventana = ventana_segundos
        self._reloj = reloj
        self._intentos: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _vigentes(self, clave: str, ahora: float) -> deque[float]:
        intentos = self._intentos.get(clave, deque())
        while intentos and intentos[0] <= ahora - self.ventana:
            intentos.popleft()
        return intentos

    def consumir(self, clave: str) -> int:
        """Cuenta un intento antes de comprobarlo; si sale bien, se llama a devolver().

        Devuelve 0 si se permite, o los segundos que faltan si la clave está
        bloqueada (en ese caso el intento no se cuenta). Reservar antes de comprobar
        evita que muchas peticiones en paralelo se salten el límite.
        """
        with self._lock:
            ahora = self._reloj()
            intentos = self._vigentes(clave, ahora)
            if len(intentos) >= self.maximo:
                return max(1, math.ceil(intentos[0] + self.ventana - ahora))
            if clave not in self._intentos and len(self._intentos) >= _MAX_CLAVES:
                self._purgar(ahora)
            intentos.append(ahora)
            self._intentos[clave] = intentos
            return 0

    def devolver(self, clave: str) -> None:
        """Descuenta el último intento: no era un fallo."""
        with self._lock:
            if intentos := self._intentos.get(clave):
                intentos.pop()

    def limpiar(self, clave: str) -> None:
        with self._lock:
            self._intentos.pop(clave, None)

    def reiniciar(self) -> None:
        with self._lock:
            self._intentos.clear()

    def _purgar(self, ahora: float) -> None:
        for clave in list(self._intentos):
            if not self._vigentes(clave, ahora):
                del self._intentos[clave]


_ventana = settings.limite_ventana_minutos * 60
# Por IP: frena a quien prueba muchos usuarios o códigos desde el mismo sitio.
por_ip = LimiteFallos(settings.limite_fallos_ip, _ventana)
# Por username: frena un ataque repartido entre muchas IP contra una misma cuenta.
por_usuario = LimiteFallos(settings.limite_fallos_usuario, _ventana)


def ip_cliente(request: Request) -> str:
    # Detrás de un proxy, la conexión llega desde el proxy: la IP real viene en la
    # cabecera que este pone (IP_CLIENTE_CABECERA). Solo se lee si está configurada,
    # porque sin un proxy delante la escribiría el propio cliente.
    if settings.ip_cliente_cabecera:
        if valor := request.headers.get(settings.ip_cliente_cabecera):
            return valor.split(",")[0].strip()[:64]
    return request.client.host if request.client else "desconocida"


def demasiados_intentos(segundos: int) -> HTTPException:
    minutos = math.ceil(segundos / 60)
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Demasiados intentos fallidos. Prueba de nuevo en {minutos} "
        f"minuto{'s' if minutos != 1 else ''}.",
        headers={"Retry-After": str(segundos)},
    )
