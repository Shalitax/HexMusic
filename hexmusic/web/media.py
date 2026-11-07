"""API del panel para buscar, letras, biblioteca de archivos e historial de un servidor."""

from __future__ import annotations

import random
import re
import secrets
import time
from collections import OrderedDict
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from aiohttp import BodyPartReader, web

from ..checks import get_player
from ..core.playback import SOURCE_LABELS, add_tracks, search_tracks
from ..errors import HexError
from ..utils.files import AUDIO_EXTENSIONS
from ..utils.lyrics import fetch_lyrics
from .api import ApiError

if TYPE_CHECKING:
    from .api import Api

RESULT_TTL = 900
RESULT_CACHE = 3000
LYRICS_CACHE = 200
MAX_PLAYLIST_RESULTS = 200


def ApiInvalid() -> ApiError:  # noqa: N802 - se lanza como una excepción más
    return ApiError(400, "web.errors.invalid_field")

_LRC_LINE = re.compile(r"\[(\d{1,3}):(\d{1,2})(?:[.:](\d{1,3}))?\]")


def parse_lrc(text: str) -> list[dict[str, Any]]:
    """``[01:23.45] verso`` → ``[{"t": 83450, "text": "verso"}]`` ordenado por tiempo."""
    lines: list[dict[str, Any]] = []
    for raw in text.splitlines():
        stamps = list(_LRC_LINE.finditer(raw))
        if not stamps:
            continue
        words = raw[stamps[-1].end():].strip()
        for stamp in stamps:
            minutes, seconds, fraction = stamp.groups()
            millis = int((fraction or "0").ljust(3, "0")[:3])
            lines.append({"t": (int(minutes) * 60 + int(seconds)) * 1000 + millis, "text": words})
    lines.sort(key=lambda item: item["t"])
    return lines


class MediaApi:
    def __init__(self, api: Api) -> None:
        self.api = api
        self.bot = api.bot
        self._results: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lyrics: OrderedDict[str, dict[str, Any] | None] = OrderedDict()

    def register(self, app: web.Application) -> None:
        router = app.router
        router.add_post("/api/guilds/{guild_id}/search", self.search)
        router.add_post("/api/guilds/{guild_id}/enqueue", self.enqueue)
        router.add_get("/api/guilds/{guild_id}/lyrics", self.lyrics)
        router.add_get("/api/guilds/{guild_id}/library", self.library)
        router.add_post("/api/guilds/{guild_id}/library", self.upload)
        router.add_post("/api/guilds/{guild_id}/library/play", self.library_play)
        router.add_patch("/api/guilds/{guild_id}/library/{entry_id}", self.library_rename)
        router.add_delete("/api/guilds/{guild_id}/library/{entry_id}", self.library_delete)
        router.add_get("/api/guilds/{guild_id}/history", self.history)
        router.add_get("/api/guilds/{guild_id}/history/summary", self.history_summary)
        router.add_delete("/api/guilds/{guild_id}/history", self.history_clear)
        router.add_get("/api/stats/history", self.global_history)

    # ───── Utilidades ─────

    def _remember(self, track: wavelink.Playable) -> str:
        """Guarda la canción en el servidor y devuelve un identificador para pedirla después."""
        token = secrets.token_urlsafe(9)
        data = dict(track.raw_data)
        data["userData"] = {}
        self._results[token] = (time.monotonic(), data)
        while len(self._results) > RESULT_CACHE:
            self._results.popitem(last=False)
        return token

    def tracks_from_ids(self, ids: Any, requester_id: int) -> list[wavelink.Playable]:
        if not isinstance(ids, list) or not ids or len(ids) > MAX_PLAYLIST_RESULTS:
            raise ApiInvalid()
        now = time.monotonic()
        tracks: list[wavelink.Playable] = []
        for token in ids:
            item = self._results.get(str(token))
            if item is None or now - item[0] > RESULT_TTL:
                raise HexError("web.errors.results_expired")
            try:
                track = wavelink.Playable(item[1])  # type: ignore[arg-type]
            except (KeyError, TypeError):
                continue
            track.extras = {"requester_id": requester_id}
            tracks.append(track)
        return tracks

    def _result_json(self, track: wavelink.Playable) -> dict[str, Any]:
        return {
            "id": self._remember(track),
            "title": track.title,
            "author": track.author,
            "uri": track.uri,
            "artwork": track.artwork,
            "length": track.length,
            "is_stream": track.is_stream,
            "source": track.source,
            "album": getattr(track.album, "name", None),
        }

    def _member_name(self, guild: discord.Guild, user_id: int | None) -> dict[str, Any] | None:
        if not user_id:
            return None
        member = guild.get_member(int(user_id))
        return {
            "id": str(user_id),
            "name": member.display_name if member else None,
            "avatar": member.display_avatar.url if member else None,
        }

    # ───── Búsqueda ─────

    async def search(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        data = await self.api.body(request)
        query = str(data.get("query") or "").strip()
        if not query or len(query) > 500:
            raise ApiInvalid()
        source = str(data["source"]) if data.get("source") else None
        if source and source not in SOURCE_LABELS:
            raise ApiInvalid()

        library = []
        if self.bot.feature("library"):
            library = [{"id": entry.id, "title": entry.title, "length": entry.length}
                       for entry in await self.bot.db.search_library(guild.id, query, limit=5)]

        results = await search_tracks(self.bot, query, source)
        if isinstance(results, wavelink.Playlist):
            tracks = list(results.tracks)[:MAX_PLAYLIST_RESULTS]
            playlist = {"name": results.name, "count": len(results.tracks), "artwork": results.artwork}
        else:
            limit = max(1, min(25, int(self.bot.config.player.search_results)))
            tracks = list(results)[:limit]
            playlist = None
        return web.json_response({
            "playlist": playlist,
            "tracks": [self._result_json(track) for track in tracks],
            "library": library,
        })

    async def enqueue(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        session = self.api.session(request)
        data = await self.api.body(request)
        tracks = self.tracks_from_ids(data.get("ids"), session.user_id)
        max_seconds = int(self.bot.config.player.max_track_duration)
        if max_seconds:
            tracks = [track for track in tracks if track.is_stream or track.length <= max_seconds * 1000]
        if not tracks:
            raise HexError("errors.track_too_long", limit=max_seconds // 60)
        if data.get("shuffle"):
            random.shuffle(tracks)
        player = await self.api.ensure_connected(guild, session.user_id, data.get("channel_id"))
        result = await add_tracks(self.bot, player, tracks, play_next=bool(data.get("next")))
        self.bot.notify_player(guild.id)
        return web.json_response({"added": len(result.tracks), "started": result.started})

    # ───── Letras ─────

    async def lyrics(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        if not self.bot.feature("lyrics"):
            raise HexError("errors.feature_disabled")
        player = get_player(guild)
        track = player.current if player is not None else None
        if track is None:
            raise HexError("errors.nothing_playing")

        key = track.uri or f"{track.title}|{track.author}"
        if key in self._lyrics:
            self._lyrics.move_to_end(key)
            result = self._lyrics[key]
        else:
            assert self.bot.http_session is not None
            found = await fetch_lyrics(self.bot.http_session, title=track.title, artist=track.author,
                                       duration_ms=None if track.is_stream else track.length, source=track.source)
            result = None if found is None else {
                "title": found.title,
                "artist": found.artist,
                "text": found.text,
                "instrumental": found.instrumental,
                "synced": parse_lrc(found.synced) if found.synced else [],
            }
            self._lyrics[key] = result
            while len(self._lyrics) > LYRICS_CACHE:
                self._lyrics.popitem(last=False)
        return web.json_response({"track": {"title": track.title, "author": track.author, "uri": track.uri},
                                  "lyrics": result})

    # ───── Biblioteca ─────

    def _require_library(self) -> None:
        if not self.bot.feature("library"):
            raise HexError("errors.feature_disabled")

    async def _entry(self, guild: discord.Guild, request: web.Request):  # type: ignore[no-untyped-def]
        entry_id = self.api.snowflake(request.match_info["entry_id"])
        entry = await self.bot.db.get_library_track(guild.id, entry_id)
        if entry is None:
            raise HexError("errors.library_not_found", name=str(entry_id))
        return entry

    async def library(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        library = self.bot.library
        entries = await self.bot.db.list_library(guild.id) if library.enabled else []
        count, used = await self.bot.db.library_usage(guild.id)
        return web.json_response({
            "enabled": library.enabled,
            "running": library.running,
            "formats": sorted(ext.lstrip(".") for ext in AUDIO_EXTENSIONS),
            "usage": {"count": count, "used": used, "max_bytes": library.max_guild_bytes,
                      "max_files": library.max_files, "max_file_bytes": library.max_file_bytes},
            "entries": [{
                "id": entry.id,
                "title": entry.title,
                "filename": entry.filename,
                "ext": entry.ext.lstrip("."),
                "size": entry.size,
                "length": entry.length,
                "created_at": entry.created_at,
                "uploader": self._member_name(guild, entry.uploader_id),
            } for entry in entries],
        })

    async def upload(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        self._require_library()
        session = self.api.session(request)
        try:
            reader = await request.multipart()
        except (AssertionError, ValueError, KeyError):
            raise ApiInvalid() from None

        title: str | None = None
        while True:
            part = await reader.next()
            if part is None:
                raise ApiInvalid()
            if not isinstance(part, BodyPartReader):
                continue
            if part.name == "title":
                title = (await part.text())[:200]
                continue
            if part.name == "file" and part.filename:
                file_part = part
                break

        async def chunks() -> AsyncIterator[bytes]:
            while True:
                chunk = await file_part.read_chunk(256 * 1024)
                if not chunk:
                    break
                yield chunk

        entry = await self.bot.library.upload_stream(guild.id, file_part.filename, chunks(), session.user_id, title)
        return web.json_response({"id": entry.id, "title": entry.title, "length": entry.length}, status=201)

    async def library_rename(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        entry = await self._entry(guild, request)
        title = " ".join(str((await self.api.body(request)).get("title") or "").split())[:100]
        if not title:
            raise ApiInvalid()
        await self.bot.db.update_library_track(entry.id, title=title)
        return web.json_response({"id": entry.id, "title": title})

    async def library_delete(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        entry = await self._entry(guild, request)
        await self.bot.library.delete(entry)
        return web.json_response({"ok": True})

    async def library_play(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        self._require_library()
        session = self.api.session(request)
        data = await self.api.body(request)
        if data.get("all"):
            entries = await self.bot.db.list_library(guild.id)
        else:
            ids = data.get("ids")
            if not isinstance(ids, list) or not ids or len(ids) > 500:
                raise ApiInvalid()
            entries = []
            for raw in ids:
                entry = await self.bot.db.get_library_track(guild.id, self.api.snowflake(raw))
                if entry is not None:
                    entries.append(entry)
        if not entries:
            raise HexError("errors.library_empty")
        if data.get("shuffle"):
            random.shuffle(entries)
        player = await self.api.ensure_connected(guild, session.user_id, data.get("channel_id"))
        tracks = await self.bot.library.tracks_for(entries, session.user_id)
        if not tracks:
            raise HexError("errors.library_invalid_file")
        result = await add_tracks(self.bot, player, tracks, play_next=bool(data.get("next")))
        self.bot.notify_player(guild.id)
        return web.json_response({"added": len(result.tracks)})

    # ───── Historial ─────

    def _history_json(self, guild: discord.Guild, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "author": row["author"],
            "uri": row["uri"],
            "source": row["source"],
            "artwork": row["artwork"],
            "length": row["length"],
            "is_stream": bool(row["is_stream"]),
            "autoplay": bool(row["autoplay"]),
            "played_at": row["played_at"],
            "requester": self._member_name(guild, row["requester_id"]),
        }

    async def history(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        limit = self.api.int_value(request.query.get("limit", 50), 1, 100)
        before = request.query.get("before")
        rows = await self.bot.db.list_history(guild.id, limit=limit,
                                              before_id=self.api.snowflake(before) if before else None)
        return web.json_response({
            "enabled": bool(self.bot.config.history.enabled),
            "retention_days": int(self.bot.config.history.retention_days),
            "items": [self._history_json(guild, row) for row in rows],
            "more": len(rows) == limit,
        })

    def _range(self, request: web.Request) -> tuple[int, int, int]:
        days = self.api.int_value(request.query.get("days", 30), 1, 365)
        tz_minutes = self.api.int_value(request.query.get("tz", 0), -840, 840)
        return days, tz_minutes * 60, int(time.time()) - days * 86400

    async def history_summary(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        days, tz_offset, since = self._range(request)
        summary = await self.bot.db.history_summary(guild.id, since=since, tz_offset=tz_offset)
        summary["top_users"] = [{**(self._member_name(guild, item["requester_id"]) or {}), "plays": item["plays"]}
                                for item in summary["top_users"]]
        summary["days"] = days
        return web.json_response(summary)

    async def history_clear(self, request: web.Request) -> web.Response:
        guild = await self.api.guild_for(request)
        await self.bot.db.clear_history(guild.id)
        return web.json_response({"ok": True})

    async def global_history(self, request: web.Request) -> web.Response:
        await self.api.require_owner(request)
        days, tz_offset, since = self._range(request)
        summary = await self.bot.db.history_summary(None, since=since, tz_offset=tz_offset)
        users = []
        for item in summary["top_users"]:
            user = self.bot.get_user(int(item["requester_id"]))
            users.append({"id": str(item["requester_id"]), "name": user.display_name if user else None,
                          "avatar": user.display_avatar.url if user else None, "plays": item["plays"]})
        summary["top_users"] = users
        summary["days"] = days
        return web.json_response(summary)

