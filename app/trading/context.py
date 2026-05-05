from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.trading.base_bot import Bar, BotContext, OpenOrder, Position

log = logging.getLogger("bot")


@dataclass
class InMemoryContext(BotContext):
    """BotContext, который держит окно баров и состояние счёта в памяти.

    Используется одинаково в backtest и live. Платформа толкает в него бары,
    обновления баланса и позиций; бот читает только методами.
    """

    history_size: int = 500
    _bars: dict[tuple[str, str], deque[Bar]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=500))
    )
    _now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _positions: dict[str, Position] = field(default_factory=dict)
    _open_orders: list[OpenOrder] = field(default_factory=list)
    _balance: float = 0.0

    def __post_init__(self) -> None:
        # rebuild deques with the configured maxlen
        self._bars = defaultdict(lambda: deque(maxlen=self.history_size))

    # --- mutators (used by engines, not by bots) ---
    def push_bar(self, bar: Bar) -> None:
        self._bars[(bar.symbol, bar.timeframe)].append(bar)

    def set_now(self, ts: datetime) -> None:
        self._now = ts

    def set_balance(self, balance: float) -> None:
        self._balance = balance

    def set_position(self, position: Position | None, symbol: str) -> None:
        if position is None:
            self._positions.pop(symbol, None)
        else:
            self._positions[symbol] = position

    def set_open_orders(self, orders: list[OpenOrder]) -> None:
        self._open_orders = list(orders)

    # --- BotContext API ---
    def history(self, symbol: str, tf: str, n: int) -> list[Bar]:
        bars = self._bars.get((symbol, tf), deque())
        if n <= 0 or n >= len(bars):
            return list(bars)
        return list(bars)[-n:]

    def position(self, symbol: str | None = None) -> Position | None:
        if symbol is not None:
            return self._positions.get(symbol)
        return next(iter(self._positions.values()), None)

    def open_orders(self, symbol: str | None = None) -> list[OpenOrder]:
        if symbol is None:
            return list(self._open_orders)
        return [o for o in self._open_orders if o.symbol == symbol]

    def balance(self) -> float:
        return self._balance

    def now(self) -> datetime:
        return self._now

    def log(self, level: str, msg: str, **kw: Any) -> None:
        log.log(getattr(logging, level.upper(), logging.INFO), "%s %s", msg, kw)
