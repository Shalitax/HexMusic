# 🖥️ Panel web

HexMusic incluye un panel web ligero que se ejecuta **dentro del propio bot**. No hace falta instalar nada más: solo activarlo y conectar el inicio de sesión con Discord.

El panel funciona **en tiempo real** (WebSocket): lo que pasa en Discord aparece al instante y lo que haces en la web llega a Discord igual de rápido. Tiene tema claro y oscuro, funciona en el móvil y un **mini reproductor** fijo abajo para controlar la música desde cualquier sección.

| Sección | Qué permite |
|---|---|
| 🏠 **Inicio** | Cifras del bot, tus servidores (con botón para invitar el bot donde falte) y estado de los nodos de Lavalink. Los dueños ven además los reproductores activos y la actividad de todos los servidores |
| 🎵 **Reproductor** | Carátula y progreso en vivo (se puede arrastrar), anterior, pausa, saltar, detener, mezclar, repetición, volumen con silencio, filtros, autoplay, 24/7, mover el bot de canal, oyentes y desconectar. Cola con **arrastrar y soltar**, **letra sincronizada** (LRCLIB) y canciones recientes |
| 🔎 **Buscar** | Resultados de cualquier fuente: añadir a la cola, poner a continuación, añadir una playlist o álbum entero o **guardar en una de tus playlists**. Muestra también las coincidencias de la biblioteca |
| 📚 **Biblioteca** | Subir audios desde el navegador (arrastrando varios a la vez, con progreso), espacio usado, filtrar, renombrar, borrar y reproducir uno o todos |
| 🕘 **Historial** | Reproducciones por día (7, 30, 90 o 365 días), tiempo de música, canciones más escuchadas, quién pide más, últimas reproducciones y volver a poner cualquiera |
| ⚙️ **Ajustes** | Idioma, prefijo, volumen inicial, anuncios, votación, autoplay, 24/7, rol DJ, **qué comandos requieren DJ** en ese servidor, **canal de peticiones** (crearlo, moverlo o quitarlo sin usar `/setup`) y restablecer |
| 📁 **Mis playlists** | Crear, renombrar, hacer pública, borrar, añadir y quitar canciones y reproducirla en cualquier servidor |
| 👑 **Administración** (dueños) | **Resumen** (memoria, miembros, almacenamiento, acciones: sincronizar comandos, recargar idiomas, guardar colas), **Configuración** global, **Servidores** (abrir o sacar el bot) y **Registros** en vivo con filtro. También la cuenta de YouTube |

### Configuración global desde la web

En **Administración → Configuración** los dueños del bot cambian sin tocar archivos unos 80 ajustes de `config.yml`: nombre, estado, colores, emojis, reproductor, búsqueda, funciones, votos y DJ, límites y presets de filtros.

- Se guardan en `panel-config.json`, en la misma carpeta que la base de datos (`data/`), y tienen **prioridad** sobre `config.yml` y sobre las variables `HEXMUSIC__`. Así sobreviven a las actualizaciones y a los redespliegues de Docker/Dokploy.
- La mayoría se aplica al momento. Los marcados como **Al reiniciar** (intents, caché de búsqueda, biblioteca, cola persistente) esperan al siguiente arranque.
- *Volver a config.yml* quita el cambio del panel y recupera el valor del archivo.

**¿Quién ve qué?**

- Cualquier usuario ve **sus playlists** y la lista de servidores donde tiene *Gestionar servidor* (o es dueño o admin). Si el bot no está en un servidor, aparece un botón **Invitar**.
- En esos servidores puede usar el **reproductor** y los **ajustes**.
- Los **dueños del bot** (`bot.owner_ids` o el dueño de la aplicación) pueden gestionar todos los servidores del bot.

---

## 1. Configurar Discord (OAuth2)

1. Entra en <https://discord.com/developers/applications> → tu aplicación → **OAuth2**.
2. En **Client Secret** pulsa *Reset Secret* y copia el valor.
3. En **Redirects** pulsa *Add Redirect* y escribe la dirección del panel seguida de `/auth/callback`:
   - En local: `http://localhost:8080/auth/callback`
   - Con dominio: `https://musica.tudominio.com/auth/callback`
4. Pulsa **Save Changes**.

> La dirección tiene que coincidir **exactamente** (protocolo, dominio, puerto y ruta) con `WEB_PUBLIC_URL` + `/auth/callback`. Si no coincide, Discord mostrará *"Invalid OAuth2 redirect_uri"*.

## 2. Activar el panel

En `.env`:

```env
WEB_ENABLED=true
WEB_PORT=8080
WEB_PUBLIC_URL=http://localhost:8080
WEB_CLIENT_SECRET=el_client_secret_que_copiaste
```

Reinicia el bot:

- **Docker:** `docker compose up -d`. El `docker-compose.yml` ya publica el puerto `WEB_PORT`.
- **Manual:** vuelve a lanzar `python -m hexmusic`.

En el log aparecerá: `Panel web disponible en http://localhost:8080`.

## 3. Entrar

Abre la dirección del panel y pulsa **Iniciar sesión con Discord**. La sesión dura `web.session_days` días (7 por defecto).

---

## Producción con HTTPS (recomendado)

En Internet, sirve el panel siempre por **HTTPS** mediante un proxy inverso. Con `WEB_PUBLIC_URL` en `https://…`, las cookies de sesión se marcan como seguras automáticamente.

**Caddy** (obtiene el certificado solo):

```caddy
musica.tudominio.com {
    reverse_proxy 127.0.0.1:8080
}
```

**nginx**:

```nginx
server {
    listen 443 ssl http2;
    server_name musica.tudominio.com;
    # ssl_certificate / ssl_certificate_key de tu certificado

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        # Tiempo real del panel (WebSocket en /ws)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 1h;
    }
}
```

> Caddy y Traefik (Dokploy) reenvían el WebSocket sin configuración extra. Si el proxy no lo permite, el panel sigue funcionando y se actualiza cada pocos segundos (arriba a la derecha pone *Sincronizando* en lugar de *En vivo*).

Después:

```env
WEB_PUBLIC_URL=https://musica.tudominio.com
```

Con Docker, limita el puerto a la propia máquina para que solo el proxy llegue a él. En `docker-compose.yml`, usa `"127.0.0.1:8080:8080"`.

## Pterodactyl

El [egg de HexMusic](../../../Pterodactyl%20eggs/HexMusic/README.md) lo configura solo: el panel escucha en el **puerto principal** del servidor y la consola muestra la URL y el *Redirect* exactos que hay que añadir en Discord. Solo tienes que activar *Panel web* y pegar el *Client Secret* en la pestaña Startup.

---

## Seguridad

- **Inicio de sesión con Discord (OAuth2)** con los permisos mínimos (`identify` y `guilds`) y un parámetro `state` que evita ataques de falsificación en el login.
- **Permisos comprobados en cada petición**: la lista de servidores con *Gestionar servidor* se consulta a Discord y se guarda en caché 2 minutos.
- **Sesiones en la base de datos**: la cookie (`HttpOnly`, `SameSite=Lax`, `Secure` con HTTPS) contiene un token aleatorio y la base de datos solo guarda su hash SHA-256.
- **Protección CSRF**: toda petición que modifica algo exige la cabecera `X-CSRF-Token` de la sesión.
- **Cabeceras de seguridad**: `Content-Security-Policy` estricta (sin scripts externos ni en línea), `X-Frame-Options: DENY` y `nosniff`.
- **Sin HTML inyectable**: la interfaz construye todos los elementos con `textContent`, así que los títulos de canciones no pueden ejecutar código.
- El archivo de la base de datos contiene los tokens de acceso de Discord de las sesiones activas: protégelo como el `.env`.

---

## API (para integraciones)

El panel usa una API JSON que puedes aprovechar desde tus propias herramientas con la misma sesión. Todas las rutas `/api/*`, salvo `/api/public` e `/api/i18n`, requieren la cookie de sesión. Las que modifican algo requieren además la cabecera `X-CSRF-Token`, cuyo valor devuelve `/api/me`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/public` | Nombre, color y avatar del bot |
| GET | `/api/i18n?lang=es` | Textos del panel |
| GET | `/api/me` | Usuario, servidores gestionables y token CSRF |
| GET | `/api/stats` | Estadísticas y nodos |
| GET | `/api/guilds/{id}` | Datos y ajustes del servidor |
| PATCH | `/api/guilds/{id}/settings` | Cambia ajustes (`language`, `prefix`, `dj_role_id`, `default_volume`, `vote_skip`, `announce`, `autoplay`, `stay_247`, `dj_commands`) |
| POST | `/api/guilds/{id}/settings/reset` | Restablece los ajustes del servidor |
| POST / DELETE | `/api/guilds/{id}/request-channel` | Crea o mueve el canal de peticiones (`{"channel_id": "…"}`, vacío = crear uno) o lo quita |
| GET | `/api/guilds/{id}/player` | Estado del reproductor, cola y recientes |
| POST | `/api/guilds/{id}/player` | Acción: `{"action": "play", "query": "…"}`, `pause`, `skip`, `previous`, `replay`, `stop`, `volume`, `seek`, `loop`, `autoplay`, `filter`, `shuffle`, `clear`, `remove`, `move`, `skipto`, `join`, `leave` |
| POST | `/api/guilds/{id}/search` | Busca y devuelve resultados con un `id` temporal: `{"query": "…", "source": "spotify"}` |
| POST | `/api/guilds/{id}/enqueue` | Añade resultados de la búsqueda: `{"ids": ["…"], "next": false}` |
| GET | `/api/guilds/{id}/lyrics` | Letra de la canción actual (con líneas sincronizadas si existen) |
| GET / POST | `/api/guilds/{id}/library` | Lista la biblioteca o sube un archivo (`multipart/form-data`: `file` y `title` opcional) |
| PATCH / DELETE | `/api/guilds/{id}/library/{archivo}` | Renombra (`{"title": "…"}`) o borra un archivo |
| POST | `/api/guilds/{id}/library/play` | Reproduce archivos: `{"ids": [1, 2]}` o `{"all": true, "shuffle": true}` |
| GET / DELETE | `/api/guilds/{id}/history` | Últimas reproducciones (`?limit=50&before=<id>`) o borrar el historial |
| GET | `/api/guilds/{id}/history/summary` | Totales, más escuchadas, quién pide más y reproducciones por día (`?days=30&tz=<minutos>`) |
| GET / POST | `/api/playlists` | Lista o crea playlists |
| GET / PATCH / DELETE | `/api/playlists/{id}` | Ver, cambiar (`name`, `public`) o borrar |
| POST | `/api/playlists/{id}/tracks` | Añadir una canción, una playlist/álbum (`{"query": "…"}`) o resultados de búsqueda (`{"ids": ["…"]}`) |
| DELETE | `/api/playlists/{id}/tracks/{posición}` | Quitar una canción |
| POST | `/api/playlists/{id}/play` | Reproducir en un servidor: `{"guild_id": "…"}` |
| GET / POST | `/api/youtube` | Solo dueños: estado de la cuenta de YouTube y acciones `{"action": "link" \| "cancel" \| "unlink"}` |
| GET | `/api/stats/history` | Solo dueños: actividad de todos los servidores |
| GET | `/api/admin/overview` | Solo dueños: estado del bot, versiones y almacenamiento |
| POST | `/api/admin/actions` | Solo dueños: `{"action": "sync" \| "reload_locales" \| "save_sessions" \| "purge_history"}` |
| GET / PATCH | `/api/admin/config` | Solo dueños: ajustes globales; `{"changes": {"player.max_volume": 200}, "reset": ["branding.color"]}` |
| GET | `/api/admin/guilds` · POST `/api/admin/guilds/{id}/leave` | Solo dueños: servidores del bot y sacar el bot de uno |
| GET | `/api/admin/logs?after=0&level=INFO` | Solo dueños: últimas líneas del registro |
| WS | `/ws` | Tiempo real: envía `{"op": "subscribe", "guild_id": "…"}` y recibe `{"type": "player", "data": …}` en cada cambio |

Los errores devuelven `{"error": "mensaje traducido"}` con el código HTTP correspondiente.

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| *Invalid OAuth2 redirect_uri* | El Redirect de Discord no coincide con `WEB_PUBLIC_URL/auth/callback`. Revisa protocolo, puerto y barra final |
| *"Discord rechazó la configuración del panel"* | `WEB_CLIENT_SECRET` incorrecto o regenerado, o el Redirect no es exactamente `WEB_PUBLIC_URL/auth/callback`. El log del bot dice cuál |
| *"El inicio de sesión caducó o se abrió desde otra dirección"* | Abre el panel con la dirección de `WEB_PUBLIC_URL`. El botón de login ya redirige a ella; si estás detrás de un proxy, reenvía `Host` y `X-Forwarded-Proto` |
| Aparece un error con *Reintentar* en vez del panel | Discord no respondió o limitó las peticiones; la sesión sigue abierta. Pulsa *Reintentar* |
| El navegador no carga la página | Comprueba que `WEB_ENABLED=true`, que el puerto está publicado (Docker o firewall) y que el log dice *Panel web disponible* |
| `No se pudo iniciar el panel web en el puerto…` | Otro programa usa ese puerto: cambia `WEB_PORT` |
| No aparece un servidor | Necesitas *Gestionar servidor* en él. Los cambios de permisos tardan hasta 2 minutos en reflejarse |
| *"El bot no está conectado: elige un canal de voz"* | Selecciona un canal en el reproductor o entra tú en uno antes de añadir canciones |
