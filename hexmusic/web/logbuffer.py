"""Últimas líneas del registro del bot en memoria, para verlas desde el panel (solo dueños)."""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

MAX_RECORDS = 1000
MAX_MESSAGE = 4000


class LogBuffer(logging.Handler):
    def __init__(self, capacity: int = MAX_RECORDS) -> None:
        super().__init__(level=logging.INFO)
        self.records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.sequence = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                message = f"{message}\n{logging.Formatter().formatException(record.exc_info)}"
            self.sequence += 1
            self.records.append({
                "seq": self.sequence,
                "time": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": message[:MAX_MESSAGE],
            })
        except Exception:  # noqa: BLE001 - registrar nunca debe fallar
            self.handleError(record)

    def since(self, sequence: int, *, level: int = logging.INFO, limit: int = 500) -> list[dict[str, Any]]:
        items = [item for item in self.records
                 if item["seq"] > sequence and logging.getLevelName(item["level"]) >= level]
        return items[-limit:]

    def attach(self) -> None:
        logging.getLogger().addHandler(self)

    def detach(self) -> None:
        logging.getLogger().removeHandler(self)
