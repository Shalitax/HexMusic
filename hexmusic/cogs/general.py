"""Comandos generales: ayuda, latencia, estadísticas e invitación."""

from __future__ import annotations

import platform
import time
from typing import TYPE_CHECKING

import discord
import wavelink
from discord.ext import commands

from .. import __version__
from ..checks import get_player
from ..core.playback import connected_nodes
from ..ui import embeds
from ..ui.views import Paginator
from ..utils.formatting import format_uptime

if TYPE_CHECKING:
    from ..bot import HexMusic

CATEGORY_ORDER = ("Music", "Filters", "Playlists", "Settings", "General")


class General(commands.Cog):
    """General commands"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", aliases=["h", "ayuda", "commands"], description="Show all commands")
    async def help(self, ctx: commands.Context) -> None:
        lang = await self.bot.lang_for(ctx.guild.id if ctx.guild else None)
        t = self.bot.i18n.t
        prefix = str(self.bot.config.bot.prefix)
        if ctx.guild is not None:
            prefix = (await self.bot.db.get_guild(ctx.guild.id)).prefix or prefix

        def order(cog: commands.Cog) -> int:
            name = cog.qualified_name
            return CATEGORY_ORDER.index(name) if name in CATEGORY_ORDER else len(CATEGORY_ORDER)

        pages = []
        for cog in sorted(self.bot.cogs.values(), key=order):
            lines = []
            for command in cog.walk_commands():
                if command.hidden:
                    continue
                name = command.qualified_name
                if isinstance(command, commands.HybridGroup):
                    if not command.fallback:
                        continue
                    name = f"{name} {command.fallback}"
                description = command.description or command.short_doc
                translated = self.bot.i18n.command_text(lang, description) or description
                lines.append(f"`/{name}` — {translated}")
            if not lines:
                continue
            title = t(lang, f"help.categories.{cog.qualified_name.lower()}")
            description = t(lang, "help.description", prefix=prefix) + "\n\n" + "\n".join(lines)
            pages.append(embeds.make_embed(self.bot, title=title, description=description[:4096]))

        for number, page in enumerate(pages, start=1):
            page.set_footer(text=t(lang, "help.footer", page=number, pages=len(pages)))
        await Paginator(pages, ctx.author.id, deny_text=t(lang, "errors.not_your_menu")).send(ctx)

    @commands.hybrid_command(name="ping", aliases=["latency"], description="Check the bot latency")
    async def ping(self, ctx: commands.Context) -> None:
        lang = await self.bot.lang_for(ctx.guild.id if ctx.guild else None)
        t = self.bot.i18n.t
        embed = embeds.make_embed(self.bot, title="🏓 Pong!")
        embed.add_field(name="Discord", value=f"`{round(self.bot.latency * 1000)} ms`")
        embed.add_field(name="Lavalink", value=t(lang, "general.nodes_online", online=len(connected_nodes()),
                                                 total=len(wavelink.Pool.nodes)))
        player = get_player(ctx.guild)
        if player is not None and player.connected and player.ping >= 0:
            embed.add_field(name=t(lang, "general.voice_ping"), value=f"`{player.ping} ms`")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="stats", aliases=["info", "botinfo"], description="Show bot and Lavalink statistics")
    async def stats(self, ctx: commands.Context) -> None:
        await ctx.defer()
        lang = await self.bot.lang_for(ctx.guild.id if ctx.guild else None)
        t = self.bot.i18n.t
        players = sum(len(node.players) for node in wavelink.Pool.nodes.values())

        embed = embeds.make_embed(self.bot, title=t(lang, "general.stats_title", name=self.bot.config.bot.name))
        embed.add_field(name=t(lang, "general.servers"), value=f"`{len(self.bot.guilds)}`")
        embed.add_field(name=t(lang, "general.players"), value=f"`{players}`")
        embed.add_field(name=t(lang, "general.uptime"), value=f"`{format_uptime(time.time() - self.bot.started_at)}`")
        embed.add_field(
            name=t(lang, "general.versions"),
            value=(f"HexMusic `{__version__}` · discord.py `{discord.__version__}` · "
                   f"wavelink `{getattr(wavelink, '__version__', '?')}` · Python `{platform.python_version()}`"),
            inline=False,
        )
        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        for node in wavelink.Pool.nodes.values():
            value = t(lang, "general.node_offline")
            if node.status is wavelink.NodeStatus.CONNECTED:
                try:
                    stats = await node.fetch_stats()
                    value = t(lang, "general.node_stats", playing=stats.playing, players=stats.players,
                              memory=stats.memory.used // 1_048_576, cpu=f"{stats.cpu.lavalink_load * 100:.1f}",
                              uptime=format_uptime(stats.uptime / 1000))
                except Exception:  # noqa: BLE001
                    pass
            embed.add_field(name=f"🎛️ {node.identifier}", value=value, inline=False)
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="invite", description="Get the link to invite the bot")
    async def invite(self, ctx: commands.Context) -> None:
        if self.bot.user is None:
            return
        lang = await self.bot.lang_for(ctx.guild.id if ctx.guild else None)
        permissions = discord.Permissions(
            view_channel=True, send_messages=True, embed_links=True, attach_files=True, read_message_history=True,
            add_reactions=True, use_external_emojis=True, manage_messages=True, manage_channels=True,
            connect=True, speak=True,
        )
        url = discord.utils.oauth_url(self.bot.user.id, permissions=permissions, scopes=("bot", "applications.commands"))
        embed = embeds.make_embed(self.bot, title=self.bot.i18n.t(lang, "general.invite_title", name=self.bot.config.bot.name),
                                  description=self.bot.i18n.t(lang, "general.invite_description", url=url))
        await ctx.send(embed=embed)

    # ───── Solo para los dueños del bot (comandos de texto) ─────

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync(self, ctx: commands.Context, scope: str = "global") -> None:
        """Registra los comandos slash. Uso: sync [global|guild|clear]"""
        if scope == "guild" and ctx.guild is not None:
            synced = await self.bot.sync_app_commands(guild_id=ctx.guild.id)
        elif scope == "clear" and ctx.guild is not None:
            self.bot.tree.clear_commands(guild=ctx.guild)
            synced = await self.bot.tree.sync(guild=ctx.guild)
        else:
            synced = await self.bot.tree.sync()
        await self.bot.respond(ctx, "general.synced", count=len(synced))

    @commands.command(name="reloadlocales", hidden=True)
    @commands.is_owner()
    async def reload_locales(self, ctx: commands.Context) -> None:
        """Recarga los archivos de idioma sin reiniciar."""
        self.bot.i18n.reload()
        await self.bot.respond(ctx, "general.locales_reloaded", languages=", ".join(self.bot.i18n.languages))


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(General(bot))
