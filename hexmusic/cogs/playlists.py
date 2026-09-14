"""Playlists personales guardadas en la base de datos."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Optional

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.playback import add_tracks, ensure_player, search_tracks, serialize_track
from ..database import PlaylistInfo, clean_playlist_name
from ..errors import HexError
from ..ui import embeds
from ..ui.views import Paginator
from ..utils.formatting import escape, format_duration, truncate

if TYPE_CHECKING:
    from ..bot import HexMusic


class Playlists(commands.Cog):
    """Saved playlists"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    async def _name_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        names = await self.bot.db.search_playlist_names(interaction.user.id, current.strip())
        return [app_commands.Choice(name=name, value=name) for name in names]

    @staticmethod
    def _clean_name(name: str) -> str:
        return clean_playlist_name(name)

    async def _get(self, ctx: commands.Context, name: str) -> PlaylistInfo:
        playlist = await self.bot.db.get_playlist(ctx.author.id, self._clean_name(name))
        if playlist is None:
            raise HexError("errors.playlist_not_found", name=escape(name))
        return playlist

    async def _store(self, ctx: commands.Context, playlist: PlaylistInfo, tracks: list[wavelink.Playable]) -> int:
        limit = int(self.bot.config.playlists.max_tracks)
        added = await self.bot.db.add_tracks(playlist.id, [serialize_track(track) for track in tracks], limit=limit)
        if added == 0:
            raise HexError("errors.playlist_full", limit=limit)
        return added

    @commands.hybrid_group(name="playlist", aliases=["pl"], fallback="list", invoke_without_command=True,
                           description="Your saved playlists")
    @commands.guild_only()
    async def playlist_group(self, ctx: commands.Context) -> None:
        lang = await self.bot.lang_for(ctx.guild.id)
        t = self.bot.i18n.t
        items = await self.bot.db.list_playlists(ctx.author.id)
        if not items:
            await self.bot.respond(ctx, "playlist.list_empty", kind="info")
            return
        lines = [t(lang, "playlist.list_entry", name=escape(item.name), count=item.track_count) for item in items]
        embed = embeds.make_embed(self.bot, title=t(lang, "playlist.list_title", user=escape(ctx.author.display_name)),
                                  description="\n".join(lines))
        await ctx.send(embed=embed)

    @playlist_group.command(name="create", aliases=["new"], description="Create a new playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_create(self, ctx: commands.Context, *, name: str) -> None:
        name = self._clean_name(name)
        await self.bot.db.create_playlist(ctx.author.id, name, limit=int(self.bot.config.playlists.max_per_user))
        await self.bot.respond(ctx, "playlist.created", name=escape(name))

    @playlist_group.command(name="delete", aliases=["del"], description="Delete one of your playlists")
    @app_commands.describe(name="Playlist name")
    async def playlist_delete(self, ctx: commands.Context, *, name: str) -> None:
        playlist = await self._get(ctx, name)
        await self.bot.db.delete_playlist(playlist.id)
        await self.bot.respond(ctx, "playlist.deleted", name=escape(playlist.name))

    @playlist_group.command(name="show", aliases=["view"], description="Show the songs in a playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_show(self, ctx: commands.Context, *, name: str) -> None:
        playlist = await self._get(ctx, name)
        rows = await self.bot.db.get_tracks(playlist.id)
        if not rows:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))

        lang = await self.bot.lang_for(ctx.guild.id)
        t = self.bot.i18n.t
        total = sum(row["length"] or 0 for row in rows)
        per_page = 10
        page_count = math.ceil(len(rows) / per_page)
        pages = []
        for page in range(page_count):
            lines = []
            for index, row in enumerate(rows[page * per_page:(page + 1) * per_page], start=page * per_page + 1):
                title = escape(truncate(row["title"], 50)).replace("[", "(").replace("]", ")")
                link = f"[{title}]({row['uri']})" if row["uri"] else f"**{title}**"
                lines.append(f"`{index}.` {link} `{format_duration(row['length'] or 0)}`")
            embed = embeds.make_embed(self.bot, title=t(lang, "playlist.show_title", name=escape(playlist.name), count=len(rows)),
                                      description="\n".join(lines))
            embed.set_footer(text=t(lang, "playlist.show_footer", page=page + 1, pages=page_count, duration=format_duration(total)))
            pages.append(embed)
        await Paginator(pages, ctx.author.id, deny_text=t(lang, "errors.not_your_menu")).send(ctx)

    @playlist_group.command(name="add", description="Add the current song or a search to a playlist")
    @app_commands.describe(name="Playlist name", query="Song or link to add (empty = current song)")
    async def playlist_add(self, ctx: commands.Context, name: str, *, query: Optional[str] = None) -> None:
        playlist = await self._get(ctx, name)
        if query:
            await ctx.defer()
            results = await search_tracks(self.bot, query)
            if not results:
                raise HexError("errors.no_results", query=escape(query))
            tracks = list(results.tracks) if isinstance(results, wavelink.Playlist) else [results[0]]
        else:
            player = get_player(ctx.guild)
            if player is None or player.current is None:
                raise HexError("errors.nothing_playing")
            tracks = [player.current]
        added = await self._store(ctx, playlist, tracks)
        await self.bot.respond(ctx, "playlist.added", count=added, name=escape(playlist.name))

    @playlist_group.command(name="savequeue", aliases=["sq"], description="Save the current queue into a playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_savequeue(self, ctx: commands.Context, *, name: str) -> None:
        playlist = await self._get(ctx, name)
        player = get_player(ctx.guild)
        if player is None:
            raise HexError("errors.no_player")
        tracks = ([player.current] if player.current else []) + list(player.queue)
        if not tracks:
            raise HexError("errors.queue_empty")
        added = await self._store(ctx, playlist, tracks)
        await self.bot.respond(ctx, "playlist.saved_queue", count=added, name=escape(playlist.name))

    @playlist_group.command(name="remove", aliases=["rm"], description="Remove a song from a playlist")
    @app_commands.describe(name="Playlist name", position="Position of the song in the playlist")
    async def playlist_remove(self, ctx: commands.Context, name: str, position: commands.Range[int, 1]) -> None:
        playlist = await self._get(ctx, name)
        title = await self.bot.db.remove_track(playlist.id, position)
        if title is None:
            raise HexError("errors.invalid_index", max=playlist.track_count)
        await self.bot.respond(ctx, "playlist.removed", track=escape(title), name=escape(playlist.name))

    @playlist_group.command(name="play", aliases=["load"], description="Play one of your playlists")
    @app_commands.describe(name="Playlist name", shuffle="Shuffle the songs before playing")
    @music_check(player=False)
    async def playlist_play(self, ctx: commands.Context, name: str, shuffle: bool = False) -> None:
        playlist = await self._get(ctx, name)
        rows = await self.bot.db.get_tracks(playlist.id)
        if not rows:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))
        await ctx.defer()

        tracks: list[wavelink.Playable] = []
        for row in rows:
            try:
                track = wavelink.Playable(row["data"])
            except (KeyError, TypeError):
                continue
            track.extras = {"requester_id": ctx.author.id}
            tracks.append(track)
        if not tracks:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))
        if shuffle:
            random.shuffle(tracks)

        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        result = await add_tracks(self.bot, player, tracks)
        await self.bot.respond(ctx, "playlist.loaded", name=escape(playlist.name), count=len(result.tracks))

    for _command in (playlist_delete, playlist_show, playlist_add, playlist_savequeue, playlist_remove, playlist_play):
        _command.autocomplete("name")(_name_autocomplete)
    del _command


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Playlists(bot))
