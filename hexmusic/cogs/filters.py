"""Filtros de audio: presets, ecualizador, velocidad y tono."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from ..checks import get_player, music_check
from ..core.presets import build_filters, get_presets
from ..errors import HexError
from ..ui import embeds
from ..utils.formatting import truncate

if TYPE_CHECKING:
    from ..bot import HexMusic


class Filters(commands.Cog):
    """Audio filters and equalizer"""

    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot

    @property
    def presets(self) -> dict[str, dict[str, Any]]:
        return get_presets(self.bot.config)

    @commands.hybrid_group(name="filter", aliases=["filters", "fx"], fallback="list", invoke_without_command=True,
                           description="Audio filters and equalizer")
    @commands.guild_only()
    async def filter_group(self, ctx: commands.Context) -> None:
        lang = await self.bot.lang_for(ctx.guild.id)
        t = self.bot.i18n.t
        player = get_player(ctx.guild)

        embed = embeds.make_embed(self.bot, title=t(lang, "filters.list_title"), description=t(lang, "filters.list_description"))
        names = " ".join(f"`{name}`" for name in sorted(self.presets))
        embed.add_field(name=t(lang, "filters.presets"), value=truncate(names, 1024) or t(lang, "common.none"), inline=False)
        current = player.filter_name if player is not None and player.filter_name else t(lang, "common.none")
        embed.add_field(name=t(lang, "filters.current"), value=current, inline=False)
        embed.add_field(name="🎧", value=t(lang, "filters.quality_note"), inline=False)
        await ctx.send(embed=embed)

    @filter_group.command(name="preset", description="Apply a filter preset (bassboost, nightcore, 8d...)")
    @app_commands.describe(name="Preset name")
    @music_check(playing=True, dj=True)
    async def filter_preset(self, ctx: commands.Context, name: str) -> None:
        key = name.lower().strip()
        payload = self.presets.get(key)
        if payload is None:
            raise HexError("errors.preset_not_found", name=name)
        player = get_player(ctx.guild)
        assert player is not None
        await player.apply_filters(build_filters(payload), key)
        await self.bot.respond(ctx, "filters.applied", name=key)

    @filter_preset.autocomplete("name")
    async def preset_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        text = current.lower().strip()
        return [app_commands.Choice(name=name, value=name) for name in sorted(self.presets) if text in name][:25]

    @filter_group.command(name="equalizer", aliases=["eq"], description="Adjust one equalizer band")
    @app_commands.describe(band="Band from 1 (bass) to 15 (treble)", gain="Gain from -0.25 to 1.0 (0 = neutral)")
    @music_check(playing=True, dj=True)
    async def filter_equalizer(self, ctx: commands.Context, band: commands.Range[int, 1, 15],
                               gain: commands.Range[float, -0.25, 1.0]) -> None:
        player = get_player(ctx.guild)
        assert player is not None
        filters = player.filters
        bands = [dict(item) for item in filters.equalizer.payload.values()]
        bands[band - 1]["gain"] = float(gain)
        filters.equalizer.set(bands=bands)  # type: ignore[typeddict-item]
        await player.apply_filters(filters, "custom")
        await self.bot.respond(ctx, "filters.eq_set", band=band, gain=f"{gain:+.2f}")

    @filter_group.command(name="speed", description="Change the playback speed")
    @app_commands.describe(value="Speed from 0.5 to 2.0 (1 = normal)")
    @music_check(playing=True, dj=True)
    async def filter_speed(self, ctx: commands.Context, value: commands.Range[float, 0.5, 2.0]) -> None:
        player = get_player(ctx.guild)
        assert player is not None
        filters = player.filters
        filters.timescale.set(speed=float(value))
        await player.apply_filters(filters, "custom")
        await self.bot.respond(ctx, "filters.speed_set", value=f"{value:.2f}")

    @filter_group.command(name="pitch", description="Change the pitch")
    @app_commands.describe(value="Pitch from 0.5 to 2.0 (1 = normal)")
    @music_check(playing=True, dj=True)
    async def filter_pitch(self, ctx: commands.Context, value: commands.Range[float, 0.5, 2.0]) -> None:
        player = get_player(ctx.guild)
        assert player is not None
        filters = player.filters
        filters.timescale.set(pitch=float(value))
        await player.apply_filters(filters, "custom")
        await self.bot.respond(ctx, "filters.pitch_set", value=f"{value:.2f}")

    @filter_group.command(name="reset", aliases=["off", "clear"], description="Remove all filters")
    @music_check(dj=True)
    async def filter_reset(self, ctx: commands.Context) -> None:
        player = get_player(ctx.guild)
        assert player is not None
        await player.apply_filters(wavelink.Filters(), None)
        await self.bot.respond(ctx, "filters.reset")


async def setup(bot: HexMusic) -> None:
    await bot.add_cog(Filters(bot))
