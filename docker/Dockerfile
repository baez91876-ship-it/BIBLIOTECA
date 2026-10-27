# Imagen ligera con la versión de Python usada por el proyecto.
FROM python:3.13-slim

# Evita bytecode en la imagen y envía los logs directamente al contenedor.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
# Instala la API y crea el usuario sin privilegios que ejecutará el servicio.
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser . .

# Ejecuta las migraciones versionadas y luego inicia la API como usuario dedicado.
USER appuser

EXPOSE 8000

# Comprueba que la API y su conexión de base de datos respondan.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"

# El paquete se normaliza al copiar desde un checkout Windows a la imagen Linux.
CMD ["sh", "-c", "if [ -d /app/app ]; then python -m app.scripts.migrate && exec uvicorn app.main:app --host 0.0.0.0 --port 8000; else python -m APP.scripts.migrate && exec uvicorn APP.main:app --host 0.0.0.0 --port 8000; fi"]
