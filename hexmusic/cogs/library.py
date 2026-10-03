"""Biblioteca de archivos de audio subidos al servidor: /upload y /library."""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.playback import add_tracks, ensure_player
from ..database import LibraryEntry
from ..errors import HexError
from ..ui import embeds
from ..ui.views import Paginator
from ..utils.formatting import escape, format_duration, truncate

if TYPE_CHECKING:
    from ..bot import HexMusic

PER_PAGE = 10


def entry_duration(entry: LibraryEntry) -> str:
    return format_duration(entry.length) if entry.length else "—"


class LibraryCommands(commands.Cog, name="Library"):
    """Uploaded audio files"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    def _require_library(self) -> None:
        if not self.bot.feature("library"):
            raise HexError("errors.feature_disabled")
        if not self.bot.library.running:
            raise HexError("errors.library_unavailable")

    async def _require_manager(self, ctx: commands.Context) -> None:
        """Subir, renombrar y borrar: administradores, "Gestionar servidor" o rol DJ."""
        if not await self.bot.is_dj(ctx.author, get_player(ctx.guild), strict=True):
            raise HexError("errors.library_dj_only")

    async def _find(self, guild_id: int, name: str) -> LibraryEntry:
        """El autocompletado envía el id; escrito a mano se busca por título."""
        text = name.strip()
        if text.isdigit():
            entry = await self.bot.db.get_library_track(guild_id, int(text))
            if entry is not None:
                return entry
        matches = await self.bot.db.search_library(guild_id, text, limit=25)
        exact = [entry for entry in matches if entry.title.lower() == text.lower()]
        if exact or matches:
            return (exact or matches)[0]
        raise HexError("errors.library_not_found", name=escape(name))

    async def _name_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if interaction.guild_id is None:
            return []
        entries = await self.bot.db.search_library(interaction.guild_id, current.strip(), limit=25)
        return [app_commands.Choice(name=truncate(f"{entry.title} ({entry_duration(entry)})", 100), value=str(entry.id))
                for entry in entries]

    async def _usage_text(self, guild_id: int, lang: str) -> str:
        library = self.bot.library
        count, used = await self.bot.db.library_usage(guild_id)
        limit = f"{library.max_guild_bytes / 1_048_576:.0f} MB" if library.max_guild_bytes else "∞"
        return self.bot.i18n.t(lang, "library.usage", count=count, used=f"{used / 1_048_576:.1f}", max=limit)

    # ───── Subir ─────

    @commands.hybrid_command(name="upload", aliases=["subir"], description="Upload an audio file to the server library")
    @app_commands.describe(file="Audio file (mp3, flac, ogg, wav, m4a...)", title="Title to show (empty = from the file)")
    @commands.guild_only()
    async def upload(self, ctx: commands.Context, file: discord.Attachment, *, title: Optional[str] = None) -> None:
        self._require_library()
        await self._require_manager(ctx)
        await ctx.defer()
        entry = await self.bot.library.upload(ctx.guild, file, ctx.author, title)
        lang = await self.bot.lang_for(ctx.guild.id)
        text = self.bot.i18n.t(lang, "library.uploaded", title=escape(entry.title), duration=entry_duration(entry))
        embed = embeds.success_embed(self.bot, text)
        embed.set_footer(text=await self._usage_text(ctx.guild.id, lang))
        await ctx.send(embed=embed)

    # ───── Biblioteca ─────

    @commands.hybrid_group(name="library", aliases=["lib", "biblioteca"], fallback="list", invoke_without_command=True,
                           description="The server library of uploaded audio files")
    @commands.guild_only()
    async def library_group(self, ctx: commands.Context) -> None:
        self._require_library()
        lang = await self.bot.lang_for(ctx.guild.id)
        t = self.bot.i18n.t
        entries = await self.bot.db.list_library(ctx.guild.id)
        if not entries:
            prefix = (await self.bot.db.get_guild(ctx.guild.id)).prefix or str(self.bot.config.bot.prefix)
            await self.bot.respond(ctx, "library.empty", kind="info", prefix=prefix)
            return

        usage = await self._usage_text(ctx.guild.id, lang)
        page_count = math.ceil(len(entries) / PER_PAGE)
        pages = []
        for page in range(page_count):
            lines = []
            for index, entry in enumerate(entries[page * PER_PAGE:(page + 1) * PER_PAGE], start=page * PER_PAGE + 1):
                uploader = f" · <@{entry.uploader_id}>" if entry.uploader_id else ""
                lines.append(f"`{index}.` **{escape(truncate(entry.title, 60))}** `{entry_duration(entry)}`{uploader}")
            embed = embeds.make_embed(self.bot, title=t(lang, "library.title", guild=escape(ctx.guild.name)),
                                      description="\n".join(lines) + "\n\n" + t(lang, "library.hint"))
            embed.set_footer(text=f"{usage} • {t(lang, 'help.footer', page=page + 1, pages=page_count)}")
            pages.append(embed)
        await Paginator(pages, ctx.author.id, deny_text=t(lang, "errors.not_your_menu")).send(ctx)

    @library_group.command(name="play", aliases=["p"], description="Play a file from the server library")
    @app_commands.describe(name="File to play", play_next="Play it right after the current song")
    @app_commands.rename(play_next="next")
    @music_check(player=False)
    async def library_play(self, ctx: commands.Context, name: str, play_next: bool = False) -> None:
        self._require_library()
        entry = await self._find(ctx.guild.id, name)
        await ctx.defer()
        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        track = await self.bot.library.track_for(entry, ctx.author.id)
        result = await add_tracks(self.bot, player, [track], play_next=play_next)
        await ctx.send(embed=embeds.enqueue_embed(self.bot, await self.bot.lang_for(ctx.guild.id), result))

    @library_group.command(name="playall", aliases=["all"], description="Play every file in the server library")
    @app_commands.describe(shuffle="Shuffle the files before playing")
    @music_check(player=False)
    async def library_playall(self, ctx: commands.Context, shuffle: bool = False) -> None:
        self._require_library()
        entries = await self.bot.db.list_library(ctx.guild.id)
        if not entries:
            raise HexError("errors.library_empty")
        await ctx.defer()
        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        if shuffle:
            random.shuffle(entries)

        tracks = await self.bot.library.tracks_for(entries, ctx.author.id)
        if not tracks:
            raise HexError("errors.library_empty")
        result = await add_tracks(self.bot, player, tracks)
        await self.bot.respond(ctx, "library.playing_all", count=len(result.tracks))

    @library_group.command(name="rename", description="Rename a file in the server library")
    @app_commands.describe(name="File to rename", title="New title")
    async def library_rename(self, ctx: commands.Context, name: str, *, title: str) -> None:
        self._require_library()
        await self._require_manager(ctx)
        entry = await self._find(ctx.guild.id, name)
        new_title = " ".join(title.split())[:100]
        if not new_title:
            raise HexError("errors.bad_argument")
        await self.bot.db.update_library_track(entry.id, title=new_title)
        await self.bot.respond(ctx, "library.renamed", old=escape(entry.title), new=escape(new_title))

    @library_group.command(name="delete", aliases=["del", "remove"], description="Delete a file from the server library")
    @app_commands.describe(name="File to delete")
    async def library_delete(self, ctx: commands.Context, *, name: str) -> None:
        self._require_library()
        await self._require_manager(ctx)
        entry = await self._find(ctx.guild.id, name)
        await self.bot.library.delete(entry)
        await self.bot.respond(ctx, "library.deleted", title=escape(entry.title))

    for _command in (library_play, library_rename, library_delete):
        _command.autocomplete("name")(_name_autocomplete)
    del _command


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(LibraryCommands(bot))
