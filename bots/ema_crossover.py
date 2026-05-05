"""EMA crossover: long when fast crosses above slow, short when below."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from app.trading.base_bot import Action, Bar, BaseBot, Hold, OrderType, PlaceOrder, Side
from app.trading.indicators import ema


class EMACrossoverParams(BaseModel):
    fast: int = Field(default=12, ge=2, le=200, description="Fast EMA period")
    slow: int = Field(default=26, ge=3, le=500, description="Slow EMA period")


class EMACrossover(BaseBot):
    name = "EMA Crossover"
    description = "Classical fast/slow EMA crossover. Reverses on opposite cross."
    params_schema = EMACrossoverParams

    def __init__(self, params, ctx):
        super().__init__(params, ctx)
        self._last = {"fast": float("nan"), "slow": float("nan"), "diff": float("nan")}

    def on_bar(self, bar: Bar) -> list[Action]:
        need = max(self.params.slow + 5, 50)
        history = self.ctx.history(bar.symbol, bar.timeframe, need)
        if len(history) < self.params.slow + 1:
            return [Hold()]

        closes = np.array([b.close for b in history], dtype=float)
        fast_arr = ema(closes, self.params.fast)
        slow_arr = ema(closes, self.params.slow)
        prev_diff = fast_arr[-2] - slow_arr[-2]
        cur_diff = fast_arr[-1] - slow_arr[-1]
        self._last = {"fast": float(fast_arr[-1]), "slow": float(slow_arr[-1]), "diff": float(cur_diff)}

        position = self.ctx.position(bar.symbol)
        if prev_diff <= 0 < cur_diff:
            return [PlaceOrder(side=Side.LONG, type=OrderType.MARKET, tag="cross_up")]
        if prev_diff >= 0 > cur_diff:
            return [PlaceOrder(side=Side.SHORT, type=OrderType.MARKET, tag="cross_down")]
        return [Hold()]

    def features(self) -> dict[str, float]:
        return self._last

    def reasoning(self, actions) -> str:
        diff = self._last["diff"]
        return f"fast-slow={diff:+.4f}; actions={[type(a).__name__ for a in actions]}"
