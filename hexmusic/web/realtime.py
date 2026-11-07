"""Tiempo real del panel web: un WebSocket por pestaña con el estado de los reproductores.

El navegador se suscribe a los servidores que está viendo. Cada segundo (o al instante cuando un evento
avisa con ``notify``) se compara el estado de esos reproductores con el último enviado y solo se manda
lo que cambió. La posición de la canción no cuenta como cambio salvo que salte (seek desde Discord).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import aiohttp
from aiohttp import web

from .auth import SESSION_COOKIE, Session

if TYPE_CHECKING:
    from .server import WebPanel

log = logging.getLogger("hexmusic.web.realtime")

TICK_SECONDS = 1.0
POSITION_DRIFT_MS = 2500
MAX_CLIENTS = 500
MAX_SUBSCRIPTIONS = 5


@dataclass(eq=False, slots=True)
class Client:
    ws: web.WebSocketResponse
    session: Session
    guilds: set[int] = field(default_factory=set)
    # guild_id → (firma sin posición, posición, momento del envío, sonando)
    sent: dict[int, tuple[str, int, float, bool]] = field(default_factory=dict)


class Realtime:
    def __init__(self, panel: WebPanel) -> None:
        self.panel = panel
        self.bot = panel.bot
        self.clients: set[Client] = set()
        self._dirty: set[int] = set()
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    # ───── Ciclo ─────

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        for client in list(self.clients):
            with contextlib.suppress(Exception):
                await client.ws.close(code=aiohttp.WSCloseCode.GOING_AWAY)
        self.clients.clear()

    def notify(self, guild_id: int) -> None:
        self._dirty.add(guild_id)
        self._wake.set()

    async def _loop(self) -> None:
        while True:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=TICK_SECONDS)
            self._wake.clear()
            self._dirty.clear()
            try:
                await self._broadcast()
            except Exception:  # noqa: BLE001 - un fallo puntual no debe parar el tiempo real
                log.exception("Error enviando el estado en tiempo real")

    async def _broadcast(self) -> None:
        if not self.clients:
            return
        now = time.time()
        payloads: dict[int, dict[str, Any]] = {}
        for client in list(self.clients):
            if client.session.expires_at <= now:
                await client.ws.close(code=aiohttp.WSCloseCode.POLICY_VIOLATION, message=b"session")
                continue
            for guild_id in list(client.guilds):
                if guild_id not in payloads:
                    guild = self.bot.get_guild(guild_id)
                    payloads[guild_id] = self.panel.api.player_payload(guild) if guild else {"connected": False}
                await self._maybe_send(client, guild_id, payloads[guild_id], now)

    @staticmethod
    def _signature(payload: dict[str, Any]) -> str:
        return json.dumps({key: value for key, value in payload.items() if key not in ("position", "now")},
                          sort_keys=True, default=str)

    async def _maybe_send(self, client: Client, guild_id: int, payload: dict[str, Any], now: float,
                          *, force: bool = False) -> None:
        signature = self._signature(payload)
        position = int(payload.get("position") or 0)
        playing = bool(payload.get("connected") and payload.get("current") and not payload.get("paused"))
        previous = client.sent.get(guild_id)
        if not force and previous is not None and previous[0] == signature:
            expected = previous[1] + (int((now - previous[2]) * 1000) if previous[3] else 0)
            if abs(position - expected) < POSITION_DRIFT_MS:
                return
        client.sent[guild_id] = (signature, position, now, playing)
        await self._send(client, {"type": "player", "guild_id": str(guild_id), "data": payload})

    @staticmethod
    async def _send(client: Client, message: dict[str, Any]) -> None:
        if client.ws.closed:
            return
        try:
            await client.ws.send_str(json.dumps(message, default=str))
        except (ConnectionError, RuntimeError, aiohttp.ClientError):
            pass

    # ───── Conexión ─────

    def _origin_allowed(self, request: web.Request) -> bool:
        origin = request.headers.get("Origin")
        if not origin:
            return True
        netloc = urlsplit(origin).netloc.lower()
        allowed = {request.host.lower(), urlsplit(self.panel.auth.public_url).netloc.lower()}
        forwarded = request.headers.get("X-Forwarded-Host")
        if forwarded:
            allowed.add(forwarded.split(",")[0].strip().lower())
        return netloc in allowed

    async def handler(self, request: web.Request) -> web.StreamResponse:
        if not self._origin_allowed(request):
            raise web.HTTPForbidden()
        session = await self.panel.auth.get_session(request.cookies.get(SESSION_COOKIE))
        if session is None:
            raise web.HTTPUnauthorized()
        if len(self.clients) >= MAX_CLIENTS:
            raise web.HTTPServiceUnavailable()

        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=4096)
        await ws.prepare(request)
        client = Client(ws=ws, session=session)
        self.clients.add(client)
        self.start()
        try:
            await self._send(client, {"type": "hello", "user_id": str(session.user_id)})
            async for message in ws:
                if message.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    data = json.loads(message.data)
                except ValueError:
                    continue
                if isinstance(data, dict):
                    await self._on_message(client, data)
        finally:
            self.clients.discard(client)
        return ws

    async def _on_message(self, client: Client, data: dict[str, Any]) -> None:
        op = data.get("op")
        if op == "ping":
            await self._send(client, {"type": "pong"})
            return
        try:
            guild_id = int(str(data.get("guild_id")))
        except (TypeError, ValueError):
            return
        if op == "unsubscribe":
            client.guilds.discard(guild_id)
            client.sent.pop(guild_id, None)
        elif op == "subscribe":
            if len(client.guilds) >= MAX_SUBSCRIPTIONS and guild_id not in client.guilds:
                return
            try:
                allowed = await self.panel.auth.can_manage(client.session, guild_id)
            except Exception:  # noqa: BLE001 - Discord no respondió: se ignora la suscripción
                allowed = False
            guild = self.bot.get_guild(guild_id)
            if not allowed or guild is None:
                await self._send(client, {"type": "error", "guild_id": str(guild_id), "error": "forbidden"})
                return
            client.guilds.add(guild_id)
            await self._maybe_send(client, guild_id, self.panel.api.player_payload(guild), time.time(), force=True)
