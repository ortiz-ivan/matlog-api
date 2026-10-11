from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app import logs
from app.auditoria import foto, registrar
from app.deps import DB, Admin, UsuarioActual
from app.models import Accion, EstadoParticipacion, Participacion, Torneo, Usuario
from app.schemas import ParticipacionIn, ParticipacionNueva, ParticipacionOut, Rechazo

router = APIRouter(prefix="/api/participaciones", tags=["participaciones"])

_CON_RELACIONES = (joinedload(Participacion.torneo), joinedload(Participacion.usuario))


def _obtener(db: DB, participacion_id: int, usuario: Usuario) -> Participacion:
    """La participación si es del usuario o si es admin. 404 en otro caso: que no se
    pueda averiguar qué pendientes tienen los demás."""
    participacion = db.get(Participacion, participacion_id)
    if participacion is None or (
        participacion.usuario_id != usuario.id and not usuario.es_admin
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Participación no encontrada")
    return participacion


def _editable(participacion: Participacion, usuario: Usuario) -> None:
    # Una vez aprobada ya está en la vitrina: solo un admin puede cambiarla o quitarla.
    if participacion.estado is EstadoParticipacion.APROBADA and not usuario.es_admin:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Ya está aprobada: pide a un admin que la corrija",
        )


def _validar(db: DB, datos: ParticipacionIn, usuario_id: int, excluir_id: int | None = None) -> None:
    if db.get(Torneo, datos.torneo_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El torneo no existe")
    consulta = select(Participacion.id).where(
        Participacion.usuario_id == usuario_id,
        Participacion.torneo_id == datos.torneo_id,
        Participacion.modalidad == datos.modalidad,
        func.lower(Participacion.categoria) == datos.categoria.lower(),
    )
    if excluir_id is not None:
        consulta = consulta.where(Participacion.id != excluir_id)
    if db.scalar(consulta):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Esa participación ya está registrada (mismo torneo y categoría)"
        )


@router.get("/mias", response_model=list[ParticipacionOut])
def mias(db: DB, usuario: UsuarioActual):
    """Las propias en cualquier estado, para seguir la revisión."""
    return db.scalars(
        select(Participacion)
        .join(Participacion.torneo)
        .options(*_CON_RELACIONES)
        .where(Participacion.usuario_id == usuario.id)
        .order_by(Torneo.fecha.desc(), Participacion.id.desc())
    ).all()


@router.get("", response_model=list[ParticipacionOut])
def listar(db: DB, _: Admin, estado: EstadoParticipacion = EstadoParticipacion.PENDIENTE):
    """Cola de revisión de los admins: por defecto las pendientes, las más antiguas primero."""
    return db.scalars(
        select(Participacion)
        .options(*_CON_RELACIONES)
        .where(Participacion.estado == estado)
        .order_by(Participacion.creado_en, Participacion.id)
    ).all()


@router.get("/{participacion_id}", response_model=ParticipacionOut)
def detalle(participacion_id: int, db: DB, usuario: UsuarioActual):
    return _obtener(db, participacion_id, usuario)


@router.post("", response_model=ParticipacionOut, status_code=status.HTTP_201_CREATED)
def crear(datos: ParticipacionNueva, db: DB, usuario: UsuarioActual):
    usuario_id = datos.usuario_id if datos.usuario_id is not None else usuario.id
    if usuario_id != usuario.id:
        if not usuario.es_admin:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Solo un admin registra participaciones de otros"
            )
        destino = db.get(Usuario, usuario_id)
        if destino is None or not destino.activo:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "El usuario no existe")
    _validar(db, datos, usuario_id)

    participacion = Participacion(
        **datos.model_dump(exclude={"usuario_id"}),
        usuario_id=usuario_id,
    )
    # Lo que registra un admin no necesita revisión.
    if usuario.es_admin:
        participacion.estado = EstadoParticipacion.APROBADA
        participacion.revisado_por_id = usuario.id
    db.add(participacion)
    registrar(db, usuario, Accion.CREAR, participacion)
    db.commit()
    return participacion


@router.put("/{participacion_id}", response_model=ParticipacionOut)
def actualizar(participacion_id: int, datos: ParticipacionIn, db: DB, usuario: UsuarioActual):
    participacion = _obtener(db, participacion_id, usuario)
    _editable(participacion, usuario)
    _validar(db, datos, participacion.usuario_id, excluir_id=participacion_id)

    antes = foto(participacion)
    for campo, valor in datos.model_dump().items():
        setattr(participacion, campo, valor)
    # El alumno que corrige una rechazada (o una pendiente) la vuelve a mandar a revisión.
    if not usuario.es_admin:
        participacion.estado = EstadoParticipacion.PENDIENTE
        participacion.motivo_rechazo = None
        participacion.revisado_por_id = None
    registrar(db, usuario, Accion.ACTUALIZAR, participacion, antes)
    db.commit()
    return participacion


@router.delete("/{participacion_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar(participacion_id: int, db: DB, usuario: UsuarioActual):
    participacion = _obtener(db, participacion_id, usuario)
    _editable(participacion, usuario)
    registrar(db, usuario, Accion.ELIMINAR, participacion)
    db.delete(participacion)
    db.commit()


def _revisar(
    db: DB,
    participacion_id: int,
    admin: Usuario,
    estado: EstadoParticipacion,
    motivo: str | None = None,
) -> Participacion:
    participacion = _obtener(db, participacion_id, admin)
    antes = foto(participacion)
    participacion.estado = estado
    participacion.motivo_rechazo = motivo
    participacion.revisado_por_id = admin.id
    registrar(db, admin, Accion.ACTUALIZAR, participacion, antes)
    db.commit()
    logs.evento(
        "participacion_revisada", admin=admin.id, participacion=participacion.id, estado=estado.value
    )
    return participacion


@router.post("/{participacion_id}/aprobar", response_model=ParticipacionOut)
def aprobar(participacion_id: int, db: DB, admin: Admin):
    return _revisar(db, participacion_id, admin, EstadoParticipacion.APROBADA)


@router.post("/{participacion_id}/rechazar", response_model=ParticipacionOut)
def rechazar(participacion_id: int, datos: Rechazo, db: DB, admin: Admin):
    motivo = (datos.motivo or "").strip() or None
    return _revisar(db, participacion_id, admin, EstadoParticipacion.RECHAZADA, motivo)
