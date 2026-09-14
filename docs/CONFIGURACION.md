# ⚙️ Configuración

HexMusic se configura en **tres niveles**:

| Nivel | Archivo o comando | Qué contiene | Quién lo cambia |
|---|---|---|---|
| Secretos | `.env` | Token, contraseñas, credenciales de plataformas | Operador del bot |
| Bot | `config.yml` | Branding, emojis, límites, funciones, módulos | Operador del bot |
| Servidor | `/settings`, `/setup` | Idioma, prefijo, rol DJ, volumen, votaciones… | Administradores de cada servidor |
| Lavalink | `lavalink/application.yml` | Calidad de audio, fuentes, plugins | Operador del bot |

> Tras editar `config.yml` o los idiomas, **reinicia el bot**. Tras editar `.env` o `application.yml`, **reinicia también Lavalink**.

---

## `.env` — variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Token del bot |
| `LAVALINK_PASSWORD` | ✅ | Contraseña compartida entre bot y Lavalink |
| `LAVALINK_URI` | — | Dirección de Lavalink (por defecto `http://localhost:2333`; Docker fuerza `http://lavalink:2333`) |
| `DEV_GUILD_ID` | — | Servidor donde se registran los comandos al instante (útil para desarrollo) |
| `LAVALINK_MEMORY` | — | Memoria máxima de Lavalink con Docker (`1G`, `2G`…) |
| `DATABASE_PATH` | — | Ruta de la base de datos (por defecto `data/hexmusic.db`) |
| `MUSIC_COUNTRY_CODE` | — | País para catálogos regionales (`ES`, `MX`, `US`…) |
| `SPOTIFY_*`, `APPLEMUSIC_*`, `DEEZER_*`, `TIDAL_*`, `QOBUZ_*` | — | Ver [Fuentes de música](FUENTES.md) |
| `YOUTUBE_OAUTH_ENABLED` | — | Ver [Fuentes → YouTube](FUENTES.md#youtube) |
| `YOUTUBE_OAUTH_REFRESH_TOKEN` | — | Refresh token de la cuenta vinculada; evita pedir el código en cada reinicio (ver [Fuentes → YouTube](FUENTES.md#youtube)) |
| `HEXMUSIC_CONFIG` | — | Ruta alternativa a `config.yml` |
| `WEB_ENABLED`, `WEB_PORT`, `WEB_PUBLIC_URL`, `WEB_CLIENT_SECRET` | — | Panel web, ver [Panel web](PANEL_WEB.md) |
| `HEXMUSIC__SECCION__CLAVE` | — | Sobrescribe cualquier ajuste de `config.yml` ([ver abajo](#sobrescribir-ajustes-con-variables-de-entorno)) |

---

## `config.yml` — referencia completa

En `config.yml` puedes escribir `"${VARIABLE}"` o `"${VARIABLE:-valor_por_defecto}"` para leer variables de entorno. Cualquier clave que borres usa el valor por defecto.

### `bot`

| Clave | Por defecto | Descripción |
|---|---|---|
| `name` | `HexMusic` | Nombre que aparece en paneles y mensajes |
| `prefix` | `hm!` | Prefijo por defecto de los comandos de texto. Cada servidor puede cambiarlo |
| `message_content_intent` | `true` | Necesario para el prefijo y el canal de peticiones |
| `owner_ids` | `[]` | IDs con acceso a comandos de dueño (`sync`, `reloadlocales`). Vacío = dueño de la aplicación |
| `default_language` | `es` | Idioma de los servidores que no han elegido uno |
| `sync_commands` | `true` | Registrar los comandos slash al arrancar |
| `dev_guild_id` | `${DEV_GUILD_ID}` | Si tiene valor, los comandos se registran solo en ese servidor, al instante |
| `database` | `data/hexmusic.db` | Archivo SQLite |
| `status.type` | `listening` | `playing`, `listening`, `watching` o `competing` |
| `status.text` | `/play • HexMusic` | Texto del estado. Vacío = sin estado |
| `extensions` | todos | Módulos cargados. Quita uno para desactivarlo entero (p. ej. `hexmusic.cogs.playlists`) |

### `logging`

| Clave | Por defecto | Descripción |
|---|---|---|
| `level` | `INFO` | `DEBUG`, `INFO`, `WARNING` o `ERROR` |

### `lavalink`

| Clave | Por defecto | Descripción |
|---|---|---|
| `nodes` | 1 nodo | Lista de nodos con `identifier`, `uri` y `password` |
| `default_search` | `ytmsearch` | Dónde se busca al escribir un nombre: `ytmsearch`, `ytsearch`, `scsearch`, `spsearch`, `dzsearch`, `tdsearch`, `amsearch` o `qbsearch` |
| `search_cache` | `128` | Búsquedas guardadas en memoria (0 = desactivado) |

> `ytmsearch` (YouTube Music) da **pistas de audio oficiales** en lugar de videoclips: mejor calidad y sin intros. Es la opción recomendada.

### `branding`

| Clave | Por defecto | Descripción |
|---|---|---|
| `color` | `#8B5CF6` | Color principal de los embeds |
| `success_color` / `error_color` / `warning_color` | verde / rojo / ámbar | Colores de respuesta |
| `footer` | `HexMusic • Hexservers` | Pie de los embeds (vacío = sin pie) |
| `footer_icon` | `""` | URL del icono del pie (vacío = avatar del bot) |
| `banner_url` | `""` | Imagen del panel del canal de peticiones cuando no suena nada |
| `large_artwork` | `false` | `true` = carátula grande; `false` = miniatura |
| `progress_bar.length` | `16` | Longitud de la barra de progreso |
| `progress_bar.filled` / `head` / `empty` | `━` / `●` / `─` | Caracteres de la barra |

### `emojis`

Emojis de los botones (`previous`, `pause`, `skip`, `stop`, `queue`, `loop`, `shuffle`, `volume_down`, `volume_up`, `autoplay`), de los mensajes (`success`, `error`, `warning`, `info`, `music`, `live`) y de cada plataforma (`sources.youtube`, `sources.spotify`…, `sources.default`).

Admiten emojis personalizados con el formato `<:nombre:id>` o `<a:nombre:id>` (animados). El bot necesita estar en el servidor donde vive el emoji.

### `player`

| Clave | Por defecto | Descripción |
|---|---|---|
| `default_volume` | `100` | Volumen inicial. **100 = máxima fidelidad** |
| `max_volume` | `150` | Volumen máximo permitido (hasta 1000) |
| `volume_step` | `10` | Cuánto cambian los botones 🔉 🔊 |
| `max_queue_size` | `1000` | Canciones máximas en cola (0 = sin límite) |
| `max_track_duration` | `0` | Duración máxima por canción en segundos (0 = sin límite) |
| `idle_timeout` | `300` | Segundos sin reproducir antes de desconectarse (0 = nunca) |
| `empty_channel_timeout` | `120` | Segundos con el canal vacío antes de salir (0 = nunca) |
| `pause_when_empty` | `true` | Pausa si todos salen y reanuda al volver alguien |
| `self_deaf` | `true` | Entrar ensordecido (ahorra ancho de banda) |
| `announce_tracks` | `true` | Enviar el panel en cada canción (cada servidor puede cambiarlo) |
| `delete_old_now_playing` | `true` | Borrar el panel anterior al empezar otra canción |
| `search_autocomplete` | `true` | Sugerencias mientras se escribe en `/play` |
| `search_results` | `10` | Resultados de `/search` (máx. 25) |

### `features`

| Clave | Por defecto | Descripción |
|---|---|---|
| `autoplay` | `true` | Recomendaciones automáticas al terminar la cola |
| `stay_247` | `true` | Permitir el modo 24/7 |
| `lyrics` | `true` | Comando `/lyrics` |
| `request_channel` | `true` | Canal de peticiones (`/setup`) |
| `vote_skip` | `true` | Permitir la votación para saltar |

### `vote_skip`

| Clave | Por defecto | Descripción |
|---|---|---|
| `default_enabled` | `false` | Si la votación está activa en servidores que no la han configurado |
| `ratio` | `0.5` | Proporción de oyentes necesaria (0.5 = la mitad) |

No tienen que votar quien pidió la canción, los admins, el rol DJ ni quien esté solo con el bot.

### `dj`

| Clave | Descripción |
|---|---|
| `commands` | Comandos que requieren permisos DJ. Para grupos se usa el nombre raíz: `filter` cubre todos los `/filter …` |

Tienen permisos DJ quienes cumplan **al menos una** condición: administrador o *Gestionar servidor*, tener el rol DJ del servidor o estar solo con el bot en el canal. **Si un servidor no configura rol DJ, todos pueden usar esos comandos.**

### `playlists`

| Clave | Por defecto | Descripción |
|---|---|---|
| `max_per_user` | `25` | Playlists por usuario |
| `max_tracks` | `500` | Canciones por playlist |

### `request_channel`

| Clave | Por defecto | Descripción |
|---|---|---|
| `channel_name` | `hexmusic` | Nombre del canal que crea `/setup` |
| `delete_after` | `8` | Segundos hasta borrar las respuestas del bot en ese canal |

### `filters`

| Clave | Descripción |
|---|---|
| `presets` | Presets propios o que sobrescriben los incluidos. Un valor `null` elimina un preset. Ver [Personalización → Presets](PERSONALIZACION.md#presets-de-filtros) |

### `web`

| Clave | Por defecto | Descripción |
|---|---|---|
| `enabled` | `${WEB_ENABLED}` (`false`) | Activa el panel web |
| `host` | `0.0.0.0` | Interfaz donde escucha |
| `port` | `${WEB_PORT}` (`8080`) | Puerto del panel |
| `public_url` | `${WEB_PUBLIC_URL}` | Dirección con la que se abre en el navegador (base del Redirect de Discord) |
| `client_secret` | `${WEB_CLIENT_SECRET}` | Client Secret de OAuth2 de tu aplicación de Discord |
| `session_days` | `7` | Días que dura una sesión |

### Sobrescribir ajustes con variables de entorno

Cualquier clave de `config.yml` se puede sobrescribir con una variable `HEXMUSIC__` seguida de la ruta de la clave, con las partes separadas por dos guiones bajos. Es la forma más cómoda en paneles de hosting y contenedores.

| Variable | Equivale a |
|---|---|
| `HEXMUSIC__BOT__PREFIX=!` | `bot.prefix: "!"` |
| `HEXMUSIC__BOT__STATUS__TEXT=/play` | `bot.status.text: "/play"` |
| `HEXMUSIC__BRANDING__COLOR=#FF0055` | `branding.color: "#FF0055"` |
| `HEXMUSIC__PLAYER__MAX_VOLUME=200` | `player.max_volume: 200` |
| `HEXMUSIC__FEATURES__LYRICS=0` | `features.lyrics: false` |
| `HEXMUSIC__BOT__OWNER_IDS=123,456` | `bot.owner_ids: [123, 456]` (las listas van separadas por comas) |

- Tienen **prioridad** sobre `config.yml`.
- Una variable vacía se ignora.
- Si la clave no existe, el log avisa y se ignora.

`bot.console: true` (`HEXMUSIC__BOT__CONSOLE=1`) activa los comandos escritos en la consola (`ayuda`, `estado`, `servidores`, `sync`, `idiomas`, `detener`). El egg de Pterodactyl lo activa automáticamente.

---

## Ajustes por servidor

Los administradores (permiso *Gestionar servidor*) los cambian desde Discord. Se guardan en la base de datos.

| Comando | Ajuste |
|---|---|
| `/settings show` | Ver todos los ajustes |
| `/settings language <código>` | Idioma del bot |
| `/settings prefix <prefijo>` | Prefijo de comandos de texto |
| `/settings djrole [rol]` | Rol DJ (sin rol = quitar) |
| `/settings volume <0-max>` | Volumen inicial |
| `/settings voteskip <sí/no>` | Votación para saltar |
| `/settings announce <sí/no>` | Panel de cada canción en el chat |
| `/settings reset` | Volver a los valores de `config.yml` |
| `/setup [canal]` · `/unsetup` | Canal de peticiones |
| `/autoplay` · `/247` | Autoplay y modo 24/7 (se guardan por servidor) |

---

## `lavalink/application.yml`

Viene preparado para la máxima calidad. Lo más habitual es tocar solo `.env`. Detalles en [Calidad de audio](CALIDAD_AUDIO.md) y [Fuentes de música](FUENTES.md).
