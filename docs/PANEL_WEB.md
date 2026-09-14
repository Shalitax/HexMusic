# 🖥️ Panel web

HexMusic incluye un panel web ligero que se ejecuta **dentro del propio bot**. No hace falta instalar nada más: solo activarlo y conectar el inicio de sesión con Discord.

| Sección | Qué permite |
|---|---|
| 📊 **Estadísticas** | Servidores, reproductores activos, uptime, latencia y estado de cada nodo de Lavalink (CPU, RAM). Los dueños del bot ven además la lista de servidores con música sonando |
| 🎵 **Reproductor** | Canción actual con barra de progreso (se puede arrastrar), pausa, anterior, saltar, detener, volumen, repetición, filtros, autoplay, conectar/desconectar el bot, añadir canciones y gestionar la cola (reordenar, saltar a, quitar, mezclar, vaciar) |
| ⚙️ **Ajustes** | Todo lo de `/settings`: idioma, prefijo, rol DJ, volumen inicial, votación, anuncios, autoplay y modo 24/7 |
| 📁 **Mis playlists** | Crear, renombrar, borrar, quitar canciones y reproducir una playlist en cualquier servidor |

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
    }
}
```

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
| PATCH | `/api/guilds/{id}/settings` | Cambia ajustes (`language`, `prefix`, `dj_role_id`, `default_volume`, `vote_skip`, `announce`, `autoplay`, `stay_247`) |
| GET | `/api/guilds/{id}/player` | Estado del reproductor y cola |
| POST | `/api/guilds/{id}/player` | Acción: `{"action": "play", "query": "…"}`, `pause`, `skip`, `previous`, `stop`, `volume`, `seek`, `loop`, `autoplay`, `filter`, `shuffle`, `clear`, `remove`, `move`, `skipto`, `join`, `leave` |
| GET / POST | `/api/playlists` | Lista o crea playlists |
| GET / PATCH / DELETE | `/api/playlists/{id}` | Ver, renombrar o borrar |
| DELETE | `/api/playlists/{id}/tracks/{posición}` | Quitar una canción |
| POST | `/api/playlists/{id}/play` | Reproducir en un servidor: `{"guild_id": "…"}` |

Los errores devuelven `{"error": "mensaje traducido"}` con el código HTTP correspondiente.

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| *Invalid OAuth2 redirect_uri* | El Redirect de Discord no coincide con `WEB_PUBLIC_URL/auth/callback`. Revisa protocolo, puerto y barra final |
| Vuelve al login con *"No se pudo iniciar sesión"* | `WEB_CLIENT_SECRET` incorrecto o caducado. Genera uno nuevo. En el log del bot aparece el motivo |
| El navegador no carga la página | Comprueba que `WEB_ENABLED=true`, que el puerto está publicado (Docker o firewall) y que el log dice *Panel web disponible* |
| `No se pudo iniciar el panel web en el puerto…` | Otro programa usa ese puerto: cambia `WEB_PORT` |
| No aparece un servidor | Necesitas *Gestionar servidor* en él. Los cambios de permisos tardan hasta 2 minutos en reflejarse |
| *"El bot no está conectado: elige un canal de voz"* | Selecciona un canal en el reproductor o entra tú en uno antes de añadir canciones |
