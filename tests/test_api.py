from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings, settings
from app.limites import LimiteFallos
from app.middleware import CabecerasSeguridad
from app.routers import auth
from tests.conftest import PASSWORD, _crear_usuario, _headers

CODIGO = settings.codigo_invitacion.get_secret_value()


def _turno(client, headers, **extra):
    datos = {"nombre": "Noche", "hora_inicio": "19:00", "hora_fin": "20:30"} | extra
    r = client.post("/api/turnos", json=datos, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _tecnica(client, headers, nombre, categoria="FINALIZACION", posicion="GUARDIA_CERRADA"):
    datos = {"nombre": nombre, "categoria": categoria, "posicion": posicion}
    r = client.post("/api/tecnicas", json=datos, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _clase(client, headers, **datos):
    r = client.post("/api/clases", json=datos, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _registro(client, **extra):
    datos = {
        "nombre": "Iván",
        "username": "Ivan.Ortiz",
        "email": "Ivan@Mail.com",
        "password": PASSWORD,
        "codigo_invitacion": CODIGO,
    } | extra
    return client.post("/api/auth/registro", json=datos)


# --- Registro y login ---


def test_registro_con_codigo(client):
    r = _registro(client)
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    me = client.get("/api/auth/me", headers=headers).json()
    assert me["username"] == "ivan.ortiz"
    assert me["email"] == "ivan@mail.com"
    assert me["es_admin"] is False

    # El username no distingue mayúsculas; el email ya no sirve para entrar.
    r = client.post("/api/auth/login", data={"username": "IVAN.ortiz", "password": PASSWORD})
    assert r.status_code == 200
    r = client.post("/api/auth/login", data={"username": "ivan@mail.com", "password": PASSWORD})
    assert r.status_code == 401


def test_registro_codigo_incorrecto(client):
    assert _registro(client, codigo_invitacion="otro-codigo").status_code == 403


def test_registro_duplicados(client):
    assert _registro(client).status_code == 201
    r = _registro(client, email="otro@mail.com", username="IVAN.ORTIZ")
    assert r.status_code == 409
    assert "usuario" in r.json()["detail"]
    r = _registro(client, email="ivan@mail.com", username="otro")
    assert r.status_code == 409
    assert "email" in r.json()["detail"]


def test_registro_username_invalido(client):
    for username in ("ab", "con espacio", "ñandú", "x" * 31):
        assert _registro(client, username=username).status_code == 422, username


def test_registro_no_permite_hacerse_admin(client):
    r = _registro(client, es_admin=True)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["es_admin"] is False


def test_login_incorrecto(client, usuario):
    r = client.post("/api/auth/login", data={"username": "usuario", "password": "otra-cosa"})
    assert r.status_code == 401


def test_sin_token(client):
    assert client.get("/api/clases").status_code == 401


# --- Permisos ---


def test_usuario_no_puede_borrar_ni_gestionar_usuarios(client, usuario):
    assert client.get("/api/usuarios", headers=usuario).status_code == 403
    assert client.patch("/api/usuarios/1", json={}, headers=usuario).status_code == 403
    assert client.delete("/api/turnos/1", headers=usuario).status_code == 403
    assert client.delete("/api/tecnicas/1", headers=usuario).status_code == 403
    assert client.delete("/api/clases/1", headers=usuario).status_code == 403


def test_admin_desactiva_usuario(client, admin, usuario):
    usuario_id = client.get("/api/auth/me", headers=usuario).json()["id"]
    r = client.patch(f"/api/usuarios/{usuario_id}", json={"activo": False}, headers=admin)
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=usuario).status_code == 401


def test_desactivar_invalida_los_tokens(client, admin, usuario):
    # Al reactivar la cuenta, los tokens emitidos antes no vuelven a servir.
    usuario_id = client.get("/api/auth/me", headers=usuario).json()["id"]
    client.patch(f"/api/usuarios/{usuario_id}", json={"activo": False}, headers=admin)
    client.patch(f"/api/usuarios/{usuario_id}", json={"activo": True}, headers=admin)
    assert client.get("/api/auth/me", headers=usuario).status_code == 401
    assert client.get("/api/auth/me", headers=_headers(client, "usuario")).status_code == 200


def test_admin_resetea_password_invalida_los_tokens(client, admin, usuario):
    usuario_id = client.get("/api/auth/me", headers=usuario).json()["id"]
    r = client.patch(
        f"/api/usuarios/{usuario_id}", json={"password": "nueva-clave-1"}, headers=admin
    )
    assert r.status_code == 200
    assert client.get("/api/auth/me", headers=usuario).status_code == 401


def test_editar_perfil_no_invalida_los_tokens(client, admin, usuario):
    usuario_id = client.get("/api/auth/me", headers=usuario).json()["id"]
    client.patch(f"/api/usuarios/{usuario_id}", json={"cinturon": "AZUL"}, headers=admin)
    client.patch("/api/auth/me", json={"nombre": "Otro"}, headers=usuario)
    assert client.get("/api/auth/me", headers=usuario).status_code == 200


def _token_a_mano(client, headers, quitar=(), secreto=None, algoritmo=None, **claims):
    """Firma un token para el usuario de `headers` con los claims alterados."""
    ahora = datetime.now(UTC)
    usuario_id = client.get("/api/auth/me", headers=headers).json()["id"]
    payload = {
        "sub": str(usuario_id),
        "ver": 0,
        "auth_time": int(ahora.timestamp()),
        "iat": ahora,
        "exp": ahora + timedelta(hours=1),
    }
    payload = {k: v for k, v in (payload | claims).items() if k not in quitar}
    token = jwt.encode(
        payload,
        secreto or settings.jwt_secret.get_secret_value(),
        algorithm=algoritmo or settings.jwt_algorithm,
    )
    return {"Authorization": f"Bearer {token}"}


def test_token_a_mano_valido(client, usuario):
    # Control: el helper genera tokens aceptados, así los rechazos de abajo son por el cambio.
    assert client.get("/api/auth/me", headers=_token_a_mano(client, usuario)).status_code == 200


@pytest.mark.parametrize(
    "cambio",
    [
        # Emitido antes de existir token_version: hay que volver a iniciar sesión.
        {"quitar": ["ver"]},
        # Sin exp no caducaría nunca.
        {"quitar": ["exp"]},
        {"quitar": ["iat"]},
        {"quitar": ["auth_time"]},
        {"quitar": ["sub"]},
        {"exp": datetime.now(UTC) - timedelta(minutes=1)},
        {"secreto": "otro-secreto-de-al-menos-32-caracteres!!"},
        {"algoritmo": "HS512"},
    ],
    ids=["sin-ver", "sin-exp", "sin-iat", "sin-auth_time", "sin-sub", "caducado", "otro-secreto", "otro-alg"],
)
def test_token_invalido_rechazado(client, usuario, cambio):
    headers = _token_a_mano(client, usuario, **cambio)
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_admin_nombra_otro_admin(client, admin, usuario):
    usuario_id = client.get("/api/auth/me", headers=usuario).json()["id"]
    r = client.patch(f"/api/usuarios/{usuario_id}", json={"es_admin": True}, headers=admin)
    assert r.json()["es_admin"] is True
    assert client.get("/api/usuarios", headers=usuario).status_code == 200


def test_admin_no_puede_quitarse_el_admin(client, admin):
    admin_id = client.get("/api/auth/me", headers=admin).json()["id"]
    for cambio in ({"es_admin": False}, {"activo": False}):
        r = client.patch(f"/api/usuarios/{admin_id}", json=cambio, headers=admin)
        assert r.status_code == 409


# --- Turnos ---


def test_turno_horario_invalido(client, usuario, admin):
    datos = {"nombre": "Mal", "hora_inicio": "20:00", "hora_fin": "19:00"}
    assert client.post("/api/turnos", json=datos, headers=admin).status_code == 422


def test_turno_desactivado_no_se_lista(client, usuario, admin):
    turno = _turno(client, admin)
    assert client.delete(f"/api/turnos/{turno['id']}", headers=admin).status_code == 204
    assert client.get("/api/turnos", headers=usuario).json() == []
    todos = client.get("/api/turnos?incluir_inactivos=true", headers=usuario).json()
    assert len(todos) == 1


# --- Técnicas ---


def test_buscar_tecnicas(client, usuario):
    _tecnica(client, usuario, "Armbar desde guardia")
    _tecnica(client, usuario, "Armbar desde montada", posicion="MONTADA")
    _tecnica(client, usuario, "Knee Cut", categoria="PASAJE", posicion="MEDIA_GUARDIA")

    def nombres(query):
        return [t["nombre"] for t in client.get(f"/api/tecnicas{query}", headers=usuario).json()]

    assert nombres("?q=ARMBAR") == ["Armbar desde guardia", "Armbar desde montada"]
    assert nombres("?categoria=PASAJE") == ["Knee Cut"]


def test_tecnica_nombre_duplicado(client, usuario):
    _tecnica(client, usuario, "Omoplata")
    datos = {"nombre": "omoplata", "categoria": "FINALIZACION", "posicion": "GUARDIA_CERRADA"}
    assert client.post("/api/tecnicas", json=datos, headers=usuario).status_code == 409


def test_tecnica_video_url_invalida(client, usuario):
    datos = {
        "nombre": "Kimura",
        "categoria": "FINALIZACION",
        "posicion": "GUARDIA_CERRADA",
        "video_url": "no-es-una-url",
    }
    assert client.post("/api/tecnicas", json=datos, headers=usuario).status_code == 422


# --- Clases ---


def test_crear_clase_toma_horario_del_turno(client, usuario, admin):
    turno = _turno(client, admin)
    armbar = _tecnica(client, usuario, "Armbar")
    triangulo = _tecnica(client, usuario, "Triángulo")

    clase = _clase(
        client,
        admin,
        fecha="2026-09-30",
        turno_id=turno["id"],
        tema="Guardia cerrada",
        instructor="Juan",
        tecnica_ids=[triangulo["id"], armbar["id"]],
        video_url="https://youtube.com/watch?v=abc",
    )
    assert clase["hora_inicio"] == "19:00:00"
    assert clase["hora_fin"] == "20:30:00"
    assert clase["modalidad"] == "GI"
    assert clase["instructor"] == "Juan"
    assert clase["creado_por"]["nombre"] == "admin"
    assert clase["turno"]["nombre"] == "Noche"
    assert [t["nombre"] for t in clase["tecnicas"]] == ["Armbar", "Triángulo"]

def test_solo_admins_registran_clases(client, usuario, admin):
    turno = _turno(client, admin)
    datos = {"fecha": "2026-09-30", "turno_id": turno["id"], "tema": "Guardia"}
    r = client.post("/api/clases", json=datos, headers=usuario)
    assert r.status_code == 403
    assert client.post("/api/clases", json=datos, headers=admin).status_code == 201


def test_crear_clase_con_referencias_inexistentes(client, usuario, admin):
    turno = _turno(client, admin)
    base = {"fecha": "2026-09-30", "tema": "X"}
    r = client.post("/api/clases", json=base | {"turno_id": 999}, headers=admin)
    assert r.status_code == 422
    r = client.post(
        "/api/clases", json=base | {"turno_id": turno["id"], "tecnica_ids": [999]}, headers=admin
    )
    assert r.status_code == 422


def test_filtrar_clases(client, usuario, admin):
    manana = _turno(client, admin, nombre="Mañana", hora_inicio="07:00", hora_fin="08:30")
    noche = _turno(client, admin)
    omoplata = _tecnica(client, usuario, "Omoplata")

    _clase(client, admin, fecha="2026-09-01", turno_id=manana["id"], tema="Pasajes",
           instructor="Juan")
    _clase(
        client,
        admin,
        fecha="2026-09-15",
        turno_id=noche["id"],
        tema="Guardia",
        modalidad="NO_GI",
        tecnica_ids=[omoplata["id"]],
    )
    _clase(client, admin, fecha="2026-09-30", turno_id=noche["id"], tema="Guardia cerrada")

    def temas(query=""):
        r = client.get(f"/api/clases{query}", headers=usuario)
        assert r.status_code == 200
        return [c["tema"] for c in r.json()["items"]]

    assert temas() == ["Guardia cerrada", "Guardia", "Pasajes"]
    assert temas(f"?turno_id={noche['id']}") == ["Guardia cerrada", "Guardia"]
    assert temas("?desde=2026-09-10&hasta=2026-09-20") == ["Guardia"]
    assert temas("?modalidad=NO_GI") == ["Guardia"]
    assert temas(f"?tecnica_id={omoplata['id']}") == ["Guardia"]
    assert temas("?instructor=juan") == ["Pasajes"]

    r = client.get("/api/clases?limit=2", headers=usuario).json()
    assert r["total"] == 3
    assert len(r["items"]) == 2


def test_clases_de_una_tecnica_paginadas(client, usuario, admin):
    turno = _turno(client, admin)
    omoplata = _tecnica(client, usuario, "Omoplata")
    for fecha in ("2026-09-02", "2026-09-30"):
        _clase(
            client, admin, fecha=fecha, turno_id=turno["id"], tema="Guardia",
            tecnica_ids=[omoplata["id"]],
        )

    r = client.get(f"/api/tecnicas/{omoplata['id']}", headers=usuario)
    assert r.status_code == 200
    assert "clases" not in r.json()  # se piden aparte, paginadas

    r = client.get(f"/api/clases?tecnica_id={omoplata['id']}&limit=1", headers=usuario).json()
    assert r["total"] == 2
    assert [c["fecha"] for c in r["items"]] == ["2026-09-30"]
    r = client.get(
        f"/api/clases?tecnica_id={omoplata['id']}&limit=1&offset=1", headers=usuario
    ).json()
    assert [c["fecha"] for c in r["items"]] == ["2026-09-02"]


def test_actualizar_y_eliminar_clase(client, usuario, admin):
    turno = _turno(client, admin)
    armbar = _tecnica(client, usuario, "Armbar")
    clase = _clase(client, admin, fecha="2026-09-30", turno_id=turno["id"], tema="A",
                   tecnica_ids=[armbar["id"]])

    datos = {"fecha": "2026-09-30", "turno_id": turno["id"], "tema": "B", "tecnica_ids": []}
    r = client.put(f"/api/clases/{clase['id']}", json=datos, headers=usuario)
    assert r.status_code == 200
    assert r.json()["tema"] == "B"
    assert r.json()["tecnicas"] == []

    assert client.delete(f"/api/clases/{clase['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/clases/{clase['id']}", headers=usuario).status_code == 404


def test_eliminar_tecnica_la_quita_de_las_clases(client, usuario, admin):
    turno = _turno(client, admin)
    armbar = _tecnica(client, usuario, "Armbar")
    clase = _clase(client, admin, fecha="2026-09-30", turno_id=turno["id"], tema="A",
                   tecnica_ids=[armbar["id"]])

    assert client.delete(f"/api/tecnicas/{armbar['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/clases/{clase['id']}", headers=usuario).json()["tecnicas"] == []


# --- Datos iniciales ---


def test_seed_es_idempotente(client, db, usuario, admin):
    from app.seed import TECNICAS, TURNOS, cargar_datos_iniciales

    # Ya existen (con otra capitalización): una sin descripción y otra escrita a mano.
    omoplata = _tecnica(client, usuario, "omoplata")
    datos = {
        "nombre": "KNEE CUT",
        "categoria": "PASAJE",
        "posicion": "GUARDIA_ABIERTA",
        "descripcion": "Nuestra versión",
    }
    knee_cut = client.post("/api/tecnicas", json=datos, headers=usuario).json()

    # "Turno 1" ya existe sin horario: se le completa; "Turno 2" se crea entero.
    _turno(client, admin, nombre="turno 1", hora_inicio="19:30", hora_fin="20:30")

    # Crea las 45 técnicas restantes y solo completa la descripción vacía.
    assert cargar_datos_iniciales(db) == (len(TURNOS) - 1, 1, len(TECNICAS) - 2, 1)
    assert cargar_datos_iniciales(db) == (0, 0, 0, 0)

    def descripcion(t):
        return client.get(f"/api/tecnicas/{t['id']}", headers=usuario).json()["descripcion"]

    assert descripcion(omoplata).startswith("Llave de hombro")
    assert descripcion(knee_cut) == "Nuestra versión"
    sin_descripcion = [t for t in client.get("/api/tecnicas", headers=usuario).json() if not t["descripcion"]]
    assert sin_descripcion == []

    turnos = client.get("/api/turnos", headers=usuario).json()
    assert [(t["nombre"].lower(), t["hora_inicio"]) for t in turnos] == [
        ("turno 1", "19:30:00"),
        ("turno 2", "20:30:00"),
    ]
    lunes_a_sabado = [{"dia": d, "modalidad": "GI"} for d in range(6)]
    assert all(t["dias"] == lunes_a_sabado for t in turnos)


# --- Gestión de usuarios (admin) ---


def _nuevo_usuario(client, headers, **extra):
    datos = {
        "nombre": "Ana Pérez",
        "username": "Ana.P",
        "email": "ana@mail.com",
        "password": PASSWORD,
    } | extra
    return client.post("/api/usuarios", json=datos, headers=headers)


def test_admin_crea_usuario(client, admin):
    r = _nuevo_usuario(client, admin, cinturon="AZUL")
    assert r.status_code == 201, r.text
    creado = r.json()
    assert creado["username"] == "ana.p"
    assert creado["cinturon"] == "AZUL"
    assert creado["es_admin"] is False
    assert creado["activo"] is True

    # Puede entrar con la contraseña inicial que le dio el admin.
    r = client.post("/api/auth/login", data={"username": "ana.p", "password": PASSWORD})
    assert r.status_code == 200

    assert client.get(f"/api/usuarios/{creado['id']}", headers=admin).json() == creado


def test_admin_crea_otro_admin(client, admin):
    assert _nuevo_usuario(client, admin, es_admin=True).json()["es_admin"] is True


def test_admin_crea_usuario_duplicado(client, admin):
    assert _nuevo_usuario(client, admin).status_code == 201
    assert _nuevo_usuario(client, admin, email="otra@mail.com").status_code == 409
    assert _nuevo_usuario(client, admin, username="otra").status_code == 409


def test_usuario_normal_no_crea_usuarios(client, usuario):
    assert _nuevo_usuario(client, usuario).status_code == 403
    assert client.get("/api/usuarios/1", headers=usuario).status_code == 403


def test_listar_usuarios_paginado_y_busqueda(client, admin):
    for i in range(3):
        _nuevo_usuario(client, admin, nombre=f"Zeta {i}", username=f"zeta{i}", email=f"z{i}@m.com")

    r = client.get("/api/usuarios?limit=2", headers=admin).json()
    assert r["total"] == 4  # admin + 3
    assert [u["username"] for u in r["items"]] == ["admin", "zeta0"]

    r = client.get("/api/usuarios?limit=2&offset=2", headers=admin).json()
    assert [u["username"] for u in r["items"]] == ["zeta1", "zeta2"]

    r = client.get("/api/usuarios?q=ZETA1", headers=admin).json()
    assert [u["username"] for u in r["items"]] == ["zeta1"]


def test_actualizar_usuario_ignora_nulos(client, admin):
    creado = _nuevo_usuario(client, admin, cinturon="AZUL").json()
    r = client.patch(
        f"/api/usuarios/{creado['id']}",
        json={"nombre": None, "activo": None, "cinturon": None},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Ana Pérez"
    assert r.json()["activo"] is True
    assert r.json()["cinturon"] is None


# --- Mi perfil ---


def test_actualizar_mi_perfil(client, usuario):
    r = client.patch(
        "/api/auth/me", json={"nombre": "Nuevo Nombre", "cinturon": "MORADO"}, headers=usuario
    )
    assert r.status_code == 200
    assert r.json()["nombre"] == "Nuevo Nombre"
    assert r.json()["cinturon"] == "MORADO"

    # Quitar el cinturón; un nombre nulo se ignora.
    r = client.patch("/api/auth/me", json={"nombre": None, "cinturon": None}, headers=usuario)
    assert r.json()["nombre"] == "Nuevo Nombre"
    assert r.json()["cinturon"] is None


def test_perfil_no_permite_hacerse_admin(client, usuario):
    r = client.patch("/api/auth/me", json={"es_admin": True, "activo": False}, headers=usuario)
    assert r.status_code == 200
    assert r.json()["es_admin"] is False
    assert r.json()["activo"] is True


def test_cambiar_mi_password(client, usuario):
    def login(password):
        return client.post("/api/auth/login", data={"username": "usuario", "password": password})

    r = client.put(
        "/api/auth/me/password", json={"actual": PASSWORD, "nueva": "otra-clave-1"}, headers=usuario
    )
    assert r.status_code == 200
    assert login(PASSWORD).status_code == 401
    assert login("otra-clave-1").status_code == 200

    # El token anterior deja de servir; el devuelto mantiene la sesión abierta.
    assert client.get("/api/auth/me", headers=usuario).status_code == 401
    nuevo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=nuevo).status_code == 200


def test_cambiar_password_exige_la_actual(client, usuario):
    def cambiar(actual, nueva):
        return client.put(
            "/api/auth/me/password", json={"actual": actual, "nueva": nueva}, headers=usuario
        )

    r = cambiar("incorrecta", "otra-clave-1")
    assert r.status_code == 400
    assert "actual" in r.json()["detail"]
    assert cambiar(PASSWORD, PASSWORD).status_code == 400  # igual que la actual
    assert cambiar(PASSWORD, "corta").status_code == 422  # menos de 8


# --- Horario semanal de los turnos ---


def test_turno_con_horario_semanal(client, admin, usuario):
    dias = [{"dia": 0, "modalidad": "GI"}, {"dia": 3, "modalidad": "NO_GI"}]
    turno = _turno(client, admin, dias=dias)
    assert turno["dias"] == dias

    # Mantener el lunes cambiando su modalidad, quitar el jueves y añadir el sábado.
    nuevos = [{"dia": 5, "modalidad": "GI"}, {"dia": 0, "modalidad": "NO_GI"}]
    datos = {"nombre": "Noche", "hora_inicio": "19:00", "hora_fin": "20:30", "dias": nuevos}
    r = client.put(f"/api/turnos/{turno['id']}", json=datos, headers=admin)
    assert r.status_code == 200, r.text
    assert r.json()["dias"] == [{"dia": 0, "modalidad": "NO_GI"}, {"dia": 5, "modalidad": "GI"}]

    # Cualquiera puede consultarlo.
    r = client.get(f"/api/turnos/{turno['id']}", headers=usuario)
    assert r.json()["dias"] == [{"dia": 0, "modalidad": "NO_GI"}, {"dia": 5, "modalidad": "GI"}]


def test_turno_horario_invalido_o_repetido(client, admin):
    base = {"nombre": "X", "hora_inicio": "19:00", "hora_fin": "20:00"}
    for dias in ([{"dia": 7}], [{"dia": -1}], [{"dia": 1}, {"dia": 1, "modalidad": "NO_GI"}]):
        r = client.post("/api/turnos", json=base | {"dias": dias}, headers=admin)
        assert r.status_code == 422, dias


def test_solo_admins_cambian_turnos(client, admin, usuario):
    datos = {"nombre": "X", "hora_inicio": "19:00", "hora_fin": "20:00"}
    assert client.post("/api/turnos", json=datos, headers=usuario).status_code == 403
    turno = _turno(client, admin)
    r = client.put(f"/api/turnos/{turno['id']}", json=datos, headers=usuario)
    assert r.status_code == 403


# --- Límite de intentos fallidos ---


def _login(client, username, password):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def test_login_bloquea_al_usuario_tras_varios_fallos(client, db, usuario):
    for _ in range(settings.limite_fallos_usuario):
        assert _login(client, "usuario", "incorrecta").status_code == 401

    # Bloqueado incluso con la contraseña correcta: si no, serviría para adivinarla.
    r = _login(client, "Usuario", PASSWORD)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # Otro usuario desde la misma IP no se ve afectado.
    _crear_usuario(db, "otro")
    assert _login(client, "otro", PASSWORD).status_code == 200


def test_login_correcto_reinicia_los_fallos_del_usuario(client, usuario):
    for _ in range(2):
        for _ in range(settings.limite_fallos_usuario - 1):
            assert _login(client, "usuario", "incorrecta").status_code == 401
        assert _login(client, "usuario", PASSWORD).status_code == 200


def test_login_bloquea_la_ip_tras_varios_fallos(client, usuario):
    # Usernames distintos para no tocar el límite por usuario.
    for i in range(settings.limite_fallos_ip):
        assert _login(client, f"nadie{i}", "incorrecta").status_code == 401
    assert _login(client, "usuario", PASSWORD).status_code == 429


def test_registro_bloquea_tras_varios_codigos_incorrectos(client):
    datos = {"nombre": "Ana", "username": "ana", "email": "ana@mail.com", "password": PASSWORD}
    for _ in range(settings.limite_fallos_ip):
        r = client.post("/api/auth/registro", json=datos | {"codigo_invitacion": "incorrecto"})
        assert r.status_code == 403
    r = client.post("/api/auth/registro", json=datos | {"codigo_invitacion": CODIGO})
    assert r.status_code == 429


def test_limite_fallos_ventana_deslizante():
    ahora = [0.0]
    limite = LimiteFallos(maximo=2, ventana_segundos=60, reloj=lambda: ahora[0])

    assert limite.consumir("x") == 0
    ahora[0] = 30
    assert limite.consumir("x") == 0
    assert limite.consumir("x") == 30  # hasta que caduque el primero (t=60)
    assert limite.consumir("y") == 0  # cada clave cuenta por separado

    ahora[0] = 61
    assert limite.consumir("x") == 0  # el primero ya caducó
    limite.devolver("x")
    assert limite.consumir("x") == 0  # devolver libera el hueco


def test_login_verifica_siempre_la_password(client, db, monkeypatch):
    # Si el login respondiera sin calcular el hash cuando el usuario no existe o está
    # desactivado, el tiempo de respuesta delataría qué cuentas hay.
    inactivo = _crear_usuario(db, "inactivo")
    inactivo.activo = False
    db.commit()

    llamadas = []
    original = auth.verificar_password
    monkeypatch.setattr(
        auth, "verificar_password", lambda *args: llamadas.append(args) or original(*args)
    )
    assert _login(client, "no-existe", PASSWORD).status_code == 401
    assert _login(client, "inactivo", PASSWORD).status_code == 401
    assert len(llamadas) == 2


# --- CORS y configuración ---


def _preflight(client, origen):
    return client.options(
        "/api/clases",
        headers={
            "Origin": origen,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


def test_cors_permite_el_frontend_sin_credenciales(client):
    r = _preflight(client, settings.cors_origins[0])
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == settings.cors_origins[0]
    assert "access-control-allow-credentials" not in r.headers


def test_cors_rechaza_otros_origenes(client):
    r = _preflight(client, "https://web-maliciosa.example")
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
    r = client.get("/health", headers={"Origin": "https://web-maliciosa.example"})
    assert "access-control-allow-origin" not in r.headers


@pytest.mark.parametrize(
    "origen",
    ["*", "http://localhost:5180/", "https://matlog.app/ruta", "localhost:5180", "https://*.app"],
)
def test_config_rechaza_origenes_cors_invalidos(origen):
    with pytest.raises(ValidationError, match="Origen CORS inválido"):
        Settings(cors_origins=[origen])


def test_config_rechaza_algoritmo_jwt_inseguro():
    for algoritmo in ("none", "RS256"):
        with pytest.raises(ValidationError):
            Settings(jwt_algorithm=algoritmo)


# --- Renovación del token ---


def _claims(token):
    return jwt.decode(
        token, settings.jwt_secret.get_secret_value(), algorithms=[settings.jwt_algorithm]
    )


def _renovar(client, headers):
    return client.post("/api/auth/renovar", headers=headers)


def test_token_dura_jwt_expire_minutes(client, usuario):
    claims = _claims(usuario["Authorization"].removeprefix("Bearer "))
    assert claims["exp"] - claims["iat"] == settings.jwt_expire_minutes * 60
    assert claims["auth_time"] == claims["iat"]


def test_renovar_conserva_el_inicio_de_sesion(client, usuario):
    hace_un_rato = datetime.now(UTC) - timedelta(hours=2)
    viejo = _token_a_mano(client, usuario, auth_time=int(hace_un_rato.timestamp()))

    r = _renovar(client, viejo)
    assert r.status_code == 200
    claims = _claims(r.json()["access_token"])
    assert claims["auth_time"] == int(hace_un_rato.timestamp())
    assert claims["exp"] - claims["iat"] == settings.jwt_expire_minutes * 60
    nuevo = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=nuevo).status_code == 200


def test_renovar_no_pasa_del_maximo_de_sesion(client, usuario):
    # Sesión a una hora de su máximo: el token renovado caduca entonces, no en 24 h.
    tope = datetime.now(UTC) + timedelta(hours=1)
    inicio = tope - timedelta(days=settings.sesion_max_dias)
    viejo = _token_a_mano(client, usuario, auth_time=int(inicio.timestamp()))

    claims = _claims(_renovar(client, viejo).json()["access_token"])
    assert claims["exp"] == int(inicio.timestamp()) + settings.sesion_max_dias * 86400


def test_renovar_sesion_agotada_da_un_token_caducado(client, usuario):
    inicio = datetime.now(UTC) - timedelta(days=settings.sesion_max_dias, minutes=1)
    viejo = _token_a_mano(client, usuario, auth_time=int(inicio.timestamp()))

    nuevo = {"Authorization": f"Bearer {_renovar(client, viejo).json()['access_token']}"}
    assert client.get("/api/auth/me", headers=nuevo).status_code == 401


def test_renovar_exige_token_valido(client, usuario):
    assert client.post("/api/auth/renovar").status_code == 401
    caducado = _token_a_mano(client, usuario, exp=datetime.now(UTC) - timedelta(minutes=1))
    assert _renovar(client, caducado).status_code == 401



# --- Límites de tamaño ---


@pytest.mark.parametrize(
    ("ruta", "metodo", "datos"),
    [
        ("/api/tecnicas", "post", {"descripcion": "x" * 5001}),
        ("/api/tecnicas", "post", {"video_url": "https://a.com/" + "x" * 500}),
        ("/api/clases", "post", {"notas": "x" * 5001}),
        ("/api/clases", "post", {"tecnica_ids": list(range(1, 52))}),
        ("/api/turnos", "post", {"dias": [{"dia": d % 7} for d in range(8)]}),
        ("/api/auth/registro", "post", {"codigo_invitacion": "x" * 129}),
        ("/api/auth/me/password", "put", {"actual": "x" * 129, "nueva": "otra-clave-1"}),
    ],
    ids=["descripcion", "video_url", "notas", "tecnica_ids", "dias", "codigo", "password-actual"],
)
def test_campos_demasiado_largos(client, admin, ruta, metodo, datos):
    # 422 de validación, nunca 500: antes una video_url de más de 500 caracteres
    # llegaba a la base de datos y reventaba contra la columna VARCHAR(500).
    base = {
        "/api/tecnicas": {"nombre": "X", "categoria": "OTRA", "posicion": "OTRA"},
        "/api/clases": {"fecha": "2026-10-01", "turno_id": 1, "tema": "X"},
        "/api/turnos": {"nombre": "X", "hora_inicio": "19:00", "hora_fin": "20:00"},
        "/api/auth/registro": {
            "nombre": "X", "username": "xxx", "email": "x@x.com", "password": PASSWORD
        },
    }.get(ruta, {})
    r = getattr(client, metodo)(ruta, json=base | datos, headers=admin)
    assert r.status_code == 422, r.text


@pytest.mark.parametrize(
    "ruta", ["/api/tecnicas?q=", "/api/clases?instructor=", "/api/usuarios?q="]
)
def test_busquedas_demasiado_largas(client, admin, ruta):
    assert client.get(ruta + "x" * 101, headers=admin).status_code == 422


def test_login_con_password_enorme(client, usuario):
    assert _login(client, "usuario", "x" * 10_000).status_code == 401


def test_cuerpo_demasiado_grande(client, usuario):
    grande = b'{"nombre": "' + b"x" * 70_000 + b'"}'
    cabeceras = usuario | {"Content-Type": "application/json", "Origin": settings.cors_origins[0]}
    r = client.post("/api/tecnicas", content=grande, headers=cabeceras)
    assert r.status_code == 413
    # Con cabeceras CORS: el frontend puede leer el error en vez de ver un fallo de red.
    assert r.headers["access-control-allow-origin"] == settings.cors_origins[0]

    # Sin Content-Length (por chunks) también se corta.
    trozos = iter([grande[:40_000], grande[40_000:]])
    r = client.post("/api/tecnicas", content=trozos, headers=cabeceras)
    assert r.status_code == 413


def test_busqueda_trata_comodines_como_texto(client, usuario):
    _tecnica(client, usuario, "Guardia 100% cerrada")
    _tecnica(client, usuario, "Guardia abierta")
    _tecnica(client, usuario, "Media_guardia")
    _tecnica(client, usuario, "Media guardia profunda")

    def nombres(q):
        r = client.get("/api/tecnicas", params={"q": q}, headers=usuario)
        return [t["nombre"] for t in r.json()]

    assert nombres("%") == ["Guardia 100% cerrada"]
    assert nombres("_") == ["Media_guardia"]


def test_docs_deshabilitadas(monkeypatch):
    import importlib

    import app.main

    monkeypatch.setattr(settings, "docs_habilitadas", False)
    try:
        sin_docs = TestClient(importlib.reload(app.main).app)
        for ruta in ("/docs", "/redoc", "/openapi.json"):
            assert sin_docs.get(ruta).status_code == 404
        assert sin_docs.get("/health").status_code == 200
    finally:
        monkeypatch.undo()
        importlib.reload(app.main)


def test_docs_habilitadas(client):
    # El .env de desarrollo y tests las tiene activadas.
    assert client.get("/openapi.json").status_code == 200


# --- Cabeceras de seguridad ---

_CABECERAS_SEGURIDAD = {
    "x-content-type-options": "nosniff",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "cache-control": "no-store",
}


def _con_cabeceras_seguridad(r):
    return all(r.headers.get(k) == v for k, v in _CABECERAS_SEGURIDAD.items())


def test_cabeceras_de_seguridad_en_todas_las_respuestas(client, usuario):
    origen = settings.cors_origins[0]
    respuestas = {
        "ok": client.get("/api/auth/me", headers=usuario),
        "401": client.get("/api/clases"),
        "404": client.get("/no-existe"),
        "422": client.get("/api/clases?limit=0", headers=usuario),
        "preflight": _preflight(client, origen),
        "413": client.post(
            "/api/tecnicas", content=b"x" * 70_000, headers=usuario | {"Origin": origen}
        ),
    }
    for caso, r in respuestas.items():
        assert _con_cabeceras_seguridad(r), (caso, dict(r.headers))
        assert "strict-transport-security" not in r.headers  # por HTTP no aplica


def test_hsts_solo_por_https(client):
    with TestClient(client.app, base_url="https://testserver") as https:
        r = https.get("/health")
    assert r.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


def test_docs_sin_csp_para_que_cargue_swagger(client):
    r = client.get("/docs")
    assert r.status_code == 200
    assert "content-security-policy" not in r.headers
    assert r.headers["x-content-type-options"] == "nosniff"


def test_cabeceras_de_seguridad_no_pisan_las_de_la_respuesta():
    async def app_con_cache(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"cache-control", b"max-age=60")],
        })
        await send({"type": "http.response.body", "body": b""})

    r = TestClient(CabecerasSeguridad(app_con_cache)).get("/")
    assert r.headers["cache-control"] == "max-age=60"
    assert r.headers["x-content-type-options"] == "nosniff"


# --- Despliegue: URL de la base de datos e IP del cliente detrás de un proxy ---


@pytest.mark.parametrize("esquema", ["postgresql", "postgres", "postgresql+psycopg"])
def test_database_url_usa_siempre_psycopg(esquema):
    # Railway da postgresql://; SQLAlchemy buscaría psycopg2, que no está instalado.
    s = Settings(database_url=f"{esquema}://u:p@postgres.railway.internal:5432/railway")
    assert str(s.database_url).startswith("postgresql+psycopg://u:p@postgres.railway.internal")


def _fallar_logins(client, n, headers=None, desde=0):
    # Usernames distintos para no tocar el límite por usuario.
    for i in range(desde, desde + n):
        r = client.post(
            "/api/auth/login", data={"username": f"nadie{i}", "password": "x"}, headers=headers
        )
        assert r.status_code == 401


def test_sin_cabecera_configurada_no_se_confia_en_x_real_ip(client, usuario):
    # Un atacante que inventa X-Real-IP en cada intento no debe saltarse el límite.
    for i in range(settings.limite_fallos_ip):
        _fallar_logins(client, 1, headers={"X-Real-IP": f"10.0.0.{i}"}, desde=i)
    r = _login(client, "usuario", PASSWORD)
    assert r.status_code == 429


def test_ip_desde_la_cabecera_del_proxy(client, usuario, monkeypatch):
    monkeypatch.setattr(settings, "ip_cliente_cabecera", "X-Real-IP")
    _fallar_logins(client, settings.limite_fallos_ip, headers={"X-Real-IP": "203.0.113.1"})

    bloqueada = client.post(
        "/api/auth/login",
        data={"username": "usuario", "password": PASSWORD},
        headers={"X-Real-IP": "203.0.113.1"},
    )
    assert bloqueada.status_code == 429
    # Otro cliente detrás del mismo proxy no se ve afectado.
    otra = client.post(
        "/api/auth/login",
        data={"username": "usuario", "password": PASSWORD},
        headers={"X-Real-IP": "198.51.100.7"},
    )
    assert otra.status_code == 200
