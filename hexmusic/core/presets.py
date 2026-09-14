"""Presets de filtros de audio. Se amplían o sobrescriben desde ``filters.presets`` en config.yml."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import wavelink

if TYPE_CHECKING:
    from ..config import Config

EQ_BANDS = 15
EQ_MIN_GAIN = -0.25
EQ_MAX_GAIN = 1.0


def _eq(*gains: float) -> list[dict[str, float]]:
    return [{"band": band, "gain": gain} for band, gain in enumerate(gains)]


# Formato de filtros de Lavalink (https://lavalink.dev/api/rest#filters)
DEFAULT_PRESETS: dict[str, dict[str, Any]] = {
    "bassboost": {"equalizer": _eq(0.25, 0.2, 0.15, 0.1, 0.05)},
    "superbass": {"equalizer": _eq(0.4, 0.35, 0.3, 0.2, 0.1, 0.0, -0.05, -0.05)},
    "pop": {"equalizer": _eq(-0.02, -0.01, 0.08, 0.1, 0.15, 0.1, 0.03, -0.02, -0.035, -0.05, -0.05, -0.05, -0.05, -0.05, -0.05)},
    "rock": {"equalizer": _eq(0.3, 0.25, 0.2, 0.1, 0.05, -0.05, -0.15, -0.2, -0.1, -0.05, 0.05, 0.1, 0.2, 0.25, 0.3)},
    "electronic": {"equalizer": _eq(0.375, 0.35, 0.125, 0.0, 0.0, -0.125, -0.125, 0.0, 0.25, 0.125, 0.15, 0.2, 0.25, 0.35, 0.4)},
    "vocals": {"equalizer": _eq(-0.1, -0.1, -0.05, 0.0, 0.1, 0.15, 0.2, 0.2, 0.15, 0.1)},
    "treble": {"equalizer": _eq(0, 0, 0, 0, 0, 0, 0, 0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.25, 0.25)},
    "nightcore": {"timescale": {"speed": 1.2, "pitch": 1.2, "rate": 1.0}},
    "vaporwave": {"timescale": {"speed": 0.85, "pitch": 0.85, "rate": 1.0}, "equalizer": _eq(0.3, 0.3)},
    "slowed": {"timescale": {"speed": 0.8, "pitch": 0.85, "rate": 1.0}},
    "chipmunk": {"timescale": {"speed": 1.05, "pitch": 1.35, "rate": 1.25}},
    "darthvader": {"timescale": {"speed": 0.975, "pitch": 0.5, "rate": 0.8}},
    "8d": {"rotation": {"rotationHz": 0.2}},
    "karaoke": {"karaoke": {"level": 1.0, "monoLevel": 1.0, "filterBand": 220.0, "filterWidth": 100.0}},
    "tremolo": {"tremolo": {"frequency": 4.0, "depth": 0.75}},
    "vibrato": {"vibrato": {"frequency": 4.0, "depth": 0.75}},
    "soft": {"lowPass": {"smoothing": 20.0}},
}


def get_presets(config: Config) -> dict[str, dict[str, Any]]:
    """Presets por defecto + los de config.yml (un valor ``null`` elimina un preset)."""
    presets = copy.deepcopy(DEFAULT_PRESETS)
    custom = config.filters.presets
    for name, payload in (custom.to_dict() if hasattr(custom, "to_dict") else {}).items():
        key = str(name).lower()
        if payload is None:
            presets.pop(key, None)
        elif isinstance(payload, dict):
            presets[key] = payload
    return presets


def normalize_equalizer(bands: list[dict[str, Any]]) -> list[dict[str, float]]:
    """Devuelve las 15 bandas (las no indicadas quedan en 0) con la ganancia limitada a su rango."""
    gains = {band: 0.0 for band in range(EQ_BANDS)}
    for item in bands:
        band = int(item["band"])
        if 0 <= band < EQ_BANDS:
            gains[band] = min(max(float(item["gain"]), EQ_MIN_GAIN), EQ_MAX_GAIN)
    return [{"band": band, "gain": gain} for band, gain in gains.items()]


def build_filters(payload: dict[str, Any]) -> wavelink.Filters:
    data = copy.deepcopy(payload)
    if "equalizer" in data:
        data["equalizer"] = normalize_equalizer(data["equalizer"] or [])
    return wavelink.Filters(data=data)  # type: ignore[arg-type]
