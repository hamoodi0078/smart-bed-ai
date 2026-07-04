"""Central logging setup — loguru with stdlib interception.

Call setup_logging() once at process startup (web_server.py / app_entry.py).
All other modules just do: from loguru import logger
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from loguru import logger


class _InterceptHandler(logging.Handler):
    """Route all stdlib logging.getLogger() calls through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back  # type: ignore[assignment]
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure loguru sinks and intercept all stdlib logging."""
    logger.remove()

    # Colorized console
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> — "
            "<level>{message}</level>"
        ),
        backtrace=True,
        diagnose=False,
    )

    # Rotating JSON file log (14-day retention)
    if log_dir is None:
        from config import settings  # late import avoids circular at module load

        log_dir = Path(settings.runtime_data_dir) / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_dir / "danah_{time:YYYY-MM-DD}.log",
        level=level,
        rotation="00:00",
        retention="14 days",
        compression="gz",
        serialize=True,
        backtrace=True,
        diagnose=False,
    )

    # Intercept every stdlib logger
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)

    # Silence noisy third-party loggers that spam at INFO
    for _name in ("uvicorn.access", "httpx", "httpcore", "multipart"):
        logging.getLogger(_name).setLevel(logging.WARNING)
