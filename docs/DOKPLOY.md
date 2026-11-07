# 🚀 Despliegue en Dokploy

Esta guía despliega HexMusic en [Dokploy](https://dokploy.com/) con el servicio **Compose** y el archivo [`docker-compose.dokploy.yml`](../docker-compose.dokploy.yml).

El despliegue funciona igual que el egg de Pterodactyl: **un único contenedor** ([`Dockerfile`](../Dockerfile), en la raíz) incluye el bot, Lavalink y el cifrado de YouTube (yt-cipher). Lavalink escucha en `127.0.0.1` dentro del contenedor, así que no depende de nombres de servicio ni de redes entre contenedores.

> Para ejecutarlo en tu PC sigue la [instalación con Docker](INSTALACION.md#4-opción-a--docker-recomendada).

---

## 1. Requisitos

| Cosa | Detalle |
|---|---|
| Servidor | 2 GB de RAM recomendados (Lavalink usa ~1 GB) · Docker + Dokploy instalados · x86_64 o ARM64 |
| Dominio | Un subdominio, por ejemplo `musica.tudominio.com`, con un registro **A** apuntando a la IP del servidor |
| Repositorio | El proyecto subido a GitHub (`Shalitax/HexMusic`) |
| Discord | Token del bot y **Client Secret** de OAuth2 |

Crea el registro DNS **antes** de desplegar: el certificado HTTPS solo se genera cuando el dominio ya resuelve a tu servidor.

---

## 2. Crear el servicio Compose

1. En Dokploy entra en tu proyecto → **Create Service** → **Compose**.
2. En **General**:
   - **Compose Type**: `Docker Compose`
   - **Provider**: `GitHub` · **Repository**: `Shalitax/HexMusic` · **Branch**: `main`
   - **Compose Path**: `./docker-compose.dokploy.yml`
3. Pulsa **Save**.

> Si el repo es privado, conecta antes tu cuenta de GitHub en **Settings → Git Sources**.

---

## 3. Variables de entorno

En la pestaña **Environment** pega algo así:

```env
# Discord
DISCORD_TOKEN=tu_token
DEV_GUILD_ID=

# Lavalink (interno). Contraseña vacía = se genera y se guarda sola.
LAVALINK_PASSWORD=
LAVALINK_MEMORY=auto

# Catálogo regional
MUSIC_COUNTRY_CODE=CL

# Fuentes opcionales (si activas una sin credenciales, se desactiva con aviso)
SPOTIFY_ENABLED=false
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
YOUTUBE_OAUTH_ENABLED=false

# Panel web
WEB_ENABLED=true
WEB_PUBLIC_URL=https://musica.tudominio.com
WEB_CLIENT_SECRET=el_client_secret_de_discord
```

- **No pongas** `LAVALINK_URI` ni `LIBRARY_PUBLIC_URL`: con Lavalink interno se ignoran y se usa `127.0.0.1`.
- `WEB_PUBLIC_URL` debe ser **exactamente** la URL pública, con `https://` y sin barra final.
- El resto de variables de [`.env.example`](../.env.example) también sirven (Apple Music, Deezer, Tidal, Qobuz…), igual que las de la tabla de la [sección 9](#9-variables-de-la-imagen).

---

## 4. Desplegar, dominio y HTTPS

1. Pulsa **Deploy**. La primera vez tarda varios minutos: construye la imagen (Python, Java, Lavalink y yt-cipher) y Lavalink descarga sus plugins.
2. Ve a **Domains** → **Add Domain**:
   - **Service**: `bot` · **Host**: `musica.tudominio.com` · **Port**: `8080`
   - **HTTPS**: activado · **Certificate Provider**: `Let's Encrypt`
3. Abre `https://musica.tudominio.com`: debe aparecer el panel de HexMusic.

> El compose conecta el servicio `bot` a `dokploy-network`, la red de Traefik. Con **Isolated Deployments** activado, Dokploy gestiona la red y esta conexión no molesta.

---

## 5. Configurar Discord

### OAuth2 del panel

1. <https://discord.com/developers/applications> → tu aplicación → **OAuth2**.
2. Copia el **Client Secret** (o *Reset Secret*) en `WEB_CLIENT_SECRET`.
3. En **Redirects** añade exactamente `https://musica.tudominio.com/auth/callback` y guarda.

### Invitar el bot

```
https://discord.com/oauth2/authorize?client_id=TU_APPLICATION_ID&scope=bot+applications.commands&permissions=3533904
```

Activa **Message Content Intent** (pestaña **Bot**) si quieres los comandos con prefijo (`hm!play`) y el canal de peticiones.

---

## 6. Comprobar el despliegue

En **Logs** del servicio `bot` verás, en este orden:

1. Un **Resumen de arranque** con Lavalink, fuentes, cifrado, panel web y biblioteca.
2. Las líneas de Lavalink con el prefijo `[lavalink]` y después `[+] Lavalink listo.`
3. El bot: `Nodo Lavalink 'main' listo`, `Panel web disponible en …` y `conectado como …`.

Luego, en Discord, entra en un canal de voz y usa `/play never gonna give you up`.

---

## 7. Migrar desde el compose de dos contenedores

Si ya tenías desplegada la versión con los servicios `lavalink` y `lavalink-init`:

1. En **Environment** borra `LAVALINK_URI` y `LIBRARY_PUBLIC_URL` si los tenías (se ignoran, pero así no confunden).
2. Pulsa **Deploy**. El servicio sigue llamándose `bot` y usa el mismo volumen `hexmusic-data`: el dominio, la base de datos, las playlists y el token de YouTube se conservan.
3. Si en **Docker** (o con `docker ps`) sigue apareciendo un contenedor `lavalink` del proyecto, páralo y elimínalo. El volumen `lavalink-plugins` ya no se usa y se puede borrar.

---

## 8. Datos, copias y actualizaciones

| Dato | Dónde vive |
|---|---|
| Base de datos, sesiones del panel, playlists, biblioteca, token de YouTube y contraseñas generadas | Volumen `hexmusic-data` (`/app/data`) |
| Plugins y registros de Lavalink | `/app/data/lavalink` (mismo volumen) |
| Registro de yt-cipher | `/app/data/logs/yt-cipher.log` |

- Los volúmenes se conservan entre despliegues. **No** despliegues con volúmenes limpios salvo que quieras borrarlo todo.
- Puedes programar **Volume Backups** de Dokploy sobre `hexmusic-data`.
- **Código, `config.yml`, `locales/` o `lavalink/application.yml`**: commit + push y vuelve a desplegar (o activa **Auto Deploy**). Todo viaja dentro de la imagen.
- **Solo variables**: cámbialas en **Environment** y pulsa **Deploy**.
- **Versiones de Lavalink, Deno o yt-cipher**: están fijadas como `ARG` al principio de [`Dockerfile`](../Dockerfile) (las mismas que el egg).

---

## 9. Variables de la imagen

Además de las de `.env.example`, la imagen entiende estas:

| Variable | Por defecto | Qué hace |
|---|---|---|
| `LAVALINK_MODE` | `interno` | `externo` = no arranca Lavalink y usa `LAVALINK_URI` + `LAVALINK_PASSWORD` |
| `LAVALINK_PASSWORD` | (generada) | Vacía = se genera una segura y se guarda en `data/.hex/` |
| `LAVALINK_MEMORY` | `auto` | `auto` = 55 % del límite de memoria del contenedor (o 1 GB si no tiene). También `1024` (MB) o `1G` |
| `LAVALINK_TIMEOUT` | `180` | Segundos que se espera a Lavalink antes de arrancar el bot igualmente |
| `YOUTUBE_CIPHER` | `true` | Servidor de cifrado interno (yt-cipher) para el error *Must find sig function* y la reproducción con cuenta |
| `LOG_RETENTION_DAYS` | `7` | Borra registros de Lavalink y yt-cipher más antiguos al arrancar |
| `HEXMUSIC__SECCION__CLAVE` | — | Sobrescribe cualquier clave de `config.yml` (p. ej. `HEXMUSIC__BOT__PREFIX=!`). Ver [CONFIGURACION.md](CONFIGURACION.md) |

---

## Solución de problemas

| Síntoma | Causa / solución |
|---|---|
| `Cannot connect to host localhost:2333` y el log **no** empieza con `Resumen de arranque` | Dokploy no está usando la imagen todo en uno: el contenedor solo lanza el bot. En una **Application**, pon **Build Type** `Dockerfile`, **Dockerfile Path** `./Dockerfile` y **Docker Context Path** `.`, y deja vacío cualquier *Command* personalizado. **Nixpacks no sirve**: no incluye Java ni Lavalink. En un **Compose**, el Compose Path debe ser `./docker-compose.dokploy.yml`. |
| `Cannot connect to host lavalink:2333 [Name or service not known]` | Estás desplegando el compose antiguo de dos contenedores. Haz pull de la versión actual (un solo servicio `bot`) y vuelve a desplegar. Si usas `LAVALINK_MODE=externo`, revisa `LAVALINK_URI`. |
| `Lavalink aún no responde` o `lavalink se cerró (código …)` | El motivo está en las líneas `[lavalink]` justo encima. Lo habitual: sin salida a internet para descargar plugins, memoria insuficiente o una fuente mal configurada. Lavalink se reinicia solo. |
| `No se puede escribir en /app/data` | El volumen no pertenece al UID 1000. Ejecuta el `chown` que muestra el log o borra el volumen si está vacío. |
| `Must find sig function from script` o fallos con YouTube con cuenta | Comprueba que el resumen diga `Cifrado de YouTube: activado` y mira `data/logs/yt-cipher.log`. |
| El panel dice `El servidor de audio (Lavalink) no está disponible` | El bot aún no tiene nodo. Espera a `Lavalink listo` y a `Nodo Lavalink 'main' listo`. |
| El panel da 502/504 | El dominio debe apuntar al servicio `bot`, puerto `8080`, con `WEB_ENABLED=true` y `WEB_CLIENT_SECRET` relleno (sin él, el panel no arranca y el log lo avisa). |
| `Invalid OAuth2 redirect_uri` | Discord no tiene registrada la URL exacta. El resumen de arranque muestra el Redirect que hay que añadir (misma `https`, dominio, `www` y sin barra final). |
| `Discord rechazó la configuración del panel` | Busca `Discord API POST /oauth2/token → …`: `401 invalid_client` = `WEB_CLIENT_SECRET` incorrecto; `400 invalid_grant` = vuelve a iniciar sesión desde el panel. |
| Sin memoria / reinicios | Con 2 GB deja `LAVALINK_MEMORY=auto` o `1G`. Si pones un límite de memoria al contenedor en Dokploy, `auto` se ajusta a él. |

---

## Alternativas

### Application en lugar de Compose

1. **Create Service → Application**, repo `Shalitax/HexMusic`, rama `main`.
2. **Build Type**: `Dockerfile` · **Dockerfile Path**: `./Dockerfile` · **Docker Context Path**: `.`
3. **Environment**: las mismas variables de la sección 3.
4. **Advanced → Volumes**: volumen `hexmusic-data` en `/app/data`.
5. **Domains**: puerto `8080`, HTTPS. **Deploy**.

### Lavalink externo

Si ya tienes un nodo Lavalink propio, añade `LAVALINK_MODE=externo`, `LAVALINK_URI=http://host:2333` y `LAVALINK_PASSWORD`. No se arrancan Java ni yt-cipher. La biblioteca (`/upload`) solo funciona si además indicas en `LIBRARY_PUBLIC_URL` una dirección con la que ese Lavalink llegue al bot (puerto `2340`).
