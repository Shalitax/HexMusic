# Imagen de Lavalink con la configuración de HexMusic ya incluida.
# Así Dokploy no necesita File Mounts ni bind mounts al repositorio.
FROM ghcr.io/lavalink-devs/lavalink:4.2.2-alpine

# La imagen base no crea /opt/Lavalink/plugins. Si se monta un volumen vacío
# en una ruta que no existe, Docker lo crea como root y Lavalink (UID 322)
# no puede descargar los plugins. La creamos con el propietario correcto para
# que el volumen herede esos permisos.
USER root
RUN mkdir -p /opt/Lavalink/plugins \
    && chown -R lavalink:lavalink /opt/Lavalink/plugins
USER lavalink

COPY --chown=lavalink:lavalink application.yml /opt/Lavalink/application.yml
