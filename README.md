<div align="center">

# 🎶 HexMusic

**Bot de música para Discord con la máxima calidad de audio, soporte multiplataforma y personalización total.**

YouTube · YouTube Music · Spotify · Apple Music · Deezer · Tidal · Qobuz · SoundCloud · Bandcamp · Twitch · Vimeo · radios por URL

`Python 3.10+` · `discord.py 2.7` · `wavelink 3.5` · `Lavalink 4.2` · `Docker`

</div>

---

## ✨ Características

| | |
|---|---|
| 🎧 **Audio de máxima calidad** | Lavalink 4 con Opus a calidad 10, remuestreo `HIGH`, búfer anti-cortes y paso directo sin recodificar cuando la fuente ya es Opus. Soporte para fuentes sin pérdida (Deezer FLAC, Qobuz). [Más info](docs/CALIDAD_AUDIO.md) |
| 🌐 **Multiplataforma** | Enlaces y búsquedas de YouTube, YouTube Music, Spotify, Apple Music, Deezer, Tidal, Qobuz, SoundCloud, Bandcamp, Twitch y streams HTTP. |
| 🎛️ **Panel con botones** | Anterior, pausa, saltar, parar, cola, repetir, mezclar, volumen y autoplay. Los botones siguen funcionando tras reiniciar el bot. |
| 📨 **Canal de peticiones** | `/setup` crea un canal con panel fijo: los usuarios escriben el nombre de una canción y suena. |
| 🎚️ **Filtros** | 17 presets (bassboost, nightcore, 8D, vaporwave, karaoke…), ecualizador de 15 bandas, velocidad y tono. Añade los tuyos en `config.yml`. |
| 📁 **Playlists** | Cada usuario guarda sus playlists y las reproduce en cualquier servidor. |
| ♾️ **Autoplay y 24/7** | Canciones relacionadas cuando se acaba la cola. El modo 24/7 se restaura tras un reinicio. |
| 🗳️ **Rol DJ y votaciones** | Decide qué comandos requieren rol DJ. Votación configurable para saltar canciones. |
| 📝 **Letras** | `/lyrics` con LRCLIB, sin clave de API. |
| 🌍 **Multi-idioma** | Español e inglés, por servidor. Las descripciones de los comandos slash también se traducen. Añadir un idioma es copiar un JSON. |
| ⌨️ **Slash + prefijo** | Todos los comandos funcionan como `/play` y como `hm!play`. |
| 🖥️ **Panel web** | Inicio de sesión con Discord: reproductor en vivo, cola, ajustes del servidor, estadísticas y playlists desde el navegador. [Más info](docs/PANEL_WEB.md) |
| 🦖 **Egg de Pterodactyl** | Imagen propia con Lavalink interno, variables en español, actualización automática y consola con comandos. Ver `Pterodactyl eggs/HexMusic`. |
| 🐳 **Integración fácil** | Bot + Lavalink con un solo `docker compose up -d`. |

## 🚀 Inicio rápido (Docker)

```bash
cd HexMusic
cp .env.example .env          # rellena DISCORD_TOKEN y LAVALINK_PASSWORD
docker compose up -d --build  # arranca Lavalink y el bot
docker compose logs -f bot    # comprueba que todo va bien
```

Invita el bot a tu servidor (ver [Instalación → Invitar el bot](docs/INSTALACION.md#3-invitar-el-bot)), entra en un canal de voz y escribe `/play never gonna give you up`.

> ¿Sin Docker? Sigue la [instalación manual](docs/INSTALACION.md#5-opción-b--instalación-manual-sin-docker).

## 📚 Documentación

| Guía | Contenido |
|---|---|
| [📦 Instalación](docs/INSTALACION.md) | Crear la aplicación en Discord, Docker, instalación manual, hosting 24/7 |
| [⚙️ Configuración](docs/CONFIGURACION.md) | Referencia completa de `config.yml`, `.env` y ajustes por servidor |
| [💬 Comandos](docs/COMANDOS.md) | Todos los comandos, alias, permisos y botones |
| [🌐 Fuentes de música](docs/FUENTES.md) | Activar Spotify, Apple Music, Deezer, Tidal, Qobuz y solucionar YouTube |
| [🎧 Calidad de audio](docs/CALIDAD_AUDIO.md) | Cómo se consigue la mejor calidad y cómo exprimirla |
| [🎨 Personalización](docs/PERSONALIZACION.md) | Branding, emojis, presets, idiomas, nuevos comandos |
| [🧱 Arquitectura](docs/ARQUITECTURA.md) | Cómo está construido el bot por dentro |
| [🖥️ Panel web](docs/PANEL_WEB.md) | Activar el panel, login con Discord, HTTPS, seguridad y API |
| [🛠️ Solución de problemas](docs/SOLUCION_PROBLEMAS.md) | Errores frecuentes y cómo resolverlos |

## 📂 Estructura del proyecto

```
HexMusic/
├── config.yml              ← personalización (colores, emojis, límites, funciones)
├── .env.example            ← plantilla de secretos (token, contraseñas, credenciales)
├── docker-compose.yml      ← bot + Lavalink
├── Dockerfile
├── requirements.txt
├── lavalink/
│   ├── application.yml     ← Lavalink ajustado para máxima calidad + plugins
│   └── plugins/            ← plugins descargados automáticamente
├── locales/
│   ├── es.json             ← textos en español
│   └── en.json             ← textos en inglés
├── hexmusic/
│   ├── __main__.py         ← punto de entrada (python -m hexmusic)
│   ├── bot.py              ← clase principal, errores, permisos DJ
│   ├── config.py           ← carga de config.yml + variables de entorno
│   ├── database.py         ← SQLite: ajustes por servidor y playlists
│   ├── i18n.py             ← sistema de idiomas
│   ├── player.py           ← reproductor (extiende wavelink.Player)
│   ├── checks.py           ← validaciones de canal de voz y DJ
│   ├── core/               ← reproducción, panel y presets de filtros
│   ├── ui/                 ← embeds y botones
│   ├── utils/              ← formato y letras
│   ├── web/                ← panel web (servidor, login con Discord, API y página)
│   ├── console.py          ← comandos escritos en la consola (Pterodactyl)
│   └── cogs/               ← comandos: music, filters, playlists, settings, general, events
└── docs/                   ← guías
```

## 🧩 Versiones probadas

| Componente | Versión |
|---|---|
| Lavalink | 4.2.2 (con soporte DAVE, el cifrado de voz de Discord) |
| youtube-source | 1.18.2 |
| LavaSrc | 4.8.3 |
| discord.py | 2.7.1 |
| wavelink | 3.5.2 |
| Python | 3.12 (mínimo 3.10) |

## ⚖️ Aviso

HexMusic reproduce contenido de servicios de terceros. Cada operador del bot es responsable de cumplir los términos de uso de Discord y de las plataformas que active, así como la legislación de derechos de autor de su país.
