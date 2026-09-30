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
- **Crear y editar** clases, técnicas y turnos.

Cada clase guarda quién la registró (`creado_por`).

### Admin (`es_admin`)

Todo lo anterior, y además:

- **Borrar** clases y técnicas, y desactivar turnos (protege contra borrados accidentales).
- Gestionar usuarios: desactivar cuentas, resetear contraseñas y nombrar otros admins.

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

- Registro con nombre, email, contraseña y **código de invitación** (definido en `.env` y compartido con los compañeros). Evita que cualquiera con el enlace cree una cuenta.
- Login con email y contraseña → JWT.
- Permisos: usuario normal / admin.
- Sin recuperación de contraseña: si alguien la olvida, un admin se la resetea.

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

Formulario (cualquier usuario):

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
email            (único)
password_hash
cinturon         BLANCO | AZUL | MORADO | MARRON | NEGRO (opcional)
es_admin
activo
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

### Relaciones

```text
Usuario  1 ─── N Clases (creado_por)
Turno    1 ─── N Clases
Clase    N ─── N Técnicas
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
```

### Usuarios (admin)

```http
GET   /api/usuarios
PATCH /api/usuarios/{id}
```

### Turnos

```http
GET    /api/turnos
POST   /api/turnos
PUT    /api/turnos/{id}
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
POST   /api/clases
PUT    /api/clases/{id}
DELETE /api/clases/{id}     (admin)
```

Los filtros se resuelven en el backend, con paginación (`limit`, `offset`).

---

## 10. Seguridad mínima

- Contraseñas con hashing seguro (Argon2).
- JWT con expiración.
- Borrado y gestión de usuarios solo para admins.
- Registro protegido por código de invitación.
- Toda la configuración y los secretos en `.env` (nunca en el código ni en el repo).
- Validación de inputs (Pydantic).
- HTTPS en deployment.
- CORS restringido al dominio del frontend.

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

1. Un alumno registra una clase en menos de 2 minutos.
2. Puede seleccionar varias técnicas existentes o crear una nueva.
3. Un alumno puede consultar y filtrar las clases anteriores.
4. Un alumno puede buscar una técnica y ver en qué clases apareció.
5. La interfaz funciona correctamente desde el móvil.
