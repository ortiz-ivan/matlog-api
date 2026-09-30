from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import auth, clases, tecnicas, turnos, usuarios

app = FastAPI(title="MatLog API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for modulo in (auth, usuarios, turnos, tecnicas, clases):
    app.include_router(modulo.router)


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok"}
