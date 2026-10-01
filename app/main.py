from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.middleware import CabecerasSeguridad, LimiteCuerpo
from app.routers import auth, clases, tecnicas, turnos, usuarios

# La documentación interactiva describe todos los endpoints y esquemas: útil en
# desarrollo, pero en producción solo facilita el reconocimiento a un atacante.
_docs = settings.docs_habilitadas
app = FastAPI(
    title="MatLog API",
    version="0.1.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
    # FastAPI exporta telemetría (OpenTelemetry) en cuanto el entorno define
    # OTEL_EXPORTER_OTLP_ENDPOINT, y entre lo que registra están los errores de
    # validación con los valores recibidos (p. ej. una contraseña demasiado corta).
    # No la usamos: que ninguna variable de entorno pueda activarla.
    telemetry={"auto_configure": False},
)

# Holgado para la petición más grande posible (una clase con notas de 5000 caracteres).
# Se añade antes que CORS para que CORS lo envuelva y el 413 lleve sus cabeceras: si no,
# el navegador lo vería como un error de red.
app.add_middleware(LimiteCuerpo, maximo=64 * 1024)

# El token viaja en la cabecera Authorization, no en cookies: no hacen falta credenciales
# CORS, y sin ellas un origen mal configurado no puede usar la sesión del navegador.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# El último añadido es el más externo: así también llevan estas cabeceras las respuestas
# que generan CORS (preflight) y LimiteCuerpo (413).
app.add_middleware(CabecerasSeguridad)

for modulo in (auth, usuarios, turnos, tecnicas, clases):
    app.include_router(modulo.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
