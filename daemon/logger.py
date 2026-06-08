from __future__ import annotations
from typing import Any

import logging

try:
    from rich.logging import RichHandler
except ImportError:  # pragma: no cover
    RichHandler = None

__all__ = ["RichLogManager", "get_logger", "configure_rich_logger"]

_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class RichLogManager:
    """Singleton manager that configures the root logger once and provides loggers.

    Instantiating this class (or importing the module) will automatically configure
    logging so callers don't need to call a separate `configure` function.
    """

    _instance: "RichLogManager" | None = None

    def __new__(cls, *args: Any, **kwargs: Any) -> "RichLogManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        level: int = logging.INFO,
        *,
        rich_tracebacks: bool = True,
        markup: bool = True,
        force: bool = False,
    ) -> None:
        if getattr(self, "_configured", False) and not force:
            return

        handler = (
            RichHandler(rich_tracebacks=rich_tracebacks, markup=markup)
            if RichHandler
            else logging.StreamHandler()
        )
        formatter = logging.Formatter(_LOG_FORMAT, _DATE_FORMAT)
        handler.setFormatter(formatter)

        root = logging.getLogger()
        root.handlers[:] = [handler]
        root.setLevel(level)

        self._configured = True

    def get_logger(self, name: str | None = None) -> logging.Logger:
        return logging.getLogger(name)