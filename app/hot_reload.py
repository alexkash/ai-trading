from __future__ import annotations

import asyncio
import logging

from watchfiles import awatch

from app.config import BOTS_DIR
from app.trading.registry import registry

log = logging.getLogger(__name__)


async def _watch() -> None:
    log.info("hot-reload watching %s", BOTS_DIR)
    async for changes in awatch(BOTS_DIR):
        log.info("bots/ changed (%d) — reloading registry", len(changes))
        try:
            registry.reload()
        except Exception:  # noqa: BLE001
            log.exception("registry reload failed")


async def start_watcher() -> asyncio.Task:
    return asyncio.create_task(_watch(), name="bot-hot-reload")
