from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _CuerpoDemasiadoGrande(HTTPException):
    # Es una HTTPException porque FastAPI convierte en 400 cualquier otra excepción que
    # surja al leer el cuerpo; esta la deja pasar y responde con su status_code.
    def __init__(self, maximo: int):
        super().__init__(413, f"La petición es demasiado grande (máximo {maximo // 1024} KB)")


class LimiteCuerpo:
    """Responde 413 si el cuerpo de la petición supera `maximo` bytes.

    Los límites de los esquemas actúan después de leer y parsear el JSON entero; esto
    corta antes, para que nadie pueda hacer que el servidor cargue en memoria un cuerpo
    enorme. Mira Content-Length y, si no viene (envío por chunks), cuenta lo recibido.
    """

    def __init__(self, app: ASGIApp, maximo: int):
        self.app = app
        self.maximo = maximo

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        largo = dict(scope["headers"]).get(b"content-length")
        if largo is not None and (not largo.isdigit() or int(largo) > self.maximo):
            await self._rechazar(scope, receive, send)
            return

        recibido = 0
        respuesta_iniciada = False

        async def receive_limitado() -> Message:
            nonlocal recibido
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                recibido += len(mensaje.get("body", b""))
                if recibido > self.maximo:
                    raise _CuerpoDemasiadoGrande(self.maximo)
            return mensaje

        async def send_vigilado(mensaje: Message) -> None:
            nonlocal respuesta_iniciada
            respuesta_iniciada = respuesta_iniciada or mensaje["type"] == "http.response.start"
            await send(mensaje)

        try:
            await self.app(scope, receive_limitado, send_vigilado)
        except _CuerpoDemasiadoGrande as error:
            # Las rutas de FastAPI ya la convierten en respuesta; esto cubre el resto.
            if respuesta_iniciada:
                raise
            await self._rechazar(scope, receive, send, error)

    async def _rechazar(
        self, scope: Scope, receive: Receive, send: Send, error: HTTPException | None = None
    ) -> None:
        error = error or _CuerpoDemasiadoGrande(self.maximo)
        respuesta = JSONResponse({"detail": error.detail}, status_code=error.status_code)
        await respuesta(scope, receive, send)


# Para una API que solo devuelve JSON: nada que cargar, nada que incrustar.
_CABECERAS = {
    # Que el navegador no "adivine" otro tipo de contenido (p. ej. tratar JSON como HTML).
    b"x-content-type-options": b"nosniff",
    # Si alguien abre una respuesta directamente, no puede ejecutar ni cargar nada.
    b"content-security-policy": b"default-src 'none'; frame-ancestors 'none'",
    # Equivalente a frame-ancestors para navegadores antiguos.
    b"x-frame-options": b"DENY",
    b"referrer-policy": b"no-referrer",
    # Las respuestas llevan datos personales y tokens: que no queden en cachés
    # compartidas ni en la del navegador.
    b"cache-control": b"no-store",
}
# Swagger UI y ReDoc cargan scripts de un CDN: con la CSP de arriba no funcionarían.
# Solo se sirven en desarrollo (DOCS_HABILITADAS).
_RUTAS_DOCS = ("/docs", "/redoc")
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class CabecerasSeguridad:
    """Añade cabeceras de seguridad a todas las respuestas, sin pisar las que ya traigan."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra = dict(_CABECERAS)
        if scope["path"].startswith(_RUTAS_DOCS):
            del extra[b"content-security-policy"]
        # HSTS solo tiene efecto por HTTPS (por HTTP el navegador la ignora). Detrás de un
        # proxy, el esquema es https si uvicorn arranca con --proxy-headers.
        if scope.get("scheme") == "https":
            extra.update([_HSTS])

        async def send_con_cabeceras(mensaje: Message) -> None:
            if mensaje["type"] == "http.response.start":
                presentes = {nombre.lower() for nombre, _ in mensaje.get("headers", [])}
                mensaje["headers"] = [
                    *mensaje.get("headers", []),
                    *((k, v) for k, v in extra.items() if k not in presentes),
                ]
            await send(mensaje)

        await self.app(scope, receive, send_con_cabeceras)
