"""Carga de config.yml con valores por defecto y variables de entorno."""

from __future__ import annotations

import copy
import logging
import os
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import discord
import yaml

log = logging.getLogger("hexmusic.config")

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")
_INT_PATTERN = re.compile(r"^-?\d+$")

# Valores por defecto. config.yml solo necesita las claves que quieras cambiar.
DEFAULTS: dict[str, Any] = {
    "bot": {
        "name": "HexMusic",
        "prefix": "hm!",
        "message_content_intent": True,
        "owner_ids": [],
        "default_language": "es",
        "sync_commands": True,
        "dev_guild_id": "${DEV_GUILD_ID:-}",
        "database": "${DATABASE_PATH:-data/hexmusic.db}",
        "console": False,
        "status": {"type": "listening", "text": "/play • HexMusic"},
        "extensions": [
            "hexmusic.cogs.general",
            "hexmusic.cogs.events",
            "hexmusic.cogs.music",
            "hexmusic.cogs.filters",
            "hexmusic.cogs.playlists",
            "hexmusic.cogs.settings",
        ],
    },
    "logging": {"level": "INFO"},
    "lavalink": {
        "nodes": [{
            "identifier": "main",
            "uri": "${LAVALINK_URI:-http://localhost:2333}",
            "password": "${LAVALINK_PASSWORD:-youshallnotpass}",
        }],
        "default_search": "ytmsearch",
        "search_cache": 128,
    },
    "branding": {
        "color": "#8B5CF6",
        "success_color": "#22C55E",
        "error_color": "#EF4444",
        "warning_color": "#F59E0B",
        "footer": "HexMusic • Hexservers",
        "footer_icon": "",
        "banner_url": "",
        "large_artwork": False,
        "progress_bar": {"length": 16, "filled": "━", "head": "●", "empty": "─"},
    },
    "emojis": {
        "success": "✅",
        "error": "❌",
        "warning": "⚠️",
        "info": "ℹ️",
        "music": "🎶",
        "live": "🔴",
        "previous": "⏮️",
        "pause": "⏯️",
        "skip": "⏭️",
        "stop": "⏹️",
        "queue": "📜",
        "loop": "🔁",
        "shuffle": "🔀",
        "volume_down": "🔉",
        "volume_up": "🔊",
        "autoplay": "♾️",
        "sources": {
            "youtube": "📺",
            "spotify": "🟢",
            "applemusic": "🍎",
            "deezer": "🟣",
            "tidal": "🌊",
            "qobuz": "🔷",
            "soundcloud": "🟠",
            "bandcamp": "💿",
            "twitch": "🟪",
            "http": "🌐",
            "default": "🎵",
        },
    },
    "player": {
        "default_volume": 100,
        "max_volume": 150,
        "volume_step": 10,
        "max_queue_size": 1000,
        "max_track_duration": 0,
        "idle_timeout": 300,
        "empty_channel_timeout": 120,
        "pause_when_empty": True,
        "self_deaf": True,
        "announce_tracks": True,
        "delete_old_now_playing": True,
        "search_autocomplete": True,
        "search_results": 10,
    },
    "features": {
        "autoplay": True,
        "stay_247": True,
        "lyrics": True,
        "request_channel": True,
        "vote_skip": True,
    },
    "vote_skip": {"default_enabled": False, "ratio": 0.5},
    "dj": {
        "commands": [
            "stop",
            "leave",
            "forceskip",
            "volume",
            "clear",
            "shuffle",
            "loop",
            "seek",
            "move",
            "remove",
            "skipto",
            "filter",
            "autoplay",
            "247",
        ]
    },
    "playlists": {"max_per_user": 25, "max_tracks": 500},
    "request_channel": {"channel_name": "hexmusic", "delete_after": 8},
    "filters": {"presets": {}},
    "web": {
        "enabled": "${WEB_ENABLED:-false}",
        "host": "${WEB_HOST:-0.0.0.0}",
        "port": "${WEB_PORT:-8080}",
        "public_url": "${WEB_PUBLIC_URL:-http://localhost:8080}",
        "client_secret": "${WEB_CLIENT_SECRET:-}",
        "session_days": 7,
    },
}

ENV_OVERRIDE_PREFIX = "HEXMUSIC__"
_TRUE_VALUES = {"1", "true", "yes", "on", "si", "sí"}


class Config:
    """Acceso por atributos a un diccionario anidado: ``config.player.max_volume``."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    @staticmethod
    def _wrap(value: Any) -> Any:
        return Config(value) if isinstance(value, dict) else value

    def __getattr__(self, name: str) -> Any:
        if name.startswith("__"):
            raise AttributeError(name)
        try:
            return self._wrap(self._data[name])
        except KeyError:
            raise AttributeError(f"La configuración no tiene la clave {name!r}") from None

    def __getitem__(self, name: str) -> Any:
        return self._wrap(self._data[name])

    def __contains__(self, name: object) -> bool:
        return name in self._data

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def get(self, name: str, default: Any = None) -> Any:
        return self._wrap(self._data.get(name, default))

    def items(self) -> Iterator[tuple[str, Any]]:
        return ((key, self._wrap(value)) for key, value in self._data.items())

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and value is None:
            continue  # sección vacía en el YAML: se mantienen los valores por defecto
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = deep_merge(current, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _coerce(value: str) -> Any:
    if value == "":
        return None
    lowered = value.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    if _INT_PATTERN.match(value):
        return int(value)
    return value


def expand_env(value: Any) -> Any:
    """Sustituye ${VAR} y ${VAR:-defecto} de forma recursiva."""
    if isinstance(value, dict):
        return {key: expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_env(item) for item in value]
    if not isinstance(value, str) or "${" not in value:
        return value

    def replace(match: re.Match[str]) -> str:
        return os.environ.get(match.group(1)) or (match.group(2) or "")

    expanded = _ENV_PATTERN.sub(replace, value)
    # Si el valor era solo una variable, se convierte al tipo adecuado (int, bool, None)
    if _ENV_PATTERN.fullmatch(value.strip()):
        return _coerce(expanded.strip())
    return expanded


def apply_env_overrides(data: dict[str, Any]) -> list[str]:
    """``HEXMUSIC__SECCION__CLAVE=valor`` sobrescribe config.yml (p. ej. ``HEXMUSIC__BOT__PREFIX=!``).

    Solo se aceptan claves que ya existen; las listas se escriben separadas por comas.
    Útil en paneles de hosting, donde es más cómodo usar variables que editar archivos.
    """
    applied: list[str] = []
    for name, raw in os.environ.items():
        if not name.upper().startswith(ENV_OVERRIDE_PREFIX) or not raw.strip():
            continue
        path = [part.lower() for part in name[len(ENV_OVERRIDE_PREFIX):].split("__") if part]
        node: Any = data
        for part in path[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
        if not path or not isinstance(node, dict) or path[-1] not in node or isinstance(node[path[-1]], dict):
            log.warning("Variable %s ignorada: no existe la clave '%s' en la configuración.", name, ".".join(path))
            continue

        current = node[path[-1]]
        value = raw.strip()
        if isinstance(current, bool):
            node[path[-1]] = value.lower() in _TRUE_VALUES
        elif isinstance(current, list):
            node[path[-1]] = [_coerce(item.strip()) for item in value.split(",") if item.strip()]
        else:
            node[path[-1]] = _coerce(value)
        applied.append(".".join(path))
    return applied


def validate(data: dict[str, Any]) -> None:
    errors: list[str] = []

    nodes = data["lavalink"].get("nodes") or []
    if not isinstance(nodes, list) or not nodes:
        errors.append("lavalink.nodes debe contener al menos un nodo.")
    for index, node in enumerate(nodes if isinstance(nodes, list) else []):
        if not isinstance(node, dict) or not node.get("uri") or node.get("password") is None:
            errors.append(f"lavalink.nodes[{index}] necesita 'uri' y 'password'.")

    for key in ("color", "success_color", "error_color", "warning_color"):
        try:
            discord.Color.from_str(str(data["branding"][key]))
        except (ValueError, KeyError):
            errors.append(f"branding.{key} no es un color válido (usa el formato #RRGGBB).")

    ratio = data["vote_skip"].get("ratio")
    if not isinstance(ratio, (int, float)) or not 0 < ratio <= 1:
        errors.append("vote_skip.ratio debe ser un número entre 0 y 1.")

    player = data["player"]
    for key in ("default_volume", "max_volume", "volume_step", "max_queue_size", "max_track_duration",
                "idle_timeout", "empty_channel_timeout", "search_results"):
        if not isinstance(player.get(key), int) or player[key] < 0:
            errors.append(f"player.{key} debe ser un número entero positivo.")
    if isinstance(player.get("max_volume"), int) and not 1 <= player["max_volume"] <= 1000:
        errors.append("player.max_volume debe estar entre 1 y 1000.")

    web = data["web"]
    if web.get("enabled"):
        if not web.get("client_secret"):
            errors.append("web.client_secret es obligatorio con el panel activado (WEB_CLIENT_SECRET en .env).")
        if not str(web.get("public_url") or "").startswith(("http://", "https://")):
            errors.append("web.public_url debe empezar por http:// o https://.")
        if not isinstance(web.get("port"), int) or not 1 <= web["port"] <= 65535:
            errors.append("web.port debe ser un puerto válido (1-65535).")
        if not isinstance(web.get("session_days"), int) or web["session_days"] < 1:
            errors.append("web.session_days debe ser un número entero mayor que 0.")

    if not isinstance(data["filters"].get("presets"), dict):
        errors.append("filters.presets debe ser un diccionario.")

    if errors:
        raise ValueError("\n  - " + "\n  - ".join(errors))


def load_config(path: Path) -> Config:
    user: dict[str, Any] = {}
    if path.is_file():
        with path.open(encoding="utf-8") as fp:
            loaded = yaml.safe_load(fp) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{path} debe contener un diccionario YAML.")
        user = loaded
    else:
        log.warning("No se encontró %s; se usarán los valores por defecto.", path)

    data = expand_env(deep_merge(DEFAULTS, user))
    overrides = apply_env_overrides(data)
    if overrides:
        log.info("Ajustes sobrescritos por variables de entorno: %s", ", ".join(overrides))
    validate(data)
    return Config(data)
