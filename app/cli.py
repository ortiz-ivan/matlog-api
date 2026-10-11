"""Comandos de administración. La configuración se toma de .env.

    uv run python -m app.cli crear-bd [--superusuario postgres]
    uv run python -m app.cli crear-rol-app [--rol matlog_app] [--superusuario postgres]
    uv run python -m app.cli crear-usuario --nombre "Juan" --username juan --email juan@mail.com [--admin]
    uv run python -m app.cli cambiar-password --username juan
    uv run python -m app.cli seed
"""

import argparse
import getpass
import re
import secrets
import sys

import psycopg
from pydantic import TypeAdapter, ValidationError
from psycopg import sql
from sqlalchemy import func, select

from app.config import get_config_migraciones, settings
from app.auditoria import foto, registrar
from app.db import SessionLocal
from app.models import Accion, Usuario
from app.schemas import Username
from app.security import hash_password, invalidar_tokens
from app.seed import cargar_datos_iniciales


def crear_bd(superusuario: str) -> None:
    """Crea el rol propietario y las bases de MIGRACIONES_DATABASE_URL y TEST_DATABASE_URL.

    Idempotente. El rol de la app se crea después, con crear-rol-app.
    """
    propietaria = get_config_migraciones().migraciones_database_url
    urls = [propietaria]
    if settings.test_database_url:
        urls.append(settings.test_database_url)

    datos = propietaria.hosts()[0]
    usuario, password = datos["username"], datos["password"]
    host, port = datos["host"], datos["port"] or 5432

    admin_password = getpass.getpass(f"Contraseña de '{superusuario}' en {host}:{port}: ")
    with psycopg.connect(
        host=host, port=port, user=superusuario, password=admin_password, dbname="postgres",
        autocommit=True,
    ) as conexion:
        existe = conexion.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [usuario]).fetchone()
        accion = "ALTER" if existe else "CREATE"
        conexion.execute(
            sql.SQL(accion + " ROLE {} WITH LOGIN PASSWORD {}").format(
                sql.Identifier(usuario), sql.Literal(password)
            )
        )
        print(f"Usuario '{usuario}' {'actualizado' if existe else 'creado'}")

        for url in urls:
            nombre = url.path.lstrip("/")
            if conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", [nombre]).fetchone():
                print(f"Base '{nombre}' ya existe")
                continue
            conexion.execute(
                sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(nombre), sql.Identifier(usuario)
                )
            )
            print(f"Base '{nombre}' creada")


# Lo único que necesita la API: leer y escribir filas. No puede crear, alterar ni vaciar
# tablas, y la auditoría solo puede leerla y añadirle filas. Los DEFAULT PRIVILEGES
# dan los mismos permisos sobre las tablas que creen migraciones futuras.
_PERMISOS_APP = [
    "GRANT CONNECT ON DATABASE {base} TO {rol}",
    "GRANT USAGE ON SCHEMA public TO {rol}",
    "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
    "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {rol}",
    "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {rol}",
    "REVOKE UPDATE, DELETE ON auditoria FROM {rol}",
    "REVOKE ALL ON alembic_version FROM {rol}",
    "ALTER DEFAULT PRIVILEGES FOR ROLE {propietario} IN SCHEMA public"
    " GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {rol}",
    "ALTER DEFAULT PRIVILEGES FOR ROLE {propietario} IN SCHEMA public"
    " GRANT USAGE, SELECT ON SEQUENCES TO {rol}",
]


def crear_rol_app(rol: str, superusuario: str | None) -> None:
    """Crea o actualiza el rol de la API con permisos mínimos e imprime su DATABASE_URL.

    Se conecta como el rol propietario (MIGRACIONES_DATABASE_URL), que necesita poder
    crear roles, o como `superusuario` si se indica. Cada ejecución pone una contraseña
    nueva: sirve también para rotarla.
    """
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", rol):
        sys.exit("Nombre de rol inválido: minúsculas, números y guion bajo")
    propietaria = get_config_migraciones().migraciones_database_url
    datos = propietaria.hosts()[0]
    propietario, host, port = datos["username"], datos["host"], datos["port"] or 5432
    base = propietaria.path.lstrip("/")
    if rol == propietario:
        sys.exit("El rol de la app debe ser distinto del propietario de las tablas")

    if superusuario:
        acceso = {
            "user": superusuario,
            "password": getpass.getpass(f"Contraseña de '{superusuario}' en {host}:{port}: "),
        }
    else:
        acceso = {"user": propietario, "password": datos["password"]}

    password = secrets.token_urlsafe(32)
    nombres = {
        "rol": sql.Identifier(rol),
        "propietario": sql.Identifier(propietario),
        "base": sql.Identifier(base),
    }
    # Una sola transacción: o queda todo aplicado o nada.
    with psycopg.connect(host=host, port=port, dbname=base, **acceso) as conexion:
        if conexion.execute("SELECT to_regclass('public.auditoria')").fetchone()[0] is None:
            sys.exit("Faltan las tablas: ejecuta antes 'alembic upgrade head'")
        existe = conexion.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [rol]).fetchone()
        accion = "ALTER" if existe else "CREATE"
        conexion.execute(
            sql.SQL(
                accion + " ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
                " NOREPLICATION NOBYPASSRLS PASSWORD {}"
            ).format(sql.Identifier(rol), sql.Literal(password))
        )
        for sentencia in _PERMISOS_APP:
            conexion.execute(sql.SQL(sentencia).format(**nombres))

    print(f"Rol '{rol}' {'actualizado' if existe else 'creado'} con permisos mínimos.")
    print("Pon esta DATABASE_URL a la API (la contraseña no se vuelve a mostrar):")
    print()
    print(f"DATABASE_URL=postgresql+psycopg://{rol}:{password}@{host}:{port}/{base}")


def crear_usuario(nombre: str, username: str, email: str, password: str, es_admin: bool) -> None:
    try:
        username = TypeAdapter(Username).validate_python(username)
    except ValidationError:
        sys.exit("Username inválido: 3-30 caracteres (letras, números, punto, guion o guion bajo)")
    email = email.lower()
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.username == username)):
            sys.exit(f"El username {username} ya está en uso")
        if db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
            sys.exit(f"Ya existe una cuenta con el email {email}")
        usuario = Usuario(
            nombre=nombre,
            username=username,
            email=email,
            password_hash=hash_password(password),
            es_admin=es_admin,
        )
        db.add(usuario)
        registrar(db, None, Accion.CREAR, usuario)
        db.commit()
    print(f"Usuario {username} creado{' (admin)' if es_admin else ''}")


def pedir_password() -> str:
    password = getpass.getpass("Contraseña (mín. 8 caracteres): ")
    if len(password) < 8:
        sys.exit("La contraseña debe tener al menos 8 caracteres")
    if getpass.getpass("Repite la contraseña: ") != password:
        sys.exit("Las contraseñas no coinciden")
    return password


def cambiar_password(username: str, password: str) -> None:
    with SessionLocal() as db:
        usuario = db.scalar(select(Usuario).where(Usuario.username == username.strip().lower()))
        if usuario is None:
            sys.exit(f"No existe el usuario {username}")
        antes = foto(usuario)
        usuario.password_hash = hash_password(password)
        invalidar_tokens(usuario)
        registrar(db, None, Accion.ACTUALIZAR, usuario, antes, extra={"password": "restablecida"})
        db.commit()
    print(f"Contraseña de {usuario.username} actualizada; sus sesiones abiertas se han cerrado")


def seed() -> None:
    with SessionLocal() as db:
        turnos, horarios, tecnicas, descripciones = cargar_datos_iniciales(db)
    print(
        f"Turnos creados: {turnos}. Horarios completados: {horarios}. "
        f"Técnicas creadas: {tecnicas}. Descripciones añadidas: {descripciones}."
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)

    bd = sub.add_parser("crear-bd", help="Crea el usuario y las bases de datos de .env")
    bd.add_argument("--superusuario", default="postgres", help="superusuario de PostgreSQL")

    crear = sub.add_parser("crear-usuario", help="Crea un usuario de la app")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--username", required=True, help="para iniciar sesión")
    crear.add_argument("--email", required=True)
    crear.add_argument("--admin", action="store_true", help="puede gestionar usuarios y borrar")

    cambiar = sub.add_parser("cambiar-password", help="Cambia la contraseña de un usuario")
    cambiar.add_argument("--username", required=True)

    rol = sub.add_parser("crear-rol-app", help="Crea el rol de la API con permisos mínimos")
    rol.add_argument("--rol", default="matlog_app", help="nombre del rol (por defecto matlog_app)")
    rol.add_argument("--superusuario", help="conectar como este superusuario (pide contraseña)")

    sub.add_parser("seed", help="Carga turnos y técnicas iniciales (solo los que falten)")

    args = parser.parse_args()
    if args.comando == "crear-bd":
        crear_bd(args.superusuario)
        return
    if args.comando == "crear-rol-app":
        crear_rol_app(args.rol, args.superusuario)
        return
    if args.comando == "seed":
        seed()
        return
    if args.comando == "cambiar-password":
        cambiar_password(args.username, pedir_password())
        return

    password = pedir_password()
    crear_usuario(args.nombre, args.username, args.email, password, args.admin)


if __name__ == "__main__":
    main()
