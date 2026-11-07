# Imagen SOLO del bot, sin Lavalink. La usa docker-compose.yml (uso local), donde Lavalink
# va en su propio contenedor. Para Dokploy, Coolify o docker run usa el Dockerfile de la raíz.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 hexmusic \
    && mkdir -p /app/data \
    && chown -R hexmusic:hexmusic /app

USER hexmusic

CMD ["python", "-m", "hexmusic"]
