"""API de administración del panel (solo dueños del bot): estado, configuración global, servidores y registros."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from aiohttp import web

from .. import __version__
from ..checks import get_player
from ..core.overrides import InvalidValue
from ..player import HexPlayer
from .api import ApiError
from .logbuffer import LogBuffer

if TYPE_CHECKING:
    from .api import Api

log = logging.getLogger("hexmusic.web.admin")

LOG_LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}


def _process_memory() -> int | None:
    """Memoria residente del proceso del bot en bytes (Linux)."""
    try:
        with open("/proc/self/status", encoding="utf-8") as fp:
            for line in fp:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def _folder_size(path: Path) -> int:
    total = 0
    try:
        for file in path.rglob("*"):
            if file.is_file():
                total += file.stat().st_size
    except OSError:
        pass
    return total


class AdminApi:
    def __init__(self, api: Api, logs: LogBuffer) -> None:
        self.api = api
        self.bot = api.bot
        self.logs = logs
        self.restart_pending: set[str] = set()

    def register(self, app: web.Application) -> None:
        router = app.router
        router.add_get("/api/admin/overview", self.overview)
        router.add_post("/api/admin/actions", self.action)
        router.add_get("/api/admin/config", self.config)
        router.add_patch("/api/admin/config", self.update_config)
        router.add_get("/api/admin/guilds", self.guilds)
        router.add_post("/api/admin/guilds/{guild_id}/leave", self.leave_guild)
        router.add_get("/api/admin/logs", self.get_logs)

    # ───── Resumen ─────

    async def overview(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        bot = self.bot
        players = [p for node in wavelink.Pool.nodes.values() for p in node.players.values() if isinstance(p, HexPlayer)]
        db_path = bot.db.path
        library_dir = bot.library.directory
        user = bot.user
        return web.json_response({
            "bot": {
                "id": str(user.id) if user else None,
                "name": str(user) if user else None,
                "avatar": user.display_avatar.url if user else None,
                "application_id": str(bot.application_id) if bot.application_id else None,
            },
            "guilds": len(bot.guilds),
            "members": sum(guild.member_count or 0 for guild in bot.guilds),
            "players": len(players),
            "playing": sum(1 for p in players if p.current is not None and not p.paused),
            "listeners": sum(len(p.listeners) for p in players),
            "uptime": int(time.time() - bot.started_at),
            "shards": bot.shard_count or 1,
            "memory": _process_memory(),
            "pid": os.getpid(),
            "versions": {
                "hexmusic": __version__,
                "discord": discord.__version__,
                "wavelink": getattr(wavelink, "__version__", "?"),
                "python": platform.python_version(),
                "platform": f"{platform.system()} {platform.machine()}",
            },
            "storage": {
                "database": db_path.stat().st_size if db_path.exists() else 0,
                "library": await asyncio.to_thread(_folder_size, library_dir) if library_dir.exists() else 0,
                "data_dir": str(db_path.parent),
            },
            "features": {name: bot.feature(name) for name in
                         ("autoplay", "stay_247", "lyrics", "request_channel", "vote_skip", "library")},
            "web": {"public_url": self.api.auth.public_url, "realtime_clients": len(getattr(bot.web, "realtime").clients)
                    if bot.web is not None else 0},
            "youtube": bot.youtube.summary(),
            "restart_pending": sorted(self.restart_pending),
            "python_executable": sys.executable,
        })

    async def action(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        data = await self.api.body(request)
        action = str(data.get("action") or "")
        if action == "sync":
            guild_id = data.get("guild_id")
            synced = await self.bot.sync_app_commands(self.api.snowflake(guild_id) if guild_id else None)
            return web.json_response({"ok": True, "count": len(synced)})
        if action == "reload_locales":
            self.bot.i18n.reload()
            return web.json_response({"ok": True, "languages": self.bot.i18n.languages})
        if action == "save_sessions":
            count = await self.bot.sessions.save()
            return web.json_response({"ok": True, "count": count})
        if action == "purge_history":
            removed = await self.bot.history.purge()
            return web.json_response({"ok": True, "count": removed})
        raise ApiError(400, "web.errors.invalid_field")

    # ───── Configuración global ─────

    def _config_payload(self) -> dict[str, Any]:
        return {
            "sections": self.bot.overrides.describe(self.bot),
            "restart_pending": sorted(self.restart_pending),
            "file": str(self.bot.overrides.path),
        }

    async def config(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        return web.json_response(self._config_payload())

    async def update_config(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        data = await self.api.body(request)
        changes = data.get("changes") or {}
        resets = data.get("reset") or []
        if not isinstance(changes, dict) or not isinstance(resets, list):
            raise ApiError(400, "web.errors.invalid_field")
        try:
            restart = self.bot.overrides.update(self.bot, changes, [str(key) for key in resets])
        except InvalidValue as exc:
            raise ApiError(400, "web.errors.config_invalid", key=exc.key, reason=exc.reason) from None
        self.restart_pending.update(restart)
        await self.bot.apply_live_config([*changes, *resets])
        session = self.api.session(request)
        log.info("Configuración global cambiada desde el panel por %s: %s", session.display_name,
                 ", ".join([*changes, *resets]) or "—")
        return web.json_response(self._config_payload())

    # ───── Servidores ─────

    async def guilds(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        items = []
        for guild in self.bot.guilds:
            player = get_player(guild)
            connected = player is not None and player.connected
            items.append({
                "id": str(guild.id),
                "name": guild.name,
                "icon": guild.icon.url if guild.icon else None,
                "members": guild.member_count or 0,
                "owner_id": str(guild.owner_id) if guild.owner_id else None,
                "joined_at": int(guild.me.joined_at.timestamp()) if guild.me and guild.me.joined_at else None,
                "player": {
                    "channel": player.channel.name if connected and player.channel else None,
                    "listeners": len(player.listeners) if connected else 0,
                    "paused": bool(player.paused) if connected else False,
                    "track": player.current.title if connected and player.current else None,
                    "queue": len(player.queue) if connected else 0,
                } if connected else None,
            })
        items.sort(key=lambda item: (item["player"] is None, -item["members"]))
        return web.json_response({"guilds": items})

    async def leave_guild(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        guild = self.bot.get_guild(self.api.snowflake(request.match_info["guild_id"]))
        if guild is None:
            raise ApiError(404, "web.errors.bot_not_in_guild")
        player = get_player(guild)
        if player is not None:
            await player.disconnect()
        await guild.leave()
        log.info("El bot salió de %s (%s) desde el panel web.", guild.name, guild.id)
        return web.json_response({"ok": True})

    # ───── Registros ─────

    async def get_logs(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        after = self.api.int_value(request.query.get("after", 0), 0, 2**62)
        level = LOG_LEVELS.get(str(request.query.get("level", "INFO")).upper(), logging.INFO)
        return web.json_response({"items": self.logs.since(after, level=level), "last": self.logs.sequence})
