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

# Ejecuta la aplicación como usuario dedicado y expone el puerto de API.
USER appuser

EXPOSE 8000

# Comprueba la salud de la API local antes de marcar el contenedor disponible.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

# El nombre del paquete cambia de mayúsculas según el checkout en Windows.
CMD ["sh", "-c", "if [ -d /app/app ]; then exec uvicorn app.main:app --host 0.0.0.0 --port 8000; else exec uvicorn APP.main:app --host 0.0.0.0 --port 8000; fi"]
