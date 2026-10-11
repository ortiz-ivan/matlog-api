# MatLog — BJJ Class Tracker

## 1. Descripción

Plataforma web para una academia de Brazilian Jiu-Jitsu (BJJ) que permite a los propios alumnos registrar las técnicas enseñadas en cada clase y consultarlas después.

Es un **proyecto experimental** para los compañeros de la academia. El objetivo no es construir el sistema perfecto, sino algo que los compañeros quieran abrir después de entrenar. Si realmente se usa, se irá ampliando.

La pregunta que debe responder el MVP:

> **"¿Qué vimos en las clases y en qué turno?"**

Preguntas concretas:

- ¿Qué técnicas vimos hoy?
- ¿Qué técnicas se enseñaron en determinado turno?
- ¿En qué clases apareció una técnica?
- ¿Qué se vio la semana pasada?

La plataforma funciona como un **historial técnico de las clases**, no como sustituto del profesor.

---

## 2. Alcance del MVP

### Incluido

- Registro con código de invitación y login.
- Turnos.
- Biblioteca de técnicas con búsqueda.
- Registro de clases con sus técnicas, notas y video (URL externa).
- Listado de clases con filtros (fecha, turno, modalidad, instructor, técnica).
- Detalle de técnica con las clases en las que apareció.

### Fuera del MVP (deliberadamente)

- **Asistencia** y, por tanto, historial personal por alumno ("mis clases", "mis técnicas").
- Estadísticas.
- Multi-academia / SaaS.
- Recomendaciones de repaso.
- Notas personales, favoritos, estados de técnica por alumno.
- Almacenamiento propio de videos.
- PWA.
- CI/CD elaborado.
- Refresh tokens.

Sin asistencia, todos los alumnos ven todas las clases de la academia. Es suficiente para responder la pregunta principal.

---

## 3. Usuarios y permisos

La plataforma la gestionan los propios alumnos: no hay rol de profesor. Todos los usuarios son iguales salvo por un flag `es_admin`.

### Usuario

- Registrarse con el código de invitación de la academia.
- Consultar y filtrar clases.
- Buscar técnicas y ver en qué clases aparecieron.
- **Editar** clases (p. ej. añadir una técnica que faltó o las notas).
- **Crear y editar** técnicas.
- Ver a sus compañeros (cinturón, antigüedad, torneos y medallas) en "Compañeros".
- Registrar sus **participaciones en torneos** (y dar de alta el torneo si no existe). Quedan pendientes hasta que un admin las aprueba; mientras tanto, o si se rechazan, puede corregirlas o borrarlas. Una vez aprobadas, solo un admin las cambia.

Cada clase guarda quién la registró (`creado_por`).

### Admin (`es_admin`)

Todo lo anterior, y además:

- **Registrar** clases nuevas.
- Gestionar los **turnos** y el horario semanal (días y modalidad).
- **Borrar** clases y técnicas, y desactivar turnos (protege contra borrados accidentales).
- Gestionar usuarios desde la pantalla "Usuarios" (menú de perfil): darlos de alta con una contraseña inicial, desactivar cuentas, resetear contraseñas y nombrar otros admins.
- Asignar a cada usuario su **cinturón, grado y fecha de ingreso** a la academia. Solo un admin puede cambiarlos: se muestran a todos en "Compañeros".
- **Revisar** las participaciones en torneos: aprobarlas o rechazarlas con un motivo. Las que registra un admin (suyas o de otro alumno) nacen aprobadas.
- Corregir y borrar **torneos** (solo si no tienen participaciones).

Un admin no puede quitarse el admin ni desactivarse a sí mismo, para que la plataforma nunca se quede sin administrador. El primer admin se crea por línea de comandos.

---

## 4. Conceptos principales

### Turno

Horario recurrente de entrenamiento. Ejemplos: `Mañana 07:00`, `Mediodía 12:00`, `Noche 19:00`.

### Clase

Sesión concreta de entrenamiento:

```text
Fecha: 30/09/2026
Horario: 19:00 - 20:30
Turno: Noche
Modalidad: Gi
Instructor: Juan
Tema: Guardia cerrada
Técnicas: Armbar, Triángulo, Omoplata
```

### Técnica

Técnica individual de la biblioteca (Armbar desde guardia, Triángulo, Omoplata, Knee Cut...).

Las técnicas existen independientemente de las clases para poder reutilizarlas.

---

## 5. Funcionalidades del MVP

### 5.1 Autenticación

- Registro con nombre, nombre de usuario, email, contraseña y **código de invitación** (definido en `.env` y compartido con los compañeros). Evita que cualquiera con el enlace cree una cuenta.
- Login con **nombre de usuario** y contraseña → JWT. El username no distingue mayúsculas (se guarda en minúsculas) y admite 3–30 caracteres: letras, números, `.`, `-` y `_`. El email se guarda para una futura recuperación de contraseña, pero no sirve para entrar.
- Permisos: usuario normal / admin.
- Cada usuario cambia su nombre y contraseña en "Mi perfil" (cambiar la contraseña exige la actual). El cinturón, el grado y la fecha de ingreso los asigna un admin.
- Sin recuperación de contraseña por email: si alguien la olvida, un admin le pone una nueva.

### 5.2 Listado de clases

Ordenado por fecha descendente. Filtros combinables:

- Rango de fechas.
- Turno.
- Modalidad.
- Instructor.
- Técnica.

### 5.3 Detalle de clase

Fecha, horario, turno, instructor, modalidad, tema, técnicas, notas, video y quién la registró.

### 5.4 Biblioteca de técnicas

Búsqueda por nombre y filtros por categoría y posición.

Cada técnica tiene: nombre, categoría, posición, descripción y video opcional.

El detalle de una técnica muestra las clases en las que apareció:

```text
OMOPLATA
Vista en 3 clases

30/09/2026 - Guardia cerrada
18/09/2026 - Scramble
02/09/2026 - Guardia
```

### 5.5 Registro de clases

Formulario (solo admins):

- Fecha.
- Turno (el horario se toma del turno si no se indica).
- Modalidad.
- Tema.
- Instructor (texto libre, opcional: quién dio la clase).
- Técnicas (seleccionadas desde la biblioteca, con opción de crear una nueva).
- Notas.
- Video/recurso.

Registrar una clase no debería llevar más de 2 minutos:

```text
Nueva clase → turno → tema → técnicas → guardar
```

---

## 6. Modelo de datos

### usuarios

```text
id
nombre
username         (único, minúsculas; para iniciar sesión)
email            (único)
password_hash
cinturon         BLANCO | AZUL | MORADO | MARRON | NEGRO (opcional)
grado            0-4 (0-6 en negro; 0 sin cinturón). Al cambiar de cinturón vuelve a 0
fecha_ingreso    fecha de ingreso a la academia (opcional)
es_admin
activo
token_version    (va en el JWT; al incrementarla se invalidan sus tokens)
creado_en
actualizado_en
```

### turnos

```text
id
nombre
hora_inicio
hora_fin
activo
creado_en
actualizado_en
```

### turno_dias

Horario semanal: qué días hay clase en cada turno y con qué modalidad.

```text
turno_id         → turnos
dia              0 = lunes ... 6 = domingo
modalidad        GI | NO_GI
```

### tecnicas

```text
id
nombre           (único)
categoria
posicion
descripcion
video_url
creado_en
actualizado_en
```

### clases

```text
id
creado_por_id    → usuarios (quién la registró)
turno_id         → turnos
fecha
hora_inicio
hora_fin
modalidad        GI | NO_GI
tema
instructor       (texto libre, opcional)
notas
video_url
creado_en
actualizado_en
```

### clase_tecnicas

Relación N:N entre clases y técnicas.

```text
clase_id         → clases
tecnica_id       → tecnicas
```

### torneos

```text
id
nombre
fecha            (ya disputado: no puede ser futura)
lugar            (opcional)
creado_por_id    → usuarios
creado_en
actualizado_en
```

### participaciones

Lo que hizo un alumno en un torneo. Única por usuario, torneo, modalidad y categoría.

```text
id
usuario_id       → usuarios
torneo_id        → torneos (sin cascada: un torneo con participaciones no se borra)
modalidad        GI | NO_GI
categoria        texto libre ("Adulto azul pluma", "Absoluto"...)
medalla          ORO | PLATA | BRONCE (nula: sin medalla)
estado           PENDIENTE | APROBADA | RECHAZADA
motivo_rechazo   (opcional)
revisado_por_id  → usuarios (el admin que la aprobó o rechazó)
creado_en
actualizado_en
```

Solo las APROBADAS se ven en Compañeros y cuentan en el medallero.

### Relaciones

```text
Usuario  1 ─── N Clases (creado_por)
Turno    1 ─── N Clases
Turno    1 ─── N TurnoDias (horario semanal)
Clase    N ─── N Técnicas
Usuario  1 ─── N Participaciones
Torneo   1 ─── N Participaciones
```

---

## 7. Taxonomía inicial

Se mantiene simple; puede evolucionar según cómo la usen los compañeros.

Categorías:

```text
GUARDIA
PASAJE
BARRIDA
FINALIZACION
ESCAPE
DERRIBO
TRANSICION
CONTROL
OTRA
```

Posiciones:

```text
GUARDIA_CERRADA
GUARDIA_ABIERTA
MEDIA_GUARDIA
CONTROL_LATERAL
MONTADA
ESPALDA
NORTE_SUR
TORTUGA
DE_PIE
OTRA
```

---

## 8. Arquitectura

```text
Frontend (repo: matlog)
React + TypeScript + Vite
        │
        │ REST API
        ▼
Backend (repo: matlog-api)
Python + FastAPI + SQLAlchemy + Alembic
        │
        ▼
PostgreSQL (desarrollo y producción)
```

- **FastAPI**: API REST y documentación automática en `/docs`.
- **SQLAlchemy 2**: ORM.
- **Alembic**: migraciones desde el principio.
- **JWT** (PyJWT) + contraseñas con Argon2 (pwdlib).
- **Docker**: solo si aporta comodidad en el deployment.

---

## 9. API

### Autenticación

```http
POST /api/auth/registro     (público, requiere código de invitación)
POST /api/auth/login
GET  /api/auth/me
PATCH /api/auth/me          (nombre propio)
PUT  /api/auth/me/password  (exige la contraseña actual; devuelve un token nuevo)
POST /api/auth/renovar      (token nuevo con la caducidad renovada)
```

### Usuarios (admin)

```http
GET   /api/usuarios?q=ana&limit=20&offset=0   (paginado; busca por nombre o usuario)
GET   /api/usuarios/{id}
POST  /api/usuarios                           (alta con contraseña inicial; puede crear admins)
PATCH /api/usuarios/{id}                      (nombre, cinturón, grado, ingreso, admin, activo, contraseña)
```

### Compañeros

```http
GET   /api/companeros        (cualquier usuario; cuentas activas, sin username ni email, con medallero)
GET   /api/companeros/{id}   (ficha: datos públicos, medallero y participaciones aprobadas)
```

Ordenados por cinturón, grado y antigüedad. Sin paginar: una academia tiene decenas de alumnos.
El medallero (oro, plata, bronce y torneos distintos) solo cuenta participaciones aprobadas.

### Torneos

```http
GET    /api/torneos?q=open
GET    /api/torneos/{id}
POST   /api/torneos         (cualquier usuario; 409 si ya existe con ese nombre y fecha)
PUT    /api/torneos/{id}    (admin)
DELETE /api/torneos/{id}    (admin; 409 si tiene participaciones)
```

### Participaciones

```http
GET    /api/participaciones/mias           (las propias, en cualquier estado)
GET    /api/participaciones?estado=PENDIENTE   (admin; cola de revisión)
GET    /api/participaciones/{id}           (la propia, o cualquiera si es admin; si no, 404)
POST   /api/participaciones                (propia → PENDIENTE; un admin puede indicar usuario_id y nace APROBADA)
PUT    /api/participaciones/{id}           (el autor si no está aprobada, y vuelve a PENDIENTE; o un admin)
DELETE /api/participaciones/{id}           (igual que PUT)
POST   /api/participaciones/{id}/aprobar   (admin)
POST   /api/participaciones/{id}/rechazar  (admin; {"motivo": "..."} opcional)
```

### Turnos

```http
GET    /api/turnos
GET    /api/turnos/{id}
POST   /api/turnos          (admin; incluye "dias": [{"dia": 0, "modalidad": "GI"}, ...])
PUT    /api/turnos/{id}     (admin)
DELETE /api/turnos/{id}     (admin; desactiva)
```

### Técnicas

```http
GET    /api/tecnicas?q=armbar&categoria=FINALIZACION&posicion=GUARDIA_CERRADA
GET    /api/tecnicas/{id}           (incluye clases donde apareció)
POST   /api/tecnicas
PUT    /api/tecnicas/{id}
DELETE /api/tecnicas/{id}           (admin)
```

### Clases

```http
GET    /api/clases?desde=2026-09-01&hasta=2026-09-30&turno_id=3&modalidad=GI&instructor=juan&tecnica_id=7
GET    /api/clases/{id}
POST   /api/clases          (admin)
PUT    /api/clases/{id}
DELETE /api/clases/{id}     (admin)
```

Los filtros se resuelven en el backend, con paginación (`limit`, `offset`).

---

## 10. Seguridad mínima

- Contraseñas con hashing seguro (Argon2).
- JWT HMAC (HS256/384/512) con `sub`, `ver`, `auth_time`, `iat` y `exp` obligatorios.
  Dura 24 h (`JWT_EXPIRE_MINUTES`) y el frontend lo renueva mientras se usa la app, sin
  pasar nunca de 7 días desde el login (`SESION_MAX_DIAS`). Es revocable:
  cambiar o resetear la contraseña y desactivar la cuenta cierran todas las sesiones
  abiertas del usuario (`token_version`).
- Límite de intentos fallidos en login (por IP y por usuario) y en el código de invitación
  (por IP): al superarlo se responde 429 con `Retry-After`. Se guarda en memoria, así que
  asume un único proceso; con varios workers habría que llevarlo a Redis.
- El login tarda lo mismo exista o no el usuario (y esté o no activo): no se puede averiguar
  quién tiene cuenta midiendo el tiempo de respuesta.
- CORS solo para los orígenes exactos de `CORS_ORIGINS` (se rechaza `*`), sin credenciales:
  el token va en la cabecera `Authorization`, así que no hay cookies que proteger de CSRF.
- El token se guarda en `localStorage`; lo protege la Content-Security-Policy estricta del
  frontend, que impide ejecutar scripts inyectados (ver README de `matlog`).
- Borrado y gestión de usuarios solo para admins.
- Registro protegido por código de invitación.
- Toda la configuración y los secretos en `.env` (nunca en el código ni en el repo).
- Validación de inputs (Pydantic), con longitud máxima en todos los textos, listas y
  búsquedas, y cuerpos de petición de 64 KB como máximo (413 si se superan). En las
  búsquedas, `%` y `_` se buscan como texto, no como comodines.
- `/docs`, `/redoc` y `/openapi.json` solo con `DOCS_HABILITADAS=true` (desactivadas en
  producción).
- Cabeceras de seguridad en todas las respuestas: `nosniff`, CSP `default-src 'none'`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store` y
  HSTS cuando llega por HTTPS.
- HTTPS en deployment (ver README, sección Producción).

---

## 11. Plan por fases

### Fase 1 — Backend base (repo `matlog-api`)

- [x] Proyecto FastAPI con configuración por variables de entorno.
- [x] SQLAlchemy + Alembic + migración inicial.
- [x] Autenticación JWT, registro con código de invitación y flag admin.
- [x] Comandos para crear la base de datos y el primer admin.
- [x] CRUD de turnos, técnicas y clases.
- [x] Filtros de clases y búsqueda de técnicas.
- [x] Tests básicos.

### Fase 2 — Frontend (repo `matlog`)

- [ ] Proyecto React + TypeScript + Vite.
- [ ] Login.
- [ ] Listado y detalle de clases con filtros.
- [ ] Biblioteca de técnicas.
- [ ] Registro de cuenta.
- [ ] Formulario de clase.
- [ ] Mobile-first.

### Fase 3 — Deployment

- [ ] PostgreSQL gestionado.
- [ ] Deploy de backend y frontend.
- [ ] Backups.

---

## 12. Principios de diseño

### Primero registrar, después analizar

El MVP se enfoca en obtener datos confiables: **clase → técnicas → consulta**. Estadísticas y recomendaciones vienen después, solo si se usa.

### Fácil de registrar

Si registrar una clase es tedioso, nadie lo hará. Pocos campos obligatorios.

### Mobile-first

El alumno consultará desde el teléfono antes o después del entrenamiento: botones grandes, búsqueda rápida, pocos pasos.

---

## 13. Evolución futura (si el MVP se usa)

1. **Asistencia**: tabla `asistencias` (clase_id, alumno_id). Habilita "mis clases" y "mis técnicas vistas", derivadas de asistencia → clases → técnicas.
2. **Seguimiento personal**: tabla `alumno_tecnicas` (estado VISTA / PRACTICADA / DOMINADA como etiqueta personal, notas privadas, favoritos).
3. **Estadísticas**: clases asistidas, técnicas vistas, técnicas más enseñadas.
4. **Recomendación de repaso**: técnicas vistas hace mucho tiempo.
5. **Planificación** de clases por semanas.
6. **Múltiples recursos** por técnica.
7. **PWA**.
8. **Multi-academia**: tabla `academias` y `academia_id` en las entidades principales, con validación de pertenencia en cada consulta.

Las estadísticas registran actividad, no competencia técnica real.

---

## 14. Criterio de éxito del MVP

1. Un admin registra una clase en menos de 2 minutos.
2. Puede seleccionar varias técnicas existentes o crear una nueva.
3. Un alumno puede consultar y filtrar las clases anteriores.
4. Un alumno puede buscar una técnica y ver en qué clases apareció.
5. La interfaz funciona correctamente desde el móvil.
