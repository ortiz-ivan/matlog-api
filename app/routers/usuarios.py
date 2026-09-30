from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.deps import DB, Admin
from app.models import Usuario
from app.schemas import UsuarioActualizar, UsuarioOut
from app.security import hash_password

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


@router.get("", response_model=list[UsuarioOut])
def listar(db: DB, _: Admin):
    return db.scalars(select(Usuario).order_by(Usuario.nombre)).all()


@router.patch("/{usuario_id}", response_model=UsuarioOut)
def actualizar(usuario_id: int, datos: UsuarioActualizar, db: DB, admin: Admin):
    usuario = db.get(Usuario, usuario_id)
    if usuario is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Usuario no encontrado")

    cambios = datos.model_dump(exclude_unset=True)
    if usuario.id == admin.id and (
        cambios.get("es_admin") is False or cambios.get("activo") is False
    ):
        # Evita que la plataforma se quede sin nadie capaz de administrarla.
        raise HTTPException(
            status.HTTP_409_CONFLICT, "No puedes quitarte el admin ni desactivarte a ti mismo"
        )

    if password := cambios.pop("password", None):
        usuario.password_hash = hash_password(password)
    for campo, valor in cambios.items():
        setattr(usuario, campo, valor)
    db.commit()
    return usuario
