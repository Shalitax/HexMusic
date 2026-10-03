"""Menú /menu: controla la música, la cola, los filtros, las playlists y los ajustes desde un solo mensaje.

El menú es privado (efímero) y se navega con un desplegable de secciones. Cada acción comprueba los mismos
permisos que su comando equivalente, porque reutiliza ``core.controls``.
"""

from __future__ import annotations

import logging
import math
import random
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import discord

from ..checks import get_player
from ..core.controls import controllable_player, perform
from ..core.panel import edit_panel
from ..core.playback import add_tracks, enqueue, ensure_player, rows_to_tracks, serialize_track
from ..database import PlaylistInfo, clean_playlist_name
from ..errors import HexError
from ..player import HexPlayer
from ..utils.formatting import escape, truncate
from . import embeds
from .views import filter_options, track_option

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.menu")

SECTIONS = ("player", "queue", "filters", "playlists", "settings")
SECTION_EMOJIS = {"player": "🎵", "queue": "📜", "filters": "🎛️", "playlists": "📁", "settings": "⚙️"}
PAGE_SIZE = 10
MAX_OPTIONS = 25

Callback = Callable[[discord.Interaction], Awaitable[None]]


class TextModal(discord.ui.Modal):
    """Formulario de un solo campo (añadir canción, nombre de playlist, volumen...)."""

    def __init__(self, *, title: str, label: str, placeholder: str, max_length: int,
                 on_submit: Callable[[discord.Interaction, str], Awaitable[None]], default: str | None = None) -> None:
        super().__init__(title=truncate(title, 45), timeout=300)
        self.field: discord.ui.TextInput[TextModal] = discord.ui.TextInput(
            label=truncate(label, 45), placeholder=truncate(placeholder, 100), max_length=max_length, default=default,
        )
        self.add_item(self.field)
        self._on_submit = on_submit

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self._on_submit(interaction, self.field.value.strip())

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        log.exception("Error en un formulario del menú", exc_info=error)
        if not interaction.response.is_done():
            await interaction.response.send_message("⚠️", ephemeral=True)


class MenuView(discord.ui.View):
    def __init__(self, bot: HexMusic, member: discord.Member, lang: str,
                 channel: discord.abc.Messageable | None) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.member = member
        self.lang = lang
        self.channel = channel
        self.section = "player"
        self.page = 0
        self.playlist_id: int | None = None
        self.confirm_delete = False
        self.message: discord.Message | discord.InteractionMessage | None = None

    # ───── Utilidades ─────

    def t(self, key: str, **kwargs: Any) -> str:
        return self.bot.i18n.t(self.lang, key, **kwargs)

    @property
    def guild(self) -> discord.Guild:
        return self.member.guild

    @property
    def player(self) -> HexPlayer | None:
        player = get_player(self.guild)
        return player if player is not None and player.connected else None

    @property
    def can_manage(self) -> bool:
        return self.member.guild_permissions.manage_guild

    def _emoji(self, name: str) -> str:
        return str(self.bot.config.emojis.get(name, "▫️"))

    def _sync_member(self, interaction: discord.Interaction) -> None:
        # Se usa siempre el miembro de la interacción: trae su canal de voz actual
        if isinstance(interaction.user, discord.Member):
            self.member = interaction.user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.member.id:
            await interaction.response.send_message(self.t("errors.not_your_menu"), ephemeral=True)
            return False
        self._sync_member(interaction)
        return True

    def _button(self, callback: Callback, *, row: int, label: str | None = None, emoji: str | None = None,
                style: discord.ButtonStyle = discord.ButtonStyle.secondary, disabled: bool = False) -> None:
        button: discord.ui.Button[MenuView] = discord.ui.Button(
            label=truncate(label, 80) if label else None, emoji=emoji, style=style, row=row, disabled=disabled,
        )
        button.callback = callback  # type: ignore[method-assign]
        self.add_item(button)

    def _select(self, callback: Callable[[discord.Interaction, str], Awaitable[None]], *, row: int, placeholder: str,
                options: list[discord.SelectOption], disabled: bool = False) -> None:
        select: discord.ui.Select[MenuView] = discord.ui.Select(
            placeholder=truncate(placeholder, 150), options=options[:MAX_OPTIONS], row=row, disabled=disabled,
        )

        async def on_select(interaction: discord.Interaction) -> None:
            await callback(interaction, select.values[0])

        select.callback = on_select  # type: ignore[method-assign]
        self.add_item(select)

    async def show(self, interaction: discord.Interaction) -> None:
        """Vuelve a dibujar la sección actual en el mismo mensaje."""
        embed = await self.render()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def _error(self, interaction: discord.Interaction, exc: HexError) -> None:
        embed = embeds.error_embed(self.bot, self.t(exc.key, **exc.kwargs))
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _notify(self, interaction: discord.Interaction, key: str, **kwargs: Any) -> None:
        await interaction.followup.send(embed=embeds.success_embed(self.bot, self.t(key, **kwargs)), ephemeral=True)

    async def _control(self, interaction: discord.Interaction, action: str, value: str | None = None) -> None:
        try:
            player = await controllable_player(self.bot, self.member, action)
            notice = await perform(self.bot, player, self.member, action, value)
        except HexError as exc:
            return await self._error(interaction, exc)
        await self.show(interaction)
        if notice:
            await interaction.followup.send(embed=embeds.info_embed(self.bot, self.t(notice[0], **notice[1])),
                                            ephemeral=True)
        if action != "stop":
            # El panel público también refleja el cambio (volumen, filtro, cola...)
            await edit_panel(self.bot, self.guild, player)

    def _control_button(self, action: str, *, row: int, disabled: bool, value: str | None = None,
                        emoji: str | None = None, label: str | None = None,
                        style: discord.ButtonStyle = discord.ButtonStyle.secondary) -> None:
        async def callback(interaction: discord.Interaction) -> None:
            await self._control(interaction, action, value)

        self._button(callback, row=row, emoji=emoji or self._emoji(action), label=label, style=style, disabled=disabled)

    async def on_timeout(self) -> None:
        if self.message is None:
            return
        for item in self.children:
            if isinstance(item, (discord.ui.Button, discord.ui.Select, discord.ui.RoleSelect)):
                item.disabled = True
        try:
            await self.message.edit(view=self)
        except discord.HTTPException:
            pass

    # ───── Secciones ─────

    async def render(self) -> discord.Embed:
        self.clear_items()
        if self.section == "settings" and not self.can_manage:
            self.section = "player"
        sections = [name for name in SECTIONS if name != "settings" or self.can_manage]
        options = [
            discord.SelectOption(label=self.t(f"menu.sections.{name}"), value=name, emoji=SECTION_EMOJIS[name],
                                 default=name == self.section)
            for name in sections
        ]
        self._select(self._change_section, row=0, placeholder=self.t("menu.choose_section"), options=options)
        renderer = {
            "player": self._render_player,
            "queue": self._render_queue,
            "filters": self._render_filters,
            "playlists": self._render_playlists,
            "settings": self._render_settings,
        }[self.section]
        embed = await renderer()
        embed.set_author(name=f"{SECTION_EMOJIS[self.section]} {self.t('menu.title', name=self.bot.config.bot.name)}")
        return embed

    async def _change_section(self, interaction: discord.Interaction, value: str) -> None:
        self.section = value if value in SECTIONS else "player"
        self.page = 0
        self.confirm_delete = False
        await self.show(interaction)

    # Reproductor

    async def _render_player(self) -> discord.Embed:
        player = self.player
        if player is not None and player.current is not None:
            embed = embeds.now_playing_embed(self.bot, self.lang, player, player.current)
        else:
            embed = embeds.make_embed(self.bot, title=self.t("menu.player_title"), description=self.t("menu.nothing_playing"))
        off = player is None
        idle = off or player.current is None  # type: ignore[union-attr]
        self._control_button("previous", row=1, disabled=off)
        self._control_button("pause", row=1, disabled=idle, style=discord.ButtonStyle.primary)
        self._control_button("skip", row=1, disabled=idle)
        self._control_button("stop", row=1, disabled=off)
        self._button(self._open_add_modal, row=1, emoji="➕", label=self.t("menu.add"), style=discord.ButtonStyle.success)
        self._control_button("loop", row=2, disabled=off)
        self._control_button("shuffle", row=2, disabled=off or len(player.queue) < 2)  # type: ignore[union-attr]
        self._control_button("volume_down", row=2, disabled=off)
        self._control_button("volume_up", row=2, disabled=off)
        if self.bot.feature("autoplay"):
            self._control_button("autoplay", row=2, disabled=off)
        self._button(self.show, row=3, emoji="🔄", label=self.t("menu.refresh"))
        return embed

    async def _open_add_modal(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TextModal(
            title=self.t("menu.add_title"), label=self.t("menu.add_label"), placeholder=self.t("menu.add_placeholder"),
            max_length=300, on_submit=self._add_song,
        ))

    async def _add_song(self, interaction: discord.Interaction, query: str) -> None:
        self._sync_member(interaction)
        await interaction.response.defer()
        try:
            player = await ensure_player(self.bot, self.member, self.channel)
            result = await enqueue(self.bot, player, self.member, query)
        except HexError as exc:
            return await self._error(interaction, exc)
        await self.show(interaction)
        await interaction.followup.send(embed=embeds.enqueue_embed(self.bot, self.lang, result), ephemeral=True)

    # Cola

    async def _render_queue(self) -> discord.Embed:
        player = self.player
        tracks = list(player.queue) if player is not None else []
        pages = max(1, math.ceil(len(tracks) / PAGE_SIZE))
        self.page = min(max(self.page, 0), pages - 1)

        if player is not None:
            embed = embeds.queue_embeds(self.bot, self.lang, player, per_page=PAGE_SIZE)[self.page]
        else:
            embed = embeds.make_embed(self.bot, title=self.t("queue.title"), description=self.t("errors.no_player"))

        start = self.page * PAGE_SIZE
        page_tracks = tracks[start:start + PAGE_SIZE]
        if page_tracks:
            options = [track_option(self.bot, self.lang, index, track)
                       for index, track in enumerate(page_tracks, start=start + 1)]

            async def jump(interaction: discord.Interaction, value: str) -> None:
                await self._control(interaction, "skipto", value)

            async def remove(interaction: discord.Interaction, value: str) -> None:
                await self._control(interaction, "remove", value)

            self._select(jump, row=1, placeholder=self.t("menu.jump_placeholder"), options=options)
            self._select(remove, row=2, placeholder=self.t("menu.remove_placeholder"), options=options)

        async def previous_page(interaction: discord.Interaction) -> None:
            self.page -= 1
            await self.show(interaction)

        async def next_page(interaction: discord.Interaction) -> None:
            self.page += 1
            await self.show(interaction)

        self._button(previous_page, row=3, emoji="◀️", disabled=self.page <= 0)
        self._button(next_page, row=3, emoji="▶️", disabled=self.page >= pages - 1)
        self._control_button("shuffle", row=3, disabled=len(tracks) < 2)
        self._control_button("clear", row=3, emoji="🗑️", label=self.t("menu.clear"), disabled=not tracks,
                             style=discord.ButtonStyle.danger)
        self._button(self._open_add_modal, row=3, emoji="➕", style=discord.ButtonStyle.success)
        return embed

    # Filtros

    async def _render_filters(self) -> discord.Embed:
        player = self.player
        playing = player is not None and player.current is not None
        current = player.filter_name if player is not None else None
        speed = float(player.filters.timescale.payload.get("speed") or 1.0) if player is not None else 1.0
        embed = embeds.make_embed(
            self.bot, title=self.t("filters.list_title"),
            description=self.t("menu.filters_description", filter=current or self.t("common.none"), speed=f"{speed:.2f}"),
        )
        embed.add_field(name="🎧", value=self.t("filters.quality_note"), inline=False)

        async def choose(interaction: discord.Interaction, value: str) -> None:
            await self._control(interaction, "filter", value)

        self._select(choose, row=1, placeholder=self.t("panel.filter_placeholder", name=current or self.t("common.none")),
                     options=filter_options(self.bot, self.lang, current), disabled=not playing)
        self._control_button("speed", row=2, value="down", emoji="⏪", label="-0.1×", disabled=not playing)
        self._control_button("speed", row=2, value="up", emoji="⏩", label="+0.1×", disabled=not playing)
        self._control_button("filter", row=2, value="none", emoji="♻️", label=self.t("menu.reset_filters"),
                             disabled=player is None)
        return embed

    # Playlists

    async def _render_playlists(self) -> discord.Embed:
        db = self.bot.db
        items = await db.list_playlists(self.member.id)
        selected = next((item for item in items if item.id == self.playlist_id), None)
        if selected is None:
            self.playlist_id = None

        lines = []
        for item in items[:MAX_OPTIONS]:
            mark = " 🌐" if item.public else ""
            line = self.t("playlist.list_entry", name=escape(item.name), count=item.track_count) + mark
            lines.append(f"**▶** {line}" if selected and item.id == selected.id else line)
        embed = embeds.make_embed(
            self.bot, title=self.t("playlist.list_title", user=escape(self.member.display_name)),
            description="\n".join(lines) if lines else self.t("playlist.list_empty"),
        )
        if selected is None and items:
            embed.set_footer(text=self.t("menu.choose_playlist_hint"))

        if items:
            options = [
                discord.SelectOption(label=truncate(item.name, 100), value=str(item.id), emoji="🌐" if item.public else "📁",
                                     description=self.t("nowplaying.tracks", count=item.track_count),
                                     default=selected is not None and item.id == selected.id)
                for item in items[:MAX_OPTIONS]
            ]

            async def choose(interaction: discord.Interaction, value: str) -> None:
                self.playlist_id = int(value)
                self.confirm_delete = False
                await self.show(interaction)

            self._select(choose, row=1, placeholder=self.t("menu.choose_playlist"), options=options)

        if selected is not None:
            self._button(self._playlist_action("play", selected), row=2, emoji="▶️", label=self.t("menu.play"),
                         style=discord.ButtonStyle.primary, disabled=not selected.track_count)
            self._button(self._playlist_action("shuffle", selected), row=2, emoji="🔀", label=self.t("menu.shuffle_play"),
                         disabled=not selected.track_count)
            self._button(self._playlist_action("add_current", selected), row=2, emoji="➕",
                         label=self.t("menu.add_current"))
            self._button(self._playlist_action("share", selected), row=2, emoji="🔒" if selected.public else "🌐",
                         label=self.t("menu.make_private" if selected.public else "menu.make_public"))
            self._button(self._playlist_action("delete", selected), row=3, emoji="🗑️",
                         label=self.t("menu.confirm_delete" if self.confirm_delete else "menu.delete"),
                         style=discord.ButtonStyle.danger)
        self._button(self._open_new_playlist, row=3, emoji="🆕", label=self.t("menu.new_playlist"),
                     style=discord.ButtonStyle.success)
        return embed

    def _playlist_action(self, action: str, playlist: PlaylistInfo) -> Callback:
        async def callback(interaction: discord.Interaction) -> None:
            db = self.bot.db
            try:
                if action in ("play", "shuffle"):
                    await interaction.response.defer()
                    tracks = rows_to_tracks(await db.get_tracks(playlist.id), self.member.id)
                    if not tracks:
                        raise HexError("errors.playlist_empty", name=escape(playlist.name))
                    if action == "shuffle":
                        random.shuffle(tracks)
                    player = await ensure_player(self.bot, self.member, self.channel)
                    result = await add_tracks(self.bot, player, tracks)
                    await self.show(interaction)
                    await self._notify(interaction, "playlist.loaded", name=escape(playlist.name), count=len(result.tracks))
                elif action == "add_current":
                    player = self.player
                    if player is None or player.current is None:
                        raise HexError("errors.nothing_playing")
                    limit = int(self.bot.config.playlists.max_tracks)
                    if not await db.add_tracks(playlist.id, [serialize_track(player.current)], limit=limit):
                        raise HexError("errors.playlist_full", limit=limit)
                    await self.show(interaction)
                    await self._notify(interaction, "playlist.added", count=1, name=escape(playlist.name))
                elif action == "share":
                    await db.set_playlist_public(playlist.id, not playlist.public)
                    await self.show(interaction)
                elif action == "delete":
                    if not self.confirm_delete:
                        self.confirm_delete = True
                        await self.show(interaction)
                        return
                    await db.delete_playlist(playlist.id)
                    self.playlist_id = None
                    self.confirm_delete = False
                    await self.show(interaction)
                    await self._notify(interaction, "playlist.deleted", name=escape(playlist.name))
            except HexError as exc:
                await self._error(interaction, exc)

        return callback

    async def _open_new_playlist(self, interaction: discord.Interaction) -> None:
        async def create(modal_interaction: discord.Interaction, name: str) -> None:
            try:
                clean = clean_playlist_name(name)
                self.playlist_id = await self.bot.db.create_playlist(
                    self.member.id, clean, limit=int(self.bot.config.playlists.max_per_user))
            except HexError as exc:
                return await self._error(modal_interaction, exc)
            self.confirm_delete = False
            await self.show(modal_interaction)

        await interaction.response.send_modal(TextModal(
            title=self.t("menu.new_playlist"), label=self.t("menu.playlist_name"),
            placeholder=self.t("menu.playlist_name"), max_length=32, on_submit=create,
        ))

    # Ajustes del servidor (Gestionar servidor)

    async def _render_settings(self) -> discord.Embed:
        cfg = self.bot.config
        settings = await self.bot.db.get_guild(self.guild.id)
        on, off = self.t("common.on"), self.t("common.off")
        vote_skip = settings.vote_skip if settings.vote_skip is not None else bool(cfg.vote_skip.default_enabled)
        announce = settings.announce if settings.announce is not None else bool(cfg.player.announce_tracks)
        volume = settings.default_volume if settings.default_volume is not None else int(cfg.player.default_volume)

        embed = embeds.make_embed(self.bot, title=self.t("settings.title", guild=escape(self.guild.name)))
        embed.add_field(name=self.t("settings.language"), value=f"{self.bot.i18n.language_name(self.lang)} (`{self.lang}`)")
        embed.add_field(name=self.t("settings.dj_role"),
                        value=f"<@&{settings.dj_role_id}>" if settings.dj_role_id else self.t("settings.no_dj_role"))
        embed.add_field(name=self.t("settings.default_volume"), value=f"{volume}%")
        embed.add_field(name=self.t("settings.vote_skip"), value=on if vote_skip else off)
        embed.add_field(name=self.t("settings.announce"), value=on if announce else off)
        embed.add_field(name=self.t("settings.autoplay"), value=on if settings.autoplay else off)

        languages = [
            discord.SelectOption(label=self.bot.i18n.language_name(code), value=code, default=code == self.lang)
            for code in self.bot.i18n.languages[:MAX_OPTIONS]
        ]
        self._select(self._set_language, row=1, placeholder=self.t("settings.language"), options=languages)

        role = self.guild.get_role(settings.dj_role_id) if settings.dj_role_id else None
        role_select: discord.ui.RoleSelect[MenuView] = discord.ui.RoleSelect(
            placeholder=self.t("menu.dj_role_placeholder"), min_values=1, max_values=1, row=2,
            default_values=[role] if role is not None else [],
        )

        async def set_role(interaction: discord.Interaction) -> None:
            chosen = role_select.values[0] if role_select.values else None
            if chosen is not None and chosen.is_default():
                chosen = None
            await self._update_settings(interaction, dj_role_id=chosen.id if chosen else None)

        role_select.callback = set_role  # type: ignore[method-assign]
        self.add_item(role_select)

        def toggle(field: str, current: bool) -> Callback:
            async def callback(interaction: discord.Interaction) -> None:
                await self._update_settings(interaction, **{field: not current})

            return callback

        style = {True: discord.ButtonStyle.success, False: discord.ButtonStyle.secondary}
        if self.bot.feature("vote_skip"):
            self._button(toggle("vote_skip", vote_skip), row=3, emoji="🗳️", label=self.t("settings.vote_skip"),
                         style=style[vote_skip])
        self._button(toggle("announce", announce), row=3, emoji="📢", label=self.t("settings.announce"),
                     style=style[announce])
        if self.bot.feature("autoplay"):
            self._button(toggle("autoplay", settings.autoplay), row=3, emoji=self._emoji("autoplay"),
                         label=self.t("settings.autoplay"), style=style[settings.autoplay])
        self._button(self._open_volume_modal, row=4, emoji="🔊", label=self.t("settings.default_volume"))
        if role is not None:
            async def clear_role(interaction: discord.Interaction) -> None:
                await self._update_settings(interaction, dj_role_id=None)

            self._button(clear_role, row=4, emoji="✖️", label=self.t("menu.clear_dj_role"))
        return embed

    async def _update_settings(self, interaction: discord.Interaction, **changes: Any) -> None:
        if not self.can_manage:
            return await self._error(interaction, HexError("errors.missing_permissions", perms="Manage Server"))
        await self.bot.db.update_guild(self.guild.id, **changes)
        player = self.player
        if "autoplay" in changes and player is not None:
            player.autoplay_enabled = bool(changes["autoplay"])
            if player.current is not None:
                player.sync_autoplay()
        await self.show(interaction)

    async def _set_language(self, interaction: discord.Interaction, code: str) -> None:
        if code not in self.bot.i18n.languages:
            return await self._error(interaction, HexError("errors.invalid_language",
                                                           languages=", ".join(self.bot.i18n.languages)))
        self.lang = code
        await self._update_settings(interaction, language=code)

    async def _open_volume_modal(self, interaction: discord.Interaction) -> None:
        max_volume = int(self.bot.config.player.max_volume)

        async def save(modal_interaction: discord.Interaction, value: str) -> None:
            self._sync_member(modal_interaction)
            try:
                volume = int(value)
            except ValueError:
                volume = -1
            if not 0 <= volume <= max_volume:
                return await self._error(modal_interaction, HexError("errors.volume_range", max=max_volume))
            await self._update_settings(modal_interaction, default_volume=volume)

        settings = await self.bot.db.get_guild(self.guild.id)
        current = settings.default_volume if settings.default_volume is not None else int(self.bot.config.player.default_volume)
        await interaction.response.send_modal(TextModal(
            title=self.t("settings.default_volume"), label=self.t("menu.volume_label", max=max_volume),
            placeholder="100", max_length=4, default=str(current), on_submit=save,
        ))
