"""Canal de peticiones (panel fijo con botones). Lo usan /setup, /unsetup y el panel web."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from ..checks import get_player
from ..errors import HexError
from .panel import build_panel_embed

if TYPE_CHECKING:
    from ..bot import HexMusic


async def setup_request_channel(bot: HexMusic, guild: discord.Guild,
                                channel: discord.TextChannel | None = None) -> discord.TextChannel:
    """Publica el panel en ``channel`` (o en un canal nuevo) y lo guarda como canal de peticiones."""
    if not bot.feature("request_channel"):
        raise HexError("errors.feature_disabled")
    lang = await bot.lang_for(guild.id)

    if channel is None:
        try:
            channel = await guild.create_text_channel(
                name=str(bot.config.request_channel.channel_name),
                topic=bot.i18n.t(lang, "settings.request_topic", name=bot.config.bot.name),
                reason="HexMusic /setup",
            )
        except discord.HTTPException:
            raise HexError("errors.request_channel_create_failed") from None

    permissions = channel.permissions_for(guild.me)
    if not (permissions.send_messages and permissions.embed_links and permissions.manage_messages):
        raise HexError("errors.bot_missing_permissions", perms="Send Messages, Embed Links, Manage Messages")

    await _delete_panel(bot, guild)
    player = get_player(guild)
    message = await channel.send(embed=build_panel_embed(bot, lang, guild, player), view=bot.controls_for(lang, player))
    await bot.db.update_guild(guild.id, request_channel_id=channel.id, request_message_id=message.id)
    return channel


async def remove_request_channel(bot: HexMusic, guild: discord.Guild) -> None:
    """Borra el panel (el canal se conserva) y deja de usar el canal de peticiones."""
    await _delete_panel(bot, guild)
    await bot.db.update_guild(guild.id, request_channel_id=None, request_message_id=None)


async def _delete_panel(bot: HexMusic, guild: discord.Guild) -> None:
    settings = await bot.db.get_guild(guild.id)
    if not (settings.request_channel_id and settings.request_message_id):
        return
    channel = guild.get_channel(settings.request_channel_id)
    if isinstance(channel, discord.TextChannel):
        try:
            await channel.get_partial_message(settings.request_message_id).delete()
        except discord.HTTPException:
            pass
