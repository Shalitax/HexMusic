"""Biblioteca de archivos subidos desde Discord (mp3, flac, ogg...), una por servidor.

Los enlaces de los adjuntos de Discord caducan en unas 24 h, así que para poder reproducir un archivo cuando
se quiera (y guardarlo en playlists o en la cola persistente) el bot guarda una copia en
``library.directory`` y se la sirve a Lavalink por HTTP desde un servidor interno pequeño. Cada enlace va
firmado (HMAC), así que nadie puede pedir otros archivos del disco. Lavalink lo reproduce con su fuente
``http``, que ya está activada: no hace falta habilitar la fuente ``local``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from aiohttp import web

from ..database import LibraryEntry
from ..errors import HexError
from ..utils.files import (AUDIO_EXTENSIONS, display_title, file_extension, has_known_title, is_audio_attachment,
                           retitle)
from .playback import search_tracks

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.library")

CONTENT_TYPES = {
    ".mp3": "audio/mpeg", ".flac": "audio/flac", ".wav": "audio/wav", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".opus": "audio/ogg", ".m4a": "audio/mp4", ".aac": "audio/aac", ".mp4": "video/mp4", ".webm": "audio/webm",
    ".mka": "audio/x-matroska", ".mkv": "video/x-matroska",
}
LIBRARY_PREFIX = "library:"


class Library:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        cfg = bot.config.library
        path = Path(str(cfg.directory or "data/library"))
        self.directory = path if path.is_absolute() else bot.root / path
        self.host = str(cfg.host or "127.0.0.1")
        self.port = int(cfg.port)
        self.base_url = (str(cfg.public_url or "") or f"http://127.0.0.1:{self.port}").rstrip("/")
        self.max_file_bytes = int(cfg.max_file_mb) * 1024 * 1024
        self.max_guild_bytes = int(cfg.max_guild_mb) * 1024 * 1024
        self.max_files = int(cfg.max_files)
        self._secret = b""
        self._runner: web.AppRunner | None = None

    @property
    def enabled(self) -> bool:
        return self.bot.feature("library")

    @property
    def running(self) -> bool:
        return self._runner is not None

    # ───── Servidor de archivos para Lavalink ─────

    def _load_secret(self) -> bytes:
        file = self.directory / ".secret"
        try:
            value = file.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if not value:
            value = secrets.token_hex(32)
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text(value, encoding="utf-8")
        return value.encode()

    def _token(self, guild_id: int, entry_id: int) -> str:
        return hmac.new(self._secret, f"{guild_id}:{entry_id}".encode(), hashlib.sha256).hexdigest()[:32]

    def path_for(self, entry: LibraryEntry) -> Path:
        return self.directory / str(entry.guild_id) / f"{entry.id}{entry.ext}"

    def url_for(self, entry: LibraryEntry) -> str:
        return f"{self.base_url}/files/{entry.guild_id}/{entry.id}/{self._token(entry.guild_id, entry.id)}{entry.ext}"

    async def start(self) -> None:
        if not self.enabled:
            return
        self.directory.mkdir(parents=True, exist_ok=True)
        self._secret = self._load_secret()
        self.sweep_temporary()
        app = web.Application()
        app.router.add_get("/files/{guild_id:\\d+}/{entry_id:\\d+}/{name}", self._serve)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, host=self.host, port=self.port).start()
        except OSError as exc:
            await runner.cleanup()
            log.error("No se pudo abrir el servidor de la biblioteca en %s:%s (%s); la biblioteca queda desactivada.",
                      self.host, self.port, exc)
            return
        self._runner = runner
        log.info("Biblioteca de archivos lista (Lavalink los lee desde %s).", self.base_url)

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _serve(self, request: web.Request) -> web.StreamResponse:
        guild_id = int(request.match_info["guild_id"])
        entry_id = int(request.match_info["entry_id"])
        name = request.match_info["name"]
        token, ext = PurePosixPath(name).stem, PurePosixPath(name).suffix.lower()
        if not hmac.compare_digest(token, self._token(guild_id, entry_id)):
            raise web.HTTPNotFound()
        entry = await self.bot.db.get_library_track(guild_id, entry_id)
        if entry is None or entry.ext != ext:
            raise web.HTTPNotFound()
        path = self.path_for(entry)
        if not path.is_file():
            raise web.HTTPNotFound()
        # FileResponse admite peticiones por rangos: Lavalink puede avanzar y retroceder en la canción
        return web.FileResponse(path, headers={"Content-Type": CONTENT_TYPES.get(ext, "application/octet-stream")})

    # ───── Gestión ─────

    def _require_running(self) -> None:
        if not self.enabled:
            raise HexError("errors.feature_disabled")
        if not self.running:
            raise HexError("errors.library_unavailable")

    async def _probe(self, url: str) -> wavelink.Playable:
        """Pide a Lavalink que cargue el archivo: así se sabe que se puede reproducir y cuánto dura."""
        try:
            results = await search_tracks(self.bot, url)
        except HexError as exc:
            if exc.key == "errors.no_nodes":
                raise
            raise HexError("errors.library_invalid_file") from None
        if isinstance(results, wavelink.Playlist) or not results:
            raise HexError("errors.library_invalid_file")
        return results[0]

    async def upload(self, guild: discord.Guild, attachment: discord.Attachment, uploader: discord.abc.User,
                     title: str | None = None) -> LibraryEntry:
        self._require_running()
        ext = file_extension(attachment.filename)
        if not is_audio_attachment(attachment) or ext not in AUDIO_EXTENSIONS:
            raise HexError("errors.library_bad_format", formats=", ".join(sorted(e.lstrip(".") for e in AUDIO_EXTENSIONS)))
        if attachment.size > self.max_file_bytes:
            raise HexError("errors.library_file_too_big", max=self.max_file_bytes // 1_048_576)
        count, used = await self.bot.db.library_usage(guild.id)
        if self.max_files and count >= self.max_files:
            raise HexError("errors.library_full_files", max=self.max_files)
        if self.max_guild_bytes and used + attachment.size > self.max_guild_bytes:
            raise HexError("errors.library_full_space", used=used // 1_048_576, max=self.max_guild_bytes // 1_048_576)

        folder = self.directory / str(guild.id)
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f"tmp-{uuid.uuid4().hex}{ext}"
        try:
            await attachment.save(temporary)
        except (discord.HTTPException, OSError) as exc:
            temporary.unlink(missing_ok=True)
            log.warning("No se pudo descargar el adjunto %s: %s", attachment.filename, exc)
            raise HexError("errors.library_download_failed") from None

        clean_title = (title or "").strip()[:100]
        entry = await self.bot.db.add_library_track(
            guild.id, clean_title or display_title(attachment.filename), attachment.filename[:200], ext,
            temporary.stat().st_size, uploader.id,
        )
        temporary.replace(self.path_for(entry))
        try:
            track = await self._probe(self.url_for(entry))
        except HexError:
            await self.delete(entry)
            raise
        # Si el archivo trae título en sus metadatos y no se indicó otro, se usa ese
        changes: dict[str, Any] = {"length": None if track.is_stream else track.length}
        if not clean_title and has_known_title(track):
            changes["title"] = track.title[:100]
        await self.bot.db.update_library_track(entry.id, **changes)
        entry.length = changes["length"]
        entry.title = changes.get("title", entry.title)
        log.info("Biblioteca de %s: subida %r (%d KB) por %s", guild.id, entry.title, entry.size // 1024, uploader.id)
        return entry

    async def delete(self, entry: LibraryEntry) -> None:
        self.path_for(entry).unlink(missing_ok=True)
        await self.bot.db.delete_library_track(entry.id)

    async def track_for(self, entry: LibraryEntry, requester_id: int) -> wavelink.Playable:
        """Canción reproducible de un archivo de la biblioteca."""
        self._require_running()
        if not self.path_for(entry).is_file():
            raise HexError("errors.library_missing_file", title=entry.title)
        track = retitle(await self._probe(self.url_for(entry)), entry.title, self.bot.i18n.t(None, "library.author"))
        track.extras = {"requester_id": requester_id}
        return track

    async def tracks_for(self, entries: list[LibraryEntry], requester_id: int) -> list[wavelink.Playable]:
        """Varias canciones de la biblioteca, de 10 en 10 para no saturar a Lavalink (las que fallen se omiten)."""
        tracks: list[wavelink.Playable] = []
        for start in range(0, len(entries), 10):
            batch = await asyncio.gather(*(self.track_for(entry, requester_id) for entry in entries[start:start + 10]),
                                         return_exceptions=True)
            tracks.extend(track for track in batch if isinstance(track, wavelink.Playable))
        return tracks

    async def resolve_query(self, guild_id: int, query: str, requester_id: int) -> wavelink.Playable | None:
        """``library:<id>`` (lo que devuelve el autocompletado) → canción de la biblioteca de ese servidor."""
        if not query.startswith(LIBRARY_PREFIX):
            return None
        try:
            entry_id = int(query[len(LIBRARY_PREFIX):])
        except ValueError:
            return None
        entry = await self.bot.db.get_library_track(guild_id, entry_id)
        if entry is None:
            raise HexError("errors.library_not_found", name=query)
        return await self.track_for(entry, requester_id)

    def sweep_temporary(self) -> None:
        """Borra descargas a medias de un arranque anterior."""
        cutoff = time.time() - 3600
        for file in self.directory.glob("*/tmp-*"):
            try:
                if file.stat().st_mtime < cutoff:
                    file.unlink()
            except OSError:
                pass
