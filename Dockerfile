# ─────────────────────────────────────────────────────────────────────────────
# ECCSA_Colaboradores — imagen de la app de fichas públicas (tarjeta NFC)
#
# Es la imagen más pequeña del ecosistema: la app es un servidor HTTP de la
# biblioteca estándar que consulta una tabla. Por eso NO hay build, ni npm, ni
# Stage de compilación — el Dockerfile entero cabe en una pantalla.
# ─────────────────────────────────────────────────────────────────────────────

# La imagen base sale del espejo pull-through de Google, no de Docker Hub ni de
# ECR Public. Los dos oficiales aplican cuotas por IP a los pulls anonimos:
#   · Docker Hub     -> 100 pulls / 6 h  (fallo el 2026-10-09, 10 veces seguidas)
#   · ECR Public     -> cuota de DATOS por IP ("Data limit exceeded", 2026-10-23)
# Los runners de GitHub comparten IP de salida, asi que la cuota la agota otro
# inquilino y el build falla aunque el repo no cambie: reintentar no sirve.
# mirror.gcr.io es el MISMO manifiesto (bit a bit) y no tiene esa cuota.
FROM mirror.gcr.io/library/python:3.11-slim

WORKDIR /app

# freetds-dev: pymssql (el paquete sin él no encuentra FreeTDS).
# fonts-dejavu-core: sin una fuente instalada, python:3.11-slim no dibuja nada
#   con Pillow y los emojis salen como píldoras vacías.
RUN apt-get update && apt-get install -y --no-install-recommends \
        freetds-dev \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENV PYTHONUNBUFFERED=1
ENV TZ=America/Mexico_City
ENV PORT=8000

# Puerto interno. El host lo mapea en /opt/apps/colaboradores/app.conf.
EXPOSE 8000

COPY . .

# El código se copia al build, no se monta: la imagen es la unidad de despliegue
# y así el contenedor vivo no puede quedar con archivos a medias.
RUN mkdir -p /data

CMD ["python3", "-m", "panel.server"]
