"""Archivos de audio: formatos admitidos, títulos y enlaces de adjuntos de Discord."""

from __future__ import annotations

from pathlib import PurePosixPath

import discord
import wavelink

# Formatos que Lavalink (lavaplayer) sabe reproducir por HTTP
AUDIO_EXTENSIONS = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".mp4", ".webm", ".mka", ".mkv"}
UNKNOWN_TITLES = {"", "unknown title"}
UNKNOWN_AUTHORS = {"", "unknown artist"}
DISCORD_CDN_HOSTS = ("cdn.discordapp.com", "media.discordapp.net")


def file_extension(filename: str) -> str:
    return PurePosixPath(filename.lower()).suffix


def is_audio_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").split(";")[0]
    return file_extension(attachment.filename) in AUDIO_EXTENSIONS or content_type.startswith("audio/")


def is_discord_attachment_url(uri: str | None) -> bool:
    """Enlace de un adjunto de Discord (caduca en ~24 h: no sirve para guardarlo en una playlist)."""
    if not uri:
        return False
    return any(f"//{host}/" in uri for host in DISCORD_CDN_HOSTS)


def display_title(filename: str) -> str:
    """``mi_cancion-final.mp3`` → ``mi cancion-final``"""
    stem = PurePosixPath(filename).stem.replace("_", " ").strip()
    return stem[:100] or filename[:100]


def has_known_title(track: wavelink.Playable) -> bool:
    title = track.title.strip()
    return title.lower() not in UNKNOWN_TITLES and not title.startswith("http")


def retitle(track: wavelink.Playable, title: str, author: str | None = None) -> wavelink.Playable:
    """Copia de la canción con título (y autor) propios si el archivo no traía metadatos.

    Solo cambia lo que muestra el bot: Lavalink reproduce a partir de ``encoded``, que no se toca.
    """
    info = dict(track.raw_data["info"])
    if not has_known_title(track):
        info["title"] = title
    if author and str(info.get("author") or "").strip().lower() in UNKNOWN_AUTHORS:
        info["author"] = author
    data = dict(track.raw_data)
    data["info"] = info
    copy = wavelink.Playable(data)  # type: ignore[arg-type]
    copy.extras = dict(track.extras)
    return copy
