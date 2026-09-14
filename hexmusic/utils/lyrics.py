"""Búsqueda de letras en LRCLIB (https://lrclib.net) — gratis y sin clave de API."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any

import aiohttp

log = logging.getLogger("hexmusic.lyrics")

LRCLIB_URL = "https://lrclib.net/api"

_NOISE = re.compile(
    r"[(\[](?:[^)\]]*?)(?:official|video|audio|lyrics?|letra|visuali[sz]er|hd|hq|4k|m/?v|clip|remaster(?:ed)?|explicit)"
    r"[^)\]]*[)\]]",
    re.IGNORECASE,
)
_FEAT = re.compile(r"\s+(?:feat\.?|ft\.?|featuring)\s.+$", re.IGNORECASE)
_TOPIC = re.compile(r"\s*-\s*topic$|vevo$", re.IGNORECASE)


@dataclass(slots=True)
class Lyrics:
    title: str
    artist: str
    text: str
    instrumental: bool = False


def clean_metadata(title: str, artist: str, *, split_artist: bool) -> tuple[str, str]:
    """Limpia títulos de vídeos: "Artista - Canción (Official Video)" → ("Canción", "Artista")."""
    artist = _TOPIC.sub("", artist or "").strip()
    title = _NOISE.sub("", title or "").strip()
    if split_artist and " - " in title:
        left, right = title.split(" - ", 1)
        artist, title = left.strip(), right.strip()
    title = _FEAT.sub("", title).strip(" -|")
    return title, artist


async def _get(session: aiohttp.ClientSession, path: str, params: dict[str, str]) -> Any:
    try:
        async with session.get(f"{LRCLIB_URL}{path}", params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            return await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        log.debug("LRCLIB no respondió: %s", exc)
        return None


async def fetch_lyrics(
    session: aiohttp.ClientSession,
    *,
    query: str | None = None,
    title: str | None = None,
    artist: str | None = None,
    duration_ms: int | None = None,
    source: str | None = None,
) -> Lyrics | None:
    results: Any = None
    if title:
        clean_title, clean_artist = clean_metadata(title, artist or "", split_artist=source in {"youtube", "soundcloud"})
        params = {"track_name": clean_title}
        if clean_artist:
            params["artist_name"] = clean_artist
        results = await _get(session, "/search", params)
        if not results:
            results = await _get(session, "/search", {"q": f"{clean_artist} {clean_title}".strip()})
    elif query:
        results = await _get(session, "/search", {"q": query})

    candidates = [item for item in results or [] if isinstance(item, dict) and (item.get("plainLyrics") or item.get("instrumental"))]
    if not candidates:
        return None
    if duration_ms:
        target = duration_ms / 1000
        candidates.sort(key=lambda item: abs(float(item.get("duration") or 0) - target))

    best = candidates[0]
    return Lyrics(
        title=str(best.get("trackName") or title or query or ""),
        artist=str(best.get("artistName") or artist or ""),
        text=str(best.get("plainLyrics") or "").strip(),
        instrumental=bool(best.get("instrumental")),
    )
