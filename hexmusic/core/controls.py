"""Acciones de control del reproductor compartidas por los botones del panel, sus menús y /menu.

Cada acción comprueba los mismos permisos que su comando equivalente (mismo canal de voz y rol DJ si el
comando figura en ``dj.commands``) y lanza ``HexError`` con un mensaje traducible si algo no cuadra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
import wavelink

from ..errors import HexError
from ..player import HexPlayer
from ..utils.formatting import track_link
from .panel import refresh_panel
from .playback import skip_or_vote
from .presets import build_filters, get_presets

if TYPE_CHECKING:
    from ..bot import HexMusic

# acción → comando equivalente para los permisos DJ (None = cualquiera en el canal)
ACTION_COMMANDS: dict[str, str | None] = {
    "previous": "previous",
    "pause": "pause",
    "skip": "skip",
    "stop": "stop",
    "queue": None,
    "loop": "loop",
    "shuffle": "shuffle",
    "volume_down": "volume",
    "volume_up": "volume",
    "autoplay": "autoplay",
    "filter": "filter",
    "speed": "filter",
    "skipto": "skipto",
    "remove": None,  # cada uno puede quitar sus canciones; las de otros requieren DJ (se comprueba abajo)
    "clear": "clear",
}

SPEED_STEP = 0.1

Notice = tuple[str, dict[str, Any]]


async def controllable_player(bot: HexMusic, member: discord.Member, action: str) -> HexPlayer:
    """Reproductor del servidor si ``member`` puede ejecutar ``action``; si no, ``HexError``."""
    player = member.guild.voice_client
    if not isinstance(player, HexPlayer) or not player.connected:
        raise HexError("errors.no_player")
    if member.voice is None or player.channel is None or member.voice.channel != player.channel:
        raise HexError("errors.not_same_channel", channel=player.channel.mention if player.channel else "—")
    command = ACTION_COMMANDS.get(action)
    if command and not await bot.can_use(member, player, command):
        raise HexError("errors.dj_only")
    return player


def queue_value(index: int, track: wavelink.Playable) -> str:
    """Valor de una opción de menú que apunta a una canción de la cola (posición + identificador)."""
    return f"{index}:{track.identifier}"[:100]


def resolve_queue_value(player: HexPlayer, value: str) -> int:
    """Posición actual (desde 1) de la canción elegida en un menú, aunque la cola haya cambiado desde entonces."""
    raw_index, _, identifier = str(value).partition(":")
    try:
        index = int(raw_index)
    except ValueError:
        raise HexError("errors.bad_argument") from None
    queue = list(player.queue)
    if 1 <= index <= len(queue) and queue[index - 1].identifier == identifier:
        return index
    for position, track in enumerate(queue, start=1):
        if track.identifier == identifier:
            return position
    raise HexError("errors.queue_changed")


async def perform(bot: HexMusic, player: HexPlayer, member: discord.Member, action: str,
                  value: str | None = None) -> Notice | None:
    """Ejecuta ``action``. Devuelve un aviso opcional ``(clave, parámetros)`` para mostrar a quien la pidió."""
    try:
        return await _perform(bot, player, member, action, value)
    except wavelink.LavalinkException as exc:
        raise HexError("errors.lavalink", error=exc.error) from exc


async def _perform(bot: HexMusic, player: HexPlayer, member: discord.Member, action: str,
                   value: str | None) -> Notice | None:
    guild = member.guild

    if action == "previous":
        if await player.go_previous() is None:
            raise HexError("errors.no_previous")
    elif action == "pause":
        if player.current is None:
            raise HexError("errors.nothing_playing")
        player.paused_by_empty = False
        await player.pause(not player.paused)
    elif action == "skip":
        if player.current is None:
            raise HexError("errors.nothing_playing")
        skipped, votes, needed = await skip_or_vote(bot, player, member)
        if not skipped:
            return "music.vote_registered", {"votes": votes, "needed": needed}
    elif action == "stop":
        await player.stop_and_clear()
        await refresh_panel(bot, guild, player, idle=True)
    elif action == "loop":
        player.cycle_loop()
    elif action == "shuffle":
        if len(player.queue) < 2:
            raise HexError("errors.queue_empty")
        player.queue.shuffle()
    elif action in ("volume_down", "volume_up"):
        step = int(bot.config.player.volume_step) * (1 if action == "volume_up" else -1)
        await player.set_volume(max(0, min(int(bot.config.player.max_volume), player.volume + step)))
    elif action == "autoplay":
        if not bot.feature("autoplay"):
            raise HexError("errors.feature_disabled")
        player.autoplay_enabled = not player.autoplay_enabled
        await bot.db.update_guild(guild.id, autoplay=player.autoplay_enabled)
        if player.current is not None:
            player.sync_autoplay()
    elif action == "filter":
        name = str(value or "").lower().strip()
        if name in ("", "none"):
            await player.apply_filters(wavelink.Filters(), None)
        else:
            payload = get_presets(bot.config).get(name)
            if payload is None:
                raise HexError("errors.preset_not_found", name=name)
            await player.apply_filters(build_filters(payload), name)
    elif action == "speed":
        if player.current is None:
            raise HexError("errors.nothing_playing")
        filters = player.filters
        current = float(filters.timescale.payload.get("speed") or 1.0)
        step = SPEED_STEP if value == "up" else -SPEED_STEP
        speed = round(min(2.0, max(0.5, current + step)), 2)
        filters.timescale.set(speed=speed)
        await player.apply_filters(filters, "custom")
        return "filters.speed_set", {"value": f"{speed:.2f}"}
    elif action in ("skipto", "remove"):
        if not player.queue:
            raise HexError("errors.queue_empty")
        index = resolve_queue_value(player, str(value or ""))
        track = player.queue[index - 1]
        if action == "remove":
            if HexPlayer.requester_id(track) != member.id and not await bot.can_use(member, player, "remove"):
                raise HexError("errors.dj_only")
            player.queue.delete(index - 1)
            return "music.removed", {"track": track_link(track)}
        if index > 1:
            del player.queue[: index - 1]
        if player.current is not None:
            await player.skip(force=True)
        else:
            await player.play(player.queue.get())
    elif action == "clear":
        count = len(player.queue)
        if not count:
            raise HexError("errors.queue_empty")
        player.queue.clear()
        return "music.cleared", {"count": count}
    else:
        raise HexError("errors.bad_argument")
    return None
