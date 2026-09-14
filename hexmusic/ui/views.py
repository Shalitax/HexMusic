"""Vistas interactivas: panel de control persistente, paginador y selector de búsqueda."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from discord.ext import commands

from ..core.panel import build_panel_embed
from ..core.playback import add_tracks, ensure_player, skip_or_vote
from ..errors import HexError
from ..player import HexPlayer
from ..utils.formatting import format_duration, truncate
from . import embeds

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.views")

# acción del botón → (comando equivalente para los permisos DJ, fila)
CONTROL_ACTIONS: dict[str, tuple[str | None, int]] = {
    "previous": ("previous", 0),
    "pause": ("pause", 0),
    "skip": ("skip", 0),
    "stop": ("stop", 0),
    "queue": (None, 0),
    "loop": ("loop", 1),
    "shuffle": ("shuffle", 1),
    "volume_down": ("volume", 1),
    "volume_up": ("volume", 1),
    "autoplay": ("autoplay", 1),
}


class ControlsView(discord.ui.View):
    """Botones del panel. Es persistente: siguen funcionando tras reiniciar el bot."""

    def __init__(self, bot: HexMusic) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        for action, (_, row) in CONTROL_ACTIONS.items():
            if action == "autoplay" and not bot.feature("autoplay"):
                continue
            button: discord.ui.Button[ControlsView] = discord.ui.Button(
                emoji=str(bot.config.emojis.get(action, "▫️")),
                style=discord.ButtonStyle.primary if action == "pause" else discord.ButtonStyle.secondary,
                custom_id=f"hexmusic:{action}",
                row=row,
            )
            button.callback = self._callback(action)
            self.add_item(button)

    def _callback(self, action: str) -> Callable[[discord.Interaction], Coroutine[Any, Any, None]]:
        async def callback(interaction: discord.Interaction) -> None:
            await self.handle(interaction, action)

        return callback

    async def _deny(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.send_message(embed=embeds.error_embed(self.bot, text), ephemeral=True)

    async def handle(self, interaction: discord.Interaction, action: str) -> None:
        bot = self.bot
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        lang = await bot.lang_for(guild.id)
        t = partial(bot.i18n.t, lang)
        player = guild.voice_client

        if not isinstance(player, HexPlayer) or not player.connected:
            return await self._deny(interaction, t("errors.no_player"))
        if member.voice is None or player.channel is None or member.voice.channel != player.channel:
            channel = player.channel.mention if player.channel else "—"
            return await self._deny(interaction, t("errors.not_same_channel", channel=channel))

        command_name = CONTROL_ACTIONS[action][0]
        if command_name and not await bot.can_use(member, player, command_name):
            return await self._deny(interaction, t("errors.dj_only"))

        notice: str | None = None
        idle = False
        try:
            if action == "queue":
                pages = embeds.queue_embeds(bot, lang, player)
                paginator = Paginator(pages, member.id, deny_text=t("errors.not_your_menu"))
                return await paginator.send_interaction(interaction, ephemeral=True)

            if action == "previous":
                if await player.go_previous() is None:
                    return await self._deny(interaction, t("errors.no_previous"))
            elif action == "pause":
                if player.current is None:
                    return await self._deny(interaction, t("errors.nothing_playing"))
                await player.pause(not player.paused)
            elif action == "skip":
                if player.current is None:
                    return await self._deny(interaction, t("errors.nothing_playing"))
                skipped, votes, needed = await skip_or_vote(bot, player, member)
                if not skipped:
                    notice = t("music.vote_registered", votes=votes, needed=needed)
            elif action == "stop":
                await player.stop_and_clear()
                idle = True
            elif action == "loop":
                player.cycle_loop()
            elif action == "shuffle":
                if not player.queue:
                    return await self._deny(interaction, t("errors.queue_empty"))
                player.queue.shuffle()
            elif action in ("volume_down", "volume_up"):
                step = int(bot.config.player.volume_step) * (1 if action == "volume_up" else -1)
                await player.set_volume(max(0, min(int(bot.config.player.max_volume), player.volume + step)))
            elif action == "autoplay":
                player.autoplay_enabled = not player.autoplay_enabled
                await bot.db.update_guild(guild.id, autoplay=player.autoplay_enabled)
                if player.current is not None:
                    player.sync_autoplay()
        except wavelink.LavalinkException as exc:
            return await self._deny(interaction, t("errors.lavalink", error=exc.error))

        embed = build_panel_embed(bot, lang, guild, player, idle=idle)
        await interaction.response.edit_message(embed=embed, view=self)
        if notice:
            await interaction.followup.send(embed=embeds.info_embed(bot, notice), ephemeral=True)


class Paginator(discord.ui.View):
    """Navegación entre varias páginas de embeds. Solo la usa quien la abrió."""

    def __init__(self, pages: list[discord.Embed], author_id: int, *, deny_text: str, start: int = 0,
                 timeout: float = 180.0) -> None:
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.deny_text = deny_text
        self.index = min(max(start, 0), len(pages) - 1)
        self.message: discord.Message | discord.InteractionMessage | None = None
        self._sync()

    def _sync(self) -> None:
        last = len(self.pages) - 1
        self.first_page.disabled = self.previous_page.disabled = self.index <= 0
        self.next_page.disabled = self.last_page.disabled = self.index >= last

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(self.deny_text, ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction) -> None:
        self._sync()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first_page(self, interaction: discord.Interaction, _: discord.ui.Button[Paginator]) -> None:
        self.index = 0
        await self._show(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, _: discord.ui.Button[Paginator]) -> None:
        self.index = max(0, self.index - 1)
        await self._show(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, _: discord.ui.Button[Paginator]) -> None:
        self.index = min(len(self.pages) - 1, self.index + 1)
        await self._show(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last_page(self, interaction: discord.Interaction, _: discord.ui.Button[Paginator]) -> None:
        self.index = len(self.pages) - 1
        await self._show(interaction)

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    async def send(self, ctx: commands.Context[Any], *, ephemeral: bool = False) -> None:
        if len(self.pages) == 1:
            self.stop()
            await ctx.send(embed=self.pages[0], ephemeral=ephemeral)
            return
        self.message = await ctx.send(embed=self.pages[self.index], view=self, ephemeral=ephemeral)

    async def send_interaction(self, interaction: discord.Interaction, *, ephemeral: bool = True) -> None:
        if len(self.pages) == 1:
            self.stop()
            await interaction.response.send_message(embed=self.pages[0], ephemeral=ephemeral)
            return
        await interaction.response.send_message(embed=self.pages[self.index], view=self, ephemeral=ephemeral)
        self.message = await interaction.original_response()


class SearchView(discord.ui.View):
    """Menú desplegable con los resultados de /search."""

    def __init__(self, bot: HexMusic, lang: str, author_id: int, tracks: list[wavelink.Playable]) -> None:
        super().__init__(timeout=60.0)
        self.bot = bot
        self.lang = lang
        self.author_id = author_id
        self.tracks = tracks[:25]
        self.message: discord.Message | None = None

        options = [
            discord.SelectOption(
                label=truncate(track.title, 100),
                description=truncate(f"{track.author} · {format_duration(track.length) if not track.is_stream else 'LIVE'}", 100),
                value=str(index),
                emoji=embeds.source_emoji(bot, track.source),
            )
            for index, track in enumerate(self.tracks)
        ]
        self.select: discord.ui.Select[SearchView] = discord.ui.Select(
            placeholder=truncate(bot.i18n.t(lang, "music.search_placeholder"), 150), options=options
        )
        self.select.callback = self.on_select
        self.add_item(self.select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message(self.bot.i18n.t(self.lang, "errors.not_your_menu"), ephemeral=True)
        return False

    async def on_select(self, interaction: discord.Interaction) -> None:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
        await interaction.response.defer()
        track = self.tracks[int(self.select.values[0])]
        track.extras = {"requester_id": member.id}
        channel = interaction.channel if isinstance(interaction.channel, discord.abc.Messageable) else None
        try:
            player = await ensure_player(self.bot, member, channel)
            result = await add_tracks(self.bot, player, [track])
        except HexError as exc:
            text = self.bot.i18n.t(self.lang, exc.key, **exc.kwargs)
            await interaction.followup.send(embed=embeds.error_embed(self.bot, text), ephemeral=True)
            return
        self.stop()
        await interaction.edit_original_response(embed=embeds.enqueue_embed(self.bot, self.lang, result), view=None)

    async def on_timeout(self) -> None:
        if self.message is not None:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass
