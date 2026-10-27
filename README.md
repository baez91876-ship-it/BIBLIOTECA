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

La página publicada está en
<https://baez91876-ship-it.github.io/BIBLIOTECA/>. El repositorio se llama
`BIBLIOTECA`; la URL anterior con `BIBBLIOTECA` ya no es válida.

La URL de la API y el origen CORS se configuran para Render en `docs/api-config.js`
y `render.yaml`. Sin un backend público disponible, Pages no puede crear ni
modificar registros; para actualizar su copia de solo lectura, exporta el
catálogo desde la API local y sube `docs/catalogo.json`.

## Desplegar API y habilitar altas en GitHub Pages

GitHub Pages solo publica la interfaz. El archivo `render.yaml` prepara la API
FastAPI y una base PostgreSQL gratuita en Render. Para desplegarlos, abre el
Dashboard de Render, selecciona **New → Blueprint**, conecta este repositorio y
confirma la creación de los recursos definidos por el Blueprint.

El servicio queda configurado para aceptar solicitudes del origen de GitHub
Pages y la interfaz apunta a
`https://biblioteca-api-baez91876-ship-it.onrender.com`. Si Render asigna otra
URL al servicio, actualiza `window.BIBLIOTECA_API_URL` en `docs/api-config.js`
con la URL que aparece en el Dashboard y sube ese cambio. GitHub Pages volverá a
publicar la interfaz automáticamente desde `main` / `/docs`.

El plan gratuito puede tardar alrededor de un minuto en despertar tras estar
inactivo, y su base PostgreSQL caduca a los 30 días. No uses ese plan para datos
que necesites conservar; antes de la caducidad, actualiza a una base de pago y
verifica la migración de los datos.

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
.
├── app/
│   ├── controllers/  # Consultas y reglas de negocio
│   ├── core/         # Base de datos, dependencias y excepciones
│   ├── models/       # Modelos y relaciones SQLAlchemy
│   ├── routes/       # Endpoints FastAPI
│   ├── schemas/      # Validación y respuestas Pydantic
│   └── main.py       # Aplicación, routers y recursos web
├── docs/             # GitHub Pages: interfaz y catálogo estático
│   ├── static/       # JavaScript y estilos
│   ├── api-config.js  # Configuración de la API para la interfaz
│   ├── catalogo.json  # Catálogo estático de respaldo
│   └── index.html     # Página principal
├── docker/           # Dockerfile, Compose y ejemplo de entorno
├── scripts/
│   └── dev.js        # Lanzador npm para Uvicorn
├── .env.example      # Plantilla de configuración local
├── package.json      # Comandos npm (sin dependencias Node)
├── requirements.txt  # Dependencias de ejecución Python
├── requirements-dev.txt
│                     # Dependencias para pruebas
├── test_main.py      # Pruebas API, interfaz y reglas de aceptación
└── README.md
```

## Recursos y endpoints

En la interfaz local, expande **Documentación interactiva de la API** bajo la
colección para abrir Swagger completo sin salir de la página. También puedes
visitar <http://127.0.0.1:8001/docs> en Docker.

Todos los listados usan `skip` (mínimo 0) y `limit` (1–100). El reporte de
libros más prestados conserva `limite` como alias obsoleto; usa `limit` para
nuevas integraciones.

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
