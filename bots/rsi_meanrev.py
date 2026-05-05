"""RSI mean-reversion: long when oversold, short when overbought."""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, Field

from app.trading.base_bot import (
    Action,
    Bar,
    BaseBot,
    ClosePosition,
    Hold,
    OrderType,
    PlaceOrder,
    Side,
)
from app.trading.indicators import rsi


class RSIMeanRevParams(BaseModel):
    rsi_period: int = Field(default=14, ge=2, le=200)
    oversold: float = Field(default=30.0, ge=1.0, le=49.0)
    overbought: float = Field(default=70.0, ge=51.0, le=99.0)
    exit_mid: float = Field(default=50.0, ge=20.0, le=80.0,
                            description="Close position when RSI crosses this midline")


class RSIMeanRev(BaseBot):
    name = "RSI Mean Reversion"
    description = "Buy when RSI is oversold; sell when overbought; exit on midline cross."
    params_schema = RSIMeanRevParams

    def __init__(self, params, ctx):
        super().__init__(params, ctx)
        self._rsi: float = float("nan")

    def on_bar(self, bar: Bar) -> list[Action]:
        need = self.params.rsi_period * 4 + 5
        history = self.ctx.history(bar.symbol, bar.timeframe, need)
        if len(history) < self.params.rsi_period + 2:
            return [Hold()]

        closes = np.array([b.close for b in history], dtype=float)
        series = rsi(closes, self.params.rsi_period)
        cur, prev = float(series[-1]), float(series[-2])
        self._rsi = cur

        position = self.ctx.position(bar.symbol)

        # exit on midline cross
        if position is not None:
            if position.side == "long" and prev < self.params.exit_mid <= cur:
                return [ClosePosition()]
            if position.side == "short" and prev > self.params.exit_mid >= cur:
                return [ClosePosition()]

        if position is None:
            if cur <= self.params.oversold:
                return [PlaceOrder(side=Side.LONG, type=OrderType.MARKET, tag="rsi_oversold")]
            if cur >= self.params.overbought:
                return [PlaceOrder(side=Side.SHORT, type=OrderType.MARKET, tag="rsi_overbought")]
        return [Hold()]

    def features(self) -> dict[str, float]:
        return {"rsi": self._rsi}

    def reasoning(self, actions) -> str:
        return f"rsi={self._rsi:.1f}; actions={[type(a).__name__ for a in actions]}"
