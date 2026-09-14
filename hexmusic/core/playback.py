"""Reproducción compartida por los comandos, los botones y el canal de peticiones."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

import discord
import wavelink

from ..errors import HexError
from ..player import HexPlayer

if TYPE_CHECKING:
    from ..bot import HexMusic

# Opción del comando → prefijo de búsqueda de Lavalink / LavaSrc
SEARCH_SOURCES: dict[str, str] = {
    "ytmusic": "ytmsearch",
    "youtube": "ytsearch",
    "spotify": "spsearch",
    "applemusic": "amsearch",
    "deezer": "dzsearch",
    "tidal": "tdsearch",
    "qobuz": "qbsearch",
    "soundcloud": "scsearch",
}

SOURCE_LABELS: dict[str, str] = {
    "ytmusic": "YouTube Music",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "applemusic": "Apple Music",
    "deezer": "Deezer",
    "tidal": "Tidal",
    "qobuz": "Qobuz",
    "soundcloud": "SoundCloud",
}

# Permite escribir el prefijo a mano: "spsearch:artista canción", "dzisrc:USUM71703861"...
_RAW_PREFIX = re.compile(r"^[a-z]{2,}(?:search|isrc|rec):", re.IGNORECASE)


@dataclass(slots=True)
class EnqueueResult:
    tracks: list[wavelink.Playable]
    playlist: wavelink.Playlist | None = None
    started: bool = False
    position: int = 0
    play_next: bool = False


def connected_nodes() -> list[wavelink.Node]:
    return [node for node in wavelink.Pool.nodes.values() if node.status is wavelink.NodeStatus.CONNECTED]


async def search_tracks(bot: HexMusic, query: str, source: str | None = None) -> wavelink.Search:
    query = query.strip()
    if not query:
        raise HexError("errors.no_results", query=query)
    if not connected_nodes():
        raise HexError("errors.no_nodes")

    if _RAW_PREFIX.match(query):
        prefix = None
    elif source:
        prefix = SEARCH_SOURCES.get(source, source)
    else:
        prefix = str(bot.config.lavalink.default_search or "") or None

    try:
        return await wavelink.Playable.search(query, source=prefix)
    except wavelink.LavalinkLoadException as exc:
        raise HexError("errors.load_failed", error=exc.error) from exc
    except wavelink.LavalinkException as exc:
        raise HexError("errors.lavalink", error=exc.error) from exc


async def ensure_player(bot: HexMusic, member: discord.Member, text_channel: discord.abc.Messageable | None) -> HexPlayer:
    """Devuelve el reproductor del servidor, conectándose al canal del usuario si hace falta."""
    guild = member.guild
    player = guild.voice_client

    if isinstance(player, HexPlayer) and player.connected:
        if member.voice is None or player.channel is None or member.voice.channel != player.channel:
            raise HexError("errors.not_same_channel", channel=player.channel.mention if player.channel else "—")
        if player.text_channel is None:
            player.text_channel = text_channel
        return player

    if member.voice is None or member.voice.channel is None:
        raise HexError("errors.not_in_voice")

    return await connect_player(bot, member.voice.channel, text_channel)


async def connect_player(
    bot: HexMusic,
    channel: discord.VoiceChannel | discord.StageChannel,
    text_channel: discord.abc.Messageable | None,
) -> HexPlayer:
    """Conecta el bot a un canal de voz concreto y aplica los ajustes del servidor."""
    permissions = channel.permissions_for(channel.guild.me)
    if not permissions.connect or not permissions.speak:
        raise HexError("errors.missing_voice_permissions", channel=channel.mention)
    if not connected_nodes():
        raise HexError("errors.no_nodes")

    try:
        player = await channel.connect(cls=HexPlayer, self_deaf=bool(bot.config.player.self_deaf), timeout=15)
    except wavelink.ChannelTimeoutException:
        raise HexError("errors.connect_timeout") from None
    except discord.ClientException:
        raise HexError("errors.connect_failed") from None

    await bot.setup_player(player, text_channel)
    return player


async def start_if_idle(player: HexPlayer) -> bool:
    player.sync_autoplay()
    if player.playing or not player.queue:
        return False
    track = player.queue.get()
    try:
        await player.play(track)
    except wavelink.LavalinkException as exc:
        raise HexError("errors.lavalink", error=exc.error) from exc
    return True


async def add_tracks(
    bot: HexMusic,
    player: HexPlayer,
    tracks: list[wavelink.Playable],
    *,
    playlist: wavelink.Playlist | None = None,
    play_next: bool = False,
) -> EnqueueResult:
    limit = int(bot.config.player.max_queue_size)
    if limit:
        space = limit - len(player.queue)
        if space <= 0:
            raise HexError("errors.queue_full", limit=limit)
        tracks = tracks[:space]

    if play_next:
        for offset, track in enumerate(tracks):
            player.queue.put_at(offset, track)
        position = 1
    else:
        position = len(player.queue) + 1
        player.queue.put(tracks)

    started = await start_if_idle(player)
    return EnqueueResult(tracks=tracks, playlist=playlist, started=started,
                         position=0 if started else position, play_next=play_next)


async def enqueue(
    bot: HexMusic,
    player: HexPlayer,
    requester: discord.abc.Snowflake,
    query: str,
    *,
    source: str | None = None,
    play_next: bool = False,
) -> EnqueueResult:
    results = await search_tracks(bot, query, source)
    if not results:
        raise HexError("errors.no_results", query=query)

    if isinstance(results, wavelink.Playlist):
        playlist: wavelink.Playlist | None = results
        tracks = list(results.tracks)
    else:
        playlist = None
        tracks = [results[0]]

    max_seconds = int(bot.config.player.max_track_duration)
    if max_seconds:
        tracks = [track for track in tracks if track.is_stream or track.length <= max_seconds * 1000]
        if not tracks:
            raise HexError("errors.track_too_long", limit=max_seconds // 60)

    for track in tracks:
        track.extras = {"requester_id": requester.id}

    return await add_tracks(bot, player, tracks, playlist=playlist, play_next=play_next)


async def skip_or_vote(bot: HexMusic, player: HexPlayer, member: discord.Member) -> tuple[bool, int, int]:
    """Salta la canción o registra un voto. Devuelve ``(saltada, votos, necesarios)``."""
    settings = await bot.db.get_guild(member.guild.id)
    vote_enabled = bot.feature("vote_skip") and (
        settings.vote_skip if settings.vote_skip is not None else bool(bot.config.vote_skip.default_enabled)
    )

    bypass = (
        not vote_enabled
        or HexPlayer.requester_id(player.current) == member.id
        or await bot.is_dj(member, player, strict=True)
    )
    if bypass:
        await player.skip(force=True)
        return True, 0, 0

    listener_ids = {listener.id for listener in player.listeners}
    player.skip_votes.add(member.id)
    player.skip_votes &= listener_ids
    needed = player.needed_votes(float(bot.config.vote_skip.ratio))
    votes = len(player.skip_votes)
    if votes >= needed:
        await player.skip(force=True)
        return True, votes, needed
    return False, votes, needed


def serialize_track(track: wavelink.Playable) -> dict[str, object]:
    """Formato guardado en la base de datos para las playlists."""
    data = dict(track.raw_data)
    data["userData"] = {}
    return {"title": track.title, "author": track.author, "uri": track.uri, "length": track.length, "data": data}
