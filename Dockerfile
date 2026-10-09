# ─────────────────────────────────────────────────────────────────────────────
# ECCSA_Colaboradores — imagen de la app de fichas públicas (tarjeta NFC)
#
# Es la imagen más pequeña del ecosistema: la app es un servidor HTTP de la
# biblioteca estándar que consulta una tabla. Por eso NO hay build, ni npm, ni
# Stage de compilación — el Dockerfile entero cabe en una pantalla.
# ─────────────────────────────────────────────────────────────────────────────

# La imagen base sale del espejo público de AWS ECR, no de Docker Hub directo.
# `public.ecr.aws/docker/library/*` es el MISMO oficial de Docker (bit a bit),
# pero ECR Public no aplica el límite de pulls anónimos que sí tiene Docker Hub.
# El 2026-10-09 la CI falló 10 veces seguidas con "429 Too Many Requests" al
# resolver python:3.11-slim; el runner compartido ya no puede bajar de Docker Hub.
FROM public.ecr.aws/docker/library/python:3.11-slim

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
