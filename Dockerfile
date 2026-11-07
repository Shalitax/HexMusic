# ╔══════════════════════════════════════════════════════════════╗
# ║      HexMusic "todo en uno": bot + Lavalink + yt-cipher       ║
# ╚══════════════════════════════════════════════════════════════╝
# Igual que el egg de Pterodactyl: un único contenedor arranca Lavalink en
# 127.0.0.1, el servidor de cifrado de YouTube y el bot. No depende de la red
# entre contenedores, así que funciona igual en Dokploy, Coolify o docker run.
#
#   docker build -t hexmusic .
#   docker run -d --name hexmusic -v hexmusic-data:/app/data -p 8080:8080 --env-file .env hexmusic
#
# Guía: docs/DOKPLOY.md

# ── Descargas (Lavalink, Deno y yt-cipher) ───────────────────────
FROM debian:bookworm-slim AS builder

# Versiones fijadas: las mismas que usa el egg de Pterodactyl.
ARG LAVALINK_VERSION=4.2.2
ARG DENO_VERSION=v2.9.6
ARG YT_CIPHER_COMMIT=1e1fd8e2f34ca90cf23545be72e46307bd3d3d2a
ARG YT_CIPHER_EJS_COMMIT=cd4e87f52e87ab6d8b318fd3a817adda6fafa8dc

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*

ENV DENO_DIR=/opt/deno-cache
WORKDIR /build

RUN set -eux; \
    mkdir -p /opt/lavalink "${DENO_DIR}"; \
    curl -fsSL --retry 3 -o /opt/lavalink/Lavalink.jar \
        "https://github.com/lavalink-devs/Lavalink/releases/download/${LAVALINK_VERSION}/Lavalink.jar"; \
    printf '%s' "${LAVALINK_VERSION}" > /opt/lavalink/VERSION; \
    case "$(uname -m)" in \
        x86_64|amd64) deno_arch=x86_64 ;; \
        aarch64|arm64) deno_arch=aarch64 ;; \
        *) echo "Arquitectura no soportada: $(uname -m)" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 3 -o deno.zip \
        "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-${deno_arch}-unknown-linux-gnu.zip"; \
    unzip -q deno.zip -d /usr/local/bin; \
    chmod +x /usr/local/bin/deno; \
    curl -fsSL --retry 3 -o yt-cipher.zip "https://github.com/kikkia/yt-cipher/archive/${YT_CIPHER_COMMIT}.zip"; \
    curl -fsSL --retry 3 -o ejs.zip "https://github.com/yt-dlp/ejs/archive/${YT_CIPHER_EJS_COMMIT}.zip"; \
    unzip -q yt-cipher.zip; \
    unzip -q ejs.zip; \
    mv "yt-cipher-${YT_CIPHER_COMMIT}" /opt/yt-cipher; \
    mv "ejs-${YT_CIPHER_EJS_COMMIT}" /opt/yt-cipher/ejs; \
    rm -rf /build/*

# ejs se publica para Node; el parche de yt-cipher lo adapta a Deno. Las
# dependencias se dejan en caché para no descargarlas en cada arranque (si
# algo falla aquí, Deno las descargará al arrancar).
RUN cd /opt/yt-cipher \
    && deno run --allow-read --allow-write scripts/patch-ejs.ts \
    && (deno cache server.ts || echo "Aviso: las dependencias de yt-cipher se descargarán al arrancar.")

# ── Java 21 (Lavalink necesita 17+) ──────────────────────────────
FROM eclipse-temurin:21-jre AS java

# ── Imagen final ─────────────────────────────────────────────────
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    JAVA_HOME=/opt/java/openjdk \
    PATH="/opt/java/openjdk/bin:${PATH}" \
    DENO_DIR=/opt/deno-cache

# tini reenvía la señal de parada al entrypoint y recoge procesos huérfanos.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 hexmusic

COPY --from=java /opt/java/openjdk /opt/java/openjdk
COPY --from=builder /usr/local/bin/deno /usr/local/bin/deno
COPY --from=builder --chown=hexmusic:hexmusic /opt/lavalink /opt/lavalink
COPY --from=builder --chown=hexmusic:hexmusic /opt/yt-cipher /opt/yt-cipher
COPY --from=builder --chown=hexmusic:hexmusic /opt/deno-cache /opt/deno-cache

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY --chown=hexmusic:hexmusic . .

# sed quita posibles finales de línea de Windows (CRLF) del script.
RUN sed -i 's/\r$//' docker/entrypoint.sh \
    && install -m 0755 docker/entrypoint.sh /usr/local/bin/hexmusic-entrypoint \
    && mkdir -p /app/data \
    && chown hexmusic:hexmusic /app/data

USER hexmusic

# Panel web (WEB_PORT). Lavalink, yt-cipher y la biblioteca solo escuchan en 127.0.0.1.
EXPOSE 8080

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/hexmusic-entrypoint"]
