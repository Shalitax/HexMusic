"""Panel "reproduciendo ahora": mensaje con botones en el canal de peticiones o en el chat."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord

from ..ui import embeds

if TYPE_CHECKING:
    from ..bot import HexMusic
    from ..player import HexPlayer

log = logging.getLogger("hexmusic.panel")


def build_panel_embed(bot: HexMusic, lang: str, guild: discord.Guild, player: HexPlayer | None, *,
                      idle: bool = False) -> discord.Embed:
    if idle or player is None or player.current is None:
        return embeds.idle_embed(bot, lang, guild)
    return embeds.now_playing_embed(bot, lang, player, player.current)


async def refresh_panel(bot: HexMusic, guild: discord.Guild, player: HexPlayer | None, *, idle: bool = False) -> None:
    settings = await bot.db.get_guild(guild.id)
    lang = await bot.lang_for(guild.id)

    # 1) Canal de peticiones: se edita siempre el mismo mensaje fijo
    if bot.feature("request_channel") and settings.request_channel_id and settings.request_message_id:
        channel = guild.get_channel(settings.request_channel_id)
        if isinstance(channel, discord.TextChannel):
            embed = build_panel_embed(bot, lang, guild, player, idle=idle)
            try:
                await channel.get_partial_message(settings.request_message_id).edit(
                    content=None, embed=embed, view=bot.controls_view
                )
                return
            except discord.NotFound:
                log.info("El panel del canal de peticiones de %s ya no existe; se desactiva.", guild.id)
            except discord.HTTPException as exc:
                log.warning("No se pudo actualizar el panel de %s: %s", guild.id, exc)
                return
        await bot.db.update_guild(guild.id, request_channel_id=None, request_message_id=None)

    # 2) Anuncio en el canal de texto donde se pidió la música
    if player is None:
        return
    announce = settings.announce if settings.announce is not None else bool(bot.config.player.announce_tracks)
    if not announce:
        return

    if idle or player.current is None:
        message, player.panel_message = player.panel_message, None
        if message is not None:
            try:
                await message.edit(embed=embeds.idle_embed(bot, lang, guild), view=None)
            except discord.HTTPException:
                pass
        return

    if player.text_channel is None:
        return

    old = player.panel_message
    if old is not None:
        try:
            if bot.config.player.delete_old_now_playing:
                await old.delete()
            else:
                await old.edit(view=None)
        except discord.HTTPException:
            pass

    try:
        player.panel_message = await player.text_channel.send(
            embed=embeds.now_playing_embed(bot, lang, player, player.current), view=bot.controls_view
        )
    except discord.HTTPException as exc:
        player.panel_message = None
        log.debug("No se pudo enviar el panel en %s: %s", guild.id, exc)


async def edit_panel(bot: HexMusic, guild: discord.Guild, player: HexPlayer | None) -> None:
    """Actualiza los paneles existentes sin enviar mensajes nuevos (p. ej. tras un cambio desde la web)."""
    settings = await bot.db.get_guild(guild.id)
    lang = await bot.lang_for(guild.id)
    embed = build_panel_embed(bot, lang, guild, player)

    if bot.feature("request_channel") and settings.request_channel_id and settings.request_message_id:
        channel = guild.get_channel(settings.request_channel_id)
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.get_partial_message(settings.request_message_id).edit(embed=embed, view=bot.controls_view)
            except discord.HTTPException:
                pass

    if player is not None and player.panel_message is not None and player.current is not None:
        try:
            await player.panel_message.edit(embed=embed)
        except discord.HTTPException:
            player.panel_message = None
