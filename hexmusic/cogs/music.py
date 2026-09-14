"""Comandos de reproducción y gestión de la cola."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.panel import refresh_panel
from ..core.playback import SOURCE_LABELS, enqueue, ensure_player, search_tracks, skip_or_vote
from ..errors import HexError
from ..player import HexPlayer
from ..ui import embeds
from ..ui.views import Paginator, SearchView
from ..utils.formatting import escape, format_duration, parse_time, track_link, truncate
from ..utils.lyrics import fetch_lyrics

if TYPE_CHECKING:
    from ..bot import HexMusic

SOURCE_CHOICES = [app_commands.Choice(name=label, value=key) for key, label in SOURCE_LABELS.items()]
LOOP_CHOICES = [
    app_commands.Choice(name="Off", value="off"),
    app_commands.Choice(name="Track", value="track"),
    app_commands.Choice(name="Queue", value="queue"),
]
LOOP_MODES = {
    "off": wavelink.QueueMode.normal,
    "none": wavelink.QueueMode.normal,
    "track": wavelink.QueueMode.loop,
    "song": wavelink.QueueMode.loop,
    "queue": wavelink.QueueMode.loop_all,
    "all": wavelink.QueueMode.loop_all,
}
LOOP_MESSAGES = {
    wavelink.QueueMode.normal: "music.loop_off",
    wavelink.QueueMode.loop: "music.loop_track",
    wavelink.QueueMode.loop_all: "music.loop_queue",
}


class Music(commands.Cog):
    """Music playback and queue"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    def _player(self, ctx: commands.Context) -> HexPlayer:
        player = get_player(ctx.guild)
        if player is None:
            raise HexError("errors.no_player")
        return player

    def _require_feature(self, name: str) -> None:
        if not self.bot.feature(name):
            raise HexError("errors.feature_disabled")

    # ───── Reproducir ─────

    @commands.hybrid_command(name="play", aliases=["p"],
                             description="Play a song, playlist or link from any supported platform")
    @app_commands.describe(query="Song name or link (YouTube, Spotify, Tidal, Deezer, SoundCloud...)",
                           source="Platform to search on when you type a name")
    @app_commands.choices(source=SOURCE_CHOICES)
    @commands.guild_only()
    @music_check(player=False)
    async def play(self, ctx: commands.Context, *, query: str, source: Optional[str] = None) -> None:
        await ctx.defer()
        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        result = await enqueue(self.bot, player, ctx.author, query, source=source)
        await ctx.send(embed=embeds.enqueue_embed(self.bot, await self.bot.lang_for(ctx.guild.id), result))

    @play.autocomplete("query")
    async def play_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.strip()
        if not self.bot.config.player.search_autocomplete or len(current) < 3 or current.startswith(("http://", "https://")):
            return []
        source = getattr(interaction.namespace, "source", None)
        try:
            results = await asyncio.wait_for(search_tracks(self.bot, current, source), timeout=2.5)
        except Exception:  # noqa: BLE001 - el autocompletado nunca debe fallar
            return []
        if isinstance(results, wavelink.Playlist):
            return []

        choices = []
        for track in results[:10]:
            if not track.uri or len(track.uri) > 100:
                continue
            label = f"{track.title} — {track.author}"
            if not track.is_stream:
                label = f"{truncate(label, 90)} ({format_duration(track.length)})"
            choices.append(app_commands.Choice(name=truncate(label, 100), value=track.uri))
        return choices

    @commands.hybrid_command(name="playnext", aliases=["pn", "playtop"], description="Add a song to the front of the queue")
    @app_commands.describe(query="Song name or link (YouTube, Spotify, Tidal, Deezer, SoundCloud...)",
                           source="Platform to search on when you type a name")
    @app_commands.choices(source=SOURCE_CHOICES)
    @commands.guild_only()
    @music_check(player=False)
    async def playnext(self, ctx: commands.Context, *, query: str, source: Optional[str] = None) -> None:
        await ctx.defer()
        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        result = await enqueue(self.bot, player, ctx.author, query, source=source, play_next=True)
        await ctx.send(embed=embeds.enqueue_embed(self.bot, await self.bot.lang_for(ctx.guild.id), result))

    @commands.hybrid_command(name="search", aliases=["find"], description="Search for songs and pick the one to play")
    @app_commands.describe(query="What to search for", source="Platform to search on when you type a name")
    @app_commands.choices(source=SOURCE_CHOICES)
    @commands.guild_only()
    @music_check(player=False)
    async def search(self, ctx: commands.Context, *, query: str, source: Optional[str] = None) -> None:
        await ctx.defer()
        results = await search_tracks(self.bot, query, source)
        tracks = list(results.tracks) if isinstance(results, wavelink.Playlist) else list(results)
        tracks = tracks[: max(1, min(25, int(self.bot.config.player.search_results)))]
        if not tracks:
            raise HexError("errors.no_results", query=query)

        lang = await self.bot.lang_for(ctx.guild.id)
        lines = [
            f"`{index}.` {embeds.source_emoji(self.bot, track.source)} {track_link(track)} "
            f"`{embeds.duration_text(self.bot, lang, track)}`"
            for index, track in enumerate(tracks, start=1)
        ]
        embed = embeds.make_embed(self.bot, title=self.bot.i18n.t(lang, "music.search_title", query=truncate(query, 80)),
                                  description="\n".join(lines))
        view = SearchView(self.bot, lang, ctx.author.id, tracks)
        view.message = await ctx.send(embed=embed, view=view)

    # ───── Conexión ─────

    @commands.hybrid_command(name="join", aliases=["connect", "summon"], description="Join your voice channel")
    @commands.guild_only()
    @music_check(player=False)
    async def join(self, ctx: commands.Context) -> None:
        player = await ensure_player(self.bot, ctx.author, ctx.channel)
        await self.bot.respond(ctx, "music.joined", channel=player.channel.mention)

    @commands.hybrid_command(name="leave", aliases=["disconnect", "dc"],
                             description="Leave the voice channel and clear the queue")
    @commands.guild_only()
    @music_check(dj=True)
    async def leave(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        key = "music.left"
        settings = await self.bot.db.get_guild(ctx.guild.id)
        if settings.stay_247:
            await self.bot.db.update_guild(ctx.guild.id, stay_247=False, stay_channel_id=None)
            key = "music.left_247_disabled"
        player.cancel_empty_task()
        await player.disconnect()
        await refresh_panel(self.bot, ctx.guild, player, idle=True)
        await self.bot.respond(ctx, key)

    # ───── Control ─────

    @commands.hybrid_command(name="pause", description="Pause the current song")
    @commands.guild_only()
    @music_check(playing=True, dj=True)
    async def pause(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        if player.paused:
            raise HexError("errors.already_paused")
        await player.pause(True)
        await self.bot.respond(ctx, "music.paused")

    @commands.hybrid_command(name="resume", aliases=["unpause"], description="Resume playback")
    @commands.guild_only()
    @music_check(playing=True, dj=True)
    async def resume(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        if not player.paused:
            raise HexError("errors.not_paused")
        player.paused_by_empty = False
        await player.pause(False)
        await self.bot.respond(ctx, "music.resumed")

    @commands.hybrid_command(name="skip", aliases=["s", "next"], description="Skip the current song (may require votes)")
    @commands.guild_only()
    @music_check(playing=True)
    async def skip(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        current = player.current
        skipped, votes, needed = await skip_or_vote(self.bot, player, ctx.author)
        if skipped:
            await self.bot.respond(ctx, "music.skipped", track=track_link(current))
        else:
            await self.bot.respond(ctx, "music.vote_registered", kind="info", votes=votes, needed=needed)

    @commands.hybrid_command(name="forceskip", aliases=["fs"], description="Skip the current song without a vote")
    @commands.guild_only()
    @music_check(playing=True, dj=True)
    async def forceskip(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        current = player.current
        await player.skip(force=True)
        await self.bot.respond(ctx, "music.skipped", track=track_link(current))

    @commands.hybrid_command(name="previous", aliases=["prev", "back"], description="Play the previous song again")
    @commands.guild_only()
    @music_check(dj=True)
    async def previous(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        track = await player.go_previous()
        if track is None:
            raise HexError("errors.no_previous")
        await self.bot.respond(ctx, "music.previous", track=track_link(track))

    @commands.hybrid_command(name="stop", description="Stop playback and clear the queue")
    @commands.guild_only()
    @music_check(dj=True)
    async def stop(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        await player.stop_and_clear()
        await refresh_panel(self.bot, ctx.guild, player, idle=True)
        await self.bot.respond(ctx, "music.stopped")

    @commands.hybrid_command(name="seek", description="Jump to a moment of the current song")
    @app_commands.describe(position="Time, e.g. 1:30, 90, 2m30s, +10 or -10")
    @commands.guild_only()
    @music_check(playing=True, dj=True)
    async def seek(self, ctx: commands.Context, position: str) -> None:
        player = self._player(ctx)
        track = player.current
        if track is None or track.is_stream or not track.is_seekable:
            raise HexError("errors.not_seekable")

        value = position.strip()
        relative = 0
        if value and value[0] in "+-":
            relative = 1 if value[0] == "+" else -1
            value = value[1:]
        milliseconds = parse_time(value)
        if milliseconds is None:
            raise HexError("errors.invalid_time")

        target = player.position + relative * milliseconds if relative else milliseconds
        target = max(0, min(target, track.length - 1000))
        await player.seek(target)
        await self.bot.respond(ctx, "music.seeked", position=format_duration(target))

    @commands.hybrid_command(name="replay", aliases=["restart"], description="Restart the current song")
    @commands.guild_only()
    @music_check(playing=True, dj=True)
    async def replay(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        if player.current is None or not player.current.is_seekable:
            raise HexError("errors.not_seekable")
        await player.seek(0)
        await self.bot.respond(ctx, "music.replay")

    @commands.hybrid_command(name="volume", aliases=["vol", "v"], description="Show or change the volume")
    @app_commands.describe(level="New volume level")
    @commands.guild_only()
    @music_check(voice=False)
    async def volume(self, ctx: commands.Context, level: Optional[commands.Range[int, 0, 1000]] = None) -> None:
        player = self._player(ctx)
        if level is None:
            await self.bot.respond(ctx, "music.volume_current", kind="info", volume=player.volume)
            return

        voice = ctx.author.voice
        if voice is None or player.channel is None or voice.channel != player.channel:
            raise HexError("errors.not_same_channel", channel=player.channel.mention if player.channel else "—")
        if not await self.bot.can_use(ctx.author, player, "volume"):
            raise HexError("errors.dj_only")
        max_volume = int(self.bot.config.player.max_volume)
        if level > max_volume:
            raise HexError("errors.volume_range", max=max_volume)

        await player.set_volume(level)
        await self.bot.respond(ctx, "music.volume_set", volume=level)

    # ───── Información ─────

    @commands.hybrid_command(name="nowplaying", aliases=["np", "now"], description="Show the song that is playing now")
    @commands.guild_only()
    @music_check(voice=False, playing=True)
    async def nowplaying(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        lang = await self.bot.lang_for(ctx.guild.id)
        await ctx.send(embed=embeds.now_playing_embed(self.bot, lang, player, player.current), view=self.bot.controls_view)

    @commands.hybrid_command(name="queue", aliases=["q", "list"], description="Show the queue")
    @app_commands.describe(page="Page number")
    @commands.guild_only()
    @music_check(voice=False)
    async def queue(self, ctx: commands.Context, page: commands.Range[int, 1] = 1) -> None:
        player = self._player(ctx)
        lang = await self.bot.lang_for(ctx.guild.id)
        pages = embeds.queue_embeds(self.bot, lang, player)
        paginator = Paginator(pages, ctx.author.id, deny_text=self.bot.i18n.t(lang, "errors.not_your_menu"), start=page - 1)
        await paginator.send(ctx)

    @commands.hybrid_command(name="grab", aliases=["save"], description="Send the current song to your DMs")
    @commands.guild_only()
    @music_check(voice=False, playing=True)
    async def grab(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        track = player.current
        lang = await self.bot.lang_for(ctx.guild.id)
        embed = embeds.make_embed(
            self.bot,
            title=truncate(track.title, 250),
            url=track.uri,
            description=self.bot.i18n.t(lang, "music.grab_description", author=escape(track.author),
                                        duration=embeds.duration_text(self.bot, lang, track),
                                        guild=escape(ctx.guild.name)),
        )
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        try:
            await ctx.author.send(embed=embed)
        except discord.HTTPException:
            raise HexError("errors.dm_closed") from None
        await self.bot.respond(ctx, "music.grabbed", ephemeral=True)

    @commands.hybrid_command(name="lyrics", aliases=["ly", "letra"], description="Show the lyrics of the current song or of a search")
    @app_commands.describe(query="Song to look up (empty = current song)")
    @commands.guild_only()
    async def lyrics(self, ctx: commands.Context, *, query: Optional[str] = None) -> None:
        self._require_feature("lyrics")
        await ctx.defer()
        assert self.bot.http_session is not None
        player = get_player(ctx.guild)

        if query:
            result = await fetch_lyrics(self.bot.http_session, query=query)
            searched = query
        elif player is not None and player.current is not None:
            track = player.current
            result = await fetch_lyrics(self.bot.http_session, title=track.title, artist=track.author,
                                        duration_ms=track.length, source=track.source)
            searched = track.title
        else:
            raise HexError("errors.nothing_playing")

        if result is None:
            raise HexError("errors.lyrics_not_found", query=truncate(searched, 100))
        lang = await self.bot.lang_for(ctx.guild.id)
        pages = embeds.lyrics_embeds(self.bot, lang, result)
        await Paginator(pages, ctx.author.id, deny_text=self.bot.i18n.t(lang, "errors.not_your_menu")).send(ctx)

    # ───── Cola ─────

    @commands.hybrid_command(name="remove", aliases=["rm"], description="Remove a song from the queue")
    @app_commands.describe(position="Position in the queue")
    @commands.guild_only()
    @music_check()
    async def remove(self, ctx: commands.Context, position: commands.Range[int, 1]) -> None:
        player = self._player(ctx)
        if not player.queue:
            raise HexError("errors.queue_empty")
        if position > len(player.queue):
            raise HexError("errors.invalid_index", max=len(player.queue))

        track = player.queue[position - 1]
        # Cualquiera puede quitar sus propias canciones; las de otros requieren DJ
        if HexPlayer.requester_id(track) != ctx.author.id and not await self.bot.can_use(ctx.author, player, "remove"):
            raise HexError("errors.dj_only")
        player.queue.delete(position - 1)
        await self.bot.respond(ctx, "music.removed", track=track_link(track))

    @commands.hybrid_command(name="move", aliases=["mv"], description="Move a song to another position in the queue")
    @app_commands.describe(from_position="Current position of the song", to_position="New position for the song")
    @commands.guild_only()
    @music_check(dj=True)
    async def move(self, ctx: commands.Context, from_position: commands.Range[int, 1],
                   to_position: commands.Range[int, 1]) -> None:
        player = self._player(ctx)
        size = len(player.queue)
        if not size:
            raise HexError("errors.queue_empty")
        if from_position > size or to_position > size:
            raise HexError("errors.invalid_index", max=size)
        if from_position == to_position:
            raise HexError("errors.same_position")

        track = player.queue[from_position - 1]
        player.queue.delete(from_position - 1)
        player.queue.put_at(to_position - 1, track)
        await self.bot.respond(ctx, "music.moved", track=track_link(track), position=to_position)

    @commands.hybrid_command(name="skipto", aliases=["jump"], description="Jump to a position in the queue")
    @app_commands.describe(position="Position in the queue")
    @commands.guild_only()
    @music_check(dj=True)
    async def skipto(self, ctx: commands.Context, position: commands.Range[int, 1]) -> None:
        player = self._player(ctx)
        if not player.queue:
            raise HexError("errors.queue_empty")
        if position > len(player.queue):
            raise HexError("errors.invalid_index", max=len(player.queue))

        track = player.queue[position - 1]
        if position > 1:
            del player.queue[: position - 1]
        if player.current is not None:
            await player.skip(force=True)
        else:
            player.queue.delete(0)
            await player.play(track)
        await self.bot.respond(ctx, "music.skipped_to", track=track_link(track))

    @commands.hybrid_command(name="clear", aliases=["cl"], description="Clear the queue")
    @commands.guild_only()
    @music_check(dj=True)
    async def clear(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        count = len(player.queue)
        if not count:
            raise HexError("errors.queue_empty")
        player.queue.clear()
        await self.bot.respond(ctx, "music.cleared", count=count)

    @commands.hybrid_command(name="shuffle", aliases=["mix"], description="Shuffle the queue")
    @commands.guild_only()
    @music_check(dj=True)
    async def shuffle(self, ctx: commands.Context) -> None:
        player = self._player(ctx)
        if len(player.queue) < 2:
            raise HexError("errors.queue_empty")
        player.queue.shuffle()
        await self.bot.respond(ctx, "music.shuffled", count=len(player.queue))

    @commands.hybrid_command(name="loop", aliases=["repeat", "l"], description="Change the loop mode")
    @app_commands.describe(mode="Loop mode (empty = next mode)")
    @app_commands.choices(mode=LOOP_CHOICES)
    @commands.guild_only()
    @music_check(dj=True)
    async def loop(self, ctx: commands.Context, mode: Optional[str] = None) -> None:
        player = self._player(ctx)
        if mode is None:
            new_mode = player.cycle_loop()
        else:
            new_mode = LOOP_MODES.get(mode.lower())
            if new_mode is None:
                raise HexError("errors.bad_argument")
            player.queue.mode = new_mode
        await self.bot.respond(ctx, LOOP_MESSAGES[new_mode])

    # ───── Modos ─────

    @commands.hybrid_command(name="autoplay", aliases=["ap", "radio"],
                             description="Turn autoplay of related songs on or off")
    @commands.guild_only()
    @music_check(voice=False, player=False, dj=True)
    async def autoplay(self, ctx: commands.Context) -> None:
        self._require_feature("autoplay")
        settings = await self.bot.db.get_guild(ctx.guild.id)
        enabled = not settings.autoplay
        await self.bot.db.update_guild(ctx.guild.id, autoplay=enabled)

        player = get_player(ctx.guild)
        if player is not None:
            player.autoplay_enabled = enabled
            if player.current is not None:
                player.sync_autoplay()
        await self.bot.respond(ctx, "music.autoplay_on" if enabled else "music.autoplay_off")

    @commands.hybrid_command(name="247", aliases=["24/7", "stay"],
                             description="Turn 24/7 mode on or off (the bot stays in the channel)")
    @commands.guild_only()
    @music_check(voice=False, player=False, dj=True)
    async def stay_247(self, ctx: commands.Context) -> None:
        self._require_feature("stay_247")
        settings = await self.bot.db.get_guild(ctx.guild.id)
        player = get_player(ctx.guild)

        if settings.stay_247:
            await self.bot.db.update_guild(ctx.guild.id, stay_247=False, stay_channel_id=None)
            if player is not None:
                player.stay_247 = False
                player.inactive_timeout = int(self.bot.config.player.idle_timeout) or None
            await self.bot.respond(ctx, "music.stay_off")
            return

        if player is None or not player.connected:
            player = await ensure_player(self.bot, ctx.author, ctx.channel)
        await self.bot.db.update_guild(ctx.guild.id, stay_247=True, stay_channel_id=player.channel.id)
        player.stay_247 = True
        player.inactive_timeout = None
        player.cancel_empty_task()
        await self.bot.respond(ctx, "music.stay_on", channel=player.channel.mention)


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Music(bot))
