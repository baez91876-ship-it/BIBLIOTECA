# API de biblioteca

API REST con FastAPI, SQLAlchemy y PostgreSQL para administrar autores,
categorías, libros, socios, préstamos y reportes.

## Requisitos

- Python 3.13 o superior
- Node.js y npm
- PostgreSQL y una base de datos `LIBRERIA`
- Docker Desktop (opcional)

## Instalación local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con la URL PostgreSQL de la base `LIBRERIA`. La aplicación verifica
el nombre de la base y no permite conectarse a otro motor o base de datos.
Usa una base vacía con permisos para crear las tablas. Las tablas antiguas no
se migran ni se eliminan automáticamente.

Inicia la aplicación desde la raíz:

```powershell
npm run dev
```

El comando usa automáticamente el Python de `.venv` si existe; de lo contrario,
usa Python del `PATH`. No requiere `npm install`.

La interfaz está en <http://127.0.0.1:8000/>, Swagger en
<http://127.0.0.1:8000/docs> y ReDoc en <http://127.0.0.1:8000/redoc>.
La interfaz local permite administrar libros, autores, categorías, socios y
préstamos; los préstamos devueltos conservan su historial.

## Preparar GitHub Pages

La interfaz estática está organizada en `docs/` y puede publicarse desde
`main` / `/docs` en **Settings → Pages → Build and deployment
→ Deploy from a branch**. La API FastAPI y PostgreSQL no se ejecutan en Pages:
primero hay que desplegar la API y su base de datos en un servicio que admita
Python y PostgreSQL.

Antes de publicar, define la URL pública de esa API en `api-config.js`:

```js
window.BIBLIOTECA_API_URL = "https://URL-PUBLICA-DE-TU-API";
```

En el servicio de la API, configura `CORS_ALLOWED_ORIGINS` con el origen de
Pages (por ejemplo, `https://baez91876-ship-it.github.io`, sin la ruta del
repositorio) y vuelve a desplegarla. El valor vacío de ejemplo solo sirve para
uso local o cuando la interfaz y API comparten origen; `127.0.0.1` no es una
URL pública. Mientras la API pública no esté configurada, Pages muestra la
copia de solo lectura de `catalogo.json`. Actualiza ese archivo desde la API
local y súbelo de nuevo cuando quieras refrescar la copia pública. Para habilitar
altas, ediciones, eliminaciones y préstamos en vivo, configura una API pública.

## Pruebas

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest -v
```

La suite incluye los 24 casos de aceptación del taller, paginación y otras
validaciones de la API. Usa SQLite en memoria para que las pruebas no modifiquen
la base PostgreSQL.

## Docker Compose

Los archivos de Docker están agrupados en `docker/`. Crea la configuración local:

```powershell
Copy-Item docker\.env.docker.example docker\.env.docker
```

Cambia `POSTGRES_PASSWORD` y la contraseña en `DATABASE_URL` dentro de
`docker\.env.docker`. Luego ejecuta desde la raíz del proyecto:

```powershell
docker compose -f docker\docker-compose.yml up --build -d
docker compose -f docker\docker-compose.yml ps
```

La interfaz estará en <http://127.0.0.1:8001/> y Swagger en
<http://127.0.0.1:8001/docs>. El PostgreSQL de Docker escucha solo en
`localhost:5433`, independiente de cualquier PostgreSQL local en `5432`.
Docker conserva los datos en el volumen `libreria_libreria_data`.

```powershell
docker compose -f docker\docker-compose.yml logs -f api
docker compose -f docker\docker-compose.yml down
```

`docker compose -f docker\docker-compose.yml down -v` borra de forma permanente
la base de Docker y su volumen. `.env`, `docker\.env.docker`, `.venv` y los
cachés se excluyen de Git. No guardes credenciales reales en los ejemplos.

## Estructura

```text
app/
├── controllers/  # Consultas y reglas de negocio
├── core/         # Base de datos, dependencias y excepciones
├── models/       # Modelos SQLAlchemy
├── routes/       # Endpoints FastAPI
├── schemas/      # Validación y respuestas Pydantic
└── main.py       # Aplicación, routers y manejador de errores
docs/             # GitHub Pages: interfaz y catálogo estático
├── static/       # JavaScript y estilos del sitio
├── index.html
├── api-config.js
└── catalogo.json
docker/           # Dockerfile, Compose y ejemplos de entorno
test_main.py      # Pruebas de API e interfaz
```

## Recursos y endpoints

En la interfaz local, expande **Documentación interactiva de la API** bajo la
colección para abrir Swagger completo sin salir de la página. También puedes
visitar <http://127.0.0.1:8001/docs> en Docker.

Todos los listados usan `skip` (mínimo 0) y `limit` (1–100), salvo que se
indique `limite` en un reporte.

| Recurso | Endpoints |
|---|---|
| Autores | `GET/POST /autores`, `GET/PATCH/DELETE /autores/{id}`, `GET /autores/{id}/libros` |
| Categorías | `GET/POST /categorias`, `GET/PATCH/DELETE /categorias/{id}` |
| Libros | `GET/POST /libros`, `GET/PATCH/DELETE /libros/{id}` |
| Socios | `GET/POST /socios`, `GET/PATCH/DELETE /socios/{id}`, `GET /socios/{id}/prestamos` |
| Préstamos | `GET/POST /prestamos`, `GET/PATCH/DELETE /prestamos/{id}`, `POST /prestamos/{id}/devolucion` |
| Reportes | `GET /reportes/libros-mas-prestados`, `/categorias`, `/prestamos-vencidos`, `/socios-con-multas`, `/autores`, `/resumen` |

`GET /libros` acepta filtros combinables: `buscar`, `autor`, `categoria_id`,
`desde`, `hasta` y `orden=titulo|anio|-anio`. La respuesta de un libro incluye
autor y categorías anidados, además de `disponibles`, calculado como ejemplares
menos préstamos sin devolver.

## Reglas principales

- ISBN: exactamente 13 dígitos. Autores y categorías no admiten nombres repetidos.
- Un préstamo dura entre 1 y 30 días (14 por defecto); no puede registrarse en
  el futuro. Se rechaza si el socio está inactivo, tiene préstamos vencidos,
  tres préstamos sin devolver, ya pidió ese mismo libro o no hay ejemplares.
- El estado del préstamo se calcula como `activo`, `vencido` o `devuelto`.
- La multa por devolución tardía es de 0,50 por cada día de retraso.
- Un socio con préstamos devueltos se desactiva al eliminarse; uno con préstamos
  sin devolver no se puede eliminar. No se permite borrar autores con libros ni
  libros con préstamos asociados.
- Los préstamos abiertos permiten cambiar la fecha límite o eliminarlos. Los
  préstamos devueltos son inmutables para conservar el historial.
- Los controladores lanzan excepciones propias; un manejador global devuelve
  errores de aplicación como `{ "detail": "mensaje" }`.
