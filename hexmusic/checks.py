"""Checks reutilizables para los comandos de música."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

import discord
from discord.ext import commands

from .errors import HexError
from .player import HexPlayer

T = TypeVar("T")


def get_player(guild: discord.Guild | None) -> HexPlayer | None:
    if guild is None:
        return None
    voice = guild.voice_client
    return voice if isinstance(voice, HexPlayer) else None


def music_check(*, voice: bool = True, player: bool = True, playing: bool = False,
                dj: bool = False) -> Callable[[T], T]:
    """Valida el estado antes de ejecutar un comando.

    - ``player``:  el bot debe estar conectado a un canal de voz.
    - ``playing``: debe haber una canción sonando.
    - ``voice``:   el usuario debe estar en el mismo canal de voz que el bot.
    - ``dj``:      si el comando figura en ``dj.commands`` de config.yml, requiere permisos DJ.
    """

    async def predicate(ctx: commands.Context[Any]) -> bool:
        if ctx.guild is None or not isinstance(ctx.author, discord.Member):
            raise commands.NoPrivateMessage()

        current = get_player(ctx.guild)
        if player and (current is None or not current.connected):
            raise HexError("errors.no_player")
        if playing and (current is None or current.current is None):
            raise HexError("errors.nothing_playing")

        if voice:
            state = ctx.author.voice
            if state is None or state.channel is None:
                raise HexError("errors.not_in_voice")
            if current is not None and current.channel is not None and state.channel.id != current.channel.id:
                raise HexError("errors.not_same_channel", channel=current.channel.mention)

        if dj:
            name = ctx.command.qualified_name.split(" ")[0] if ctx.command else ""
            if not await ctx.bot.can_use(ctx.author, current, name):
                raise HexError("errors.dj_only")
        return True

    return commands.check(predicate)
