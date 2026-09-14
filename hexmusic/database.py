"""Persistencia en SQLite: ajustes por servidor y playlists de usuario."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import aiosqlite

from .errors import HexError

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id           INTEGER PRIMARY KEY,
    language           TEXT,
    prefix             TEXT,
    dj_role_id         INTEGER,
    default_volume     INTEGER,
    vote_skip          INTEGER,
    announce           INTEGER,
    autoplay           INTEGER NOT NULL DEFAULT 0,
    stay_247           INTEGER NOT NULL DEFAULT 0,
    stay_channel_id    INTEGER,
    request_channel_id INTEGER,
    request_message_id INTEGER
);

CREATE TABLE IF NOT EXISTS playlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id   INTEGER NOT NULL,
    name       TEXT    NOT NULL COLLATE NOCASE,
    created_at INTEGER NOT NULL,
    UNIQUE (owner_id, name)
);

CREATE TABLE IF NOT EXISTS playlist_tracks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    playlist_id INTEGER NOT NULL REFERENCES playlists (id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    author      TEXT,
    uri         TEXT,
    length      INTEGER,
    data        TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_playlist_tracks_playlist ON playlist_tracks (playlist_id);

CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash   TEXT    PRIMARY KEY,
    user_id      INTEGER NOT NULL,
    user_data    TEXT    NOT NULL,
    access_token TEXT    NOT NULL,
    csrf_token   TEXT    NOT NULL,
    expires_at   INTEGER NOT NULL
);
"""


@dataclass(slots=True)
class GuildSettings:
    """Ajustes de un servidor. ``None`` significa "usar el valor de config.yml"."""

    guild_id: int
    language: str | None = None
    prefix: str | None = None
    dj_role_id: int | None = None
    default_volume: int | None = None
    vote_skip: bool | None = None
    announce: bool | None = None
    autoplay: bool = False
    stay_247: bool = False
    stay_channel_id: int | None = None
    request_channel_id: int | None = None
    request_message_id: int | None = None


_BOOL_FIELDS = {"vote_skip", "announce", "autoplay", "stay_247"}
_COLUMNS = [f.name for f in fields(GuildSettings)]

PLAYLIST_NAME_MAX = 32


def clean_playlist_name(name: str) -> str:
    """Normaliza espacios y valida la longitud del nombre de una playlist."""
    name = " ".join(str(name).split())
    if not 1 <= len(name) <= PLAYLIST_NAME_MAX:
        raise HexError("errors.invalid_playlist_name", max=PLAYLIST_NAME_MAX)
    return name


@dataclass(slots=True)
class PlaylistInfo:
    id: int
    owner_id: int
    name: str
    created_at: int
    track_count: int


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._guilds: dict[int, GuildSettings] = {}

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("La base de datos no está conectada.")
        return self._conn

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ───── Ajustes de servidor ─────

    @staticmethod
    def _row_to_settings(row: aiosqlite.Row) -> GuildSettings:
        values = {key: row[key] for key in row.keys()}
        for key in _BOOL_FIELDS:
            if values.get(key) is not None:
                values[key] = bool(values[key])
        return GuildSettings(**values)

    async def get_guild(self, guild_id: int) -> GuildSettings:
        cached = self._guilds.get(guild_id)
        if cached is not None:
            return cached
        async with self.conn.execute("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
            row = await cursor.fetchone()
        settings = self._row_to_settings(row) if row else GuildSettings(guild_id=guild_id)
        self._guilds[guild_id] = settings
        return settings

    async def update_guild(self, guild_id: int, **changes: Any) -> GuildSettings:
        unknown = set(changes) - set(_COLUMNS[1:])
        if unknown:
            raise ValueError(f"Campos desconocidos: {', '.join(sorted(unknown))}")

        settings = await self.get_guild(guild_id)
        for key, value in changes.items():
            setattr(settings, key, value)

        values = [int(v) if isinstance(v, bool) else v for v in (getattr(settings, c) for c in _COLUMNS)]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        updates = ", ".join(f"{column} = excluded.{column}" for column in _COLUMNS[1:])
        await self.conn.execute(
            f"INSERT INTO guild_settings ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
            f"ON CONFLICT (guild_id) DO UPDATE SET {updates}",
            values,
        )
        await self.conn.commit()
        return settings

    async def guilds_with_247(self) -> list[GuildSettings]:
        async with self.conn.execute(
            "SELECT * FROM guild_settings WHERE stay_247 = 1 AND stay_channel_id IS NOT NULL"
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_settings(row) for row in rows]

    # ───── Playlists ─────

    async def create_playlist(self, owner_id: int, name: str, *, limit: int = 0) -> int:
        async with self.conn.execute("SELECT COUNT(*) FROM playlists WHERE owner_id = ?", (owner_id,)) as cursor:
            (count,) = await cursor.fetchone()  # type: ignore[misc]
        if limit and count >= limit:
            raise HexError("errors.playlist_limit", limit=limit)
        try:
            cursor = await self.conn.execute(
                "INSERT INTO playlists (owner_id, name, created_at) VALUES (?, ?, ?)",
                (owner_id, name, int(time.time())),
            )
        except sqlite3.IntegrityError:
            raise HexError("errors.playlist_exists", name=name) from None
        await self.conn.commit()
        return int(cursor.lastrowid or 0)

    _PLAYLIST_SELECT = (
        "SELECT p.id, p.owner_id, p.name, p.created_at, COUNT(t.id) AS track_count "
        "FROM playlists p LEFT JOIN playlist_tracks t ON t.playlist_id = p.id "
    )

    async def get_playlist(self, owner_id: int, name: str) -> PlaylistInfo | None:
        async with self.conn.execute(
            self._PLAYLIST_SELECT + "WHERE p.owner_id = ? AND p.name = ? GROUP BY p.id", (owner_id, name)
        ) as cursor:
            row = await cursor.fetchone()
        return PlaylistInfo(**{key: row[key] for key in row.keys()}) if row else None

    async def list_playlists(self, owner_id: int) -> list[PlaylistInfo]:
        async with self.conn.execute(
            self._PLAYLIST_SELECT + "WHERE p.owner_id = ? GROUP BY p.id ORDER BY p.name", (owner_id,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [PlaylistInfo(**{key: row[key] for key in row.keys()}) for row in rows]

    async def search_playlist_names(self, owner_id: int, text: str, *, limit: int = 25) -> list[str]:
        async with self.conn.execute(
            "SELECT name FROM playlists WHERE owner_id = ? AND name LIKE ? ORDER BY name LIMIT ?",
            (owner_id, f"%{text}%", limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [row["name"] for row in rows]

    async def delete_playlist(self, playlist_id: int) -> None:
        await self.conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
        await self.conn.commit()

    async def add_tracks(self, playlist_id: int, tracks: Sequence[dict[str, Any]], *, limit: int = 0) -> int:
        """Añade canciones serializadas. Devuelve cuántas se añadieron (respeta ``limit``)."""
        async with self.conn.execute(
            "SELECT COUNT(*) FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)
        ) as cursor:
            (count,) = await cursor.fetchone()  # type: ignore[misc]
        if limit:
            tracks = tracks[: max(0, limit - count)]
        if not tracks:
            return 0
        await self.conn.executemany(
            "INSERT INTO playlist_tracks (playlist_id, title, author, uri, length, data) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (playlist_id, t["title"], t.get("author"), t.get("uri"), t.get("length"), json.dumps(t["data"]))
                for t in tracks
            ],
        )
        await self.conn.commit()
        return len(tracks)

    async def get_tracks(self, playlist_id: int) -> list[dict[str, Any]]:
        async with self.conn.execute(
            "SELECT id, title, author, uri, length, data FROM playlist_tracks WHERE playlist_id = ? ORDER BY id",
            (playlist_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        result = []
        for row in rows:
            item = {key: row[key] for key in row.keys()}
            item["data"] = json.loads(item["data"])
            result.append(item)
        return result

    async def remove_track(self, playlist_id: int, index: int) -> str | None:
        """Elimina la canción en la posición ``index`` (empezando en 1). Devuelve su título."""
        async with self.conn.execute(
            "SELECT id, title FROM playlist_tracks WHERE playlist_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (playlist_id, index - 1),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        await self.conn.execute("DELETE FROM playlist_tracks WHERE id = ?", (row["id"],))
        await self.conn.commit()
        return str(row["title"])

    async def get_playlist_by_id(self, owner_id: int, playlist_id: int) -> PlaylistInfo | None:
        async with self.conn.execute(
            self._PLAYLIST_SELECT + "WHERE p.owner_id = ? AND p.id = ? GROUP BY p.id", (owner_id, playlist_id)
        ) as cursor:
            row = await cursor.fetchone()
        return PlaylistInfo(**{key: row[key] for key in row.keys()}) if row else None

    async def rename_playlist(self, playlist_id: int, name: str) -> None:
        try:
            await self.conn.execute("UPDATE playlists SET name = ? WHERE id = ?", (name, playlist_id))
        except sqlite3.IntegrityError:
            raise HexError("errors.playlist_exists", name=name) from None
        await self.conn.commit()

    # ───── Sesiones del panel web ─────

    async def create_web_session(self, token_hash: str, user_id: int, user: dict[str, Any], access_token: str,
                                 csrf_token: str, expires_at: int) -> None:
        await self.conn.execute(
            "INSERT OR REPLACE INTO web_sessions (token_hash, user_id, user_data, access_token, csrf_token, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (token_hash, user_id, json.dumps(user), access_token, csrf_token, expires_at),
        )
        await self.conn.commit()

    async def get_web_session(self, token_hash: str) -> dict[str, Any] | None:
        async with self.conn.execute("SELECT * FROM web_sessions WHERE token_hash = ?", (token_hash,)) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "token_hash": row["token_hash"],
            "user_id": int(row["user_id"]),
            "user": json.loads(row["user_data"]),
            "access_token": row["access_token"],
            "csrf_token": row["csrf_token"],
            "expires_at": int(row["expires_at"]),
        }

    async def delete_web_session(self, token_hash: str) -> None:
        await self.conn.execute("DELETE FROM web_sessions WHERE token_hash = ?", (token_hash,))
        await self.conn.commit()

    async def purge_web_sessions(self) -> None:
        await self.conn.execute("DELETE FROM web_sessions WHERE expires_at <= ?", (int(time.time()),))
        await self.conn.commit()
