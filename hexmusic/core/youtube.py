"""Cuenta de YouTube (OAuth) para el plugin youtube-source de Lavalink.

El bot gestiona la vinculación en lugar de Lavalink:

- Pide a Google el código de vinculación (flujo de dispositivo) y lo muestra en la consola y en el panel web.
- Comprueba el refresh token guardado antes de usarlo: si Google lo rechaza se descarta y se pide un código nuevo.
- Se lo entrega a cada nodo con la API REST del plugin (``POST /youtube``) cada vez que el nodo se conecta.

Así un token caducado ya no impide arrancar a Lavalink (antes el plugin lanzaba una excepción al leerlo de
application.yml y Lavalink se reiniciaba en bucle) y se puede volver a vincular sin reiniciar el servidor.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
import wavelink

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.youtube")

# Credenciales públicas del cliente de YouTube para TV: las mismas que usa youtube-source
# (dev.lavalink.youtube.http.YoutubeOauth2Handler). Los tokens que generan sirven para el plugin.
CLIENT_ID = "861556708454-d6dlm3lh05idd8npek18k6be8ba3oc68.apps.googleusercontent.com"
CLIENT_SECRET = "SboVhoG9s0rNafixCSGGKXAT"
SCOPES = "http://gdata.youtube.com https://www.googleapis.com/auth/youtube"
DEVICE_CODE_URL = "https://www.youtube.com/o/oauth2/device/code"
TOKEN_URL = "https://www.youtube.com/o/oauth2/token"
DEVICE_GRANT = "http://oauth.net/grant_type/device/1.0"

# Respuestas de Google que significan "este token ya no sirve" (no un fallo de red pasajero)
REJECTED_ERRORS = {"invalid_grant", "unauthorized_client", "invalid_client"}


class GoogleUnavailable(Exception):
    """Google no respondió o respondió algo inesperado: no se puede saber si el token es válido."""


class YouTubeAccount:
    """Estado de la cuenta vinculada. ``status``: off | pending | linking | linked | unverified."""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        cfg = bot.config.youtube
        self.enabled = bool(cfg.oauth)
        path = Path(str(cfg.token_file or "data/youtube-refresh-token.txt"))
        self.token_file = path if path.is_absolute() else bot.root / path
        self.panel_token = str(cfg.refresh_token or "").strip()

        self.refresh_token: str | None = None
        self.status = "pending" if self.enabled else "off"
        self.code: dict[str, Any] | None = None  # código de vinculación en curso (para el panel web)
        self._resolved = False
        self._lock = asyncio.Lock()
        self._link_task: asyncio.Task[None] | None = None
        self._missing_plugin: set[str] = set()

    # ───── Utilidades ─────

    def t(self, key: str, **kwargs: Any) -> str:
        return self.bot.i18n.t(self.bot.i18n.default, f"youtube.{key}", **kwargs)

    @staticmethod
    def _print(*lines: str) -> None:
        """Avisos para quien mira la consola (Pterodactyl, docker logs): siempre visibles, sin formato de log."""
        bar = "-" * 60
        print("\n".join([bar, *lines, bar]), flush=True)

    @property
    def linking(self) -> bool:
        return self._link_task is not None and not self._link_task.done()

    def _read_file(self) -> str:
        try:
            return self.token_file.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def _write_file(self, token: str) -> None:
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            self.token_file.write_text(token, encoding="utf-8")
        except OSError as exc:
            log.warning("No se pudo guardar el token de YouTube en %s: %s", self.token_file, exc)

    def _discard_file(self, *, keep_copy: bool) -> None:
        """Retira el token guardado. Con ``keep_copy`` se conserva como .invalido para soporte."""
        try:
            if keep_copy:
                self.token_file.replace(self.token_file.with_name(self.token_file.name + ".invalido"))
            else:
                self.token_file.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            log.warning("No se pudo retirar %s: %s", self.token_file, exc)

    async def _google(self, url: str, payload: dict[str, str]) -> dict[str, Any]:
        """POST a Google. Devuelve el JSON aunque el estado sea 4xx (ahí viene el campo ``error``)."""
        assert self.bot.http_session is not None
        try:
            async with self.bot.http_session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                try:
                    data = await resp.json(content_type=None)
                except ValueError:
                    data = None
                if not isinstance(data, dict):
                    raise GoogleUnavailable(f"HTTP {resp.status}")
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            raise GoogleUnavailable(str(exc) or type(exc).__name__) from exc

    async def check_token(self, token: str) -> bool:
        """``True`` si Google acepta el token, ``False`` si lo rechaza. ``GoogleUnavailable`` si no se sabe."""
        data = await self._google(TOKEN_URL, {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": token,
            "grant_type": "refresh_token",
        })
        if data.get("access_token"):
            return True
        if str(data.get("error")) in REJECTED_ERRORS:
            return False
        raise GoogleUnavailable(str(data.get("error") or "respuesta sin access_token"))

    # ───── Nodos de Lavalink ─────

    @staticmethod
    def _nodes() -> list[wavelink.Node]:
        return [node for node in wavelink.Pool.nodes.values() if node.status is wavelink.NodeStatus.CONNECTED]

    async def _push(self, node: wavelink.Node, token: str | None) -> bool:
        """Entrega el token al plugin del nodo (``None`` = desvincular). Devuelve si el nodo lo aceptó."""
        try:
            await node.send("POST", path="youtube", data={"refreshToken": token, "skipInitialization": True})
        except wavelink.LavalinkException as exc:
            if exc.status in (400, 404):
                # Sin plugin de YouTube (p. ej. un Lavalink externo distinto): se avisa una sola vez
                if node.identifier not in self._missing_plugin:
                    self._missing_plugin.add(node.identifier)
                    log.warning("El nodo %r no tiene el plugin de YouTube; no se le puede dar la cuenta.", node.identifier)
                return False
            log.warning("El nodo %r rechazó el token de YouTube: %s", node.identifier, exc.error)
            return False
        except (wavelink.NodeException, aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("No se pudo enviar el token de YouTube al nodo %r: %s", node.identifier, exc)
            return False

        if token:
            await self._sync_rotated(node, token)
        return True

    async def _sync_rotated(self, node: wavelink.Node, token: str) -> None:
        """Si Google entregó un refresh token nuevo al renovar, se guarda para el próximo arranque."""
        try:
            data = await node.send("GET", path="youtube")
        except Exception:  # noqa: BLE001 - es solo una comprobación
            return
        current = data.get("refreshToken") if isinstance(data, dict) else None
        if current and current != token:
            self.refresh_token = current
            self._write_file(current)
            log.info("YouTube entregó un refresh token nuevo; guardado.")

    async def _push_all(self, token: str | None) -> int:
        results = await asyncio.gather(*(self._push(node, token) for node in self._nodes()))
        return sum(results)

    async def on_node_ready(self, node: wavelink.Node) -> None:
        """Cada vez que un nodo se conecta (también si Lavalink se reinició) recibe el token."""
        if not self.enabled:
            return
        async with self._lock:
            if not self._resolved:
                await self._resolve()
        if self.refresh_token:
            await self._push(node, self.refresh_token)
        elif not self.linking:
            self.start_link()

    async def _resolve(self) -> None:
        """Elige el token a usar: primero el de la variable del panel y después el guardado."""
        self._resolved = True
        stored = self._read_file()
        candidates = [(self.panel_token, "panel"), (stored, "file")]
        seen: set[str] = set()

        for token, origin in candidates:
            if not token or token in seen:
                continue
            seen.add(token)
            try:
                valid = await self.check_token(token)
            except GoogleUnavailable as exc:
                # Sin respuesta de Google no se descarta nada: se usa y se vuelve a comprobar al reconectar
                log.warning("No se pudo comprobar el token de YouTube (%s); se usa igualmente.", exc)
                self.refresh_token, self.status = token, "unverified"
                self._resolved = False
                return
            if valid:
                self.refresh_token, self.status = token, "linked"
                if token != stored:
                    self._write_file(token)
                log.info("YouTube: cuenta vinculada (token %s).", "de la variable del panel" if origin == "panel" else "guardado")
                return
            if origin == "panel":
                self._print(self.t("panel_token_rejected"))
            else:
                self._discard_file(keep_copy=True)
                self._print(self.t("stored_token_rejected"))

        self.refresh_token = None
        self.status = "pending"

    # ───── Vinculación ─────

    def start_link(self) -> bool:
        """Empieza a pedir un código de vinculación. ``False`` si ya hay uno en curso."""
        if self.linking:
            return False
        self._link_task = asyncio.create_task(self._link_flow())
        return True

    async def _link_flow(self) -> None:
        self.status = "linking"
        try:
            try:
                data = await self._google(DEVICE_CODE_URL, {
                    "client_id": CLIENT_ID,
                    "scope": SCOPES,
                    "device_id": uuid.uuid4().hex,
                    "device_model": "ytlr::",
                })
            except GoogleUnavailable as exc:
                self._print(self.t("code_failed", error=exc))
                return
            device_code = str(data.get("device_code") or "")
            url = str(data.get("verification_url") or "https://www.google.com/device")
            user_code = str(data.get("user_code") or "")
            if not device_code or not user_code:
                self._print(self.t("code_failed", error=data.get("error") or "?"))
                return

            interval = max(5, int(data.get("interval") or 5))
            expires_in = int(data.get("expires_in") or 1800)
            deadline = time.monotonic() + expires_in
            self.code = {"url": url, "code": user_code, "expires_at": int(time.time()) + expires_in}
            self._print(
                self.t("link_title"),
                self.t("link_step_open", url=url),
                self.t("link_step_code", code=user_code),
                self.t("link_step_account"),
                self.t("link_footer", minutes=max(1, expires_in // 60)),
            )

            while time.monotonic() < deadline:
                await asyncio.sleep(interval)
                try:
                    result = await self._google(TOKEN_URL, {
                        "client_id": CLIENT_ID,
                        "client_secret": CLIENT_SECRET,
                        "code": device_code,
                        "grant_type": DEVICE_GRANT,
                    })
                except GoogleUnavailable as exc:
                    log.debug("Esperando la vinculación de YouTube: %s", exc)
                    continue

                error = result.get("error")
                if error == "authorization_pending":
                    continue
                if error == "slow_down":
                    interval += 5
                    continue
                if error == "access_denied":
                    self._print(self.t("link_denied"))
                    return
                if error == "expired_token":
                    break
                if error or not result.get("refresh_token"):
                    self._print(self.t("code_failed", error=error or "?"))
                    return

                token = str(result["refresh_token"])
                self.refresh_token, self.status = token, "linked"
                self._write_file(token)
                nodes = await self._push_all(token)
                self._print(self.t("link_done", nodes=nodes))
                return

            self._print(self.t("link_expired"))
        finally:
            self.code = None
            if self.status == "linking":
                self.status = "linked" if self.refresh_token else "pending"

    def cancel_link(self) -> None:
        if self.linking:
            assert self._link_task is not None
            self._link_task.cancel()

    async def unlink(self) -> int:
        """Olvida la cuenta: borra el token guardado y lo retira de los nodos."""
        self.cancel_link()
        self.refresh_token = None
        self.status = "pending" if self.enabled else "off"
        self._discard_file(keep_copy=False)
        return await self._push_all(None)

    async def set_token(self, token: str) -> bool | None:
        """Usa un refresh token escrito a mano. ``None`` si no se pudo comprobar con Google."""
        try:
            if not await self.check_token(token):
                return False
        except GoogleUnavailable:
            return None
        self.cancel_link()
        self.refresh_token, self.status = token, "linked"
        self._resolved = True
        self._write_file(token)
        await self._push_all(token)
        return True

    async def close(self) -> None:
        self.cancel_link()

    def summary(self) -> dict[str, Any]:
        """Estado para la consola y el panel web (nunca incluye el token)."""
        return {
            "enabled": self.enabled,
            "status": self.status,
            "linking": self.linking,
            "code": dict(self.code) if self.code else None,
            "panel_token": bool(self.panel_token),
            "nodes": len(self._nodes()),
        }
