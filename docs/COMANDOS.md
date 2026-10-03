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
| `/play <búsqueda> [plataforma] [archivo]` | `p` | 🟢 | Reproduce una canción, playlist, álbum o enlace, o un **archivo de audio adjunto**. El autocompletado sugiere también los archivos de la biblioteca (📚) |
| `/playnext <búsqueda> [plataforma] [archivo]` | `pn`, `playtop` | 🟢 | Añade al principio de la cola |
| `/search <búsqueda> [plataforma]` | `find` | 🟢 | Muestra resultados en un menú para elegir |
| `/menu` | `m`, `panel` | 🟢 | Menú privado para controlarlo todo sin escribir comandos (ver abajo) |
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

Las playlists son **de cada usuario** y funcionan en cualquier servidor donde esté el bot. Se pueden hacer **públicas** (🌐) para que otros las vean, reproduzcan o copien indicando tu usuario.

| Comando | Alias | Descripción |
|---|---|---|
| `/playlist list [usuario]` | `pl` | Tus playlists, o las públicas de otro usuario |
| `/playlist create <nombre>` | `new` | Crea una playlist |
| `/playlist delete <nombre>` | `del` | Elimina una playlist |
| `/playlist show <nombre> [usuario]` | `view` | Muestra sus canciones (con usuario: una playlist pública suya) |
| `/playlist add <nombre> [búsqueda]` | — | Añade la canción actual o una búsqueda o enlace (las playlists de Spotify, YouTube… se añaden enteras) |
| `/playlist import <enlace> [nombre]` | — | Crea una playlist con todas las canciones de una playlist o álbum (YouTube, Spotify, Deezer…). Si ya tienes una con ese nombre, las añade |
| `/playlist savequeue <nombre>` | `sq` | Guarda la canción actual y la cola |
| `/playlist remove <nombre> <posición>` | `rm` | Quita una canción |
| `/playlist play <nombre> [usuario] [mezclar]` | `load` | Añade la playlist a la cola (con usuario: una playlist pública suya) |
| `/playlist share <nombre> [pública]` | `public` | Hace la playlist pública o privada (sin valor: cambia) |
| `/playlist copy <usuario> <nombre> [nuevo nombre]` | `clone` | Copia la playlist pública de otra persona en las tuyas |

---

## 📚 Biblioteca de archivos

Cada servidor tiene una biblioteca de audios subidos desde Discord (mp3, flac, wav, ogg, opus, m4a, aac, webm…). El bot guarda una copia, así que se pueden reproducir cuando se quiera y guardar en playlists.

| Comando | Alias | Acceso | Descripción |
|---|---|---|---|
| `/upload <archivo> [título]` | `subir` | 🎧 | Guarda el archivo en la biblioteca. Sin título se usa el de sus etiquetas o el nombre del archivo |
| `/library list` | `lib`, `biblioteca` | 🟢 | Lista los archivos y el espacio usado |
| `/library play <archivo> [next]` | `p` | 🟢 | Reproduce un archivo (con autocompletado) |
| `/library playall [mezclar]` | `all` | 🟢 | Añade toda la biblioteca a la cola |
| `/library rename <archivo> <título>` | — | 🎧 | Cambia el título |
| `/library delete <archivo>` | `del` | 🎧 | Borra el archivo |

🎧 = administradores, *Gestionar servidor* o rol DJ. Con prefijo, adjunta el archivo al mensaje: `hm!upload Mi intro`.

- **`/play` con un archivo adjunto** lo reproduce al momento sin guardarlo. Ese enlace de Discord caduca en ~24 h, así que no se puede añadir a playlists: para conservarlo usa `/upload`.
- En el **canal de peticiones** basta con soltar el archivo.
- Límites (`config.yml → library`): 25 MB por archivo, 500 MB y 200 archivos por servidor. Discord limita las subidas a 10 MB sin Nitro.
- También desde `/menu` → 📚 Biblioteca.

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
| 3 | 🎛️ Menú de **filtro**: elige un preset o *Sin filtro* |
| 4 | ⏭️ Menú **Saltar a…**: las próximas 25 canciones de la cola |

Los botones y menús respetan los mismos permisos que su comando equivalente (DJ, votación…). Los emojis se cambian en `config.yml → emojis`.

## 🧭 Menú `/menu`

Abre un menú que solo ves tú, con un desplegable para cambiar de sección:

| Sección | Qué se puede hacer |
|---|---|
| 🎵 Reproductor | Canción actual y todos los controles del panel; **➕ Añadir** abre un formulario para escribir una canción o enlace |
| 📜 Cola | Ver la cola por páginas, saltar a una canción, quitarla, mezclar o vaciar |
| 🎛️ Filtros | Elegir un preset, subir o bajar la velocidad y quitar los filtros |
| 📁 Mis playlists | Elegir una playlist para reproducirla (normal o mezclada), añadir la canción actual, hacerla pública o privada, borrarla o crear una nueva |
| 📚 Biblioteca | Reproducir un archivo subido o toda la biblioteca mezclada; borrar archivos (DJ o admins) |
| ⚙️ Ajustes del servidor | Solo con *Gestionar servidor*: idioma, rol DJ, volumen inicial, votación, anuncios y autoplay |

Cada acción comprueba los mismos permisos que su comando (canal de voz, rol DJ…). El menú se desactiva tras 10 minutos sin usarlo; vuelve a abrirlo con `/menu`.
