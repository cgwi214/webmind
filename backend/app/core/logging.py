"""统一日志配置：控制台 + logs/backend.log。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.core.config import settings

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def setup_logging(level: int | None = None) -> None:
    global _configured
    if _configured:
        return
    if level is None:
        level = logging.DEBUG if settings.DEBUG else logging.INFO

    formatter = logging.Formatter(_FORMAT, datefmt=_DATE_FORMAT)

    # Windows 控制台默认 GBK，中文日志会乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = settings.log_dir / "backend.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    agent_file = RotatingFileHandler(
        settings.log_dir / "agent.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    agent_file.setFormatter(formatter)
    logging.getLogger("webmind.agent").addHandler(agent_file)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # 第三方库心跳日志过于嘈杂
    for noisy in ("pymongo", "pymongo.topology", "urllib3", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
