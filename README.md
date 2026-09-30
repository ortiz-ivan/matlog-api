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

En `/docs`, el botón **Authorize** permite hacer login con el nombre de usuario.

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
