"""Sistema de idiomas: mensajes del bot y descripciones de los comandos slash."""

from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any

import discord
from discord import app_commands

log = logging.getLogger("hexmusic.i18n")


class I18n:
    """Carga todos los ``locales/*.json``. Cada archivo es un idioma (``es.json`` → ``es``)."""

    def __init__(self, directory: Path, default: str = "es") -> None:
        self.directory = directory
        self.default = default
        self._data: dict[str, dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        data: dict[str, dict[str, Any]] = {}
        for file in sorted(self.directory.glob("*.json")):
            with file.open(encoding="utf-8") as fp:
                data[file.stem] = json.load(fp)
        if not data:
            raise RuntimeError(f"No hay archivos de idioma en {self.directory}")
        if self.default not in data:
            fallback = "en" if "en" in data else next(iter(data))
            log.warning("El idioma por defecto %r no existe; se usará %r.", self.default, fallback)
            self.default = fallback
        self._data = data
        log.info("Idiomas cargados: %s", ", ".join(data))

    @property
    def languages(self) -> list[str]:
        return list(self._data)

    def language_name(self, code: str) -> str:
        return str(self._data.get(code, {}).get("_meta", {}).get("name", code))

    def _lookup(self, lang: str, key: str) -> str | None:
        node: Any = self._data.get(lang)
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, str) else None

    def has(self, lang: str, key: str) -> bool:
        return self._lookup(lang, key) is not None

    def t(self, lang: str | None, key: str, /, **kwargs: Any) -> str:
        """Traduce ``key``. Si falta en ``lang`` usa el idioma por defecto y, si no, la propia clave."""
        text = self._lookup(lang or self.default, key) or self._lookup(self.default, key)
        if text is None:
            log.debug("Falta la traducción %r (%s)", key, lang)
            return key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, IndexError, ValueError):
                log.warning("Parámetros incorrectos para la traducción %r", key)
        return text

    def section(self, lang: str, name: str) -> dict[str, Any]:
        """Sección completa de un idioma, completada con el idioma por defecto (usada por el panel web)."""

        def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
            result = copy.deepcopy(base)
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key] = merge(result[key], value)
                else:
                    result[key] = value
            return result

        base = self._data.get(self.default, {}).get(name, {})
        current = self._data.get(lang, {}).get(name, {})
        return merge(base if isinstance(base, dict) else {}, current if isinstance(current, dict) else {})

    def command_text(self, lang: str, source: str) -> str | None:
        """Traducción de una descripción de comando (tabla ``_commands``)."""
        table = self._data.get(lang, {}).get("_commands", {})
        value = table.get(source)
        return value if isinstance(value, str) else None


class HexTranslator(app_commands.Translator):
    """Traduce las descripciones de los comandos slash según el idioma del cliente de Discord.

    Los textos originales están en inglés dentro del código; las traducciones
    viven en la sección ``_commands`` de cada archivo de idioma.
    """

    SKIP = {
        app_commands.TranslationContextLocation.command_name,
        app_commands.TranslationContextLocation.group_name,
        app_commands.TranslationContextLocation.parameter_name,
    }

    def __init__(self, i18n: I18n) -> None:
        self.i18n = i18n

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContextTypes,
    ) -> str | None:
        if context.location in self.SKIP:
            return None
        lang = locale.value.split("-")[0].lower()
        if lang not in self.i18n.languages:
            return None
        text = self.i18n.command_text(lang, string.message)
        return text[:100] if text else None
