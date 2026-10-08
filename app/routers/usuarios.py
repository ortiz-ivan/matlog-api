from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select

from app import logs
from app.auditoria import foto, registrar
from app.cuentas import crear_cuenta
from app.deps import DB, Admin
from app.models import Accion, Usuario
from app.schemas import (
    BUSQUEDA_MAX,
    Pagina,
    UsuarioActualizar,
    UsuarioNuevo,
    UsuarioOut,
    comprobar_grado,
)
from app.security import hash_password, invalidar_tokens

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


def _obtener(db: DB, usuario_id: int) -> Usuario:
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")
    return usuario


@router.get("", response_model=Pagina[UsuarioOut])
def listar(
    db: DB,
    _: Admin,
    q: Annotated[str | None, Query(max_length=BUSQUEDA_MAX)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    filtros = []
    if q and q.strip():
        texto = q.strip()
        filtros.append(
            or_(
                Usuario.nombre.icontains(texto, autoescape=True),
                Usuario.username.icontains(texto, autoescape=True),
            )
        )

    total = db.scalar(select(func.count(Usuario.id)).where(*filtros))
    usuarios = db.scalars(
        select(Usuario)
        .where(*filtros)
        .order_by(func.lower(Usuario.nombre), Usuario.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return Pagina(items=usuarios, total=total)


@router.get("/{usuario_id}", response_model=UsuarioOut)
def detalle(usuario_id: int, db: DB, _: Admin):
    return _obtener(db, usuario_id)


@router.post("", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def crear(datos: UsuarioNuevo, db: DB, admin: Admin):
    usuario = crear_cuenta(db, datos, autor=admin, es_admin=datos.es_admin)
    logs.evento("usuario_creado", admin=admin.id, usuario=usuario.id, es_admin=usuario.es_admin)
    return usuario


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def actualizar(usuario_id: int, datos: UsuarioActualizar, db: DB, admin: Admin):
    usuario = _obtener(db, usuario_id)

    # null solo tiene sentido en el cinturón y la fecha de ingreso (quitarlos); en el
    # resto se ignora.
    cambios = {
        campo: valor
        for campo, valor in datos.model_dump(exclude_unset=True).items()
        if valor is not None or campo in ("cinturon", "fecha_ingreso")
    }
    if usuario.id == admin.id and (
        cambios.get("es_admin") is False or cambios.get("activo") is False
    ):
        # Evita que la plataforma se quede sin nadie capaz de administrarla.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No puedes quitarte el admin ni desactivarte a ti mismo"
        )

    # Un cambio de cinturón empieza sin grados, salvo que se indiquen.
    if "cinturon" in cambios and cambios["cinturon"] != usuario.cinturon:
        cambios.setdefault("grado", 0)
    try:
        comprobar_grado(
            cambios.get("cinturon", usuario.cinturon), cambios.get("grado", usuario.grado)
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None

    antes = foto(usuario)
    if password := cambios.pop("password", None):
        usuario.password_hash = hash_password(password)
    # Al resetear la contraseña o desactivar la cuenta se cierran sus sesiones: si luego
    # se reactiva, los tokens antiguos no vuelven a servir.
    if password or cambios.get("activo") is False:
        invalidar_tokens(usuario)
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    extra = {"password": "restablecida"} if password else None
    registrar(db, admin, Accion.ACTUALIZAR, usuario, antes, extra=extra)
    db.commit()

    # Los cambios de permisos y accesos se marcan aparte, como aviso, en el log.
    sensibles = [c for c in ("es_admin", "activo") if c in cambios and antes[c] != cambios[c]]
    if password:
        sensibles.append("password")
    if sensibles:
        logs.aviso("usuario_modificado", admin=admin.id, usuario=usuario.id, campos=sensibles)
    return usuario
