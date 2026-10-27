# API de biblioteca

API REST de biblioteca con FastAPI, SQLAlchemy, PostgreSQL, Alembic y JWT.
La rama `version-2` incorpora autenticación y permisos; conserva la API del
Taller 1 en rutas legacy solo para desarrollo.

## Requisitos

- Python 3.13 o superior
- Node.js y npm
- PostgreSQL y una base de datos `libreria`

## Instalación local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con la URL PostgreSQL de la base `libreria`. La aplicación verifica
el nombre de la base y no permite conectarse a otro motor o base de datos.
`JWT_SECRET_KEY` debe contener al menos 32 caracteres aleatorios; el valor de
ejemplo solo es válido para desarrollo. Las tablas se crean y actualizan con
migraciones versionadas, nunca con `create_all`.

Para una base nueva, inicia desde la raíz:

```powershell
npm run dev
```

El comando ejecuta `python -m app.scripts.migrate` antes de iniciar Uvicorn y usa
automáticamente el Python de `.venv` si existe; de lo contrario, usa Python del
`PATH`. No requiere `npm install`.

Si conectarás una base existente del Taller 1 que todavía no tiene historial
Alembic, el lanzador reconoce el esquema completo y marca el baseline sin
modificar sus datos. Si prefieres hacerlo manualmente, marca la revisión
correspondiente antes de iniciar:

```powershell
.venv\Scripts\python.exe -m alembic stamp 0001_estado_inicial
.venv\Scripts\python.exe -m alembic upgrade head
```

`npm run dev` requiere una base creada y accesible en PostgreSQL. Las migraciones
no borran ni recrean los datos de las tablas existentes.

La interfaz está en <http://127.0.0.1:8000/>, Swagger en
<http://127.0.0.1:8000/docs> y ReDoc en <http://127.0.0.1:8000/redoc>.
La interfaz pública permite consultar el catálogo. Inicia sesión con un usuario
bibliotecario o administrador para gestionar el catálogo y las operaciones
internas. El acceso dura 15 minutos y la interfaz rota el refresh token; al
cerrar sesión revoca ese token.

## Preparar GitHub Pages

La interfaz estática está organizada en `docs/` y puede publicarse desde
`main` / `/docs` en **Settings → Pages → Build and deployment
→ Deploy from a branch**. La API FastAPI y PostgreSQL no se ejecutan en Pages:
primero hay que desplegar la API y su base de datos en un servicio que admita
Python y PostgreSQL.

La página publicada está en
<https://baez91876-ship-it.github.io/BIBLIOTECA/>. El repositorio se llama
`BIBLIOTECA`; la URL anterior con `BIBBLIOTECA` ya no es válida.

Si la API no responde, la interfaz muestra el catálogo guardado en modo de solo
lectura. Para recuperar el inicio de sesión y la gestión de datos, la API de
Render debe estar disponible.

La URL de la API y el origen CORS se configuran para Render en
[`docs/api-config.js`](./docs/api-config.js) y [`render.yaml`](./render.yaml).
Pages no conserva credenciales; para operaciones de administración inicia sesión
en la interfaz desplegada.

## Desplegar API y habilitar altas en GitHub Pages

GitHub Pages solo publica la interfaz. El archivo `render.yaml` prepara la API
FastAPI y una base PostgreSQL gratuita en Render. El despliegue aplica Alembic
antes de arrancar la API y genera una clave JWT de producción. Para desplegarlos, abre el
Dashboard de Render, selecciona **New → Blueprint**, conecta este repositorio y
confirma la creación de los recursos definidos por el Blueprint.

El servicio queda configurado para aceptar solicitudes del origen de GitHub
Pages y la interfaz apunta a
`https://biblioteca-api-baez91876-ship-it.onrender.com`. Si Render asigna otra
URL al servicio, actualiza `window.BIBLIOTECA_API_URL` en `docs/api-config.js`
con la URL que aparece en el Dashboard y sube ese cambio. GitHub Pages volverá a
publicar la interfaz automáticamente desde `main` / `/docs`.

Si los logs de Render muestran `ValidationError` para `Settings` y el campo
`database_url` como obligatorio, Render no entregó la variable requerida y la
API no puede iniciar sin una base de datos configurada. Crea o sincroniza los
recursos desde **New → Blueprint** usando este repositorio y la rama que
contiene `render.yaml`; el Blueprint conecta `DATABASE_URL` con la cadena de
conexión de `biblioteca-postgres`. Si el servicio web se creó manualmente,
abre **Environment**, agrega exactamente la variable `DATABASE_URL` con la URL
interna de PostgreSQL y confirma que la base se llame `libreria`. El archivo
`render.yaml` no agrega variables a un servicio independiente hasta que sus
recursos se administren con el Blueprint. No guardes la URL ni sus credenciales
en Git. Guarda los cambios, vuelve a desplegar y verifica
`/api/v1/health`.

Después del primer despliegue, crea el primer administrador desde la consola
del servicio con `python -m app.scripts.crear_admin`. El comando solicita correo,
nombre y contraseña sin mostrarla en pantalla; no existe una contraseña inicial
ni una ruta pública para asignar roles privilegiados.

El plan gratuito puede tardar alrededor de un minuto en despertar tras estar
inactivo, y su base PostgreSQL caduca a los 30 días. No uses ese plan para datos
que necesites conservar; antes de la caducidad, actualiza a una base de pago y
verifica la migración de los datos.

## Pruebas

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest --cov=app --cov-report=term-missing
```

La suite incluye los 24 casos de aceptación del Taller 1, autenticación,
bloqueo, rotación y reuso de refresh tokens, RBAC, propiedad, rate limiting,
paginación y request ID. Usa SQLite en memoria para no modificar PostgreSQL; la
cobertura comprobada supera el 70%.

## Estructura

```text
.
├── app/
│   ├── controllers/  # Consultas y reglas de negocio
│   ├── core/         # Base de datos, dependencias y excepciones
│   ├── models/       # Modelos y relaciones SQLAlchemy
│   ├── routes/       # Endpoints FastAPI
│   ├── schemas/      # Validación y respuestas Pydantic
│   ├── scripts/      # Migración de arranque y alta inicial de admin
│   └── main.py       # Aplicación, routers y recursos web
├── alembic/
│   └── versions/     # Estado inicial, multa_pagada y tablas de identidad
├── docs/             # GitHub Pages: interfaz y catálogo estático
│   ├── static/       # JavaScript y estilos
│   ├── api-config.js  # Configuración de la API para la interfaz
│   ├── catalogo.json  # Catálogo estático de respaldo
│   └── index.html     # Página principal
├── scripts/
│   └── dev.js        # Lanzador npm para Uvicorn
├── .env.example      # Plantilla de configuración local
├── package.json      # Comandos npm (sin dependencias Node)
├── requirements.txt  # Dependencias de ejecución Python
├── requirements-dev.txt
│                     # Dependencias para pruebas
├── test_main.py      # Pruebas API, interfaz y reglas de aceptación
├── test_auth.py      # Pruebas de autenticación y permisos V2
└── README.md
```

## Recursos y endpoints

En la interfaz local, expande **Documentación interactiva de la API** bajo la
colección para abrir Swagger completo sin salir de la página. También puedes
visitar <http://127.0.0.1:8000/docs>.

Todos los listados usan `skip` (mínimo 0) y `limit` (1–100). El reporte de
libros más prestados conserva `limite` como alias obsoleto; usa `limit` para
nuevas integraciones.

| Recurso | Endpoints |
|---|---|
| Autores | `GET/POST /api/v1/autores`, `GET/PATCH/DELETE /api/v1/autores/{id}`, `GET /api/v1/autores/{id}/libros` |
| Categorías | `GET/POST /api/v1/categorias`, `GET/PATCH/DELETE /api/v1/categorias/{id}` |
| Libros | `GET/POST /api/v1/libros`, `GET/PATCH/DELETE /api/v1/libros/{id}` |
| Socios | `GET/POST /api/v1/socios`, `GET/PATCH/DELETE /api/v1/socios/{id}`, `GET /api/v1/socios/{id}/prestamos` |
| Préstamos | `GET/POST /api/v1/prestamos`, `GET/PATCH/DELETE /api/v1/prestamos/{id}`, `POST /api/v1/prestamos/{id}/devolucion` |
| Reportes | `GET /api/v1/reportes/libros-mas-prestados`, `/categorias`, `/prestamos-vencidos`, `/socios-con-multas`, `/autores`, `/resumen` |

Autenticación: `POST /api/v1/auth/registro`, `POST /api/v1/auth/login`,
`POST /api/v1/auth/refresh`, `POST /api/v1/auth/logout`,
`POST /api/v1/auth/bibliotecarios` (solo administrador) y
`GET /api/v1/auth/me`. Login usa OAuth2 form (`username` = correo). Los
listados V2 responden `{ items, total, skip, limit }`; los reportes calculan el
total dentro de la misma consulta SQL. `GET` de autores, categorías y libros es
público; las escrituras y reportes requieren bibliotecario o administrador.
Los socios solo ven sus propios datos y préstamos, y solo pueden solicitar
préstamos para su cuenta. Las rutas legacy sin `/api/v1` solo están disponibles
con `APP_ENV=development`.

`GET /api/v1/libros` acepta filtros combinables: `buscar`, `autor`, `categoria_id`,
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
