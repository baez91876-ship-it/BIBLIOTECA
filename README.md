# API de biblioteca

API REST de biblioteca con FastAPI, SQLAlchemy, PostgreSQL, Alembic y JWT.
La rama `version-2` incorpora autenticación y permisos; conserva la API del
Taller 1 en rutas legacy solo para desarrollo.

## Requisitos

- Python 3.13
- Node.js y npm
- PostgreSQL y una base de datos para la biblioteca

## Instalación local

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con la URL PostgreSQL de la base de datos. Se admiten nombres
asignados por proveedores como Render. La aplicación solo admite PostgreSQL y
los endpoints de salud verifican el nombre exacto indicado en `DATABASE_URL`.
En conexiones externas usa `sslmode=require` para cifrar el tráfico.
`JWT_SECRET_KEY` debe contener al menos 32 caracteres aleatorios; el valor de
ejemplo solo es válido para desarrollo. Las tablas se crean y actualizan con
migraciones versionadas, nunca con `create_all`.

Para una base nueva, inicia desde la raíz:

```powershell
npm run dev
```

El comando ejecuta `python -m backend.app.scripts.migrate` antes de iniciar Uvicorn y usa
automáticamente el Python de `.venv` si existe; de lo contrario, usa Python del
`PATH`. No requiere `npm install`.

Si conectarás una base existente del Taller 1 que todavía no tiene historial
Alembic, el lanzador reconoce el esquema completo y marca el baseline sin
modificar sus datos. Si prefieres hacerlo manualmente, marca la revisión
correspondiente antes de iniciar:

```powershell
.venv\Scripts\python.exe -m alembic -c database\alembic.ini stamp 0001_estado_inicial
.venv\Scripts\python.exe -m alembic -c database\alembic.ini upgrade head
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

La interfaz estática está organizada en `frontend/` y se publica en cada cambio a
`main` con [`.github/workflows/pages.yml`](./.github/workflows/pages.yml). En
**Settings → Pages → Build and deployment**, selecciona **GitHub Actions** como
fuente. La API FastAPI y PostgreSQL no se ejecutan en Pages: la API se despliega
por separado en Render.

La página publicada está en
<https://baez91876-ship-it.github.io/BIBLIOTECA/>. El repositorio se llama
`BIBLIOTECA`; la URL anterior con `BIBBLIOTECA` ya no es válida.

Si la API no responde o todavía no se configura su URL, la interfaz muestra el
catálogo guardado en modo de solo lectura.

La URL de la API para GitHub Pages se configura en
[`frontend/api-config.js`](./frontend/api-config.js). Pages no conserva credenciales;
para operaciones de administración inicia sesión en la interfaz desplegada.

## Desplegar en Render

El archivo local `.env` no se sube a GitHub ni se copia a Render. Si aparece
`ValidationError: ... Settings`, revisa el campo que indica el log:
`database_url` con `Field required` significa que falta `DATABASE_URL`;
`jwt_secret_key` o el mensaje de clave aleatoria indica una clave ausente,
corta o de ejemplo. No publiques los valores de esas variables en los logs.

### Con Blueprint

En Render selecciona **New → Blueprint**, conecta este repositorio y elige
la rama `version-2`. El archivo [`render.yaml`](./render.yaml) configura el
servicio sin crear otra base de datos. Cuando Render solicite `DATABASE_URL`,
pega la URL de la base PostgreSQL existente desde su panel **Connect**.
El Blueprint genera `JWT_SECRET_KEY` y configura `APP_ENV=production`.

### Si el Web Service ya existe

Los cambios del Blueprint no se aplican automáticamente a un servicio creado
manualmente. En **Settings** configura:

- **Branch:** `version-2`.
- **Root Directory:** vacío (raíz del repositorio).
- **Build Command:** `python -m pip install -r requirements.txt`.
- **Start Command:** `python -m backend.app.scripts.migrate && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`.
- **Health Check Path:** `/api/v1/health`.

En **Environment** agrega:

| Variable | Valor |
|---|---|
| `DATABASE_URL` | URL PostgreSQL de Render, sin comillas envolventes |
| `JWT_SECRET_KEY` | Clave aleatoria propia de al menos 32 caracteres |
| `APP_ENV` | `production` |
| `CORS_ALLOWED_ORIGINS` | `https://baez91876-ship-it.github.io` si usas GitHub Pages |

Puedes generar la clave localmente con
`python -c "import secrets; print(secrets.token_urlsafe(48))"` y guardarla solo
en **Environment**. Conserva la misma clave entre despliegues. Usa la URL interna
si el servicio y la base están en la misma región de Render; para acceso externo,
usa la URL externa con `sslmode=require`. Se admiten los prefijos `postgres://`,
`postgresql://` y `postgresql+psycopg://`.

Guarda y selecciona **Manual Deploy → Deploy latest commit** después de subir
estos cambios. El arranque aplica las migraciones antes de abrir el puerto y
se detiene si fallan; no borra tablas ni importa datos.
Comprueba `https://TU-SERVICIO.onrender.com/api/v1/health` y la página `/`.
Para servir también la interfaz, no necesitas otro servicio ni cambiar
[`frontend/api-config.js`](./frontend/api-config.js): la interfaz usa la API
del mismo origen.

Para crear el primer administrador, desde la raíz y con `DATABASE_URL`
configurada en el entorno local, ejecuta:

```powershell
.venv\Scripts\python.exe -m backend.app.scripts.crear_admin
```

El comando de alta solicita correo, nombre y contraseña sin mostrarla. No existe
una contraseña inicial ni una ruta pública para asignar roles privilegiados.
Para habilitar el inicio de sesión desde GitHub Pages, actualiza
`window.BIBLIOTECA_API_URL` en
[`frontend/api-config.js`](./frontend/api-config.js) con ese dominio HTTPS y sube el
cambio. Si cambia el dominio, actualiza también `CORS_ALLOWED_ORIGINS` y vuelve
a desplegar.

## Pruebas

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m playwright install chromium
.venv\Scripts\python.exe -m pytest --cov=backend.app --cov-branch --cov-report=term-missing
npm run check
```

La suite incluye los 24 casos de aceptación del Taller 1, flujos CRUD V2,
autenticación, bloqueo, rotación y reuso de refresh tokens, permisos, paginación,
reportes, scripts de administración y manejo de errores. Las pruebas de API usan
SQLite en memoria para no modificar PostgreSQL.

[`frontend/tests/test_ui.py`](./frontend/tests/test_ui.py) ejecuta Chromium contra un servidor FastAPI real
con SQLite temporal y un puerto libre; cierra el navegador y el servidor al
terminar. Comprueba catálogo, búsqueda, paginación de más de 100 libros, registro,
permisos, inicio y cierre de sesión, rotación y caducidad de tokens, CRUD de
libros/autores/categorías/socios, préstamos y devoluciones, errores HTTP y de red,
catálogo de respaldo, Swagger y diseños de 320, 390, 768, 1024, 1440 y 1920 píxeles.
Las comprobaciones visuales exigen textos de al menos 14 px, campos de 16 px,
controles de al menos 44 × 44 px, foco de teclado visible y texto ampliable al
200 %, sin desbordar la página; las tablas anchas se desplazan dentro de su panel.
También verifica que vaciar campos opcionales al editar elimine sus valores. No requiere
credenciales reales ni modifica los datos de PostgreSQL.

Para ejecutar solo el navegador:

```powershell
.venv\Scripts\python.exe -m pytest frontend\tests -q
```

`npm run check` comprueba la sintaxis de los scripts JavaScript sin instalar
dependencias Node. El informe de cobertura muestra sentencias y ramas sin cubrir;
las pruebas locales no sustituyen una validación de despliegue contra PostgreSQL
ni una comprobación de la URL pública.

## Estructura

```text
.
├── frontend/         # Interfaz y publicación de GitHub Pages
│   ├── static/       # JavaScript y estilos
│   ├── tests/        # Pruebas de navegador Chromium
│   ├── api-config.js # Configuración de la API para la interfaz
│   ├── catalogo.json # Catálogo estático de respaldo
│   └── index.html    # Página principal
├── backend/
│   ├── app/
│   │   ├── controllers/ # Consultas y reglas de negocio
│   │   ├── core/        # Conexión, dependencias y excepciones
│   │   ├── models/      # Modelos y relaciones SQLAlchemy
│   │   ├── routes/      # Endpoints FastAPI
│   │   ├── schemas/     # Validación y respuestas Pydantic
│   │   ├── scripts/     # Migración de arranque y alta inicial de admin
│   │   └── main.py      # Aplicación, routers y recursos web
│   ├── tests/           # Pruebas API y reglas de negocio
│   ├── requirements.txt
│   └── requirements-dev.txt
├── database/
│   ├── alembic/
│   │   └── versions/ # Migraciones versionadas de PostgreSQL
│   └── alembic.ini   # Configuración de migraciones
├── scripts/
│   └── dev.js        # Lanzador npm para Uvicorn
├── .env.example      # Plantilla de configuración local
├── .python-version   # Versión de Python para Render
├── pyproject.toml    # Dependencias y configuración de pruebas
├── package.json      # Comandos npm (sin dependencias Node)
├── requirements.txt  # Referencia a backend/requirements.txt para despliegues
└── README.md
```

Ejecuta los comandos de instalación, inicio y pruebas desde la raíz. El punto
de entrada de la API es `backend.app.main:app`. La configuración compartida
(`.env`, `pyproject.toml` y `package.json`) permanece en la raíz.
Los modelos ORM siguen dentro del backend; `database/` contiene el historial
del esquema, no los datos de PostgreSQL. Reorganizar las carpetas no mueve ni
borra la base de datos.

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
