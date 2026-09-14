"""Reproductor de HexMusic: amplía ``wavelink.Player`` con el estado propio del bot."""

from __future__ import annotations

import asyncio
import math
from typing import Any

import discord
import wavelink

LOOP_ORDER = (wavelink.QueueMode.normal, wavelink.QueueMode.loop, wavelink.QueueMode.loop_all)


class HexPlayer(wavelink.Player):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.text_channel: discord.abc.Messageable | None = None
        self.panel_message: discord.Message | None = None
        self.skip_votes: set[int] = set()
        self.autoplay_enabled: bool = False
        self.stay_247: bool = False
        self.filter_name: str | None = None
        self.empty_task: asyncio.Task[None] | None = None
        self.paused_by_empty: bool = False

    @property
    def listeners(self) -> list[discord.Member]:
        """Personas (no bots) en el canal de voz del reproductor."""
        channel = self.channel
        if channel is None:
            return []
        return [member for member in channel.members if not member.bot]

    @staticmethod
    def requester_id(track: wavelink.Playable | None) -> int | None:
        if track is None:
            return None
        value = dict(track.extras).get("requester_id")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def sync_autoplay(self) -> None:
        """``partial`` reproduce la cola sola; ``enabled`` además añade recomendaciones."""
        self.autoplay = wavelink.AutoPlayMode.enabled if self.autoplay_enabled else wavelink.AutoPlayMode.partial

    def cycle_loop(self) -> wavelink.QueueMode:
        index = LOOP_ORDER.index(self.queue.mode)
        self.queue.mode = LOOP_ORDER[(index + 1) % len(LOOP_ORDER)]
        return self.queue.mode

    def needed_votes(self, ratio: float) -> int:
        return max(1, math.ceil(len(self.listeners) * ratio))

    async def go_previous(self) -> wavelink.Playable | None:
        """Vuelve a la canción anterior del historial. La actual pasa al frente de la cola."""
        history = self.queue.history
        if history is None:
            return None
        current = self.current
        offset = 2 if current is not None and len(history) and history[-1] == current else 1
        if len(history) < offset:
            return None

        previous = history[-offset]
        if current is not None:
            self.queue.put_at(0, current)
        del history[-offset:]  # play() vuelve a añadir "previous" al historial
        await self.play(previous)
        return previous

    async def stop_and_clear(self) -> None:
        self.queue.clear()
        self.auto_queue.clear()
        self.skip_votes.clear()
        self.queue.mode = wavelink.QueueMode.normal
        # Evita que el autoplay continúe tras un /stop; se restaura al volver a reproducir
        self.autoplay = wavelink.AutoPlayMode.partial
        if self.current is not None:
            await self.skip(force=True)

    async def apply_filters(self, filters: wavelink.Filters, name: str | None) -> None:
        seek = bool(self.current and self.current.is_seekable and not self.current.is_stream)
        await self.set_filters(filters, seek=seek)
        self.filter_name = name

    def cancel_empty_task(self) -> None:
        if self.empty_task is not None and not self.empty_task.done():
            self.empty_task.cancel()
        self.empty_task = None
