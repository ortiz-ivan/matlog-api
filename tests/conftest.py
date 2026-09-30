import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, get_db
from app.main import app
from app.models import Usuario
from app.security import hash_password

PASSWORD = "secreto123"


@pytest.fixture(scope="session")
def engine():
    url = settings.test_database_url
    if url is None:
        pytest.exit("Falta TEST_DATABASE_URL en .env", returncode=1)
    if url.path == settings.database_url.path:
        # Los tests borran todas las tablas: nunca contra la base de desarrollo.
        pytest.exit("TEST_DATABASE_URL no puede apuntar a la misma base que DATABASE_URL", returncode=1)

    engine = create_engine(str(url))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    # Cada test corre en una transacción que se revierte al final; los commit()
    # de la app se convierten en savepoints, así la base queda limpia.
    with engine.connect() as conexion:
        transaccion = conexion.begin()
        with Session(
            bind=conexion,
            autoflush=False,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        ) as sesion:
            yield sesion
        transaccion.rollback()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _crear_usuario(db, email: str, es_admin: bool = False) -> Usuario:
    usuario = Usuario(
        nombre=email.split("@")[0],
        email=email,
        password_hash=hash_password(PASSWORD),
        es_admin=es_admin,
    )
    db.add(usuario)
    db.commit()
    return usuario


def _headers(client, email: str) -> dict[str, str]:
    r = client.post("/api/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin(client, db):
    _crear_usuario(db, "admin@matlog.test", es_admin=True)
    return _headers(client, "admin@matlog.test")


@pytest.fixture
def usuario(client, db):
    _crear_usuario(db, "usuario@matlog.test")
    return _headers(client, "usuario@matlog.test")
