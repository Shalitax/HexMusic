"""Errores propios con mensajes traducibles."""

from __future__ import annotations

from typing import Any

from discord import app_commands
from discord.ext import commands


class HexError(commands.CheckFailure, app_commands.CheckFailure):
    """Error que se muestra al usuario.

    ``key`` es una clave de los archivos de idioma (``locales/*.json``) y
    ``kwargs`` son los valores para rellenar el texto.
    """

    def __init__(self, key: str, /, **kwargs: Any) -> None:
        super().__init__(key)
        self.key = key
        self.kwargs = kwargs
