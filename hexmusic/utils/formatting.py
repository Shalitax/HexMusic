"""Formato de duraciones, barras de progreso y enlaces."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    import wavelink

_CLOCK = re.compile(r"^\d+(?::\d{1,2}){0,2}$")
_UNITS = re.compile(r"^(?:(\d+)h)?\s*(?:(\d+)m)?\s*(?:(\d+)s)?$", re.IGNORECASE)


def format_duration(milliseconds: int | float) -> str:
    """``215000`` → ``3:35`` · ``3723000`` → ``1:02:03``"""
    seconds = max(0, int(milliseconds // 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def format_uptime(seconds: float) -> str:
    """``93784`` → ``1d 2h 3m``"""
    seconds = int(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if days or hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def parse_time(value: str) -> int | None:
    """Convierte ``90``, ``1:30``, ``1:02:03`` o ``2m30s`` a milisegundos."""
    text = value.strip().lower()
    if not text:
        return None
    if _CLOCK.match(text):
        total = 0
        for part in text.split(":"):
            total = total * 60 + int(part)
        return total * 1000
    match = _UNITS.match(text)
    if match and any(match.groups()):
        hours, minutes, seconds = (int(group) if group else 0 for group in match.groups())
        return (hours * 3600 + minutes * 60 + seconds) * 1000
    return None


def progress_bar(position: int, length: int, *, size: int = 16, filled: str = "━", head: str = "●",
                 empty: str = "─") -> str:
    size = max(2, size)
    if length <= 0:
        return head + empty * (size - 1)
    ratio = min(max(position / length, 0.0), 1.0)
    index = min(int(ratio * size), size - 1)
    return filled * index + head + empty * (size - index - 1)


def truncate(text: str, limit: int) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def escape(text: str) -> str:
    return discord.utils.escape_markdown(str(text))


def track_link(track: wavelink.Playable, limit: int = 60) -> str:
    """Título enlazado y escapado para usar dentro de un embed."""
    title = escape(truncate(track.title, limit)).replace("[", "(").replace("]", ")")
    if not track.uri:
        return f"**{title}**"
    uri = track.uri.replace("(", "%28").replace(")", "%29")
    return f"[{title}]({uri})"
