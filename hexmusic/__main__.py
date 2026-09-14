"""Punto de entrada: python -m hexmusic"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import discord
from dotenv import load_dotenv

from .bot import HexMusic
from .config import load_config

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    load_dotenv(ROOT / ".env")

    config_path = Path(os.getenv("HEXMUSIC_CONFIG", ROOT / "config.yml"))
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as exc:
        print(f"[HexMusic] Error en la configuración: {exc}", file=sys.stderr)
        sys.exit(1)

    level = getattr(logging, str(config.logging.level).upper(), logging.INFO)
    discord.utils.setup_logging(level=level, root=True)

    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        logging.getLogger("hexmusic").critical("Falta DISCORD_TOKEN. Cópialo en el archivo .env (ver .env.example).")
        sys.exit(1)

    bot = HexMusic(config=config, root=ROOT)
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
