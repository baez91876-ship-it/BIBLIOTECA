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

Si la API no responde o todavía no se configura su URL, la interfaz muestra el
catálogo guardado en modo de solo lectura.

La URL de la API para GitHub Pages se configura en
[`docs/api-config.js`](./docs/api-config.js). Pages no conserva credenciales;
para operaciones de administración inicia sesión en la interfaz desplegada.

## Desplegar en FastAPI Cloud

FastAPI Cloud despliega aplicaciones FastAPI con el comando `fastapi deploy`.
La dependencia `fastapi[standard]` de `requirements.txt` ya incluye el CLI.
El punto de entrada está configurado en [`pyproject.toml`](./pyproject.toml) y
Python 3.13 en [`.python-version`](./.python-version). Instala los requisitos en
Windows y ejecuta el comando desde la raíz:

```powershell
$env:PYTHONUTF8 = "1"
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\fastapi.exe deploy
```

Inicia sesión o crea una cuenta cuando el CLI abra el navegador y sigue las
indicaciones para crear la aplicación. El primer despliegue crea el vínculo
local `.fastapicloud`. Si la aplicación informa que faltan variables al iniciar,
configúralas para esa aplicación antes de desplegar de nuevo. Puedes hacerlo
desde **App Details → Environment Variables** en el Dashboard o con el CLI:

```powershell
.venv\Scripts\fastapi.exe cloud env set --secret --no-redeploy DATABASE_URL
.venv\Scripts\fastapi.exe cloud env set --secret --no-redeploy JWT_SECRET_KEY
.venv\Scripts\fastapi.exe cloud env set --no-redeploy APP_ENV production
.venv\Scripts\fastapi.exe cloud env set --no-redeploy CORS_ALLOWED_ORIGINS https://baez91876-ship-it.github.io
```

El CLI solicita los valores secretos sin mostrarlos. Configura estas variables:

- `DATABASE_URL`: URL de PostgreSQL, con nombre de base `libreria`. FastAPI
  Cloud ofrece integraciones con Neon y Supabase; confirma que la conexión
  seleccionada use esa base.
- `JWT_SECRET_KEY`: clave aleatoria de al menos 32 caracteres.
- `APP_ENV`: `production`.
- `CORS_ALLOWED_ORIGINS`: `https://baez91876-ship-it.github.io`.

FastAPI Cloud aplica los cambios de variables en el siguiente despliegue. Antes
de desplegar de nuevo, aplica las migraciones a esa misma base. Copia la URL
`DATABASE_URL` en tu `.env` local ignorado por Git (sin reemplazar otros valores
locales) y ejecuta:

```powershell
.venv\Scripts\python.exe -m app.scripts.migrate
.venv\Scripts\python.exe -m app.scripts.crear_admin
.venv\Scripts\fastapi.exe deploy
```

El comando de alta solicita correo, nombre y contraseña sin mostrarla. No existe
una contraseña inicial ni una ruta pública para asignar roles privilegiados.
Después del despliegue, comprueba `/api/v1/health` y `/docs` en el dominio
`.fastapicloud.dev` asignado a la aplicación. Para habilitar el inicio de sesión
desde GitHub Pages, actualiza `window.BIBLIOTECA_API_URL` en
[`docs/api-config.js`](./docs/api-config.js) con ese dominio HTTPS y sube el
cambio. Si cambia el dominio, actualiza también `CORS_ALLOWED_ORIGINS` y vuelve
a desplegar.

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
├── .python-version   # Python 3.13 en FastAPI Cloud
├── pyproject.toml    # Dependencias y punto de entrada FastAPI Cloud
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
