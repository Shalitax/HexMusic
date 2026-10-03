"""Vistas interactivas: panel de control persistente, paginador y selector de búsqueda."""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import partial
from typing import TYPE_CHECKING, Any

import discord
import wavelink
from discord.ext import commands

from ..core.controls import controllable_player, perform, queue_value
from ..core.panel import build_panel_embed
from ..core.playback import add_tracks, ensure_player
from ..core.presets import get_presets
from ..errors import HexError
from ..player import HexPlayer
from ..utils.formatting import format_duration, truncate
from . import embeds

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.views")

# acción del botón → fila
CONTROL_BUTTONS: dict[str, int] = {
    "previous": 0,
    "pause": 0,
    "skip": 0,
    "stop": 0,
    "queue": 0,
    "loop": 1,
    "shuffle": 1,
    "volume_down": 1,
    "volume_up": 1,
    "autoplay": 1,
}
MAX_OPTIONS = 25  # límite de Discord por menú desplegable


def track_option(bot: HexMusic, lang: str, index: int, track: wavelink.Playable) -> discord.SelectOption:
    """Opción de menú para una canción de la cola."""
    return discord.SelectOption(
        label=truncate(f"{index}. {track.title}", 100),
        description=truncate(f"{track.author} · {embeds.duration_text(bot, lang, track)}", 100),
        value=queue_value(index, track),
        emoji=embeds.source_emoji(bot, track.source),
    )


def filter_options(bot: HexMusic, lang: str, current: str | None) -> list[discord.SelectOption]:
    t = partial(bot.i18n.t, lang)
    options = [discord.SelectOption(label=t("panel.no_filter"), value="none", emoji="🚫", default=current is None)]
    for name in sorted(get_presets(bot.config))[: MAX_OPTIONS - 1]:
        options.append(discord.SelectOption(label=name, value=name, default=name == current))
    return options


class ControlsView(discord.ui.View):
    """Botones y menús del panel "reproduciendo ahora".

    La instancia que se registra al arrancar (sin reproductor) es persistente: recibe las pulsaciones de todos
    los paneles, también de los enviados antes de reiniciar el bot. Cada panel se envía con una copia ya
    detenida (``build_controls``) que solo sirve para dibujar sus menús con la cola y el filtro de ese servidor;
    al estar detenida, discord.py no la guarda y las pulsaciones llegan a la persistente.
    """

    def __init__(self, bot: HexMusic, *, lang: str | None = None, player: HexPlayer | None = None,
                 display: bool = False) -> None:
        super().__init__(timeout=None)
        self.bot = bot
        lang = lang or bot.i18n.default
        t = partial(bot.i18n.t, lang)

        for action, row in CONTROL_BUTTONS.items():
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

        playing = player is not None and player.current is not None
        current_filter = player.filter_name if player is not None else None
        filter_select: discord.ui.Select[ControlsView] = discord.ui.Select(
            custom_id="hexmusic:filter",
            placeholder=truncate(t("panel.filter_placeholder", name=current_filter or t("common.none")), 150),
            options=filter_options(bot, lang, current_filter),
            disabled=display and not playing,
            row=2,
        )
        filter_select.callback = self._callback("filter", select=True)
        self.add_item(filter_select)

        queue = list(player.queue)[:MAX_OPTIONS] if player is not None else []
        if queue:
            options = [track_option(bot, lang, index, track) for index, track in enumerate(queue, start=1)]
            placeholder = t("panel.jump_placeholder", count=len(player.queue))  # type: ignore[union-attr]
        else:
            options = [discord.SelectOption(label="—", value="none")]
            placeholder = t("panel.queue_empty_placeholder")
        jump_select: discord.ui.Select[ControlsView] = discord.ui.Select(
            custom_id="hexmusic:jump",
            placeholder=truncate(placeholder, 150),
            options=options,
            disabled=display and not queue,
            row=3,
        )
        jump_select.callback = self._callback("skipto", select=True)
        self.add_item(jump_select)

    def _callback(self, action: str, *, select: bool = False) -> Callable[[discord.Interaction], Coroutine[Any, Any, None]]:
        async def callback(interaction: discord.Interaction) -> None:
            # El valor se lee de la propia interacción: la vista persistente es compartida por todos los paneles
            values: list[Any] = list((interaction.data or {}).get("values") or []) if select else []
            value = str(values[0]) if values else None
            if select and (value is None or (action == "skipto" and value == "none")):
                await interaction.response.defer()
                return
            await self.handle(interaction, action, value)

        return callback

    async def _deny(self, interaction: discord.Interaction, text: str) -> None:
        await interaction.response.send_message(embed=embeds.error_embed(self.bot, text), ephemeral=True)

    async def handle(self, interaction: discord.Interaction, action: str, value: str | None = None) -> None:
        bot = self.bot
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return

        lang = await bot.lang_for(guild.id)
        t = partial(bot.i18n.t, lang)
        try:
            player = await controllable_player(bot, member, action)
            if action == "queue":
                pages = embeds.queue_embeds(bot, lang, player)
                paginator = Paginator(pages, member.id, deny_text=t("errors.not_your_menu"))
                return await paginator.send_interaction(interaction, ephemeral=True)
            notice = await perform(bot, player, member, action, value)
        except HexError as exc:
            return await self._deny(interaction, t(exc.key, **exc.kwargs))

        idle = action == "stop"
        embed = build_panel_embed(bot, lang, guild, player, idle=idle)
        try:
            await interaction.response.edit_message(embed=embed, view=build_controls(bot, lang, player))
        except discord.HTTPException:
            # El panel pudo borrarse justo ahora (p. ej. al saltar, se envía uno nuevo)
            if not interaction.response.is_done():
                await interaction.response.defer()
        if notice:
            await interaction.followup.send(embed=embeds.info_embed(bot, t(notice[0], **notice[1])), ephemeral=True)


def build_controls(bot: HexMusic, lang: str, player: HexPlayer | None) -> ControlsView:
    """Copia del panel con los menús de ese servidor, lista para enviar o editar (ver ``ControlsView``)."""
    view = ControlsView(bot, lang=lang, player=player, display=True)
    view.stop()
    return view


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
