"""Inicio de sesión con Discord (OAuth2) y sesiones del panel web."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import discord

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.web.auth")

DISCORD_API = "https://discord.com/api/v10"
AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
SESSION_COOKIE = "hexmusic_session"
STATE_COOKIE = "hexmusic_oauth_state"
ADMINISTRATOR = 1 << 3
MANAGE_GUILD = 1 << 5
GUILDS_CACHE_SECONDS = 120


class AuthExpired(Exception):
    """El token de Discord ya no es válido: hay que volver a iniciar sesión."""


class DiscordAPIError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"La API de Discord respondió {status}")
        self.status = status


@dataclass(slots=True)
class Session:
    token_hash: str
    user_id: int
    user: dict[str, Any]
    access_token: str
    csrf_token: str
    expires_at: int

    @property
    def display_name(self) -> str:
        return str(self.user.get("global_name") or self.user.get("username") or self.user_id)

    @property
    def avatar_url(self) -> str:
        avatar = self.user.get("avatar")
        if avatar:
            return f"https://cdn.discordapp.com/avatars/{self.user_id}/{avatar}.png?size=96"
        return f"https://cdn.discordapp.com/embed/avatars/{(self.user_id >> 22) % 6}.png"


def hash_token(token: str) -> str:
    """En la base de datos solo se guarda el hash del token de sesión."""
    return hashlib.sha256(token.encode()).hexdigest()


class Auth:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self._sessions: dict[str, Session] = {}
        self._guilds: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    @property
    def public_url(self) -> str:
        return str(self.bot.config.web.public_url).rstrip("/")

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_url}/auth/callback"

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.startswith("https://")

    @property
    def client_id(self) -> int:
        return int(self.bot.application_id or (self.bot.user.id if self.bot.user else 0))

    def login_url(self, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "redirect_uri": self.redirect_uri,
            "scope": "identify guilds",
            "state": state,
            "prompt": "none",
        }
        return f"{AUTHORIZE_URL}?{urlencode(params)}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        assert self.bot.http_session is not None
        for attempt in range(3):
            async with self.bot.http_session.request(method, f"{DISCORD_API}{path}", **kwargs) as resp:
                if resp.status == 429 and attempt < 2:
                    data = await resp.json(content_type=None)
                    await asyncio.sleep(min(float((data or {}).get("retry_after", 1)), 5))
                    continue
                if resp.status == 401:
                    raise AuthExpired()
                if resp.status >= 400:
                    log.warning("Discord API %s %s → %s: %s", method, path, resp.status, (await resp.text())[:300])
                    raise DiscordAPIError(resp.status)
                return await resp.json()
        raise DiscordAPIError(429)

    async def exchange_code(self, code: str) -> dict[str, Any]:
        data = {
            "client_id": str(self.client_id),
            "client_secret": str(self.bot.config.web.client_secret),
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
        }
        return await self._request("POST", "/oauth2/token", data=data)

    async def create_session(self, token_payload: dict[str, Any]) -> tuple[str, Session]:
        access_token = str(token_payload["access_token"])
        user = await self._request("GET", "/users/@me", headers={"Authorization": f"Bearer {access_token}"})

        token = secrets.token_urlsafe(32)
        lifetime = min(int(token_payload.get("expires_in", 604800)), int(self.bot.config.web.session_days) * 86400)
        session = Session(
            token_hash=hash_token(token),
            user_id=int(user["id"]),
            user={key: user.get(key) for key in ("id", "username", "global_name", "avatar")},
            access_token=access_token,
            csrf_token=secrets.token_urlsafe(24),
            expires_at=int(time.time()) + lifetime,
        )
        await self.bot.db.create_web_session(
            session.token_hash, session.user_id, session.user, session.access_token, session.csrf_token, session.expires_at
        )
        self._sessions[session.token_hash] = session
        log.info("Inicio de sesión en el panel: %s (%s)", session.display_name, session.user_id)
        return token, session

    async def get_session(self, token: str | None) -> Session | None:
        if not token:
            return None
        token_hash = hash_token(token)
        session = self._sessions.get(token_hash)
        if session is None:
            row = await self.bot.db.get_web_session(token_hash)
            if row is None:
                return None
            session = Session(**row)
            self._sessions[token_hash] = session
        if session.expires_at <= time.time():
            await self.destroy(session)
            return None
        return session

    async def destroy(self, session: Session) -> None:
        self._sessions.pop(session.token_hash, None)
        self._guilds.pop(session.token_hash, None)
        await self.bot.db.delete_web_session(session.token_hash)

    async def user_guilds(self, session: Session) -> list[dict[str, Any]]:
        cached = self._guilds.get(session.token_hash)
        if cached and time.monotonic() - cached[0] < GUILDS_CACHE_SECONDS:
            return cached[1]
        guilds = await self._request("GET", "/users/@me/guilds", headers={"Authorization": f"Bearer {session.access_token}"})
        self._guilds[session.token_hash] = (time.monotonic(), guilds)
        return guilds

    async def manageable_guilds(self, session: Session) -> dict[int, dict[str, Any]]:
        """Servidores donde el usuario es dueño, administrador o tiene "Gestionar servidor"."""
        result: dict[int, dict[str, Any]] = {}
        for guild in await self.user_guilds(session):
            permissions = int(guild.get("permissions") or 0)
            if guild.get("owner") or permissions & (ADMINISTRATOR | MANAGE_GUILD):
                result[int(guild["id"])] = guild
        return result

    async def is_owner(self, session: Session) -> bool:
        return await self.bot.is_owner(discord.Object(id=session.user_id))  # type: ignore[arg-type]

    async def can_manage(self, session: Session, guild_id: int) -> bool:
        if await self.is_owner(session):
            return True
        return guild_id in await self.manageable_guilds(session)
