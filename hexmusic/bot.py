"""Clase principal del bot."""

from __future__ import annotations

import asyncio
import logging
import time
from functools import partial
from pathlib import Path
from typing import Any

import aiohttp
import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from . import __version__
from .config import Config
from .database import Database
from .errors import HexError
from .i18n import HexTranslator, I18n
from .player import HexPlayer
from .ui.embeds import error_embed, info_embed, success_embed
from .ui.views import ControlsView

log = logging.getLogger("hexmusic")

ACTIVITY_TYPES = {
    "playing": discord.ActivityType.playing,
    "listening": discord.ActivityType.listening,
    "watching": discord.ActivityType.watching,
    "competing": discord.ActivityType.competing,
}

_ERROR_WRAPPERS = (commands.CommandInvokeError, commands.HybridCommandError, app_commands.CommandInvokeError)


def unwrap_error(error: BaseException) -> BaseException:
    while isinstance(error, _ERROR_WRAPPERS) and getattr(error, "original", None) is not None:
        error = error.original  # type: ignore[union-attr]
    return error


class Colors:
    __slots__ = ("primary", "success", "error", "warning")

    def __init__(self, branding: Config) -> None:
        self.primary = discord.Color.from_str(str(branding.color))
        self.success = discord.Color.from_str(str(branding.success_color))
        self.error = discord.Color.from_str(str(branding.error_color))
        self.warning = discord.Color.from_str(str(branding.warning_color))


class HexMusic(commands.AutoShardedBot):
    def __init__(self, *, config: Config, root: Path) -> None:
        self.config = config
        self.root = root

        intents = discord.Intents.default()
        intents.message_content = bool(config.bot.message_content_intent)

        status = config.bot.status
        activity = None
        if status.text:
            activity_type = ACTIVITY_TYPES.get(str(status.type).lower(), discord.ActivityType.listening)
            activity = discord.Activity(type=activity_type, name=str(status.text))

        super().__init__(
            command_prefix=self._get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            strip_after_prefix=True,
            activity=activity,
            owner_ids={int(owner) for owner in (config.bot.owner_ids or [])},
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, replied_user=False),
        )

        self.i18n = I18n(root / "locales", default=str(config.bot.default_language))
        db_path = Path(str(config.bot.database))
        self.db = Database(db_path if db_path.is_absolute() else root / db_path)
        self.colors = Colors(config.branding)
        self.http_session: aiohttp.ClientSession | None = None
        self.controls_view: ControlsView | None = None
        self.started_at = time.time()
        self._nodes_task: asyncio.Task[None] | None = None
        self.web: Any = None  # WebPanel cuando web.enabled = true
        self.console: Any = None  # Console cuando bot.console = true

    # ───── Arranque ─────

    async def setup_hook(self) -> None:
        self.http_session = aiohttp.ClientSession(headers={"User-Agent": f"HexMusic/{__version__}"})
        await self.db.connect()

        await self.tree.set_translator(HexTranslator(self.i18n))
        self.tree.error(self.on_app_command_error)

        self.controls_view = ControlsView(self)
        self.add_view(self.controls_view)

        for extension in self.config.bot.extensions:
            await self.load_extension(str(extension))
            log.info("Módulo cargado: %s", extension)

        # En segundo plano: el bot arranca aunque Lavalink tarde en estar listo
        self._nodes_task = asyncio.create_task(self.connect_nodes())

        if self.config.web.enabled:
            from .web.server import WebPanel

            self.web = WebPanel(self)
            try:
                await self.web.start()
            except OSError as exc:
                log.error("No se pudo iniciar el panel web en el puerto %s: %s", self.config.web.port, exc)
                self.web = None

        if self.config.bot.get("console"):
            from .console import Console

            self.console = Console(self)
            self.console.start()

        if self.config.bot.sync_commands:
            await self.sync_app_commands()

    async def connect_nodes(self) -> None:
        idle = int(self.config.player.idle_timeout) or None
        nodes = [
            wavelink.Node(
                identifier=str(node.get("identifier") or f"node-{index}"),
                uri=str(node["uri"]),
                password=str(node["password"]),
                inactive_player_timeout=idle,
            )
            for index, node in enumerate(self.config.lavalink.nodes)
        ]
        cache = int(self.config.lavalink.search_cache or 0) or None
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=cache)

    async def sync_app_commands(self, guild_id: int | None = None) -> list[app_commands.AppCommand]:
        target = guild_id or self.config.bot.dev_guild_id
        if target:
            guild = discord.Object(id=int(target))
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Sincronizados %d comandos slash en el servidor %s", len(synced), target)
        else:
            synced = await self.tree.sync()
            log.info("Sincronizados %d comandos slash globales (pueden tardar en aparecer)", len(synced))
        return synced

    async def on_ready(self) -> None:
        log.info("%s conectado como %s (%s) en %d servidores", self.config.bot.name, self.user,
                 self.user.id if self.user else "?", len(self.guilds))

    async def close(self) -> None:
        if self._nodes_task is not None:
            self._nodes_task.cancel()
        if self.web is not None:
            await self.web.stop()
        try:
            await wavelink.Pool.close()
        except Exception:  # noqa: BLE001 - el cierre no debe fallar
            log.debug("Error al cerrar los nodos de Lavalink", exc_info=True)
        await super().close()
        if self.http_session is not None:
            await self.http_session.close()
        await self.db.close()

    # ───── Utilidades ─────

    async def _get_prefix(self, bot: commands.Bot, message: discord.Message) -> list[str]:
        prefix = str(self.config.bot.prefix)
        if message.guild is not None:
            settings = await self.db.get_guild(message.guild.id)
            prefix = settings.prefix or prefix
        return commands.when_mentioned_or(prefix)(bot, message)

    def feature(self, name: str) -> bool:
        return bool(self.config.features.get(name, False))

    async def lang_for(self, guild_id: int | None) -> str:
        if guild_id is None:
            return self.i18n.default
        settings = await self.db.get_guild(guild_id)
        if settings.language in self.i18n.languages:
            return settings.language  # type: ignore[return-value]
        return self.i18n.default

    async def tr(self, guild: discord.Guild | None, key: str, /, **kwargs: Any) -> str:
        return self.i18n.t(await self.lang_for(guild.id if guild else None), key, **kwargs)

    async def respond(self, ctx: commands.Context[Any], key: str, /, *, kind: str = "success",
                      ephemeral: bool = False, **kwargs: Any) -> None:
        """Responde con un embed traducido. ``kind``: ``success`` o ``info``."""
        text = await self.tr(ctx.guild, key, **kwargs)
        embed = success_embed(self, text) if kind == "success" else info_embed(self, text)
        await ctx.send(embed=embed, ephemeral=ephemeral)

    async def setup_player(self, player: HexPlayer, text_channel: discord.abc.Messageable | None) -> None:
        """Aplica los ajustes del servidor a un reproductor recién conectado."""
        assert player.guild is not None
        settings = await self.db.get_guild(player.guild.id)
        player.text_channel = text_channel
        player.autoplay_enabled = settings.autoplay and self.feature("autoplay")
        player.stay_247 = settings.stay_247 and self.feature("stay_247")
        player.sync_autoplay()
        player.inactive_timeout = None if player.stay_247 else (int(self.config.player.idle_timeout) or None)

        max_volume = int(self.config.player.max_volume)
        volume = settings.default_volume if settings.default_volume is not None else int(self.config.player.default_volume)
        volume = max(0, min(volume, max_volume))
        if volume != player.volume:
            await player.set_volume(volume)

    async def is_dj(self, member: discord.Member, player: HexPlayer | None = None, *, strict: bool = False) -> bool:
        """Admins, rol DJ o quien esté solo con el bot. Sin rol DJ configurado todos lo son (salvo ``strict``)."""
        permissions = member.guild_permissions
        if permissions.administrator or permissions.manage_guild:
            return True
        if player is not None and player.channel is not None:
            listeners = player.listeners
            if len(listeners) == 1 and listeners[0].id == member.id:
                return True
        settings = await self.db.get_guild(member.guild.id)
        if settings.dj_role_id:
            return member.get_role(settings.dj_role_id) is not None
        return not strict

    async def can_use(self, member: discord.Member, player: HexPlayer | None, command_name: str) -> bool:
        restricted = {str(name) for name in (self.config.dj.commands or [])}
        if command_name not in restricted:
            return True
        return await self.is_dj(member, player)

    # ───── Errores ─────

    def error_text(self, lang: str, error: BaseException) -> str | None:
        t = partial(self.i18n.t, lang)

        def perms(names: list[str]) -> str:
            return ", ".join(name.replace("_", " ").title() for name in names)

        if isinstance(error, HexError):
            return t(error.key, **error.kwargs)
        if isinstance(error, (commands.MissingPermissions, app_commands.MissingPermissions)):
            return t("errors.missing_permissions", perms=perms(error.missing_permissions))
        if isinstance(error, (commands.BotMissingPermissions, app_commands.BotMissingPermissions)):
            return t("errors.bot_missing_permissions", perms=perms(error.missing_permissions))
        if isinstance(error, (commands.NoPrivateMessage, app_commands.NoPrivateMessage)):
            return t("errors.guild_only")
        if isinstance(error, commands.NotOwner):
            return t("errors.owner_only")
        if isinstance(error, (commands.CommandOnCooldown, app_commands.CommandOnCooldown)):
            return t("errors.cooldown", seconds=f"{error.retry_after:.1f}")
        if isinstance(error, commands.MissingRequiredArgument):
            return t("errors.missing_argument", name=error.param.name)
        if isinstance(error, (commands.UserInputError, app_commands.TransformerError)):
            return t("errors.bad_argument")
        if isinstance(error, (commands.CheckFailure, app_commands.CheckFailure)):
            return t("errors.check_failed")
        if isinstance(error, wavelink.LavalinkLoadException):
            return t("errors.load_failed", error=error.error)
        if isinstance(error, wavelink.LavalinkException):
            return t("errors.lavalink", error=error.error)
        if isinstance(error, wavelink.InvalidNodeException):
            return t("errors.no_nodes")
        if isinstance(error, wavelink.ChannelTimeoutException):
            return t("errors.connect_timeout")
        return None

    async def on_command_error(self, ctx: commands.Context[Any], error: commands.CommandError) -> None:  # type: ignore[override]
        if isinstance(error, (commands.CommandNotFound, commands.DisabledCommand)):
            return
        if ctx.command is not None and ctx.command.has_error_handler():
            return

        original = unwrap_error(error)
        lang = await self.lang_for(ctx.guild.id if ctx.guild else None)
        text = self.error_text(lang, original)
        if text is None:
            log.error("Error no controlado en el comando %s", ctx.command, exc_info=original)
            text = self.i18n.t(lang, "errors.unexpected")
        try:
            await ctx.send(embed=error_embed(self, text), ephemeral=True)
        except discord.HTTPException:
            pass

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        original = unwrap_error(error)
        if isinstance(original, app_commands.CommandNotFound):
            return
        lang = await self.lang_for(interaction.guild_id)
        text = self.error_text(lang, original)
        if text is None:
            log.error("Error no controlado en /%s", interaction.command.qualified_name if interaction.command else "?",
                      exc_info=original)
            text = self.i18n.t(lang, "errors.unexpected")
        # Si ya se respondió (p. ej. on_command_error lo gestionó) no se duplica el mensaje
        if interaction.response.is_done():
            return
        try:
            await interaction.response.send_message(embed=error_embed(self, text), ephemeral=True)
        except discord.HTTPException:
            pass
