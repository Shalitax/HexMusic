# 🎨 Personalización

HexMusic está pensado para adaptarse a cualquier marca sin tocar código. Si quieres ir más allá, añadir comandos es sencillo.

- [Branding: nombre, colores y pie](#branding-nombre-colores-y-pie)
- [Emojis y botones](#emojis-y-botones)
- [Presets de filtros](#presets-de-filtros)
- [Textos e idiomas](#textos-e-idiomas)
- [Activar o desactivar funciones](#activar-o-desactivar-funciones)
- [Permisos DJ](#permisos-dj)
- [Varios nodos de Lavalink](#varios-nodos-de-lavalink)
- [Crear un comando nuevo](#crear-un-comando-nuevo)

---

## Branding: nombre, colores y pie

```yaml
bot:
  name: "HexMusic"
  prefix: "hm!"
  status:
    type: "listening"
    text: "/play • hexservers.com"

branding:
  color: "#8B5CF6"            # color de marca
  footer: "HexMusic • Hexservers"
  footer_icon: "https://tu-cdn.com/icono.png"
  banner_url: "https://tu-cdn.com/banner.png"   # panel del canal de peticiones en reposo
  large_artwork: true         # carátula grande en el panel
  progress_bar:
    length: 18
    filled: "▰"
    head: "▰"
    empty: "▱"
```

El avatar, el nombre visible y el banner del perfil del bot se cambian en el [portal de desarrolladores](https://discord.com/developers/applications).

---

## Emojis y botones

Cambia cualquier emoji en `config.yml → emojis`. Para usar **emojis personalizados**:

1. Sube el emoji a un servidor donde esté el bot.
2. En Discord escribe `\:nombre_del_emoji:` y envía el mensaje. Obtendrás algo como `<:hexplay:1234567890>`.
3. Pégalo en la configuración:

```yaml
emojis:
  pause: "<:hexplay:1234567890>"
  skip: "<a:hexskip_animado:1234567891>"
  sources:
    spotify: "<:spotify:1234567892>"
```

**Cambiar o reordenar los botones.** La lista está en `hexmusic/ui/views.py → CONTROL_ACTIONS`. Cada entrada es `acción: (comando para permisos DJ, fila)`. Discord permite hasta 5 botones por fila.

---

## Presets de filtros

Añade tus presets en `config.yml`. Usan el [formato de filtros de Lavalink](https://lavalink.dev/api/rest#filters):

```yaml
filters:
  presets:
    hexboost:                          # nombre del preset (/filter preset hexboost)
      equalizer:                       # bandas 0 (25 Hz) … 14 (16 kHz), ganancia -0.25 a 1.0
        - { band: 0, gain: 0.2 }
        - { band: 1, gain: 0.15 }
        - { band: 13, gain: 0.1 }
      timescale: { speed: 1.0, pitch: 1.05, rate: 1.0 }
    party:
      rotation: { rotationHz: 0.1 }
      equalizer:
        - { band: 0, gain: 0.3 }
    chipmunk: null                     # elimina un preset incluido
```

Filtros disponibles:

| Filtro | Parámetros |
|---|---|
| `equalizer` | lista de `{band, gain}` |
| `timescale` | `speed`, `pitch`, `rate` |
| `karaoke` | `level`, `monoLevel`, `filterBand`, `filterWidth` |
| `tremolo` / `vibrato` | `frequency`, `depth` |
| `rotation` | `rotationHz` (efecto 8D) |
| `distortion` | `sinOffset`, `sinScale`, `cosOffset`, `cosScale`, `tanOffset`, `tanScale`, `offset`, `scale` |
| `channelMix` | `leftToLeft`, `leftToRight`, `rightToLeft`, `rightToRight` |
| `lowPass` | `smoothing` |
| `volume` | multiplicador (1.0 = 100 %) |

Los presets incluidos están en `hexmusic/core/presets.py`.

---

## Textos e idiomas

Todos los mensajes del bot están en `locales/*.json`. **Edítalos libremente** para ajustar el tono de tu marca. Después reinicia el bot o usa `hm!reloadlocales`.

### Añadir un idioma

1. Copia `locales/en.json` como `locales/pt.json`. El nombre del archivo es el código del idioma.
2. Cambia `"_meta": { "name": "Português" }` y traduce los valores. **No cambies las claves** ni los `{marcadores}`.
3. En `"_commands"` añade las traducciones de las descripciones de los comandos slash. Las claves son los textos en inglés, y puedes copiar la lista de `es.json`:
   ```json
   "_commands": {
     "Play a song, playlist or link from any supported platform": "Toca uma música, playlist ou link de qualquer plataforma"
   }
   ```
4. Reinicia el bot. Los servidores lo eligen con `/settings language pt`. Discord muestra automáticamente las descripciones traducidas a quien tenga su cliente en portugués.

> El código de idioma debe coincidir con el prefijo de los [locales de Discord](https://discord.com/developers/docs/reference#locales): `pt` sirve para `pt-BR`, `es` para `es-ES` y `es-419`, etc.

---

## Activar o desactivar funciones

**Funciones sueltas**, en `config.yml → features`:

```yaml
features:
  autoplay: true
  stay_247: false        # desactiva el 24/7 en todo el bot
  lyrics: true
  request_channel: true
  vote_skip: true
```

**Módulos completos:** quita la línea correspondiente de `bot.extensions`:

```yaml
bot:
  extensions:
    - hexmusic.cogs.general
    - hexmusic.cogs.events      # necesario: paneles, 24/7, canal de peticiones
    - hexmusic.cogs.music       # necesario
    - hexmusic.cogs.filters
    # - hexmusic.cogs.playlists  ← playlists desactivadas
    - hexmusic.cogs.settings
```

---

## Permisos DJ

```yaml
dj:
  commands:
    - stop
    - volume
    - filter    # todos los /filter …
    - "247"
```

Quita un comando de la lista para que lo pueda usar cualquiera, o añade otros (`pause`, `resume`, `previous`, `replay`, `skip`…) para restringirlos.

---

## Varios nodos de Lavalink

Con muchos servidores, reparte la carga entre varios Lavalink. Cada reproductor nuevo va al nodo con menos reproductores.

```yaml
lavalink:
  nodes:
    - identifier: "eu-1"
      uri: "http://10.0.0.10:2333"
      password: "${LAVALINK_PASSWORD}"
    - identifier: "eu-2"
      uri: "http://10.0.0.11:2333"
      password: "${LAVALINK_PASSWORD}"
```

Todos los nodos deben usar el mismo `application.yml` (plugins y credenciales).

---

## Crear un comando nuevo

Ejemplo: un **temporizador de apagado** (`/sleep 30`) que detiene la música pasados X minutos.

**1. Crea `hexmusic/cogs/sleep.py`:**

```python
"""Temporizador de apagado."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.panel import refresh_panel

if TYPE_CHECKING:
    from ..bot import HexMusic


class SleepTimer(commands.Cog):
    """Sleep timer"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self.timers: dict[int, asyncio.Task[None]] = {}

    @commands.hybrid_command(name="sleep", description="Stop the music after some minutes")
    @app_commands.describe(minutes="Minutes until the music stops")
    @commands.guild_only()
    @music_check()  # el usuario debe estar en el canal de voz del bot
    async def sleep(self, ctx: commands.Context, minutes: commands.Range[int, 1, 240]) -> None:
        if old := self.timers.pop(ctx.guild.id, None):
            old.cancel()
        self.timers[ctx.guild.id] = asyncio.create_task(self._stop_later(ctx.guild, minutes))
        await self.bot.respond(ctx, "sleep.set", minutes=minutes)

    async def _stop_later(self, guild: discord.Guild, minutes: int) -> None:
        await asyncio.sleep(minutes * 60)
        self.timers.pop(guild.id, None)
        player = get_player(guild)
        if player is not None:
            await player.disconnect()
            await refresh_panel(self.bot, guild, player, idle=True)


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(SleepTimer(bot))
```

**2. Añade los textos** en `locales/es.json` y `locales/en.json`:

```json
"sleep": {
  "set": "😴 La música se detendrá en **{minutes}** minutos."
},
"_commands": {
  "Stop the music after some minutes": "Detiene la música pasados unos minutos",
  "Minutes until the music stops": "Minutos hasta que se detenga la música"
}
```

**3. Actívalo** en `config.yml`:

```yaml
bot:
  extensions:
    # …
    - hexmusic.cogs.sleep
```

**4. Reinicia.** Si los comandos slash no aparecen enseguida, usa `hm!sync`.

### Piezas útiles para tus comandos

| Pieza | Para qué |
|---|---|
| `music_check(voice, player, playing, dj)` | Valida canal de voz, reproductor, canción sonando y permisos DJ |
| `get_player(guild)` | Reproductor del servidor (`HexPlayer`) o `None` |
| `ensure_player(bot, member, channel)` | Conecta el bot al canal del usuario si hace falta |
| `enqueue(bot, player, member, query)` | Busca y añade a la cola (con límites y autoplay) |
| `bot.respond(ctx, "clave", **valores)` | Respuesta traducida con el estilo del bot |
| `raise HexError("clave", **valores)` | Error traducido que se muestra al usuario |
| `bot.db.get_guild(id)` / `update_guild(id, …)` | Ajustes del servidor |
| `refresh_panel(bot, guild, player)` | Actualiza el panel "reproduciendo ahora" |
