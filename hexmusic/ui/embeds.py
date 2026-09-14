"""Constructores de embeds con el branding de config.yml."""

from __future__ import annotations

import math
from functools import partial
from typing import TYPE_CHECKING

import discord
import wavelink

from ..player import HexPlayer
from ..utils.formatting import escape, format_duration, progress_bar, track_link, truncate

if TYPE_CHECKING:
    from ..bot import HexMusic
    from ..core.playback import EnqueueResult
    from ..utils.lyrics import Lyrics

LOOP_KEYS = {
    wavelink.QueueMode.normal: "loop.off",
    wavelink.QueueMode.loop: "loop.track",
    wavelink.QueueMode.loop_all: "loop.queue",
}


def make_embed(bot: HexMusic, *, title: str | None = None, description: str | None = None,
               color: discord.Color | None = None, url: str | None = None) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, url=url, color=color or bot.colors.primary)
    branding = bot.config.branding
    if branding.footer:
        icon = branding.footer_icon or (bot.user.display_avatar.url if bot.user else None)
        embed.set_footer(text=str(branding.footer), icon_url=icon or None)
    return embed


def success_embed(bot: HexMusic, text: str) -> discord.Embed:
    return make_embed(bot, description=f"{bot.config.emojis.success} {text}", color=bot.colors.success)


def error_embed(bot: HexMusic, text: str) -> discord.Embed:
    return make_embed(bot, description=f"{bot.config.emojis.error} {text}", color=bot.colors.error)


def info_embed(bot: HexMusic, text: str, *, title: str | None = None) -> discord.Embed:
    return make_embed(bot, title=title, description=text)


def source_emoji(bot: HexMusic, source: str) -> str:
    sources = bot.config.emojis.sources
    return str(sources.get(source) or sources.get("default") or "🎵")


def duration_text(bot: HexMusic, lang: str, track: wavelink.Playable) -> str:
    if track.is_stream:
        return f"{bot.config.emojis.live} {bot.i18n.t(lang, 'nowplaying.live')}"
    return format_duration(track.length)


def now_playing_embed(bot: HexMusic, lang: str, player: HexPlayer, track: wavelink.Playable) -> discord.Embed:
    t = partial(bot.i18n.t, lang)
    bar = bot.config.branding.progress_bar

    if track.is_stream:
        timeline = duration_text(bot, lang, track)
    else:
        position = player.position
        line = progress_bar(position, track.length, size=int(bar.length), filled=str(bar.filled),
                            head=str(bar.head), empty=str(bar.empty))
        timeline = f"`{format_duration(position)}` {line} `{format_duration(track.length)}`"

    embed = make_embed(
        bot,
        title=truncate(track.title, 250),
        url=track.uri,
        description=f"{t('nowplaying.by', author=escape(track.author))}\n\n{timeline}",
    )
    state = t("nowplaying.paused") if player.paused else t("nowplaying.title")
    embed.set_author(name=f"{source_emoji(bot, track.source)} {state}")

    requester = HexPlayer.requester_id(track)
    if requester:
        requested_by = f"<@{requester}>"
    elif track.recommended:
        requested_by = f"{bot.config.emojis.autoplay} {t('nowplaying.autoplay')}"
    else:
        requested_by = "—"

    on, off = t("common.on"), t("common.off")
    embed.add_field(name=t("nowplaying.requester"), value=requested_by, inline=True)
    embed.add_field(name=t("nowplaying.volume"), value=f"{player.volume}%", inline=True)
    embed.add_field(name=t("nowplaying.loop"), value=t(LOOP_KEYS[player.queue.mode]), inline=True)
    embed.add_field(name=t("nowplaying.queue"), value=t("nowplaying.tracks", count=len(player.queue)), inline=True)
    embed.add_field(name=t("nowplaying.filter"), value=player.filter_name or t("common.none"), inline=True)
    embed.add_field(name=t("nowplaying.autoplay"), value=on if player.autoplay_enabled else off, inline=True)

    if track.artwork:
        if bot.config.branding.large_artwork:
            embed.set_image(url=track.artwork)
        else:
            embed.set_thumbnail(url=track.artwork)
    return embed


def idle_embed(bot: HexMusic, lang: str, guild: discord.Guild | None) -> discord.Embed:
    t = partial(bot.i18n.t, lang)
    embed = make_embed(
        bot,
        title=t("panel.idle_title", name=bot.config.bot.name),
        description=t("panel.idle_description", prefix=bot.config.bot.prefix),
    )
    if bot.config.branding.banner_url:
        embed.set_image(url=str(bot.config.branding.banner_url))
    elif bot.user:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
    return embed


def queue_embeds(bot: HexMusic, lang: str, player: HexPlayer, *, per_page: int = 10) -> list[discord.Embed]:
    t = partial(bot.i18n.t, lang)
    tracks = list(player.queue)
    title = t("queue.title")

    header = ""
    if player.current is not None:
        current = player.current
        header = (f"**{t('queue.now_playing')}**\n{source_emoji(bot, current.source)} "
                  f"{track_link(current)} `{duration_text(bot, lang, current)}`\n\n")

    if not tracks:
        body = t("queue.empty")
        if player.autoplay_enabled:
            body += "\n" + t("queue.autoplay_hint")
        return [make_embed(bot, title=title, description=header + body)]

    total = sum(track.length for track in tracks if not track.is_stream)
    pages_count = math.ceil(len(tracks) / per_page)
    pages = []
    for page in range(pages_count):
        start = page * per_page
        lines = []
        for index, track in enumerate(tracks[start:start + per_page], start=start + 1):
            requester = HexPlayer.requester_id(track)
            mention = f" · <@{requester}>" if requester else ""
            lines.append(f"`{index}.` {track_link(track, 50)} `{duration_text(bot, lang, track)}`{mention}")
        embed = make_embed(bot, title=title, description=f"{header}**{t('queue.up_next')}**\n" + "\n".join(lines))
        embed.set_footer(text=t("queue.footer", page=page + 1, pages=pages_count, count=len(tracks),
                                duration=format_duration(total)))
        pages.append(embed)
    return pages


def enqueue_embed(bot: HexMusic, lang: str, result: EnqueueResult) -> discord.Embed:
    t = partial(bot.i18n.t, lang)
    first = result.tracks[0]
    if result.playlist is not None:
        text = t("music.added_playlist", name=escape(result.playlist.name), count=len(result.tracks))
    elif result.started:
        text = t("music.playing_now", track=track_link(first))
    elif result.play_next:
        text = t("music.added_next", track=track_link(first))
    else:
        text = t("music.added_track", track=track_link(first), position=result.position)

    embed = success_embed(bot, text)
    artwork = (result.playlist.artwork if result.playlist else None) or first.artwork
    if artwork:
        embed.set_thumbnail(url=artwork)
    return embed


def lyrics_embeds(bot: HexMusic, lang: str, lyrics: Lyrics) -> list[discord.Embed]:
    t = partial(bot.i18n.t, lang)
    title = truncate(t("lyrics.title", title=lyrics.title, artist=lyrics.artist), 250)
    if lyrics.instrumental or not lyrics.text:
        return [make_embed(bot, title=title, description=t("lyrics.instrumental"))]

    chunks: list[str] = []
    current = ""
    for line in lyrics.text.splitlines():
        if len(current) + len(line) + 1 > 3500:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)

    pages = []
    for number, chunk in enumerate(chunks, start=1):
        embed = make_embed(bot, title=title, description=chunk)
        embed.set_footer(text=t("lyrics.footer", page=number, pages=len(chunks)))
        pages.append(embed)
    return pages
