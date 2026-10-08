import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app import limites, logs
from app.auditoria import foto, registrar
from app.config import settings
from app.cuentas import crear_cuenta
from app.deps import DB, UsuarioActual, oauth2
from app.models import Accion, Usuario
from app.schemas import (
    PASSWORD_MAX,
    CambioPassword,
    PerfilActualizar,
    Registro,
    Token,
    UsuarioOut,
)
from app.security import (
    crear_token,
    hash_password,
    invalidar_tokens,
    leer_token,
    verificar_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/registro", response_model=Token, status_code=status.HTTP_201_CREATED)
def registro(datos: Registro, db: DB, request: Request):
    ip = limites.ip_cliente(request)
    if espera := limites.por_ip.consumir(ip):
        logs.aviso("registro_bloqueado", ip=ip, espera=espera)
        raise limites.demasiados_intentos(espera)

    codigo_valido = secrets.compare_digest(
        datos.codigo_invitacion.encode(), settings.codigo_invitacion.get_secret_value().encode()
    )
    if not codigo_valido:
        logs.aviso("registro_codigo_incorrecto", ip=ip, username=datos.username)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Código de invitación incorrecto")
    limites.por_ip.devolver(ip)

    usuario = crear_cuenta(db, datos)
    logs.evento("registro", usuario=usuario.id, username=usuario.username, ip=ip)
    return Token(access_token=crear_token(usuario))


@router.post("/login", response_model=Token)
def login(db: DB, request: Request, form: Annotated[OAuth2PasswordRequestForm, Depends()]):
    ip = limites.ip_cliente(request)
    username = form.username.strip().lower()
    # Un username de más de 30 caracteres no existe; recortar la clave acota la memoria.
    clave = username[:30]

    # Se comprueba antes de verificar la contraseña: el hash Argon2 es caro a propósito
    # y no debe poder forzarse sin límite.
    espera = limites.por_ip.consumir(ip)
    if not espera and (espera := limites.por_usuario.consumir(clave)):
        limites.por_ip.devolver(ip)
    if espera:
        logs.aviso("login_bloqueado", username=clave, ip=ip, espera=espera)
        raise limites.demasiados_intentos(espera)

    usuario = db.scalar(select(Usuario).where(Usuario.username == username))
    # La contraseña se verifica siempre y "activo" se mira después: si no, responder
    # más rápido delataría qué usernames existen o cuáles están desactivados.
    # Una contraseña más larga que el máximo no puede ser válida: no se calcula su hash.
    password_ok = len(form.password) <= PASSWORD_MAX and verificar_password(
        form.password, usuario.password_hash if usuario else None
    )
    if usuario is None or not password_ok or not usuario.activo:
        # El motivo solo va al log; la respuesta es la misma en los tres casos.
        motivo = (
            "usuario_inexistente" if usuario is None
            else "password_incorrecta" if not password_ok
            else "cuenta_desactivada"
        )
        logs.aviso("login_fallido", username=clave, ip=ip, motivo=motivo)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario o contraseña incorrectos")

    # El fallo de la IP solo se descuenta: si se borrara, alguien con una cuenta propia
    # podría alternar logins correctos para seguir probando contraseñas ajenas.
    limites.por_ip.devolver(ip)
    limites.por_usuario.limpiar(clave)
    logs.evento("login", usuario=usuario.id, ip=ip)
    return Token(access_token=crear_token(usuario))


@router.post("/renovar", response_model=Token)
def renovar(usuario: UsuarioActual, token: Annotated[str, Depends(oauth2)]):
    """Token nuevo con la caducidad renovada; la sesión sigue sin pasar de SESION_MAX_DIAS."""
    datos = leer_token(token)  # ya validado por UsuarioActual
    return Token(access_token=crear_token(usuario, inicio_sesion=datos.inicio_sesion))


@router.get("/me", response_model=UsuarioOut)
def me(usuario: UsuarioActual):
    return usuario


@router.patch("/me", response_model=UsuarioOut)
def actualizar_perfil(datos: PerfilActualizar, db: DB, usuario: UsuarioActual):
    antes = foto(usuario)
    cambios = datos.model_dump(exclude_unset=True)
    # null solo tiene sentido en el cinturón (quitarlo); un nombre nulo se ignora.
    if cambios.get("nombre") is None:
        cambios.pop("nombre", None)
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    registrar(db, usuario, Accion.ACTUALIZAR, usuario, antes)
    db.commit()
    return usuario


@router.put("/me/password", response_model=Token)
def cambiar_password(datos: CambioPassword, db: DB, usuario: UsuarioActual):
    # Pedir la actual evita que alguien con tu sesión abierta te deje fuera.
    if not verificar_password(datos.actual, usuario.password_hash):
        logs.aviso("password_actual_incorrecta", usuario=usuario.id)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "La contraseña actual no es correcta")
    if datos.nueva == datos.actual:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "La nueva contraseña debe ser distinta de la actual"
        )
    antes = foto(usuario)
    usuario.password_hash = hash_password(datos.nueva)
    # Cierra las demás sesiones (p. ej. si alguien conocía la contraseña anterior) y
    # devuelve un token nuevo para que esta siga abierta.
    invalidar_tokens(usuario)
    registrar(db, usuario, Accion.ACTUALIZAR, usuario, antes, extra={"password": "cambiada"})
    db.commit()
    logs.evento("password_cambiada", usuario=usuario.id)
    return Token(access_token=crear_token(usuario))
