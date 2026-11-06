# 🚀 Despliegue en Dokploy

Esta guía despliega **HexMusic + Lavalink** en [Dokploy](https://dokploy.com/) usando el servicio **Compose** y el archivo [`docker-compose.dokploy.yml`](../docker-compose.dokploy.yml).

> Para ejecutarlo en tu PC sigue la [instalación con Docker](INSTALACION.md#4-opción-a--docker-recomendada). El compose de Dokploy es distinto porque no publica puertos en el host y construye una imagen de Lavalink con su configuración incluida.

---

## 1. Requisitos

| Cosa | Detalle |
|---|---|
| Servidor | 2 GB de RAM mínimo (Lavalink usa ~1 GB) · Docker + Dokploy instalados |
| Dominio | Un subdominio, por ejemplo `musica.tudominio.com`, con un registro **A** apuntando a la IP del servidor |
| Repositorio | El proyecto subido a GitHub (`Shalitax/HexMusic`) |
| Discord | Token del bot y **Client Secret** de OAuth2 |

Crea el registro DNS **antes** de desplegar:

```
musica.tudominio.com  →  A  →  IP_DE_TU_SERVIDOR
```

> El certificado HTTPS se genera solo cuando el DNS ya resuelve a tu servidor.

---

## 2. Crear el servicio Compose

1. En Dokploy entra en tu proyecto → **Create Service** → **Compose**.
2. En **General**:
   - **Name**: `hexmusic`
   - **Compose Type**: `Docker Compose`
   - **Provider**: `GitHub` (autoriza Dokploy si es la primera vez)
   - **Repository**: `Shalitax/HexMusic`
   - **Branch**: `main`
   - **Compose Path**: `./docker-compose.dokploy.yml`
3. Pulsa **Save**.

> Si el repo es privado, conecta antes tu cuenta de GitHub en **Settings → Git Sources**.

---

## 3. Configuración de Lavalink (sin File Mount)

El compose de Dokploy construye una imagen derivada de Lavalink con [`lavalink/Dockerfile`](../lavalink/Dockerfile), que copia la configuración dentro de la imagen:

```dockerfile
FROM ghcr.io/lavalink-devs/lavalink:4.2.2-alpine
COPY application.yml /opt/Lavalink/application.yml
```

No hay que crear ningún File Mount: Dokploy clona el repo, construye esta imagen y `application.yml` viaja dentro. Si lo cambias, haz commit/push y vuelve a desplegar.

El compose también incluye un servicio `lavalink-init` que ajusta los permisos del volumen `lavalink-plugins` antes de arrancar Lavalink (corre como UID 322).

> Alternativa: si prefieres no construir nada, usa la imagen oficial `ghcr.io/lavalink-devs/lavalink:4.2.2-alpine` y crea un **File Mount** en `Advanced → Mounts` con `application.yml` en `/opt/Lavalink/application.yml`. Ese es el único caso en el que el mount sí es necesario.

---

## 4. Variables de entorno

Ve a la pestaña **Environment** y pega algo así (adaptado de [`.env.example`](../.env.example)):

```env
# Discord
DISCORD_TOKEN=tu_token
DEV_GUILD_ID=

# Lavalink
LAVALINK_PASSWORD=una_clave_larga_y_aleatoria
LAVALINK_MEMORY=1G

# Base de datos (volumen hexmusic-data)
DATABASE_PATH=data/hexmusic.db

# Catálogo regional
MUSIC_COUNTRY_CODE=CL

# Fuentes opcionales
SPOTIFY_ENABLED=false
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
APPLEMUSIC_ENABLED=false
YOUTUBE_OAUTH_ENABLED=false

# Panel web
WEB_ENABLED=true
WEB_PORT=8080
WEB_PUBLIC_URL=https://musica.tudominio.com
WEB_CLIENT_SECRET=el_client_secret_de_discord
```

Notas:

- `LAVALINK_URI` no hace falta: el compose fuerza `http://lavalink:2333`.
- Mantén `WEB_PORT=8080` y usa ese mismo puerto al crear el dominio.
- `WEB_PUBLIC_URL` debe ser **exactamente** la URL pública, sin barra final.
- Los secretos quedan guardados por Dokploy y se escriben en un `.env` junto al compose.

---

## 5. Dominio y HTTPS

1. Pulsa **Deploy**. La primera vez tarda unos minutos (compila el bot y Lavalink descarga sus plugins).
2. Cuando termine, ve a la pestaña **Domains** → **Add Domain**:
   - **Service**: `bot`
   - **Host**: `musica.tudominio.com`
   - **Port**: `8080`
   - **HTTPS**: activado
   - **Certificate Provider**: `Let's Encrypt`
3. Guarda y espera unos segundos a que Traefik emita el certificado.
4. Abre `https://musica.tudominio.com`. Debe aparecer el panel de HexMusic.

> El compose ya conecta el servicio `bot` a `dokploy-network`, que es la red que usa Traefik. Si tu instalación tiene activado **Isolated Deployments**, Dokploy gestiona la red automáticamente y esta conexión no molesta.

---

## 6. Configurar Discord

### OAuth2 del panel

1. Entra en <https://discord.com/developers/applications> → tu aplicación → **OAuth2**.
2. Copia el **Client Secret** (o pulsa *Reset Secret*) y pégalo en `WEB_CLIENT_SECRET`.
3. En **Redirects** añade exactamente:

```
https://musica.tudominio.com/auth/callback
```

4. Guarda los cambios y vuelve a desplegar si cambiaste el Client Secret.

### Invitar el bot

Abre esta URL cambiando `TU_APPLICATION_ID`:

```
https://discord.com/oauth2/authorize?client_id=TU_APPLICATION_ID&scope=bot+applications.commands&permissions=3533904
```

Recuerda activar **Message Content Intent** en la pestaña **Bot** del portal de Discord si quieres los comandos con prefijo (`hm!play`) y el canal de peticiones.

---

## 7. Comprobar el despliegue

En Dokploy abre **Logs**:

- `lavalink`: espera `Lavalink is ready to accept connections.`
- `bot`: espera `Nodo Lavalink 'main' listo` y `Panel web disponible en ...`

Luego, en Discord, entra en un canal de voz y usa `/play never gonna give you up`.

---

## 8. Datos y copias de seguridad

| Dato | Dónde vive |
|---|---|
| Base de datos, sesiones del panel, playlists, biblioteca y token de YouTube | Volumen `hexmusic-data` (`/app/data`) |
| Plugins descargados de Lavalink | Volumen `lavalink-plugins` |

- Los volúmenes se conservan entre despliegues. **No** uses la opción de desplegar con volúmenes limpios (`--volumes`) salvo que quieras borrar todo.
- Puedes configurar **Volume Backups** de Dokploy sobre `hexmusic-data` para copiarlo a S3.

---

## 9. Actualizar

- **Código, `config.yml`, `locales/` o dependencias**: haz commit y push; con **Auto Deploy** activado (pestaña General) Dokploy vuelve a construir la imagen. El bot incluye esos archivos dentro de la imagen, no se montan desde el repo.
- **`lavalink/application.yml`**: actualízalo en el repo y vuelve a desplegar; se reconstruye la imagen de Lavalink.
- **Solo variables de entorno**: cambia lo necesario en **Environment** y pulsa **Deploy**.

---

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| Lavalink arranca sin plugins o con la configuración por defecto | Revisa que el build use `lavalink/Dockerfile` y que `application.yml` esté en esa carpeta; luego vuelve a desplegar. |
| El panel dice `El servidor de audio (Lavalink) no está disponible` | El bot no tiene ningún nodo conectado. En los logs de `lavalink` debe aparecer `Lavalink is ready to accept connections.`; en los del `bot`, `Nodo Lavalink 'main' listo`. Si Lavalink reinicia, mira el error justo antes (plugins, permisos o memoria). |
| Lavalink no arranca o no descarga plugins | El volumen `lavalink-plugins` debe ser escribible por UID 322. El compose incluye `lavalink-init` para ajustarlo en cada despliegue. Si el volumen se creó antes con permisos de root, pára el servicio, bórralo con `docker volume rm <proyecto>_lavalink-plugins` y vuelve a desplegar (los plugins se descargan otra vez). |
| El panel da 502/504 | Revisa que el dominio apunte al servicio `bot`, puerto `8080`, y que `WEB_ENABLED=true`. |
| `Invalid OAuth2 redirect_uri` / `redirect_uri de OAuth2 no válido` | Discord no tiene registrada la URL exacta. Mira en los logs del bot al arrancar `Panel web disponible en https://...`; el redirect que hay que registrar es esa URL + `/auth/callback`. Añádelo en Discord → OAuth2 → Redirects y guarda. Debe coincidir en `https`, dominio, `www`, puerto y sin barra final. Si cambias `WEB_PUBLIC_URL`, reinicia/redeploya el bot. |
| `Discord rechazó la configuración del panel (Client Secret o Redirect)` | El redirect ya funciona, pero falla el intercambio de token. En los logs busca `Discord API POST /oauth2/token → ...`: `401 invalid_client` = `WEB_CLIENT_SECRET` incorrecto, de otra aplicación o sin redesplegar; `400 invalid_grant` = código/redirect caducado o distinto, vuelve a iniciar sesión desde el panel. |
| El bot no conecta con Lavalink | Revisa que `LAVALINK_PASSWORD` sea la misma para ambos servicios y que no hayas cambiado `LAVALINK_URI`. |
| Sin memoria / reinicios | Sube `LAVALINK_MEMORY` solo si el servidor tiene RAM libre; con 2 GB deja `1G`. |
| El panel funciona por HTTP pero no por HTTPS | `WEB_PUBLIC_URL` debe empezar por `https://`; así las cookies se marcan como seguras y Traefik reenvía el protocolo correcto. |

---

## Alternativa: usar el compose local

Si prefieres desplegar [`docker-compose.yml`](../docker-compose.yml) tal cual:

- Publica el puerto `8080` en el host, así que no uses dominio de Dokploy o cambia el mapeo a `127.0.0.1:8080:8080`.
- Vuelve a poner los mounts `./config.yml`, `./locales` y `./lavalink/application.yml`; en cada redespliegue Dokploy puede dejar esos mounts vacíos por el re-clonado del repo.
- Elimina `container_name` y añade el servicio `bot` a `dokploy-network` para que Dokploy gestione bien logs, métricas y dominios.

Por eso se recomienda `docker-compose.dokploy.yml`.

---

## Alternativa: Nixpacks (bot) + Lavalink aparte

Nixpacks construye **una sola aplicación**: el bot. Lavalink es Java y tiene que ir en un segundo servicio. Si ya tienes un Lavalink funcionando, puedes desplegar solo el bot.

> Si vienes del compose, **páralo primero** (`Stop`) para no tener dos bots conectados con el mismo token.

### 1. Lavalink (Application)

1. **Create Service → Application**.
2. Provider `GitHub`, repo `Shalitax/HexMusic`, rama `main`.
3. **Build Type**: `Dockerfile`.
   - **Dockerfile Path**: `./lavalink/Dockerfile`
   - **Docker Context Path**: `./lavalink`
4. **Environment**:

   ```env
   JAVA_TOOL_OPTIONS=-Xmx1G
   LAVALINK_PASSWORD=la_misma_que_en_el_bot
   MUSIC_COUNTRY_CODE=CL
   ```

   Añade también las credenciales de las fuentes que uses (`SPOTIFY_*`, `DEEZER_*`, etc.) y `YOUTUBE_OAUTH_ENABLED=true` si usas cuenta de YouTube.

5. **Advanced → Volumes**: volumen `lavalink-plugins` en `/opt/Lavalink/plugins`.
6. **Sin dominio** y sin publicar el puerto `2333`: se usa por la red interna.
7. Anota el **App Name** de la aplicación (General). Ese es el hostname interno que usará el bot.

### 2. Bot (Application)

1. **Create Service → Application**.
2. Provider `GitHub`, repo `Shalitax/HexMusic`, rama `main`.
3. **Build Type**: `Nixpacks`.
4. **Environment**:

   ```env
   NIXPACKS_PYTHON_VERSION=3.12
   NIXPACKS_START_CMD=python -m hexmusic

   DISCORD_TOKEN=...
   LAVALINK_URI=http://<app-name-lavalink>:2333
   LAVALINK_PASSWORD=la_misma_que_en_lavalink

   WEB_ENABLED=true
   WEB_PORT=8080
   WEB_PUBLIC_URL=https://musica.tudominio.com
   WEB_CLIENT_SECRET=...

   LIBRARY_HOST=0.0.0.0
   LIBRARY_PUBLIC_URL=http://<app-name-bot>:2340
   DATABASE_PATH=data/hexmusic.db
   ```

   Sustituye `<app-name-lavalink>` y `<app-name-bot>` por los **App Name** exactos que muestra Dokploy. No uses `localhost` ni `127.0.0.1`: dentro del contenedor apuntan al propio bot.

5. **Advanced → Volumes**: volumen `hexmusic-data` en `/app/data`.
6. **Domains**: host `musica.tudominio.com`, puerto `8080`, HTTPS.
7. **Deploy**.

### 3. Red

Ambas Applications deben estar en la misma red (`dokploy-network`; Dokploy las conecta por defecto, revísalo en **Networks**). Sin eso, el bot no resolverá el nombre de Lavalink.

### Notas

- `config.yml` y `locales/` van dentro del build de Nixpacks: cámbialos en el repo y vuelve a desplegar.
- `/upload` necesita que Lavalink alcance `LIBRARY_PUBLIC_URL`; por eso se usa el nombre interno del bot y no se publica el puerto `2340`.
- El bot debe tener `discord.py[voice]` en `requirements.txt` para que se instalen `PyNaCl` y `davey`; sin ellos Discord no permite entrar en voz.
- Si solo quieres el bot con un Lavalink externo, omite el paso 1 y apunta `LAVALINK_URI` a ese servidor (con su IP o dominio y el puerto `2333`).
