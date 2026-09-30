"""Comandos de administración. La configuración se toma de .env.

    uv run python -m app.cli crear-bd [--superusuario postgres]
    uv run python -m app.cli crear-usuario --nombre "Juan" --email juan@mail.com [--admin]
    uv run python -m app.cli seed
"""

import argparse
import getpass
import sys

import psycopg
from psycopg import sql
from sqlalchemy import func, select

from app.config import settings
from app.db import SessionLocal
from app.models import Usuario
from app.security import hash_password
from app.seed import cargar_datos_iniciales


def crear_bd(superusuario: str) -> None:
    """Crea el usuario y las bases de DATABASE_URL y TEST_DATABASE_URL (idempotente)."""
    urls = [settings.database_url]
    if settings.test_database_url:
        urls.append(settings.test_database_url)

    datos = settings.database_url.hosts()[0]
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


def crear_usuario(nombre: str, email: str, password: str, es_admin: bool) -> None:
    email = email.lower()
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(func.lower(Usuario.email) == email)):
            sys.exit(f"Ya existe un usuario con el email {email}")
        db.add(
            Usuario(
                nombre=nombre,
                email=email,
                password_hash=hash_password(password),
                es_admin=es_admin,
            )
        )
        db.commit()
    print(f"Usuario {email} creado{' (admin)' if es_admin else ''}")


def seed() -> None:
    with SessionLocal() as db:
        turnos, tecnicas = cargar_datos_iniciales(db)
    print(f"Turnos creados: {turnos}. Técnicas creadas: {tecnicas}.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="comando", required=True)

    bd = sub.add_parser("crear-bd", help="Crea el usuario y las bases de datos de .env")
    bd.add_argument("--superusuario", default="postgres", help="superusuario de PostgreSQL")

    crear = sub.add_parser("crear-usuario", help="Crea un usuario de la app")
    crear.add_argument("--nombre", required=True)
    crear.add_argument("--email", required=True)
    crear.add_argument("--admin", action="store_true", help="puede gestionar usuarios y borrar")

    sub.add_parser("seed", help="Carga turnos y técnicas iniciales (solo los que falten)")

    args = parser.parse_args()
    if args.comando == "crear-bd":
        crear_bd(args.superusuario)
        return
    if args.comando == "seed":
        seed()
        return

    password = getpass.getpass("Contraseña (mín. 8 caracteres): ")
    if len(password) < 8:
        sys.exit("La contraseña debe tener al menos 8 caracteres")
    crear_usuario(args.nombre, args.email, password, args.admin)


if __name__ == "__main__":
    main()
