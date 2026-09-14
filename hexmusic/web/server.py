"""Servidor HTTP del panel web. Corre dentro del proceso del bot."""

from __future__ import annotations

import hmac
import logging
import re
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wavelink
from aiohttp import web

from ..errors import HexError
from .api import Api, ApiError
from .auth import SESSION_COOKIE, STATE_COOKIE, Auth, AuthExpired, DiscordAPIError, Session

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.web")

STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_API = {"/api/public", "/api/i18n"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSP = (
    "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class WebPanel:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self.auth = Auth(bot)
        self.api = Api(bot, self.auth)
        self.app = self._build_app()
        self._runner: web.AppRunner | None = None

    # ───── Aplicación ─────

    def _build_app(self) -> web.Application:
        @web.middleware
        async def api_middleware(request: web.Request, handler: Any) -> web.StreamResponse:
            if not request.path.startswith("/api/"):
                return await handler(request)

            lang = self.api.lang(request)
            t = self.bot.i18n.t
            try:
                if request.path not in PUBLIC_API:
                    session = await self.auth.get_session(request.cookies.get(SESSION_COOKIE))
                    if session is None:
                        raise ApiError(401, "web.errors.session")
                    if request.method not in SAFE_METHODS:
                        self._check_csrf(request, session)
                    request["session"] = session
                return await handler(request)
            except ApiError as exc:
                return self._error(exc.status, t(lang, exc.key, **exc.kwargs))
            except HexError as exc:
                return self._error(400, t(lang, exc.key, **exc.kwargs))
            except AuthExpired:
                session = request.get("session")
                if session is not None:
                    await self.auth.destroy(session)
                return self._error(401, t(lang, "web.errors.session"))
            except DiscordAPIError:
                return self._error(502, t(lang, "web.errors.discord"))
            except wavelink.LavalinkException as exc:
                return self._error(502, t(lang, "errors.lavalink", error=exc.error))
            except web.HTTPException:
                raise
            except Exception:  # noqa: BLE001
                log.exception("Error no controlado en %s %s", request.method, request.path)
                return self._error(500, t(lang, "errors.unexpected"))

        app = web.Application(middlewares=[api_middleware], client_max_size=256 * 1024)
        app.on_response_prepare.append(self._security_headers)
        app.router.add_get("/", self.index)
        app.router.add_get("/auth/login", self.login)
        app.router.add_get("/auth/callback", self.callback)
        app.router.add_post("/auth/logout", self.logout)
        app.router.add_static("/static/", STATIC_DIR)
        self.api.register(app)
        return app

    async def start(self) -> None:
        cfg = self.bot.config.web
        await self.bot.db.purge_web_sessions()
        self._runner = web.AppRunner(self.app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host=str(cfg.host), port=int(cfg.port))
        await site.start()
        log.info("Panel web disponible en %s (escuchando en %s:%s)", self.auth.public_url, cfg.host, cfg.port)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    # ───── Utilidades ─────

    @staticmethod
    async def _security_headers(request: web.Request, response: web.StreamResponse) -> None:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("Content-Security-Policy", CSP)
        if request.path.startswith("/api/") or request.path.startswith("/auth/"):
            response.headers["Cache-Control"] = "no-store"

    @staticmethod
    def _check_csrf(request: web.Request, session: Session) -> None:
        token = request.headers.get("X-CSRF-Token", "")
        if not hmac.compare_digest(token, session.csrf_token):
            raise ApiError(403, "web.errors.csrf")

    def _clean(self, text: str) -> str:
        """Los mensajes del bot usan formato de Discord; en la web se simplifican."""
        def channel_name(match: re.Match[str]) -> str:
            channel = self.bot.get_channel(int(match.group(1)))
            return f"#{getattr(channel, 'name', match.group(1))}"

        text = re.sub(r"<#(\d+)>", channel_name, text)
        return text.replace("**", "").replace("`", "")

    def _error(self, status: int, text: str) -> web.Response:
        return web.json_response({"error": self._clean(text)}, status=status)

    @staticmethod
    def _redirect(location: str) -> web.Response:
        return web.Response(status=302, headers={"Location": location})

    # ───── Rutas ─────

    async def index(self, request: web.Request) -> web.FileResponse:
        return web.FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    async def login(self, request: web.Request) -> web.Response:
        state = secrets.token_urlsafe(24)
        response = self._redirect(self.auth.login_url(state))
        response.set_cookie(STATE_COOKIE, state, max_age=600, path="/auth", httponly=True, samesite="Lax",
                            secure=self.auth.secure_cookies)
        return response

    async def callback(self, request: web.Request) -> web.Response:
        code = request.query.get("code")
        state = request.query.get("state", "")
        expected = request.cookies.get(STATE_COOKIE, "")
        if not code or not expected or not hmac.compare_digest(state, expected):
            return self._redirect("/?login_error=1")

        try:
            payload = await self.auth.exchange_code(code)
            token, session = await self.auth.create_session(payload)
        except (AuthExpired, DiscordAPIError, KeyError, ValueError) as exc:
            log.warning("Fallo en el inicio de sesión del panel (revisa WEB_CLIENT_SECRET y la URL de redirección): %r", exc)
            return self._redirect("/?login_error=1")

        response = self._redirect("/")
        response.set_cookie(SESSION_COOKIE, token, max_age=max(60, session.expires_at - int(time.time())), path="/",
                            httponly=True, samesite="Lax", secure=self.auth.secure_cookies)
        response.del_cookie(STATE_COOKIE, path="/auth")
        return response

    async def logout(self, request: web.Request) -> web.Response:
        session = await self.auth.get_session(request.cookies.get(SESSION_COOKIE))
        if session is not None:
            if not hmac.compare_digest(request.headers.get("X-CSRF-Token", ""), session.csrf_token):
                return web.json_response({"error": "csrf"}, status=403)
            await self.auth.destroy(session)
        response = web.json_response({"ok": True})
        response.del_cookie(SESSION_COOKIE, path="/")
        return response
