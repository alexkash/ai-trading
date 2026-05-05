"""Single shared Bybit V5 WebSocket; multiplexes kline subscriptions.

Powered by ``pybit.unified_trading.WebSocket``. The pybit callback runs on a
background thread; we hop back to asyncio via ``loop.call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from app.bybit.client import TF_TO_BYBIT
from app.config import settings
from app.trading.base_bot import Bar

log = logging.getLogger(__name__)

BarHandler = Callable[[Bar], Awaitable[None]]


class BybitWS:
    """Один WebSocket-клиент на всё приложение.

    Подписки kline.{interval}.{symbol} мультиплексируются между ботами.
    Хендлерам отдаются только закрытые бары (``confirm=true``).
    """

    def __init__(self, testnet: bool | None = None) -> None:
        self.testnet = settings.bybit_testnet if testnet is None else testnet
        self._handlers: dict[tuple[str, str], list[BarHandler]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None  # pybit.unified_trading.WebSocket lazily created
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._loop = asyncio.get_running_loop()
        self._started = True

    async def stop(self) -> None:
        if self._ws is not None:
            try:
                self._ws.exit()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                log.exception("error stopping bybit ws")
            self._ws = None
        self._started = False

    async def subscribe_kline(self, symbol: str, tf: str, handler: BarHandler) -> None:
        if not self._started:
            await self.start()
        key = (symbol, tf)
        first = key not in self._handlers
        self._handlers.setdefault(key, []).append(handler)
        if first:
            self._ensure_ws().kline_stream(
                symbol=symbol,
                interval=TF_TO_BYBIT[tf],
                callback=lambda msg: self._on_message(symbol, tf, msg),
            )

    def _ensure_ws(self):  # pragma: no cover — network singleton
        if self._ws is None:
            from pybit.unified_trading import WebSocket  # local import for testability

            self._ws = WebSocket(testnet=self.testnet, channel_type="linear")
        return self._ws

    def _on_message(self, symbol: str, tf: str, msg: dict) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(asyncio.create_task, self._dispatch(symbol, tf, msg))

    async def _dispatch(self, symbol: str, tf: str, msg: dict) -> None:
        for item in msg.get("data", []):
            if not item.get("confirm"):
                continue
            bar = Bar(
                ts=datetime.fromtimestamp(int(item["end"]) / 1000.0, tz=timezone.utc),
                symbol=symbol,
                timeframe=tf,
                open=float(item["open"]),
                high=float(item["high"]),
                low=float(item["low"]),
                close=float(item["close"]),
                volume=float(item["volume"]),
            )
            for h in self._handlers.get((symbol, tf), []):
                try:
                    await h(bar)
                except Exception:  # noqa: BLE001
                    log.exception("ws handler error for %s/%s", symbol, tf)


_ws: BybitWS | None = None


def get_ws() -> BybitWS:
    global _ws
    if _ws is None:
        _ws = BybitWS()
    return _ws


__all__ = ["BybitWS", "get_ws"]
