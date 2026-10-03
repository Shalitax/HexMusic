"""Comandos escritos en la consola (stdin). Pensado para paneles como Pterodactyl.

Se activa con ``bot.console: true`` en config.yml (o ``HEXMUSIC__BOT__CONSOLE=1``).
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import time
from typing import TYPE_CHECKING, Any

import wavelink

from .utils.formatting import format_uptime

if TYPE_CHECKING:
    from .bot import HexMusic

log = logging.getLogger("hexmusic.console")


class Console:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    def t(self, key: str, **kwargs: Any) -> str:
        return self.bot.i18n.t(self.bot.i18n.default, key, **kwargs)

    def start(self) -> None:
        loop = asyncio.get_running_loop()

        def reader() -> None:
            # Hilo daemon: si stdin nunca recibe nada, no impide cerrar el bot.
            try:
                for line in sys.stdin:
                    loop.call_soon_threadsafe(self._queue.put_nowait, line)
            except (RuntimeError, ValueError, OSError):
                return

        threading.Thread(target=reader, name="hexmusic-console", daemon=True).start()
        self._task = asyncio.create_task(self._run())
        log.info(self.t("console.ready"))

    async def _run(self) -> None:
        while not self.bot.is_closed():
            line = (await self._queue.get()).strip()
            if not line:
                continue
            try:
                await self.handle(line)
            except Exception:  # noqa: BLE001 - un comando de consola nunca debe tumbar el bot
                log.exception(self.t("console.error"))

    @staticmethod
    def _print(text: str) -> None:
        print(text, flush=True)

    async def handle(self, line: str) -> None:
        command = line.split(" ", 1)[0].lower()

        if command in ("ayuda", "help", "?"):
            self._print(self.t("console.help"))
        elif command in ("estado", "status"):
            nodes = list(wavelink.Pool.nodes.values())
            online = sum(1 for node in nodes if node.status is wavelink.NodeStatus.CONNECTED)
            players = sum(len(node.players) for node in nodes)
            web = str(self.bot.config.web.public_url) if self.bot.web is not None else self.t("console.web_off")
            self._print(self.t(
                "console.status",
                user=self.bot.user or "—",
                servers=len(self.bot.guilds),
                players=players,
                online=online,
                total=len(nodes),
                uptime=format_uptime(time.time() - self.bot.started_at),
                web=web,
            ))
        elif command in ("servidores", "servers", "guilds"):
            guilds = sorted(self.bot.guilds, key=lambda guild: guild.name.lower())
            lines = [f"  {guild.name} ({guild.id}) · {guild.member_count or '?'}" for guild in guilds[:50]]
            self._print("\n".join([self.t("console.servers", count=len(guilds)), *lines]))
        elif command == "sync":
            synced = await self.bot.sync_app_commands()
            self._print(self.t("console.synced", count=len(synced)))
        elif command in ("idiomas", "reload", "recargar"):
            self.bot.i18n.reload()
            self._print(self.t("console.reloaded", languages=", ".join(self.bot.i18n.languages)))
        elif command in ("youtube", "yt"):
            await self.youtube(line.split()[1:])
        elif command in ("guardar", "save"):
            count = await self.bot.sessions.save()
            self._print(self.t("console.saved", count=count))
        elif command in ("detener", "stop", "salir", "exit"):
            self._print(self.t("console.stopping"))
            await self.bot.close()
        else:
            self._print(self.t("console.unknown", command=command))

    async def youtube(self, args: list[str]) -> None:
        """youtube [estado | vincular | desvincular | token <refresh token>]"""
        account = self.bot.youtube
        action = args[0].lower() if args else "estado"

        def yt(key: str, **kwargs: Any) -> str:
            return self.t(f"youtube.{key}", **kwargs)

        if action in ("estado", "status"):
            info = account.summary()
            self._print(yt(f"status_{info['status']}"))
            if info["code"]:
                self._print(yt("status_code", url=info["code"]["url"], code=info["code"]["code"]))
            if info["panel_token"]:
                self._print(yt("status_panel_token"))
            return

        if not account.enabled:
            self._print(yt("disabled"))
            return

        if action in ("vincular", "link", "codigo", "código"):
            if not account.start_link():
                self._print(yt("already_linking"))
            else:
                self._print(yt("link_requested"))
        elif action in ("desvincular", "unlink", "olvidar"):
            nodes = await account.unlink()
            self._print(yt("unlinked", nodes=nodes))
            if account.panel_token:
                self._print(yt("status_panel_token"))
        elif action == "token":
            if len(args) < 2:
                self._print(yt("usage"))
                return
            result = await account.set_token(args[1].strip())
            self._print(yt("token_saved" if result else "token_unchecked" if result is None else "token_rejected"))
        elif action in ("cancelar", "cancel"):
            account.cancel_link()
            self._print(yt("link_cancelled"))
        else:
            self._print(yt("usage"))
