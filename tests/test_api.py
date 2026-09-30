from app.config import settings
from tests.conftest import PASSWORD

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
    assert me["email"] == "ivan@mail.com"
    assert me["es_admin"] is False

    r = client.post("/api/auth/login", data={"username": "IVAN@mail.com", "password": PASSWORD})
    assert r.status_code == 200


def test_registro_codigo_incorrecto(client):
    assert _registro(client, codigo_invitacion="otro-codigo").status_code == 403


def test_registro_email_duplicado(client):
    assert _registro(client).status_code == 201
    assert _registro(client, email="ivan@mail.com").status_code == 409


def test_registro_no_permite_hacerse_admin(client):
    r = _registro(client, es_admin=True)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/auth/me", headers=headers).json()["es_admin"] is False


def test_login_incorrecto(client, usuario):
    r = client.post(
        "/api/auth/login", data={"username": "usuario@matlog.test", "password": "otra-cosa"}
    )
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


def test_turno_horario_invalido(client, usuario):
    datos = {"nombre": "Mal", "hora_inicio": "20:00", "hora_fin": "19:00"}
    assert client.post("/api/turnos", json=datos, headers=usuario).status_code == 422


def test_turno_desactivado_no_se_lista(client, usuario, admin):
    turno = _turno(client, usuario)
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


def test_crear_clase_toma_horario_del_turno(client, usuario):
    turno = _turno(client, usuario)
    armbar = _tecnica(client, usuario, "Armbar")
    triangulo = _tecnica(client, usuario, "Triángulo")

    clase = _clase(
        client,
        usuario,
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
    assert clase["creado_por"]["nombre"] == "usuario"
    assert clase["turno"]["nombre"] == "Noche"
    assert [t["nombre"] for t in clase["tecnicas"]] == ["Armbar", "Triángulo"]


def test_crear_clase_con_referencias_inexistentes(client, usuario):
    turno = _turno(client, usuario)
    base = {"fecha": "2026-09-30", "tema": "X"}
    r = client.post("/api/clases", json=base | {"turno_id": 999}, headers=usuario)
    assert r.status_code == 422
    r = client.post(
        "/api/clases", json=base | {"turno_id": turno["id"], "tecnica_ids": [999]}, headers=usuario
    )
    assert r.status_code == 422


def test_filtrar_clases(client, usuario):
    manana = _turno(client, usuario, nombre="Mañana", hora_inicio="07:00", hora_fin="08:30")
    noche = _turno(client, usuario)
    omoplata = _tecnica(client, usuario, "Omoplata")

    _clase(client, usuario, fecha="2026-09-01", turno_id=manana["id"], tema="Pasajes",
           instructor="Juan")
    _clase(
        client,
        usuario,
        fecha="2026-09-15",
        turno_id=noche["id"],
        tema="Guardia",
        modalidad="NO_GI",
        tecnica_ids=[omoplata["id"]],
    )
    _clase(client, usuario, fecha="2026-09-30", turno_id=noche["id"], tema="Guardia cerrada")

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


def test_detalle_tecnica_muestra_clases(client, usuario):
    turno = _turno(client, usuario)
    omoplata = _tecnica(client, usuario, "Omoplata")
    for fecha in ("2026-09-02", "2026-09-30"):
        _clase(
            client, usuario, fecha=fecha, turno_id=turno["id"], tema="Guardia",
            tecnica_ids=[omoplata["id"]],
        )

    r = client.get(f"/api/tecnicas/{omoplata['id']}", headers=usuario)
    assert r.status_code == 200
    assert [c["fecha"] for c in r.json()["clases"]] == ["2026-09-30", "2026-09-02"]


def test_actualizar_y_eliminar_clase(client, usuario, admin):
    turno = _turno(client, usuario)
    armbar = _tecnica(client, usuario, "Armbar")
    clase = _clase(client, usuario, fecha="2026-09-30", turno_id=turno["id"], tema="A",
                   tecnica_ids=[armbar["id"]])

    datos = {"fecha": "2026-09-30", "turno_id": turno["id"], "tema": "B", "tecnica_ids": []}
    r = client.put(f"/api/clases/{clase['id']}", json=datos, headers=usuario)
    assert r.status_code == 200
    assert r.json()["tema"] == "B"
    assert r.json()["tecnicas"] == []

    assert client.delete(f"/api/clases/{clase['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/clases/{clase['id']}", headers=usuario).status_code == 404


def test_eliminar_tecnica_la_quita_de_las_clases(client, usuario, admin):
    turno = _turno(client, usuario)
    armbar = _tecnica(client, usuario, "Armbar")
    clase = _clase(client, usuario, fecha="2026-09-30", turno_id=turno["id"], tema="A",
                   tecnica_ids=[armbar["id"]])

    assert client.delete(f"/api/tecnicas/{armbar['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/clases/{clase['id']}", headers=usuario).json()["tecnicas"] == []
