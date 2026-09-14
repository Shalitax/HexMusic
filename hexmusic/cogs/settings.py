"""Ajustes por servidor y canal de peticiones."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..checks import get_player
from ..core.panel import build_panel_embed
from ..errors import HexError
from ..ui import embeds
from ..utils.formatting import escape

if TYPE_CHECKING:
    from ..bot import HexMusic


class Settings(commands.Cog):
    """Server settings"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    async def _show(self, ctx: commands.Context) -> None:
        cfg = self.bot.config
        settings = await self.bot.db.get_guild(ctx.guild.id)
        lang = await self.bot.lang_for(ctx.guild.id)

        def t(key: str, **kwargs: object) -> str:
            return self.bot.i18n.t(lang, key, **kwargs)

        def state(value: bool) -> str:
            return t("common.on") if value else t("common.off")

        vote_skip = settings.vote_skip if settings.vote_skip is not None else bool(cfg.vote_skip.default_enabled)
        announce = settings.announce if settings.announce is not None else bool(cfg.player.announce_tracks)
        volume = settings.default_volume if settings.default_volume is not None else int(cfg.player.default_volume)
        stay = state(settings.stay_247) + (f" · <#{settings.stay_channel_id}>" if settings.stay_247 and settings.stay_channel_id else "")

        embed = embeds.make_embed(self.bot, title=t("settings.title", guild=escape(ctx.guild.name)))
        embed.add_field(name=t("settings.language"), value=f"{self.bot.i18n.language_name(lang)} (`{lang}`)")
        embed.add_field(name=t("settings.prefix"), value=f"`{settings.prefix or cfg.bot.prefix}`")
        embed.add_field(name=t("settings.dj_role"), value=f"<@&{settings.dj_role_id}>" if settings.dj_role_id else t("settings.no_dj_role"))
        embed.add_field(name=t("settings.default_volume"), value=f"{volume}%")
        embed.add_field(name=t("settings.vote_skip"), value=state(vote_skip))
        embed.add_field(name=t("settings.announce"), value=state(announce))
        embed.add_field(name=t("settings.autoplay"), value=state(settings.autoplay))
        embed.add_field(name=t("settings.stay_247"), value=stay)
        embed.add_field(name=t("settings.request_channel"),
                        value=f"<#{settings.request_channel_id}>" if settings.request_channel_id else t("common.none"))
        await ctx.send(embed=embed)

    @commands.hybrid_group(name="settings", aliases=["config", "ajustes"], fallback="show", invoke_without_command=True,
                           description="Server settings for the bot")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def settings_group(self, ctx: commands.Context) -> None:
        await self._show(ctx)

    @settings_group.command(name="language", aliases=["lang", "idioma"], description="Change the bot language in this server")
    @app_commands.describe(language="Language code")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_language(self, ctx: commands.Context, language: str) -> None:
        code = language.lower().strip()
        if code not in self.bot.i18n.languages:
            raise HexError("errors.invalid_language", languages=", ".join(self.bot.i18n.languages))
        await self.bot.db.update_guild(ctx.guild.id, language=code)
        text = self.bot.i18n.t(code, "settings.language_set", language=self.bot.i18n.language_name(code))
        await ctx.send(embed=embeds.success_embed(self.bot, text))

    @settings_language.autocomplete("language")
    async def language_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        text = current.lower().strip()
        choices = []
        for code in self.bot.i18n.languages:
            name = self.bot.i18n.language_name(code)
            if text in code or text in name.lower():
                choices.append(app_commands.Choice(name=f"{name} ({code})", value=code))
        return choices[:25]

    @settings_group.command(name="prefix", description="Change the text command prefix")
    @app_commands.describe(prefix="New prefix (max. 10 characters)")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_prefix(self, ctx: commands.Context, prefix: commands.Range[str, 1, 10]) -> None:
        await self.bot.db.update_guild(ctx.guild.id, prefix=prefix.strip() or None)
        await self.bot.respond(ctx, "settings.prefix_set", prefix=escape(prefix.strip()))

    @settings_group.command(name="djrole", aliases=["dj"], description="Set or remove the DJ role")
    @app_commands.describe(role="DJ role (empty = remove)")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_djrole(self, ctx: commands.Context, role: Optional[discord.Role] = None) -> None:
        await self.bot.db.update_guild(ctx.guild.id, dj_role_id=role.id if role else None)
        if role:
            await self.bot.respond(ctx, "settings.dj_role_set", role=role.mention)
        else:
            await self.bot.respond(ctx, "settings.dj_role_cleared")

    @settings_group.command(name="volume", description="Set the default volume")
    @app_commands.describe(volume="Volume used when the bot joins")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_volume(self, ctx: commands.Context, volume: commands.Range[int, 0, 1000]) -> None:
        max_volume = int(self.bot.config.player.max_volume)
        if volume > max_volume:
            raise HexError("errors.volume_range", max=max_volume)
        await self.bot.db.update_guild(ctx.guild.id, default_volume=volume)
        await self.bot.respond(ctx, "settings.volume_set", volume=volume)

    @settings_group.command(name="voteskip", description="Turn vote skip on or off")
    @app_commands.describe(enabled="Enabled or disabled")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_voteskip(self, ctx: commands.Context, enabled: bool) -> None:
        if not self.bot.feature("vote_skip"):
            raise HexError("errors.feature_disabled")
        await self.bot.db.update_guild(ctx.guild.id, vote_skip=enabled)
        state = await self.bot.tr(ctx.guild, "common.on" if enabled else "common.off")
        await self.bot.respond(ctx, "settings.vote_skip_set", state=state)

    @settings_group.command(name="announce", description="Turn now playing announcements on or off")
    @app_commands.describe(enabled="Enabled or disabled")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_announce(self, ctx: commands.Context, enabled: bool) -> None:
        await self.bot.db.update_guild(ctx.guild.id, announce=enabled)
        state = await self.bot.tr(ctx.guild, "common.on" if enabled else "common.off")
        await self.bot.respond(ctx, "settings.announce_set", state=state)

    @settings_group.command(name="reset", description="Reset all settings to default values")
    @commands.has_guild_permissions(manage_guild=True)
    async def settings_reset(self, ctx: commands.Context) -> None:
        await self.bot.db.update_guild(ctx.guild.id, language=None, prefix=None, dj_role_id=None, default_volume=None,
                                       vote_skip=None, announce=None, autoplay=False)
        await self.bot.respond(ctx, "settings.reset")

    # ───── Canal de peticiones ─────

    @commands.hybrid_command(name="setup", description="Create the song request channel with a control panel")
    @app_commands.describe(channel="Existing channel to use (empty = create a new one)")
    @app_commands.default_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def setup_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        if not self.bot.feature("request_channel"):
            raise HexError("errors.feature_disabled")
        await ctx.defer()
        guild = ctx.guild
        lang = await self.bot.lang_for(guild.id)

        if channel is None:
            try:
                channel = await guild.create_text_channel(
                    name=str(self.bot.config.request_channel.channel_name),
                    topic=self.bot.i18n.t(lang, "settings.request_topic", name=self.bot.config.bot.name),
                    reason="HexMusic /setup",
                )
            except discord.HTTPException:
                raise HexError("errors.request_channel_create_failed") from None

        permissions = channel.permissions_for(guild.me)
        if not (permissions.send_messages and permissions.embed_links and permissions.manage_messages):
            raise HexError("errors.bot_missing_permissions", perms="Send Messages, Embed Links, Manage Messages")

        settings = await self.bot.db.get_guild(guild.id)
        if settings.request_channel_id and settings.request_message_id:
            old_channel = guild.get_channel(settings.request_channel_id)
            if isinstance(old_channel, discord.TextChannel):
                try:
                    await old_channel.get_partial_message(settings.request_message_id).delete()
                except discord.HTTPException:
                    pass

        player = get_player(guild)
        message = await channel.send(embed=build_panel_embed(self.bot, lang, guild, player), view=self.bot.controls_view)
        await self.bot.db.update_guild(guild.id, request_channel_id=channel.id, request_message_id=message.id)
        await self.bot.respond(ctx, "settings.setup_done", channel=channel.mention)

    @commands.hybrid_command(name="unsetup", description="Remove the song request channel setup")
    @app_commands.default_permissions(manage_guild=True)
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def unsetup_channel(self, ctx: commands.Context) -> None:
        settings = await self.bot.db.get_guild(ctx.guild.id)
        if settings.request_channel_id and settings.request_message_id:
            channel = ctx.guild.get_channel(settings.request_channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await channel.get_partial_message(settings.request_message_id).delete()
                except discord.HTTPException:
                    pass
        await self.bot.db.update_guild(ctx.guild.id, request_channel_id=None, request_message_id=None)
        await self.bot.respond(ctx, "settings.setup_removed")


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Settings(bot))
