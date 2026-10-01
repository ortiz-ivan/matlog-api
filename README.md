# matlog-api

Backend de **MatLog**, que registra las técnicas enseñadas en las clases de BJJ. El frontend está en el repo [`matlog`](../matlog).

La documentación funcional está en [`bjj_class_tracker_documentation.md`](bjj_class_tracker_documentation.md).

**Stack**: Python 3.12 · FastAPI · SQLAlchemy 2 · Alembic · PostgreSQL · JWT.

## Puesta en marcha

Requiere [uv](https://docs.astral.sh/uv/) y PostgreSQL.

Toda la configuración va en `.env` (nunca se sube al repo). `.env.example` es la plantilla documentada; la app no arranca si falta una variable obligatoria.

```bash
uv sync                                   # instala dependencias
cp .env.example .env                      # y completar los valores CAMBIAR
uv run python -m app.cli crear-bd         # crea usuario y bases de .env (pide la contraseña del superusuario)
uv run alembic upgrade head               # crea las tablas
uv run python -m app.cli seed             # turnos y técnicas iniciales (idempotente)
uv run python -m app.cli crear-usuario --nombre "Juan" --username juan --email juan@mail.com --admin  # primer admin
# uv run python -m app.cli cambiar-password --username juan  # si alguien olvida la contraseña
uv run fastapi dev app/main.py            # http://localhost:8000/docs
```

En `/docs`, el botón **Authorize** permite hacer login con el nombre de usuario. La documentación
solo se sirve con `DOCS_HABILITADAS=true`; en producción debe ir a `false`.

## Producción

En `.env`: `DOCS_HABILITADAS=false` y `CORS_ORIGINS` con el dominio real del frontend
(`https://...`, sin barra final).

Antes de cada despliegue, comprobar que ninguna dependencia tiene vulnerabilidades
conocidas (debe terminar en "No known vulnerabilities found"):

```bash
uv export --no-dev --no-hashes --no-emit-project -q > requirements-audit.txt
uvx pip-audit -r requirements-audit.txt --no-deps --disable-pip
```

En el servidor, instalar exactamente lo que fija `uv.lock` (con sus hashes) y sin las
dependencias de desarrollo; `--locked` falla si el lock no corresponde a `pyproject.toml`:

```bash
uv sync --locked --no-dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000   --no-server-header --proxy-headers --forwarded-allow-ips=127.0.0.1
```

- `--no-server-header`: no anunciar `server: uvicorn` (lo añade uvicorn, no la app).
- `--proxy-headers` y `--forwarded-allow-ips` (la IP del proxy): para que el límite de
  intentos use la IP real del cliente y la app sepa que la petición llegó por HTTPS
  (de eso depende la cabecera HSTS).
- Un solo proceso (sin `--workers`): el límite de intentos se guarda en memoria.
- HTTPS lo pone el proxy (nginx, Caddy...), que es quien debe exponerse a internet.

## Tests

```bash
uv run pytest
```

Usan la base `matlog_test` (`TEST_DATABASE_URL`), que se recrea al iniciar; cada test se revierte al terminar.

## Estructura

```text
app/
├── main.py          # app FastAPI, CORS y routers
├── config.py        # configuración por variables de entorno
├── db.py            # engine, sesión y Base
├── models.py        # tablas: usuarios, turnos, tecnicas, clases, clase_tecnicas
├── schemas.py       # modelos Pydantic de entrada/salida
├── security.py      # hashing de contraseñas y JWT
├── deps.py          # dependencias: sesión, usuario actual, solo admin
├── cli.py           # crear-bd, crear-usuario y seed desde la terminal
├── seed.py          # turnos de la academia y biblioteca base de técnicas
└── routers/         # auth, usuarios, turnos, tecnicas, clases
alembic/             # migraciones
tests/
```

## Migraciones

Tras cambiar `app/models.py`:

```bash
uv run alembic revision --autogenerate -m "descripcion"
uv run alembic upgrade head
```

Revisa siempre la migración generada. En particular, Alembic duplica los `CheckConstraint` de las columnas `Enum`: hay que borrar los `sa.CheckConstraint(...)` explícitos, porque la columna ya crea el suyo.
