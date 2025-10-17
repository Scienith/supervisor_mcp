from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


_CONFIGURED = False


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    # 日志目录可通过 SUPERVISOR_LOG_DIR 配置，默认为仓库根目录下 logs/
    log_dir = os.environ.get("SUPERVISOR_LOG_DIR")
    if not log_dir:
        # 尝试相对 src/ 的上一级作为仓库根
        here = Path(__file__).resolve()
        repo_root = here.parent.parent
        log_dir = str(repo_root / "logs")

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(log_dir, "supervisor_mcp.log")

    logger = logging.getLogger("supervisor_mcp")
    logger.setLevel(logging.INFO)

    # 轮转日志：每个文件最大 5MB，保留 5 个
    handler = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    # 可选：在开发模式下输出到控制台
    if os.environ.get("SUPERVISOR_LOG_CONSOLE") == "1":
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        logger.addHandler(console)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"supervisor_mcp.{name}")

