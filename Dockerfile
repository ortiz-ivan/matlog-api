# Imagen de la API para Railway (o cualquier servidor con Docker).
FROM python:3.12-slim

# uv fijado a una versión concreta: el mismo build hoy y dentro de un mes.
COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Primero solo las dependencias, en su propia capa: no se reinstalan si solo cambia el
# código. --locked falla si uv.lock no corresponde a pyproject.toml; --no-dev deja fuera
# pytest, httpx y fastapi-cli.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Sin privilegios de root: si alguien llegara a ejecutar código en el contenedor, no
# podría modificar la app ni el sistema.
RUN useradd --system --uid 10001 --no-create-home matlog
USER matlog

ENV PATH="/app/.venv/bin:$PATH"

# Railway indica el puerto en $PORT. --proxy-headers con '*' para que la app sepa que
# la petición llegó por HTTPS (cabecera HSTS); la IP del cliente para el límite de
# intentos NO sale de aquí sino de IP_CLIENTE_CABECERA (ver app/limites.py).
# exec: uvicorn recibe directamente SIGTERM y termina limpio en cada despliegue.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-server-header --proxy-headers --forwarded-allow-ips='*'"]
