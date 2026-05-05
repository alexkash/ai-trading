from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT_DIR, settings
from app.db import Base, engine
from app.routers import bots, exports, runs
from app.trading.registry import registry

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    log.info("starting; bot hot-reload=%s", settings.bot_hot_reload)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    registry.reload()
    if settings.bot_hot_reload:
        from app.hot_reload import start_watcher

        watcher_task = await start_watcher()
    else:
        watcher_task = None
    yield
    if watcher_task is not None:
        watcher_task.cancel()


app = FastAPI(title="AI Trading", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=ROOT_DIR / "app" / "static"), name="static")
app.include_router(bots.router)
app.include_router(runs.router)
app.include_router(exports.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/bots")
