"""Historial de reproducción por servidor (panel web → Historial)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

import wavelink

if TYPE_CHECKING:
    from ..bot import HexMusic
    from ..player import HexPlayer

log = logging.getLogger("hexmusic.history")

PURGE_EVERY = 6 * 3600


class History:
    def __init__(self, bot: HexMusic) -> None:
        self.bot = bot
        self._task: asyncio.Task[None] | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.bot.config.history.enabled)

    async def record(self, player: HexPlayer, track: wavelink.Playable) -> None:
        if not self.enabled or player.guild is None:
            return
        try:
            await self.bot.db.add_history(
                player.guild.id,
                title=track.title or "?",
                author=track.author,
                uri=track.uri,
                source=track.source,
                artwork=track.artwork,
                length=None if track.is_stream else track.length,
                is_stream=track.is_stream,
                requester_id=player.requester_id(track),
                autoplay=bool(track.recommended),
            )
        except Exception:  # noqa: BLE001 - el historial nunca debe interrumpir la música
            log.debug("No se pudo guardar la canción en el historial", exc_info=True)

    async def purge(self) -> int:
        days = max(1, int(self.bot.config.history.retention_days or 90))
        return await self.bot.db.purge_history(int(time.time()) - days * 86400)

    async def _loop(self) -> None:
        while True:
            try:
                removed = await self.purge()
                if removed:
                    log.info("Historial: borradas %d reproducciones antiguas.", removed)
            except Exception:  # noqa: BLE001
                log.exception("No se pudo limpiar el historial")
            await asyncio.sleep(PURGE_EVERY)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
