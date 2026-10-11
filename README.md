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
uv run python -m app.cli crear-bd         # crea el rol propietario y las bases (pide la contraseña del superusuario)
uv run alembic upgrade head               # crea las tablas
uv run python -m app.cli crear-rol-app --superusuario postgres  # rol de la API: copiar la DATABASE_URL que imprime a .env
uv run python -m app.cli seed             # turnos y técnicas iniciales (idempotente)
uv run python -m app.cli crear-usuario --nombre "Juan" --username juan --email juan@mail.com --admin  # primer admin
# uv run python -m app.cli cambiar-password --username juan  # si alguien olvida la contraseña
uv run fastapi dev app/main.py            # http://localhost:8000/docs
```

En `/docs`, el botón **Authorize** permite hacer login con el nombre de usuario. La documentación
solo se sirve con `DOCS_HABILITADAS=true`; en producción debe ir a `false`.

## Producción (Railway)

La API se despliega en [Railway](https://railway.com) con el `Dockerfile` del repo
(`railway.toml` lo indica). Cada push a la rama configurada despliega solo: Railway
construye la imagen, ejecuta `alembic upgrade head` y, si la migración va bien y
`/health` responde, cambia a la versión nueva.

### Puesta en marcha

1. En Railway: **New Project → Deploy from GitHub repo** con este repo.
2. En el proyecto: **New → Database → PostgreSQL**. Es una base nueva y vacía.
3. En el servicio de la API, pestaña **Variables**:

   | Variable | Valor |
   |---|---|
   | `MIGRACIONES_DATABASE_URL` | `${{Postgres.DATABASE_URL}}` (propietario: solo para migraciones) |
   | `DATABASE_URL` | Al principio también `${{Postgres.DATABASE_URL}}`; ver el paso 6 |
   | `JWT_SECRET` | Nuevo: `uv run python -c "import secrets; print(secrets.token_urlsafe(48))"` |
   | `CODIGO_INVITACION` | Nuevo, distinto del de desarrollo |
   | `CORS_ORIGINS` | `["https://<proyecto>.pages.dev"]` (el dominio del frontend) |
   | `DOCS_HABILITADAS` | `false` |
   | `IP_CLIENTE_CABECERA` | `X-Real-IP` |

   El resto (`JWT_EXPIRE_MINUTES`, `SESION_MAX_DIAS`, `LIMITE_*`) tiene valores por
   defecto adecuados. **No definir `TEST_DATABASE_URL`**: es la base que pytest borra.
4. En **Settings → Networking → Generate Domain** para tener la URL pública
   (`https://<algo>.up.railway.app`). Esa URL es la `VITE_API_URL` del frontend.
5. Crear el primer admin y cargar los datos iniciales desde una consola en el
   contenedor (`railway ssh` con la [CLI de Railway](https://docs.railway.com/guides/cli)):

   ```bash
   python -m app.cli seed
   python -m app.cli crear-usuario --nombre "Juan" --username juan --email juan@mail.com --admin
   ```

6. Pasar la API a un rol con permisos mínimos (ver [Roles de la base de datos](#roles-de-la-base-de-datos)).
   Desde `railway ssh`:

   ```bash
   python -m app.cli crear-rol-app
   ```

   Copiar la `DATABASE_URL` que imprime en la variable `DATABASE_URL` del servicio
   (sustituyendo la referencia) y redesplegar.

### Roles de la base de datos

La API se conecta con un rol que solo puede leer y escribir filas:

| | Propietario (`MIGRACIONES_DATABASE_URL`) | API (`DATABASE_URL`, `matlog_app`) |
|---|---|---|
| Crear, alterar, borrar o vaciar tablas | Sí | No |
| Leer y escribir filas | Sí | Sí |
| Tabla `auditoria` | Todo | Solo leer y añadir filas |
| `alembic_version` | Todo | Nada |

Así, aunque un fallo en la API permitiera ejecutar SQL arbitrario, no podría cambiar el
esquema ni borrar o reescribir el historial de auditoría. Solo Alembic (en el pre-deploy)
y `app.cli` cargan la URL del propietario; la API nunca la lee.

`crear-rol-app` es idempotente: aplica los permisos sobre las tablas existentes y, con
`DEFAULT PRIVILEGES`, sobre las que creen migraciones futuras. Cada ejecución genera una
contraseña nueva, así que también sirve para **rotarla** (después hay que actualizar
`DATABASE_URL`). Si una migración futura añade una tabla que deba ser de solo inserción
como `auditoria`, hay que añadir su `REVOKE` a `_PERMISOS_APP` en `app/cli.py` y volver
a ejecutar el comando.

Límite conocido: en Railway el pre-deploy corre en el mismo contenedor, así que la
variable del propietario está en el entorno del servicio. El rol protege frente a fallos
de la aplicación (inyección SQL, bugs), no frente a alguien que consiga ejecutar comandos
en el contenedor.

### Cómo está montado

- **Una sola réplica**: el límite de intentos se guarda en memoria. No subir réplicas.
- **IP del cliente**: llega en `X-Real-IP`, que pone el proxy de Railway
  (`IP_CLIENTE_CABECERA`). La app no confía en `X-Forwarded-For` para esto: según
  cómo enrute Railway, puede incluir valores que manda el propio cliente.
- **uvicorn** arranca con `--no-server-header` (no anunciar `server: uvicorn`) y
  `--proxy-headers`, para saber que la petición llegó por HTTPS (cabecera HSTS).
- **La imagen** instala solo lo que fija `uv.lock` y sin dependencias de desarrollo
  (`uv sync --locked --no-dev`), y la app corre con un usuario sin privilegios.
  `.dockerignore` impide que `.env` acabe dentro.
- **Log de seguridad**: líneas `evento=...` del logger `matlog.seguridad` en la salida
  estándar, que Railway guarda en los logs del servicio. Para buscarlas, filtrar por
  `evento=login_fallido`, `evento=login_bloqueado`, `evento=acceso_denegado`,
  `evento=usuario_modificado`, `evento=cambio`... Nunca contienen contraseñas, tokens
  ni los valores de los cambios.
- **Auditoría**: cada alta, cambio o borrado de clases, técnicas, turnos y usuarios
  queda en la tabla `auditoria` (quién, cuándo, valor anterior y nuevo; al borrar, la
  fila entera). Los admins la consultan en `GET /api/auditoria`. Los cambios hechos con
  `app.cli` figuran sin usuario.

### Antes de cada despliegue

Comprobar que ninguna dependencia tiene vulnerabilidades conocidas (debe terminar en
"No known vulnerabilities found"):

```bash
uv export --no-dev --no-hashes --no-emit-project -q > requirements-audit.txt
uvx pip-audit -r requirements-audit.txt --no-deps --disable-pip
```

### Sin Railway

El `Dockerfile` sirve igual en cualquier servidor con Docker, detrás de un proxy con
HTTPS (nginx, Caddy...). Definir `IP_CLIENTE_CABECERA` con la cabecera en la que ese
proxy ponga la IP del cliente (y asegurarse de que la sobrescribe), o dejarla vacía si
la API recibe las conexiones directamente. Sin Docker:

```bash
uv sync --locked --no-dev
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-server-header \
  --proxy-headers --forwarded-allow-ips=127.0.0.1
```

## Tests

```bash
uv run pytest
```

Usan la base `matlog_test` (`TEST_DATABASE_URL`), que se recrea al iniciar; cada test se revierte al terminar.

## Estructura

```text
app/
├── main.py          # app FastAPI, CORS, logs y routers
├── config.py        # configuración por variables de entorno
├── db.py            # engine, sesión y Base
├── models.py        # tablas: usuarios, turnos, tecnicas, clases, clase_tecnicas, auditoria
├── schemas.py       # modelos Pydantic de entrada/salida
├── security.py      # hashing de contraseñas y JWT
├── deps.py          # dependencias: sesión, usuario actual, solo admin
├── auditoria.py     # registro de cambios en la tabla auditoria
├── logs.py          # log de eventos de seguridad
├── cli.py           # crear-bd, crear-usuario y seed desde la terminal
├── seed.py          # turnos de la academia y biblioteca base de técnicas
└── routers/         # auth, usuarios, turnos, tecnicas, clases, auditoria
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
