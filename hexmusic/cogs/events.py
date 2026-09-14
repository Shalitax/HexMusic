"""Eventos de Lavalink y Discord: panel, inactividad, 24/7 y canal de peticiones."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import discord
import wavelink
from discord.ext import commands

from ..checks import get_player
from ..core.panel import refresh_panel
from ..core.playback import enqueue, ensure_player
from ..errors import HexError
from ..player import HexPlayer
from ..ui import embeds
from ..utils.formatting import escape, truncate

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.events")


class Events(commands.Cog):
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self._restored = False
        self._tasks: set[asyncio.Task[None]] = set()

    def _spawn(self, coro) -> None:  # type: ignore[no-untyped-def]
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _notify(self, guild: discord.Guild, channel: discord.abc.Messageable | None, key: str, **kwargs: object) -> None:
        if channel is None:
            return
        settings = await self.bot.db.get_guild(guild.id)
        in_request_channel = settings.request_channel_id is not None and getattr(channel, "id", None) == settings.request_channel_id
        delete_after = float(self.bot.config.request_channel.delete_after) if in_request_channel else None
        text = await self.bot.tr(guild, key, **kwargs)
        try:
            await channel.send(embed=embeds.info_embed(self.bot, text), delete_after=delete_after)
        except discord.HTTPException:
            pass

    # ───── Nodos ─────

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        log.info("Nodo Lavalink %r listo (sesión reanudada: %s)", payload.node.identifier, payload.resumed)
        if not self._restored:
            self._restored = True
            self._spawn(self._restore_247())

    @commands.Cog.listener()
    async def on_wavelink_node_disconnected(self, payload: wavelink.NodeDisconnectedEventPayload) -> None:
        log.warning("Nodo Lavalink %r desconectado; wavelink intentará reconectar.", payload.node.identifier)

    async def _restore_247(self) -> None:
        await self.bot.wait_until_ready()
        if not self.bot.feature("stay_247"):
            return
        for settings in await self.bot.db.guilds_with_247():
            guild = self.bot.get_guild(settings.guild_id)
            if guild is None or guild.voice_client is not None or settings.stay_channel_id is None:
                continue
            channel = guild.get_channel(settings.stay_channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                continue
            try:
                player = await channel.connect(cls=HexPlayer, self_deaf=bool(self.bot.config.player.self_deaf), timeout=15)
                await self.bot.setup_player(player, None)  # type: ignore[arg-type]
                log.info("Modo 24/7 restaurado en %s (%s)", guild.name, channel.name)
            except Exception as exc:  # noqa: BLE001
                log.warning("No se pudo restaurar el modo 24/7 en %s: %s", guild.id, exc)

    # ───── Pistas ─────

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload) -> None:
        player = payload.player
        if not isinstance(player, HexPlayer) or player.guild is None:
            return
        player.skip_votes.clear()
        await refresh_panel(self.bot, player.guild, player)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload) -> None:
        player = payload.player
        if not isinstance(player, HexPlayer) or player.guild is None:
            return
        # Se espera un momento por si el autoplay o la cola inician otra canción
        await asyncio.sleep(1.5)
        if player.connected and player.current is None and not player.queue:
            await refresh_panel(self.bot, player.guild, player, idle=True)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload) -> None:
        player = payload.player
        if not isinstance(player, HexPlayer) or player.guild is None:
            return
        error = str(payload.exception.get("message") or payload.exception.get("cause") or "?")
        log.warning("Error reproduciendo %r en %s: %s", payload.track.title, player.guild.id, error)
        await self._notify(player.guild, player.text_channel, "errors.track_failed",
                           title=escape(truncate(payload.track.title, 80)), error=truncate(error, 200))

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload) -> None:
        player = payload.player
        if isinstance(player, HexPlayer) and player.current is not None:
            log.warning("Pista atascada (%s ms): %r; se salta.", payload.threshold, payload.track.title)
            await player.skip(force=True)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player) -> None:
        if not isinstance(player, HexPlayer) or player.guild is None or player.stay_247:
            return
        guild, channel = player.guild, player.text_channel
        player.cancel_empty_task()
        await player.disconnect()
        await refresh_panel(self.bot, guild, player, idle=True)
        await self._notify(guild, channel, "music.left_inactive")

    # ───── Canal de voz vacío ─────

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState,
                                    after: discord.VoiceState) -> None:
        guild = member.guild
        if self.bot.user is not None and member.id == self.bot.user.id:
            if before.channel is not None and after.channel is None:
                player = get_player(guild)
                if player is not None:
                    player.cancel_empty_task()
                await refresh_panel(self.bot, guild, player, idle=True)
            return

        player = get_player(guild)
        if player is None or player.channel is None:
            return
        channel_id = player.channel.id
        if not ((before.channel and before.channel.id == channel_id) or (after.channel and after.channel.id == channel_id)):
            return

        if player.listeners:
            player.cancel_empty_task()
            if player.paused_by_empty:
                player.paused_by_empty = False
                if player.paused:
                    await player.pause(False)
        elif player.empty_task is None:
            player.empty_task = asyncio.create_task(self._handle_empty(player))

    async def _handle_empty(self, player: HexPlayer) -> None:
        cfg = self.bot.config.player
        try:
            if cfg.pause_when_empty and player.current is not None and not player.paused:
                await player.pause(True)
                player.paused_by_empty = True

            timeout = int(cfg.empty_channel_timeout)
            if not timeout or player.stay_247:
                return
            await asyncio.sleep(timeout)
            if player.listeners or player.stay_247 or not player.connected or player.guild is None:
                return

            guild, channel = player.guild, player.text_channel
            await player.disconnect()
            await refresh_panel(self.bot, guild, player, idle=True)
            await self._notify(guild, channel, "music.left_empty")
        except wavelink.WavelinkException as exc:
            log.debug("Error gestionando canal vacío: %s", exc)
        finally:
            if player.empty_task is asyncio.current_task():
                player.empty_task = None

    # ───── Canal de peticiones ─────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not self.bot.feature("request_channel"):
            return
        settings = await self.bot.db.get_guild(message.guild.id)
        if settings.request_channel_id is None or message.channel.id != settings.request_channel_id:
            return

        delete_after = float(self.bot.config.request_channel.delete_after)
        ctx = await self.bot.get_context(message)
        if ctx.valid:  # es un comando de texto: lo procesa el bot normalmente
            await message.delete(delay=delete_after)
            return

        query = message.content.strip() or (message.attachments[0].url if message.attachments else "")
        try:
            await message.delete(delay=0.5)
        except discord.HTTPException:
            pass
        if not query or not isinstance(message.author, discord.Member):
            return

        lang = await self.bot.lang_for(message.guild.id)
        try:
            async with message.channel.typing():
                player = await ensure_player(self.bot, message.author, message.channel)
                result = await enqueue(self.bot, player, message.author, query)
            embed = embeds.enqueue_embed(self.bot, lang, result)
        except HexError as exc:
            embed = embeds.error_embed(self.bot, self.bot.i18n.t(lang, exc.key, **exc.kwargs))
        except Exception:  # noqa: BLE001
            log.exception("Error en el canal de peticiones de %s", message.guild.id)
            embed = embeds.error_embed(self.bot, self.bot.i18n.t(lang, "errors.unexpected"))

        try:
            await message.channel.send(embed=embed, delete_after=delete_after)
        except discord.HTTPException:
            pass


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Events(bot))
