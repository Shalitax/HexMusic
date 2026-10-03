"""Playlists personales guardadas en la base de datos (se pueden compartir con los demás)."""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.playback import add_tracks, ensure_player, rows_to_tracks, search_tracks, serialize_tracks
from ..database import PLAYLIST_NAME_MAX, PlaylistInfo, clean_playlist_name
from ..errors import HexError
from ..ui import embeds
from ..ui.views import Paginator
from ..utils.formatting import escape, format_duration, truncate

if TYPE_CHECKING:
    from ..bot import HexMusic

PUBLIC_MARK = "🌐"


class Playlists(commands.Cog):
    """Saved playlists"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    async def _name_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        # Con la opción "user" rellenada se sugieren las playlists públicas de esa persona
        owner = getattr(interaction.namespace, "user", None)
        owner_id = getattr(owner, "id", None)
        if owner_id and int(owner_id) != interaction.user.id:
            names = await self.bot.db.search_playlist_names(int(owner_id), current.strip(), public_only=True)
        else:
            names = await self.bot.db.search_playlist_names(interaction.user.id, current.strip())
        return [app_commands.Choice(name=name, value=name) for name in names]

    async def _get(self, ctx: commands.Context, name: str, owner: discord.abc.User | None = None) -> PlaylistInfo:
        """Playlist propia o, si se indica ``owner``, una playlist pública de esa persona."""
        clean = clean_playlist_name(name)
        if owner is None or owner.id == ctx.author.id:
            playlist = await self.bot.db.get_playlist(ctx.author.id, clean)
            if playlist is None:
                raise HexError("errors.playlist_not_found", name=escape(name))
            return playlist
        playlist = await self.bot.db.get_playlist(owner.id, clean)
        if playlist is None or not playlist.public:
            raise HexError("errors.public_playlist_not_found", name=escape(name), user=escape(owner.display_name))
        return playlist

    async def _store(self, playlist: PlaylistInfo, tracks: list[wavelink.Playable]) -> int:
        limit = int(self.bot.config.playlists.max_tracks)
        added = await self.bot.db.add_tracks(playlist.id, serialize_tracks(tracks), limit=limit)
        if added == 0:
            raise HexError("errors.playlist_full", limit=limit)
        return added

    @staticmethod
    def _entry(t: Callable[..., str], item: PlaylistInfo) -> str:
        text = t("playlist.list_entry", name=escape(item.name), count=item.track_count)
        return f"{text} {PUBLIC_MARK}" if item.public else text

    @commands.hybrid_group(name="playlist", aliases=["pl"], fallback="list", invoke_without_command=True,
                           description="Your saved playlists")
    @app_commands.describe(user="Show the public playlists of this user")
    @commands.guild_only()
    async def playlist_group(self, ctx: commands.Context, user: Optional[discord.User] = None) -> None:
        lang = await self.bot.lang_for(ctx.guild.id)

        def t(key: str, **kwargs: object) -> str:
            return self.bot.i18n.t(lang, key, **kwargs)

        other = user is not None and user.id != ctx.author.id
        target = user if other else ctx.author
        items = await self.bot.db.list_playlists(target.id)
        if other:
            items = [item for item in items if item.public]
        if not items:
            if other:
                await self.bot.respond(ctx, "playlist.list_empty_public", kind="info", user=escape(target.display_name))
            else:
                await self.bot.respond(ctx, "playlist.list_empty", kind="info")
            return
        lines = [self._entry(t, item) for item in items]
        if not other and any(item.public for item in items):
            lines.append("\n" + t("playlist.public_legend", mark=PUBLIC_MARK))
        embed = embeds.make_embed(self.bot, title=t("playlist.list_title", user=escape(target.display_name)),
                                  description="\n".join(lines))
        await ctx.send(embed=embed)

    @playlist_group.command(name="create", aliases=["new"], description="Create a new playlist")
    @app_commands.describe(name="Playlist name")
    async def playlist_create(self, ctx: commands.Context, *, name: str) -> None:
        name = clean_playlist_name(name)
        await self.bot.db.create_playlist(ctx.author.id, name, limit=int(self.bot.config.playlists.max_per_user))
        await self.bot.respond(ctx, "playlist.created", name=escape(name))

    @playlist_group.command(name="delete", aliases=["del"], description="Delete one of your playlists")
    @app_commands.describe(name="Playlist name")
    async def playlist_delete(self, ctx: commands.Context, *, name: str) -> None:
        playlist = await self._get(ctx, name)
        await self.bot.db.delete_playlist(playlist.id)
        await self.bot.respond(ctx, "playlist.deleted", name=escape(playlist.name))

    @playlist_group.command(name="show", aliases=["view"], description="Show the songs in a playlist")
    @app_commands.describe(name="Playlist name", user="Owner of the playlist (empty = you)")
    async def playlist_show(self, ctx: commands.Context, name: str, user: Optional[discord.User] = None) -> None:
        playlist = await self._get(ctx, name, user)
        rows = await self.bot.db.get_tracks(playlist.id)
        if not rows:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))

        lang = await self.bot.lang_for(ctx.guild.id)
        t = self.bot.i18n.t
        total = sum(row["length"] or 0 for row in rows)
        per_page = 10
        page_count = math.ceil(len(rows) / per_page)
        title = t(lang, "playlist.show_title", name=escape(playlist.name), count=len(rows))
        if playlist.public:
            title = f"{title} {PUBLIC_MARK}"
        pages = []
        for page in range(page_count):
            lines = []
            for index, row in enumerate(rows[page * per_page:(page + 1) * per_page], start=page * per_page + 1):
                track_title = escape(truncate(row["title"], 50)).replace("[", "(").replace("]", ")")
                link = f"[{track_title}]({row['uri']})" if row["uri"] else f"**{track_title}**"
                lines.append(f"`{index}.` {link} `{format_duration(row['length'] or 0)}`")
            embed = embeds.make_embed(self.bot, title=title, description="\n".join(lines))
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
        added = await self._store(playlist, tracks)
        await self.bot.respond(ctx, "playlist.added", count=added, name=escape(playlist.name))

    @playlist_group.command(name="import", description="Import a whole playlist or album from a link")
    @app_commands.describe(url="Link to a playlist or album (YouTube, Spotify, Deezer...)",
                           name="Name for the playlist (empty = original name)")
    async def playlist_import(self, ctx: commands.Context, url: str, *, name: Optional[str] = None) -> None:
        await ctx.defer()
        results = await search_tracks(self.bot, url)
        if not isinstance(results, wavelink.Playlist) or not results.tracks:
            raise HexError("errors.import_not_playlist")
        clean = clean_playlist_name(name or truncate(results.name, PLAYLIST_NAME_MAX).rstrip("…") or "Playlist")

        playlist = await self.bot.db.get_playlist(ctx.author.id, clean)
        created = playlist is None
        if playlist is None:
            await self.bot.db.create_playlist(ctx.author.id, clean, limit=int(self.bot.config.playlists.max_per_user))
            playlist = await self.bot.db.get_playlist(ctx.author.id, clean)
            assert playlist is not None
        added = await self._store(playlist, list(results.tracks))
        key = "playlist.imported_new" if created else "playlist.imported_existing"
        await self.bot.respond(ctx, key, count=added, name=escape(playlist.name))

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
        added = await self._store(playlist, tracks)
        await self.bot.respond(ctx, "playlist.saved_queue", count=added, name=escape(playlist.name))

    @playlist_group.command(name="remove", aliases=["rm"], description="Remove a song from a playlist")
    @app_commands.describe(name="Playlist name", position="Position of the song in the playlist")
    async def playlist_remove(self, ctx: commands.Context, name: str, position: commands.Range[int, 1]) -> None:
        playlist = await self._get(ctx, name)
        title = await self.bot.db.remove_track(playlist.id, position)
        if title is None:
            raise HexError("errors.invalid_index", max=playlist.track_count)
        await self.bot.respond(ctx, "playlist.removed", track=escape(title), name=escape(playlist.name))

    @playlist_group.command(name="share", aliases=["public"], description="Make a playlist public or private")
    @app_commands.describe(name="Playlist name", public="Public or private (empty = switch)")
    async def playlist_share(self, ctx: commands.Context, name: str, public: Optional[bool] = None) -> None:
        playlist = await self._get(ctx, name)
        value = (not playlist.public) if public is None else public
        await self.bot.db.set_playlist_public(playlist.id, value)
        if value:
            prefix = (await self.bot.db.get_guild(ctx.guild.id)).prefix or str(self.bot.config.bot.prefix)
            await self.bot.respond(ctx, "playlist.shared", name=escape(playlist.name), user=ctx.author.mention,
                                   prefix=prefix)
        else:
            await self.bot.respond(ctx, "playlist.unshared", name=escape(playlist.name))

    @playlist_group.command(name="copy", aliases=["clone"], description="Copy someone's public playlist into yours")
    @app_commands.describe(user="Owner of the playlist", name="Playlist name", new_name="Name for your copy (empty = same name)")
    async def playlist_copy(self, ctx: commands.Context, user: discord.User, name: str, *,
                            new_name: Optional[str] = None) -> None:
        source = await self._get(ctx, name, user)
        target = clean_playlist_name(new_name or source.name)
        cfg = self.bot.config.playlists
        count = await self.bot.db.copy_playlist(source.id, ctx.author.id, target, max_playlists=int(cfg.max_per_user),
                                                max_tracks=int(cfg.max_tracks))
        await self.bot.respond(ctx, "playlist.copied", count=count, name=escape(target))

    @playlist_group.command(name="play", aliases=["load"], description="Play one of your playlists")
    @app_commands.describe(name="Playlist name", user="Owner of the playlist (empty = you)",
                           shuffle="Shuffle the songs before playing")
    @music_check(player=False)
    async def playlist_play(self, ctx: commands.Context, name: str, user: Optional[discord.User] = None,
                            shuffle: bool = False) -> None:
        playlist = await self._get(ctx, name, user)
        rows = await self.bot.db.get_tracks(playlist.id)
        if not rows:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))
        await ctx.defer()

        tracks = rows_to_tracks(rows, ctx.author.id)
        if not tracks:
            raise HexError("errors.playlist_empty", name=escape(playlist.name))
        if shuffle:
            random.shuffle(tracks)

        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        result = await add_tracks(self.bot, player, tracks)
        await self.bot.respond(ctx, "playlist.loaded", name=escape(playlist.name), count=len(result.tracks))

    for _command in (playlist_delete, playlist_show, playlist_add, playlist_savequeue, playlist_remove, playlist_play,
                     playlist_share, playlist_copy):
        _command.autocomplete("name")(_name_autocomplete)
    del _command


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Playlists(bot))
