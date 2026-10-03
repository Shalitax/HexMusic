"""Cola persistente: guarda lo que suena en cada servidor y lo recupera tras un reinicio.

Se guarda una foto de cada reproductor (canción actual y posición, cola, volumen, repetición, filtros...)
cada ``player.persist_interval`` segundos y al apagar el bot. Al volver a arrancar, en cuanto Lavalink está
listo, el bot vuelve a cada canal y continúa donde lo dejó. Así un reinicio o una actualización automática
del egg no corta la música.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

import discord
import wavelink

from ..player import HexPlayer
from ..ui.embeds import info_embed

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.sessions")

# Una sesión más antigua que esto no se restaura (el bot estuvo apagado demasiado tiempo)
MAX_AGE_SECONDS = 6 * 3600


def _track_data(track: wavelink.Playable) -> dict[str, Any]:
    data = dict(track.raw_data)
    data["userData"] = {}
    return {"data": data, "requester_id": HexPlayer.requester_id(track)}


def _build_track(item: dict[str, Any]) -> wavelink.Playable | None:
    try:
        track = wavelink.Playable(item["data"])
    except (KeyError, TypeError):
        return None
    if item.get("requester_id"):
        track.extras = {"requester_id": int(item["requester_id"])}
    return track


def snapshot(player: HexPlayer, *, max_queue: int = 0) -> dict[str, Any] | None:
    """Estado del reproductor. ``None`` si no hay nada que recuperar."""
    if player.guild is None or player.channel is None or not player.connected:
        return None
    current = player.current
    queue = list(player.queue)
    if current is None and not queue:
        return None
    if max_queue:
        queue = queue[:max_queue]

    position = player.position if current is not None and current.is_seekable and not current.is_stream else 0
    return {
        "channel_id": player.channel.id,
        "text_channel_id": getattr(player.text_channel, "id", None),
        "current": _track_data(current) if current is not None else None,
        "position": int(position),
        "paused": bool(player.paused and not player.paused_by_empty),
        "volume": player.volume,
        "loop": player.queue.mode.name,
        "autoplay": player.autoplay_enabled,
        "filters": player.filters(),
        "filter_name": player.filter_name,
        "queue": [_track_data(track) for track in queue],
        "saved_at": int(time.time()),
    }


class SessionStore:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        cfg = bot.config.player
        self.enabled = bool(cfg.persist_queue)
        self.interval = max(10, int(cfg.persist_interval or 30))
        self._task: asyncio.Task[None] | None = None
        self._restored = False

    def _players(self) -> list[HexPlayer]:
        return [player for node in wavelink.Pool.nodes.values() for player in node.players.values()
                if isinstance(player, HexPlayer)]

    async def save(self) -> int:
        """Guarda la foto de todos los reproductores y borra las de los servidores donde ya no suena nada."""
        max_queue = int(self.bot.config.player.max_queue_size)
        sessions: dict[int, dict[str, Any]] = {}
        for player in self._players():
            data = snapshot(player, max_queue=max_queue)
            if data is not None and player.guild is not None:
                sessions[player.guild.id] = data
        await self.bot.db.replace_sessions(sessions)
        return len(sessions)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.interval)
            try:
                await self.save()
            except Exception:  # noqa: BLE001 - el guardado periódico nunca debe parar
                log.exception("No se pudo guardar el estado de los reproductores")

    def start(self) -> None:
        if self.enabled and self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def close(self) -> None:
        """Al apagar: última foto antes de que se desconecten los reproductores."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self.enabled and self._restored:
            try:
                count = await self.save()
                if count:
                    log.info("Guardado el estado de %d reproductor(es) para recuperarlo al volver.", count)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo guardar el estado de los reproductores al apagar")

    # ───── Restauración ─────

    async def restore(self) -> set[int]:
        """Vuelve a los canales guardados. Devuelve los servidores restaurados."""
        restored: set[int] = set()
        if not self.enabled:
            self._restored = True
            return restored
        try:
            sessions = await self.bot.db.load_sessions()
            for guild_id, data in sessions.items():
                try:
                    if await self._restore_one(guild_id, data):
                        restored.add(guild_id)
                except Exception as exc:  # noqa: BLE001 - un servidor no debe impedir restaurar los demás
                    log.warning("No se pudo restaurar la música en %s: %s", guild_id, exc)
            await self.bot.db.replace_sessions({})
        finally:
            # A partir de aquí las fotos nuevas sustituyen a las antiguas
            self._restored = True
            self.start()
        return restored

    async def _restore_one(self, guild_id: int, data: dict[str, Any]) -> bool:
        bot = self.bot
        guild = bot.get_guild(guild_id)
        if guild is None or guild.voice_client is not None:
            return False
        if time.time() - int(data.get("saved_at") or 0) > MAX_AGE_SECONDS:
            return False
        channel = guild.get_channel(int(data.get("channel_id") or 0))
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            return False

        settings = await bot.db.get_guild(guild_id)
        listeners = [member for member in channel.members if not member.bot]
        if not listeners and not settings.stay_247:
            return False  # nadie lo escucharía: el bot entraría para salir enseguida
        permissions = channel.permissions_for(guild.me)
        if not permissions.connect or not permissions.speak:
            return False

        current = _build_track(data["current"]) if data.get("current") else None
        queue = [track for item in data.get("queue") or [] if (track := _build_track(item)) is not None]
        if current is None and not queue:
            return False

        text_channel = guild.get_channel(int(data.get("text_channel_id") or 0))
        if not isinstance(text_channel, discord.abc.Messageable):
            text_channel = None

        player = await channel.connect(cls=HexPlayer, self_deaf=bool(bot.config.player.self_deaf), timeout=15)
        await bot.setup_player(player, text_channel)

        try:
            player.queue.mode = wavelink.QueueMode[str(data.get("loop") or "normal")]
        except KeyError:
            pass
        if bot.feature("autoplay"):
            player.autoplay_enabled = bool(data.get("autoplay"))
        volume = data.get("volume")
        if isinstance(volume, int) and 0 <= volume <= int(bot.config.player.max_volume):
            await player.set_volume(volume)
        if data.get("filters"):
            try:
                await player.set_filters(wavelink.Filters(data=data["filters"]))
                player.filter_name = data.get("filter_name")
            except Exception:  # noqa: BLE001 - un filtro inválido no debe impedir la reproducción
                log.debug("No se pudieron restaurar los filtros en %s", guild_id, exc_info=True)

        player.queue.put(queue)
        player.sync_autoplay()
        if current is None:
            current = player.queue.get()
            start = 0
        else:
            start = max(0, int(data.get("position") or 0))
            if current.is_stream or not current.is_seekable or start >= current.length - 2000:
                start = 0
        await player.play(current, start=start, paused=bool(data.get("paused")))
        log.info("Música restaurada en %s (%s): %d canción(es) en cola.", guild.name, channel.name, len(player.queue))

        if text_channel is not None:
            lang = await bot.lang_for(guild_id)
            try:
                await text_channel.send(embed=info_embed(bot, bot.i18n.t(lang, "music.session_restored")), delete_after=30)
            except discord.HTTPException:
                pass
        return True
