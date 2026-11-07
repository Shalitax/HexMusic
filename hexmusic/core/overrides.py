"""Ajustes globales editables desde el panel web (solo los dueños del bot).

Se guardan en ``panel-config.json`` junto a la base de datos (``data/``) y se aplican encima de
config.yml y de las variables ``HEXMUSIC__``: lo último que se cambia en el panel manda. Así, en
Docker/Dokploy, donde config.yml va dentro de la imagen, los cambios sobreviven a los despliegues.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..config import Config, validate
from .presets import build_filters

if TYPE_CHECKING:
    from ..bot import HexMusic

log = logging.getLogger("hexmusic.overrides")

FILE_NAME = "panel-config.json"
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_PRESET_NAME = re.compile(r"^[a-z0-9_-]{1,32}$")

# Comandos que admiten la restricción DJ (primer nombre del comando)
DJ_COMMANDS = [
    "pause", "resume", "skip", "forceskip", "previous", "replay", "stop", "leave", "volume", "seek", "loop",
    "shuffle", "clear", "move", "remove", "skipto", "filter", "autoplay", "247",
]
SEARCH_PREFIXES = ["ytmsearch", "ytsearch", "scsearch", "spsearch", "amsearch", "dzsearch", "tdsearch", "qbsearch"]
STATUS_TYPES = ["playing", "listening", "watching", "competing"]
EMOJI_KEYS = [
    "success", "error", "warning", "info", "music", "live", "previous", "pause", "skip", "stop", "queue", "loop",
    "shuffle", "volume_down", "volume_up", "autoplay",
]
SOURCE_EMOJI_KEYS = [
    "youtube", "spotify", "applemusic", "deezer", "tidal", "qobuz", "soundcloud", "bandcamp", "twitch", "http", "default",
]


@dataclass(slots=True)
class Field:
    key: str
    type: str  # text | int | float | bool | color | url | emoji | select | multiselect | json
    min: float | None = None
    max: float | None = None
    max_length: int = 200
    min_length: int = 0
    options: list[str] | str | None = None  # lista fija o "languages"
    live: bool = True  # False = se aplica al reiniciar el bot


@dataclass(slots=True)
class Section:
    id: str
    icon: str
    fields: list[Field] = field(default_factory=list)


SECTIONS: list[Section] = [
    Section("general", "settings", [
        Field("bot.name", "text", min_length=1, max_length=32),
        Field("bot.prefix", "text", min_length=1, max_length=10),
        Field("bot.default_language", "select", options="languages"),
        Field("bot.status.type", "select", options=STATUS_TYPES),
        Field("bot.status.text", "text", max_length=128),
        Field("bot.message_content_intent", "bool", live=False),
        Field("web.support_url", "url"),
        Field("web.terms_url", "url"),
        Field("web.privacy_url", "url"),
    ]),
    Section("branding", "palette", [
        Field("branding.color", "color"),
        Field("branding.success_color", "color"),
        Field("branding.error_color", "color"),
        Field("branding.warning_color", "color"),
        Field("branding.footer", "text", max_length=200),
        Field("branding.footer_icon", "url"),
        Field("branding.banner_url", "url"),
        Field("branding.large_artwork", "bool"),
        Field("branding.progress_bar.length", "int", min=5, max=40),
        Field("branding.progress_bar.filled", "emoji", min_length=1, max_length=8),
        Field("branding.progress_bar.head", "emoji", min_length=1, max_length=8),
        Field("branding.progress_bar.empty", "emoji", min_length=1, max_length=8),
    ]),
    Section("emojis", "smile", [
        *(Field(f"emojis.{key}", "emoji", min_length=1, max_length=64) for key in EMOJI_KEYS),
        *(Field(f"emojis.sources.{key}", "emoji", min_length=1, max_length=64) for key in SOURCE_EMOJI_KEYS),
    ]),
    Section("player", "play", [
        Field("player.default_volume", "int", min=0, max=1000),
        Field("player.max_volume", "int", min=1, max=1000),
        Field("player.volume_step", "int", min=1, max=100),
        Field("player.max_queue_size", "int", min=0, max=100000),
        Field("player.max_track_duration", "int", min=0, max=86400),
        Field("player.idle_timeout", "int", min=0, max=86400),
        Field("player.empty_channel_timeout", "int", min=0, max=86400),
        Field("player.pause_when_empty", "bool"),
        Field("player.self_deaf", "bool"),
        Field("player.announce_tracks", "bool"),
        Field("player.delete_old_now_playing", "bool"),
        Field("player.search_autocomplete", "bool"),
        Field("player.search_results", "int", min=1, max=25),
        Field("player.persist_queue", "bool", live=False),
        Field("player.persist_interval", "int", min=10, max=3600, live=False),
    ]),
    Section("search", "search", [
        Field("lavalink.default_search", "select", options=SEARCH_PREFIXES),
        Field("lavalink.search_cache", "int", min=0, max=10000, live=False),
    ]),
    Section("features", "toggle", [
        Field("features.autoplay", "bool"),
        Field("features.stay_247", "bool"),
        Field("features.lyrics", "bool"),
        Field("features.request_channel", "bool"),
        Field("features.vote_skip", "bool"),
        Field("features.library", "bool", live=False),
        Field("history.enabled", "bool"),
        Field("history.retention_days", "int", min=1, max=3650),
    ]),
    Section("permissions", "shield", [
        Field("vote_skip.default_enabled", "bool"),
        Field("vote_skip.ratio", "float", min=0.05, max=1),
        Field("dj.commands", "multiselect", options=DJ_COMMANDS),
    ]),
    Section("limits", "gauge", [
        Field("playlists.max_per_user", "int", min=0, max=1000),
        Field("playlists.max_tracks", "int", min=1, max=10000),
        Field("library.max_file_mb", "int", min=1, max=1024),
        Field("library.max_guild_mb", "int", min=0, max=100000),
        Field("library.max_files", "int", min=0, max=100000),
        Field("library.max_total_mb", "int", min=0, max=10_000_000),
        Field("request_channel.channel_name", "text", min_length=1, max_length=100),
        Field("request_channel.delete_after", "int", min=0, max=300),
        Field("web.session_days", "int", min=1, max=90),
    ]),
    Section("filters", "sliders", [
        Field("filters.presets", "json"),
    ]),
]

FIELDS: dict[str, Field] = {item.key: item for section in SECTIONS for item in section.fields}


def _get(data: dict[str, Any], key: str) -> Any:
    node: Any = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return copy.deepcopy(node)


def _set(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = copy.deepcopy(value)


class InvalidValue(ValueError):
    def __init__(self, key: str, reason: str = "invalid") -> None:
        super().__init__(f"{key}: {reason}")
        self.key = key
        self.reason = reason


def clean_value(spec: Field, value: Any, *, languages: list[str] | None = None) -> Any:
    """Valida y normaliza el valor de un campo. Lanza ``InvalidValue``."""
    kind = spec.type
    if kind == "bool":
        if not isinstance(value, bool):
            raise InvalidValue(spec.key)
        return value
    if kind in ("int", "float"):
        if isinstance(value, bool):
            raise InvalidValue(spec.key)
        try:
            number: float = int(value) if kind == "int" else float(value)
        except (TypeError, ValueError):
            raise InvalidValue(spec.key) from None
        if kind == "int" and isinstance(value, float) and not value.is_integer():
            raise InvalidValue(spec.key)
        if (spec.min is not None and number < spec.min) or (spec.max is not None and number > spec.max):
            raise InvalidValue(spec.key, "range")
        return number
    if kind in ("text", "emoji", "url", "color"):
        if not isinstance(value, str):
            raise InvalidValue(spec.key)
        text = value.strip()
        if kind == "color":
            if not _COLOR.match(text):
                raise InvalidValue(spec.key, "color")
            return text.upper()
        if kind == "url":
            if text and (len(text) > 500 or not re.match(r"^https?://\S+$", text)):
                raise InvalidValue(spec.key, "url")
            return text
        if not spec.min_length <= len(text) <= spec.max_length:
            raise InvalidValue(spec.key, "length")
        return text
    if kind == "select":
        options = languages if spec.options == "languages" else spec.options
        if value not in (options or []):
            raise InvalidValue(spec.key)
        return value
    if kind == "multiselect":
        if not isinstance(value, list) or any(item not in (spec.options or []) for item in value):
            raise InvalidValue(spec.key)
        return [item for item in (spec.options or []) if item in value]
    if kind == "json":
        return _clean_presets(spec, value)
    raise InvalidValue(spec.key)


def _clean_presets(spec: Field, value: Any) -> dict[str, Any]:
    """Presets de filtros propios: {"nombre": {formato de filtros de Lavalink} | null}."""
    if not isinstance(value, dict) or len(value) > 50:
        raise InvalidValue(spec.key)
    cleaned: dict[str, Any] = {}
    for name, payload in value.items():
        key = str(name).strip().lower()
        if not _PRESET_NAME.match(key):
            raise InvalidValue(spec.key, "preset_name")
        if payload is None:
            cleaned[key] = None
            continue
        if not isinstance(payload, dict):
            raise InvalidValue(spec.key, "preset")
        try:
            build_filters(payload)
        except Exception:  # noqa: BLE001 - cualquier formato que wavelink no entienda
            raise InvalidValue(spec.key, "preset") from None
        cleaned[key] = payload
    return cleaned


class ConfigOverrides:
    """Valores cambiados desde el panel, guardados aparte de config.yml."""

    def __init__(self, config: Config, root: Path) -> None:
        self.config = config
        database = Path(str(config.bot.database))
        folder = (database if database.is_absolute() else root / database).parent
        self.path = folder / FILE_NAME
        # Valores de config.yml + variables de entorno, para mostrarlos y para "restablecer"
        self.base = config.to_dict()
        self.values: dict[str, Any] = {}
        self._load()

    @property
    def data(self) -> dict[str, Any]:
        return self.config._data  # noqa: SLF001 - el objeto Config envuelve este diccionario

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            log.warning("No se pudo leer %s (%s); se ignoran los ajustes del panel.", self.path, exc)
            return
        if not isinstance(raw, dict):
            return

        applied: dict[str, Any] = {}
        for key, value in raw.items():
            spec = FIELDS.get(key)
            if spec is None:
                continue
            try:
                # El idioma se comprueba al aplicarlo (los idiomas aún no están cargados)
                value = value if spec.options == "languages" else clean_value(spec, value)
            except InvalidValue:
                log.warning("Ajuste del panel %r no válido; se ignora.", key)
                continue
            applied[key] = value

        candidate = copy.deepcopy(self.data)
        for key, value in applied.items():
            _set(candidate, key, value)
        try:
            validate(candidate)
        except ValueError as exc:
            log.warning("Los ajustes del panel no son válidos (%s); se ignoran.", exc)
            return
        for key, value in applied.items():
            _set(self.data, key, value)
        self.values = applied
        if applied:
            log.info("Ajustes del panel web aplicados: %d (%s)", len(applied), self.path)

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.values, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)

    def describe(self, bot: HexMusic) -> list[dict[str, Any]]:
        """Secciones y campos con su valor actual, el de config.yml y si requieren reinicio."""
        languages = bot.i18n.languages
        sections = []
        for section in SECTIONS:
            items = []
            for spec in section.fields:
                options = languages if spec.options == "languages" else spec.options
                items.append({
                    "key": spec.key,
                    "type": spec.type,
                    "value": _get(self.data, spec.key),
                    "base": _get(self.base, spec.key),
                    "overridden": spec.key in self.values,
                    "live": spec.live,
                    "min": spec.min,
                    "max": spec.max,
                    "max_length": spec.max_length,
                    "options": options,
                })
            sections.append({"id": section.id, "icon": section.icon, "fields": items})
        return sections

    def update(self, bot: HexMusic, changes: dict[str, Any], resets: list[str]) -> list[str]:
        """Aplica cambios (y restablece claves). Devuelve las claves que requieren reiniciar."""
        cleaned: dict[str, Any] = {}
        for key, value in changes.items():
            spec = FIELDS.get(key)
            if spec is None:
                raise InvalidValue(key, "unknown")
            cleaned[key] = clean_value(spec, value, languages=bot.i18n.languages)
        for key in resets:
            if key not in FIELDS:
                raise InvalidValue(key, "unknown")

        candidate = copy.deepcopy(self.data)
        for key in resets:
            _set(candidate, key, _get(self.base, key))
        for key, value in cleaned.items():
            _set(candidate, key, value)
        try:
            validate(candidate)
        except ValueError as exc:
            raise InvalidValue("config", str(exc).strip()) from None

        touched: list[str] = []
        for key in resets:
            if key in self.values:
                del self.values[key]
            _set(self.data, key, _get(self.base, key))
            touched.append(key)
        for key, value in cleaned.items():
            if value == _get(self.base, key):
                self.values.pop(key, None)  # igual que config.yml: no hace falta guardarlo
            else:
                self.values[key] = value
            _set(self.data, key, value)
            touched.append(key)
        self._save()
        return [key for key in touched if not FIELDS[key].live]
