# API v2 de ERETZ para la beta cerrada (P21): FastAPI + snapshot SQLite en volumen.
#
# La imagen NO trae datos: la snapshot es estado privado y vive en el volumen
# persistente montado en /data (ver RUNBOOK.md). Sin snapshot activa, /healthz
# responde y /readyz da 503: el orquestador no manda trafico.
#
# Construir desde la RAIZ del repo:
#   docker build -f deploy/api-beta/Dockerfile -t eretz-api-beta .
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHON_DOTENV_DISABLED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ERETZ_BETA_DATA=/data \
    ERETZ_API_SNAPSHOT=/data/ERETZ_API_SNAPSHOT.sqlite3 \
    PORT=8080

WORKDIR /app

COPY deploy/api-beta/requirements.runtime.lock /app/requirements.runtime.lock
RUN python -m pip install --require-hashes -r /app/requirements.runtime.lock

# Solo lo que la API importa: el paquete api/ y la resolucion de rutas de datos.
COPY api/ /app/api/
COPY scripts/rutas_de_datos.py /app/scripts/rutas_de_datos.py
COPY deploy/api-beta/activar_snapshot.py /app/deploy/activar_snapshot.py

# Usuario sin privilegios. /data lo monta el orquestador; el entrypoint no
# escribe ahi salvo `activar_snapshot.py`, que se corre a mano por SSH.
RUN useradd --system --uid 10001 --home /app eretz \
    && mkdir -p /data && chown eretz:eretz /data
USER eretz

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8080'), timeout=4)"

# Un proceso: SQLite en solo lectura no gana con mas workers en una maquina de
# 1 vCPU compartida, y asi el consumo de memoria es predecible.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
