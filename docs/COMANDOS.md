# 💬 Comandos

Todos los comandos funcionan de dos formas:

- **Slash:** `/play never gonna give you up`
- **Prefijo:** `hm!play never gonna give you up` (el prefijo se cambia con `/settings prefix`)

Leyenda de la columna **Acceso**:

| Símbolo | Quién puede usarlo |
|---|---|
| 🟢 | Cualquiera que esté en el canal de voz del bot |
| 🎧 | Permisos DJ: rol DJ, admins o quien esté solo con el bot. Configurable en `dj.commands`; si el servidor no tiene rol DJ, todos |
| 🛡️ | Permiso *Gestionar servidor* |
| 👑 | Dueños del bot (solo comandos de texto) |

> Con prefijo, si un argumento tiene espacios y le sigue otro argumento, ponlo entre comillas: `hm!playlist add "Mi lista" bohemian rhapsody`.

---

## 🎵 Música

| Comando | Alias | Acceso | Descripción |
|---|---|---|---|
| `/play <búsqueda> [plataforma]` | `p` | 🟢 | Reproduce una canción, playlist, álbum o enlace. Con autocompletado |
| `/playnext <búsqueda> [plataforma]` | `pn`, `playtop` | 🟢 | Añade al principio de la cola |
| `/search <búsqueda> [plataforma]` | `find` | 🟢 | Muestra resultados en un menú para elegir |
| `/join` | `connect`, `summon` | 🟢 | Entra en tu canal de voz |
| `/leave` | `disconnect`, `dc` | 🎧 | Sale del canal, vacía la cola y desactiva el 24/7 |
| `/pause` · `/resume` | `unpause` | 🟢 | Pausa o reanuda |
| `/skip` | `s`, `next` | 🟢 | Salta la canción (con votación si está activa) |
| `/forceskip` | `fs` | 🎧 | Salta sin votación |
| `/previous` | `prev`, `back` | 🟢 | Vuelve a la canción anterior |
| `/stop` | — | 🎧 | Detiene la música y vacía la cola |
| `/seek <tiempo>` | — | 🎧 | Salta a un momento: `1:30`, `90`, `2m30s`, `+10`, `-15` |
| `/replay` | `restart` | 🟢 | Reinicia la canción |
| `/volume [nivel]` | `vol`, `v` | 🟢 ver · 🎧 cambiar | Muestra o cambia el volumen |
| `/nowplaying` | `np`, `now` | 🟢 | Panel de la canción actual con botones |
| `/queue [página]` | `q`, `list` | 🟢 | Muestra la cola paginada |
| `/remove <posición>` | `rm` | 🟢 las tuyas · 🎧 las demás | Quita una canción de la cola |
| `/move <desde> <hasta>` | `mv` | 🎧 | Mueve una canción dentro de la cola |
| `/skipto <posición>` | `jump` | 🎧 | Salta directamente a una posición |
| `/clear` | `cl` | 🎧 | Vacía la cola |
| `/shuffle` | `mix` | 🎧 | Mezcla la cola |
| `/loop [off/track/queue]` | `repeat`, `l` | 🎧 | Modo de repetición (sin argumento pasa al siguiente modo) |
| `/autoplay` | `ap`, `radio` | 🎧 | Activa o desactiva las recomendaciones al terminar la cola |
| `/247` | `24/7`, `stay` | 🎧 | Activa o desactiva el modo 24/7 |
| `/grab` | `save` | 🟢 | Te envía la canción actual por mensaje privado |
| `/lyrics [búsqueda]` | `ly`, `letra` | 🟢 | Letra de la canción actual o de la búsqueda |

**Plataformas de `/play`:** YouTube Music (por defecto), YouTube, Spotify, Apple Music, Deezer, Tidal, Qobuz y SoundCloud. Los enlaces se detectan solos, así que no hace falta elegir plataforma.

**Búsqueda avanzada:** también puedes escribir el prefijo de búsqueda a mano, p. ej. `/play spsearch:bad bunny` o `/play dzisrc:USUM71703861`.

---

## 🎛️ Filtros

| Comando | Alias | Acceso | Descripción |
|---|---|---|---|
| `/filter list` | `filters`, `fx` | 🟢 | Presets disponibles y filtro actual |
| `/filter preset <nombre>` | — | 🎧 | Aplica un preset |
| `/filter equalizer <banda 1-15> <ganancia>` | `eq` | 🎧 | Ajusta una banda (-0.25 a 1.0) |
| `/filter speed <0.5-2.0>` | — | 🎧 | Velocidad |
| `/filter pitch <0.5-2.0>` | — | 🎧 | Tono |
| `/filter reset` | `off`, `clear` | 🎧 | Quita todos los filtros |

**Presets incluidos:** `bassboost`, `superbass`, `pop`, `rock`, `electronic`, `vocals`, `treble`, `nightcore`, `vaporwave`, `slowed`, `chipmunk`, `darthvader`, `8d`, `karaoke`, `tremolo`, `vibrato`, `soft`.

---

## 📁 Playlists

Las playlists son **de cada usuario** y funcionan en cualquier servidor donde esté el bot.

| Comando | Alias | Descripción |
|---|---|---|
| `/playlist list` | `pl` | Tus playlists |
| `/playlist create <nombre>` | `new` | Crea una playlist |
| `/playlist delete <nombre>` | `del` | Elimina una playlist |
| `/playlist show <nombre>` | `view` | Muestra sus canciones |
| `/playlist add <nombre> [búsqueda]` | — | Añade la canción actual o una búsqueda o enlace (las playlists de Spotify, YouTube… se añaden enteras) |
| `/playlist savequeue <nombre>` | `sq` | Guarda la canción actual y la cola |
| `/playlist remove <nombre> <posición>` | `rm` | Quita una canción |
| `/playlist play <nombre> [mezclar]` | `load` | Añade la playlist a la cola |

---

## ⚙️ Ajustes (🛡️ Gestionar servidor)

| Comando | Alias | Descripción |
|---|---|---|
| `/settings show` | `config`, `ajustes` | Ver los ajustes del servidor |
| `/settings language <código>` | `lang`, `idioma` | Idioma (`es`, `en`…) |
| `/settings prefix <prefijo>` | — | Prefijo de texto |
| `/settings djrole [rol]` | `dj` | Rol DJ (vacío = quitar) |
| `/settings volume <nivel>` | — | Volumen inicial |
| `/settings voteskip <sí/no>` | — | Votación para saltar |
| `/settings announce <sí/no>` | — | Panel en cada canción |
| `/settings reset` | — | Restablecer ajustes |
| `/setup [canal]` | — | Crea (o usa) el canal de peticiones con panel fijo |
| `/unsetup` | — | Desactiva el canal de peticiones |

### Canal de peticiones

Tras `/setup`:

- En el canal queda un **panel fijo** que muestra la canción actual y tiene todos los botones.
- Cualquier mensaje escrito ahí se toma como una petición: el bot la busca, la añade a la cola y borra el mensaje para mantener el canal limpio.
- También puedes **arrastrar un archivo de audio** al canal para reproducirlo.

---

## ℹ️ General

| Comando | Alias | Acceso | Descripción |
|---|---|---|---|
| `/help` | `h`, `ayuda`, `commands` | 🟢 | Lista de comandos por categorías |
| `/ping` | `latency` | 🟢 | Latencia con Discord, Lavalink y la voz |
| `/stats` | `info`, `botinfo` | 🟢 | Servidores, reproductores, uptime y estado de los nodos |
| `/invite` | — | 🟢 | Enlace de invitación |
| `hm!sync [global/guild/clear]` | — | 👑 | Registra los comandos slash |
| `hm!reloadlocales` | — | 👑 | Recarga los idiomas sin reiniciar |

---

## 🎛️ Botones del panel

| Fila | Botones |
|---|---|
| 1 | ⏮️ Anterior · ⏯️ Pausa/Reanudar · ⏭️ Saltar · ⏹️ Parar · 📜 Ver cola |
| 2 | 🔁 Repetición · 🔀 Mezclar · 🔉 Bajar volumen · 🔊 Subir volumen · ♾️ Autoplay |

Los botones respetan los mismos permisos que su comando equivalente (DJ, votación…). Los emojis se cambian en `config.yml → emojis`.
