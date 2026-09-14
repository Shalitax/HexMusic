"""API JSON del panel web."""

from __future__ import annotations

import math
import platform
import random
import time
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from aiohttp import web

from .. import __version__
from ..checks import get_player
from ..core.panel import edit_panel, refresh_panel
from ..core.playback import SOURCE_LABELS, add_tracks, connect_player, enqueue
from ..core.presets import build_filters, get_presets
from ..database import clean_playlist_name
from ..errors import HexError
from ..player import HexPlayer
from .auth import Auth, Session

if TYPE_CHECKING:
    from ..bot import HexMusic

INVITE_PERMISSIONS = 3533904
LOOP_NAMES = {
    wavelink.QueueMode.normal: "off",
    wavelink.QueueMode.loop: "track",
    wavelink.QueueMode.loop_all: "queue",
}
LOOP_VALUES = {name: mode for mode, name in LOOP_NAMES.items()}
FEATURES = ("autoplay", "stay_247", "lyrics", "request_channel", "vote_skip")


class ApiError(Exception):
    def __init__(self, status: int, key: str, /, **kwargs: Any) -> None:
        super().__init__(key)
        self.status = status
        self.key = key
        self.kwargs = kwargs


def _invalid() -> ApiError:
    return ApiError(400, "web.errors.invalid_field")


def track_json(track: wavelink.Playable, guild: discord.Guild | None) -> dict[str, Any]:
    requester_id = HexPlayer.requester_id(track)
    member = guild.get_member(requester_id) if guild is not None and requester_id else None
    return {
        "title": track.title,
        "author": track.author,
        "uri": track.uri,
        "artwork": track.artwork,
        "length": track.length,
        "is_stream": track.is_stream,
        "source": track.source,
        "recommended": track.recommended,
        "requester": {"id": str(requester_id), "name": member.display_name if member else None} if requester_id else None,
    }


class Api:
    def __init__(self, bot: HexMusic, auth: Auth) -> None:
        self.bot = bot
        self.auth = auth

    def register(self, app: web.Application) -> None:
        router = app.router
        router.add_get("/api/public", self.public)
        router.add_get("/api/i18n", self.strings)
        router.add_get("/api/me", self.me)
        router.add_get("/api/stats", self.stats)
        router.add_get("/api/guilds/{guild_id}", self.guild)
        router.add_patch("/api/guilds/{guild_id}/settings", self.update_settings)
        router.add_get("/api/guilds/{guild_id}/player", self.player)
        router.add_post("/api/guilds/{guild_id}/player", self.player_action)
        router.add_get("/api/playlists", self.playlists)
        router.add_post("/api/playlists", self.create_playlist)
        router.add_get("/api/playlists/{playlist_id}", self.playlist)
        router.add_patch("/api/playlists/{playlist_id}", self.rename_playlist)
        router.add_delete("/api/playlists/{playlist_id}", self.delete_playlist)
        router.add_delete("/api/playlists/{playlist_id}/tracks/{index}", self.remove_playlist_track)
        router.add_post("/api/playlists/{playlist_id}/play", self.play_playlist)

    # ───── Utilidades ─────

    def lang(self, request: web.Request) -> str:
        lang = request.headers.get("X-Lang", "")
        return lang if lang in self.bot.i18n.languages else self.bot.i18n.default

    @staticmethod
    def session(request: web.Request) -> Session:
        return request["session"]

    @staticmethod
    async def body(request: web.Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            raise _invalid() from None
        if not isinstance(data, dict):
            raise _invalid()
        return data

    @staticmethod
    def _int(value: Any, minimum: int, maximum: int) -> int:
        if isinstance(value, bool):
            raise _invalid()
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise _invalid() from None
        if not minimum <= number <= maximum:
            raise _invalid()
        return number

    @staticmethod
    def _snowflake(value: Any) -> int:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            raise _invalid() from None

    @staticmethod
    def _icon(guild_id: int, icon: str | None) -> str | None:
        return f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.png?size=96" if icon else None

    def _invite_url(self, guild_id: int) -> str | None:
        if not self.auth.client_id:
            return None
        return discord.utils.oauth_url(
            self.auth.client_id,
            permissions=discord.Permissions(INVITE_PERMISSIONS),
            guild=discord.Object(id=guild_id),
            scopes=("bot", "applications.commands"),
            disable_guild_select=True,
        )

    async def guild_for(self, request: web.Request) -> discord.Guild:
        guild_id = self._snowflake(request.match_info["guild_id"])
        if not await self.auth.can_manage(self.session(request), guild_id):
            raise ApiError(403, "web.errors.forbidden")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ApiError(404, "web.errors.bot_not_in_guild")
        return guild

    async def _connect(self, guild: discord.Guild, user_id: int, channel_id: Any) -> HexPlayer:
        """Canal elegido en el panel o, si no, el canal de voz donde esté el usuario."""
        channel: discord.abc.GuildChannel | None = None
        if channel_id not in (None, ""):
            channel = guild.get_channel(self._snowflake(channel_id))
        if channel is None:
            for voice_channel in (*guild.voice_channels, *guild.stage_channels):
                if user_id in voice_channel.voice_states:
                    channel = voice_channel
                    break
        if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            raise ApiError(400, "web.errors.choose_channel")
        return await connect_player(self.bot, channel, None)

    # ───── Público ─────

    async def public(self, request: web.Request) -> web.Response:
        user = self.bot.user
        return web.json_response({
            "name": str(self.bot.config.bot.name),
            "color": str(self.bot.config.branding.color),
            "avatar": user.display_avatar.url if user else None,
            "version": __version__,
        })

    async def strings(self, request: web.Request) -> web.Response:
        i18n = self.bot.i18n
        lang = request.query.get("lang", "")
        if lang not in i18n.languages:
            lang = i18n.default
        return web.json_response({
            "lang": lang,
            "languages": [{"code": code, "name": i18n.language_name(code)} for code in i18n.languages],
            "strings": i18n.section(lang, "web"),
        })

    # ───── Sesión ─────

    async def me(self, request: web.Request) -> web.Response:
        session = self.session(request)
        owner = await self.auth.is_owner(session)
        manageable = await self.auth.manageable_guilds(session)

        guilds = []
        for guild_id, data in manageable.items():
            guild = self.bot.get_guild(guild_id)
            guilds.append({
                "id": str(guild_id),
                "name": guild.name if guild else str(data.get("name") or guild_id),
                "icon": (guild.icon.url if guild and guild.icon else self._icon(guild_id, data.get("icon"))),
                "bot_present": guild is not None,
                "invite_url": None if guild else self._invite_url(guild_id),
            })
        if owner:
            for guild in self.bot.guilds:
                if guild.id not in manageable:
                    guilds.append({"id": str(guild.id), "name": guild.name, "icon": guild.icon.url if guild.icon else None,
                                   "bot_present": True, "invite_url": None})
        guilds.sort(key=lambda item: (not item["bot_present"], item["name"].lower()))

        return web.json_response({
            "user": {"id": str(session.user_id), "name": session.display_name, "avatar": session.avatar_url},
            "owner": owner,
            "csrf": session.csrf_token,
            "guilds": guilds,
        })

    # ───── Estadísticas ─────

    async def stats(self, request: web.Request) -> web.Response:
        owner = await self.auth.is_owner(self.session(request))
        nodes = []
        for node in wavelink.Pool.nodes.values():
            item: dict[str, Any] = {
                "identifier": node.identifier,
                "online": node.status is wavelink.NodeStatus.CONNECTED,
                "players": len(node.players),
            }
            if item["online"]:
                try:
                    stats = await node.fetch_stats()
                    item.update(
                        players=stats.players, playing=stats.playing, uptime=stats.uptime,
                        memory_used=stats.memory.used, memory_allocated=stats.memory.allocated,
                        cpu=round(stats.cpu.lavalink_load * 100, 1), system_cpu=round(stats.cpu.system_load * 100, 1),
                        cores=stats.cpu.cores,
                    )
                except Exception:  # noqa: BLE001
                    pass
            nodes.append(item)

        players = [p for node in wavelink.Pool.nodes.values() for p in node.players.values() if isinstance(p, HexPlayer)]
        latency = self.bot.latency
        data: dict[str, Any] = {
            "servers": len(self.bot.guilds),
            "players": len(players),
            "playing": sum(1 for p in players if p.current is not None and not p.paused),
            "uptime": int(time.time() - self.bot.started_at),
            "latency": round(latency * 1000) if math.isfinite(latency) else None,
            "versions": {
                "hexmusic": __version__,
                "discord": discord.__version__,
                "wavelink": getattr(wavelink, "__version__", "?"),
                "python": platform.python_version(),
            },
            "nodes": nodes,
            "active": None,
        }
        if owner:
            data["active"] = [
                {
                    "guild": {"id": str(p.guild.id), "name": p.guild.name, "icon": p.guild.icon.url if p.guild.icon else None},
                    "channel": p.channel.name if p.channel else None,
                    "listeners": len(p.listeners),
                    "paused": p.paused,
                    "track": {"title": p.current.title, "author": p.current.author} if p.current else None,
                }
                for p in players
                if p.guild is not None
            ]
        return web.json_response(data)

    # ───── Servidor ─────

    async def _guild_payload(self, guild: discord.Guild) -> dict[str, Any]:
        cfg = self.bot.config
        i18n = self.bot.i18n
        settings = await self.bot.db.get_guild(guild.id)

        def snowflake(value: int | None) -> str | None:
            return str(value) if value else None

        return {
            "id": str(guild.id),
            "name": guild.name,
            "icon": guild.icon.url if guild.icon else None,
            "settings": {
                "language": settings.language,
                "prefix": settings.prefix,
                "dj_role_id": snowflake(settings.dj_role_id),
                "default_volume": settings.default_volume,
                "vote_skip": settings.vote_skip,
                "announce": settings.announce,
                "autoplay": settings.autoplay,
                "stay_247": settings.stay_247,
                "stay_channel_id": snowflake(settings.stay_channel_id),
                "request_channel_id": snowflake(settings.request_channel_id),
            },
            "defaults": {
                "language": i18n.default,
                "prefix": str(cfg.bot.prefix),
                "default_volume": int(cfg.player.default_volume),
                "vote_skip": bool(cfg.vote_skip.default_enabled),
                "announce": bool(cfg.player.announce_tracks),
            },
            "languages": [{"code": code, "name": i18n.language_name(code)} for code in i18n.languages],
            "roles": [{"id": str(role.id), "name": role.name} for role in reversed(guild.roles)
                      if not role.is_default() and not role.managed],
            "text_channels": [{"id": str(channel.id), "name": channel.name} for channel in guild.text_channels],
            "voice_channels": [
                {"id": str(channel.id), "name": channel.name, "members": len([m for m in channel.members if not m.bot])}
                for channel in (*guild.voice_channels, *guild.stage_channels)
            ],
            "presets": sorted(get_presets(cfg)),
            "sources": [{"value": key, "label": label} for key, label in SOURCE_LABELS.items()],
            "max_volume": int(cfg.player.max_volume),
            "features": {name: self.bot.feature(name) for name in FEATURES},
        }

    async def guild(self, request: web.Request) -> web.Response:
        guild = await self.guild_for(request)
        return web.json_response(await self._guild_payload(guild))

    async def update_settings(self, request: web.Request) -> web.Response:
        guild = await self.guild_for(request)
        data = await self.body(request)
        cfg = self.bot.config
        changes: dict[str, Any] = {}

        for key, value in data.items():
            if key == "language":
                if value in (None, ""):
                    changes[key] = None
                elif value in self.bot.i18n.languages:
                    changes[key] = value
                else:
                    raise HexError("errors.invalid_language", languages=", ".join(self.bot.i18n.languages))
            elif key == "prefix":
                prefix = str(value or "").strip()
                if len(prefix) > 10:
                    raise _invalid()
                changes[key] = prefix or None
            elif key == "dj_role_id":
                if value in (None, ""):
                    changes[key] = None
                else:
                    role = guild.get_role(self._snowflake(value))
                    if role is None or role.is_default():
                        raise _invalid()
                    changes[key] = role.id
            elif key == "default_volume":
                changes[key] = None if value in (None, "") else self._int(value, 0, int(cfg.player.max_volume))
            elif key in ("vote_skip", "announce"):
                if value is not None and not isinstance(value, bool):
                    raise _invalid()
                changes[key] = value
            elif key in ("autoplay", "stay_247"):
                if not isinstance(value, bool):
                    raise _invalid()
                changes[key] = value
            else:
                raise _invalid()

        player = get_player(guild)
        settings = await self.bot.db.get_guild(guild.id)

        if "autoplay" in changes:
            if changes["autoplay"] and not self.bot.feature("autoplay"):
                raise HexError("errors.feature_disabled")
            if player is not None:
                player.autoplay_enabled = changes["autoplay"]
                if player.current is not None:
                    player.sync_autoplay()

        if "stay_247" in changes:
            if changes["stay_247"] and not settings.stay_247:
                if not self.bot.feature("stay_247"):
                    raise HexError("errors.feature_disabled")
                if player is None or not player.connected or player.channel is None:
                    raise ApiError(400, "web.errors.stay_needs_player")
                changes["stay_channel_id"] = player.channel.id
                player.stay_247 = True
                player.inactive_timeout = None
                player.cancel_empty_task()
            elif not changes["stay_247"] and settings.stay_247:
                changes["stay_channel_id"] = None
                if player is not None:
                    player.stay_247 = False
                    player.inactive_timeout = int(cfg.player.idle_timeout) or None

        if changes:
            await self.bot.db.update_guild(guild.id, **changes)
        return web.json_response(await self._guild_payload(guild))

    # ───── Reproductor ─────

    def _player_payload(self, guild: discord.Guild) -> dict[str, Any]:
        player = get_player(guild)
        if player is None or not player.connected:
            return {"connected": False}
        queue = list(player.queue)
        return {
            "connected": True,
            "channel": {"id": str(player.channel.id), "name": player.channel.name} if player.channel else None,
            "listeners": len(player.listeners),
            "paused": player.paused,
            "volume": player.volume,
            "loop": LOOP_NAMES[player.queue.mode],
            "autoplay": player.autoplay_enabled,
            "stay_247": player.stay_247,
            "filter": player.filter_name,
            "position": player.position,
            "current": track_json(player.current, guild) if player.current else None,
            "queue": [track_json(track, guild) for track in queue[:100]],
            "queue_length": len(queue),
            "queue_duration": sum(track.length for track in queue if not track.is_stream),
        }

    async def player(self, request: web.Request) -> web.Response:
        guild = await self.guild_for(request)
        return web.json_response(self._player_payload(guild))

    async def player_action(self, request: web.Request) -> web.Response:
        guild = await self.guild_for(request)
        session = self.session(request)
        data = await self.body(request)
        action = str(data.get("action") or "")
        player = get_player(guild)
        connected = player is not None and player.connected

        if action == "play":
            query = str(data.get("query") or "").strip()
            if not query or len(query) > 500:
                raise _invalid()
            if player is None or not connected:
                player = await self._connect(guild, session.user_id, data.get("channel_id"))
            source = data.get("source") or None
            await enqueue(self.bot, player, discord.Object(id=session.user_id), query,
                          source=str(source) if source else None, play_next=bool(data.get("next")))
        elif action == "join":
            channel = guild.get_channel(self._snowflake(data.get("channel_id")))
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                raise ApiError(400, "web.errors.choose_channel")
            if player is not None and connected:
                await player.move_to(channel)
            else:
                await connect_player(self.bot, channel, None)
        else:
            if player is None or not connected:
                raise HexError("errors.no_player")
            await self._control(guild, player, action, data)

        return web.json_response(self._player_payload(guild))

    async def _control(self, guild: discord.Guild, player: HexPlayer, action: str, data: dict[str, Any]) -> None:
        cfg = self.bot.config
        queue_size = len(player.queue)

        if action == "pause":
            if player.current is None:
                raise HexError("errors.nothing_playing")
            player.paused_by_empty = False
            await player.pause(bool(data.get("paused", not player.paused)))
        elif action == "skip":
            if player.current is None:
                raise HexError("errors.nothing_playing")
            await player.skip(force=True)
        elif action == "previous":
            if await player.go_previous() is None:
                raise HexError("errors.no_previous")
        elif action == "stop":
            await player.stop_and_clear()
            await refresh_panel(self.bot, guild, player, idle=True)
            return
        elif action == "leave":
            settings = await self.bot.db.get_guild(guild.id)
            if settings.stay_247:
                await self.bot.db.update_guild(guild.id, stay_247=False, stay_channel_id=None)
            player.cancel_empty_task()
            await player.disconnect()
            await refresh_panel(self.bot, guild, player, idle=True)
            return
        elif action == "volume":
            await player.set_volume(self._int(data.get("value"), 0, int(cfg.player.max_volume)))
        elif action == "seek":
            track = player.current
            if track is None or track.is_stream or not track.is_seekable:
                raise HexError("errors.not_seekable")
            await player.seek(self._int(data.get("position"), 0, max(0, track.length - 1000)))
        elif action == "loop":
            mode = LOOP_VALUES.get(str(data.get("mode")))
            if mode is None:
                raise _invalid()
            player.queue.mode = mode
        elif action == "autoplay":
            if not self.bot.feature("autoplay"):
                raise HexError("errors.feature_disabled")
            player.autoplay_enabled = bool(data.get("enabled"))
            await self.bot.db.update_guild(guild.id, autoplay=player.autoplay_enabled)
            if player.current is not None:
                player.sync_autoplay()
        elif action == "filter":
            name = str(data.get("preset") or "").lower().strip()
            if not name:
                await player.apply_filters(wavelink.Filters(), None)
            else:
                payload = get_presets(cfg).get(name)
                if payload is None:
                    raise HexError("errors.preset_not_found", name=name)
                await player.apply_filters(build_filters(payload), name)
        elif action in ("shuffle", "clear", "remove", "move", "skipto"):
            if not queue_size:
                raise HexError("errors.queue_empty")
            if action == "shuffle":
                player.queue.shuffle()
            elif action == "clear":
                player.queue.clear()
            elif action == "remove":
                player.queue.delete(self._int(data.get("index"), 1, queue_size) - 1)
            elif action == "move":
                source = self._int(data.get("from"), 1, queue_size)
                target = self._int(data.get("to"), 1, queue_size)
                track = player.queue[source - 1]
                player.queue.delete(source - 1)
                player.queue.put_at(target - 1, track)
            else:
                index = self._int(data.get("index"), 1, queue_size)
                if index > 1:
                    del player.queue[: index - 1]
                if player.current is not None:
                    await player.skip(force=True)
                else:
                    await player.play(player.queue.get())
        else:
            raise _invalid()

        await edit_panel(self.bot, guild, player)

    # ───── Playlists ─────

    async def _playlist(self, request: web.Request):  # type: ignore[no-untyped-def]
        playlist_id = self._snowflake(request.match_info["playlist_id"])
        playlist = await self.bot.db.get_playlist_by_id(self.session(request).user_id, playlist_id)
        if playlist is None:
            raise ApiError(404, "web.errors.not_found")
        return playlist

    async def playlists(self, request: web.Request) -> web.Response:
        items = await self.bot.db.list_playlists(self.session(request).user_id)
        return web.json_response({
            "playlists": [{"id": item.id, "name": item.name, "tracks": item.track_count, "created_at": item.created_at}
                          for item in items],
            "limits": {"max_playlists": int(self.bot.config.playlists.max_per_user),
                       "max_tracks": int(self.bot.config.playlists.max_tracks)},
        })

    async def create_playlist(self, request: web.Request) -> web.Response:
        data = await self.body(request)
        name = clean_playlist_name(str(data.get("name") or ""))
        playlist_id = await self.bot.db.create_playlist(self.session(request).user_id, name,
                                                        limit=int(self.bot.config.playlists.max_per_user))
        return web.json_response({"id": playlist_id, "name": name}, status=201)

    async def playlist(self, request: web.Request) -> web.Response:
        playlist = await self._playlist(request)
        rows = await self.bot.db.get_tracks(playlist.id)
        return web.json_response({
            "id": playlist.id,
            "name": playlist.name,
            "tracks": [
                {"index": index, "title": row["title"], "author": row["author"], "uri": row["uri"], "length": row["length"] or 0}
                for index, row in enumerate(rows, start=1)
            ],
        })

    async def rename_playlist(self, request: web.Request) -> web.Response:
        playlist = await self._playlist(request)
        data = await self.body(request)
        name = clean_playlist_name(str(data.get("name") or ""))
        await self.bot.db.rename_playlist(playlist.id, name)
        return web.json_response({"id": playlist.id, "name": name})

    async def delete_playlist(self, request: web.Request) -> web.Response:
        playlist = await self._playlist(request)
        await self.bot.db.delete_playlist(playlist.id)
        return web.json_response({"ok": True})

    async def remove_playlist_track(self, request: web.Request) -> web.Response:
        playlist = await self._playlist(request)
        index = self._int(request.match_info["index"], 1, max(1, playlist.track_count))
        if await self.bot.db.remove_track(playlist.id, index) is None:
            raise ApiError(404, "web.errors.not_found")
        return web.json_response({"ok": True})

    async def play_playlist(self, request: web.Request) -> web.Response:
        session = self.session(request)
        playlist = await self._playlist(request)
        data = await self.body(request)

        guild_id = self._snowflake(data.get("guild_id"))
        if not await self.auth.can_manage(session, guild_id):
            raise ApiError(403, "web.errors.forbidden")
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ApiError(404, "web.errors.bot_not_in_guild")

        tracks: list[wavelink.Playable] = []
        for row in await self.bot.db.get_tracks(playlist.id):
            try:
                track = wavelink.Playable(row["data"])
            except (KeyError, TypeError):
                continue
            track.extras = {"requester_id": session.user_id}
            tracks.append(track)
        if not tracks:
            raise HexError("errors.playlist_empty", name=playlist.name)
        if data.get("shuffle"):
            random.shuffle(tracks)

        player = get_player(guild)
        if player is None or not player.connected:
            player = await self._connect(guild, session.user_id, data.get("channel_id"))
        result = await add_tracks(self.bot, player, tracks)
        return web.json_response({"added": len(result.tracks)})
