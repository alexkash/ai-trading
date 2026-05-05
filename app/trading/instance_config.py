from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class MarginMode(StrEnum):
    isolated = "isolated"
    cross = "cross"


class AllowedSides(StrEnum):
    long_only = "long_only"
    short_only = "short_only"
    both = "both"


class OrderTypeDefault(StrEnum):
    market = "market"
    limit = "limit"


class TimeInForce(StrEnum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"


class StopMode(StrEnum):
    off = "off"
    pct = "pct"
    atr = "atr"


class RiskMode(StrEnum):
    pct_of_equity = "pct_of_equity"
    fixed_usdt = "fixed_usdt"


class StopConfig(BaseModel):
    mode: StopMode = StopMode.off
    value: float = Field(default=0.0, ge=0, description="% или множитель ATR")
    atr_period: int = Field(default=14, ge=2, le=200)


class InstanceConfig(BaseModel):
    """Общий конфиг инстанса бота — единый для всех стратегий."""

    # Капитал и размер позиции
    initial_balance_usdt: float = Field(default=1000.0, gt=0)
    risk_mode: RiskMode = RiskMode.pct_of_equity
    risk_per_trade: float = Field(default=2.0, gt=0, description="% от equity или USDT")
    max_position_notional_usdt: float = Field(default=5000.0, gt=0)
    max_concurrent_positions: int = Field(default=1, ge=1, le=20)
    leverage: float = Field(default=3.0, ge=1, le=125)
    margin_mode: MarginMode = MarginMode.isolated

    # Защитные стопы
    stop_loss: StopConfig = Field(default_factory=lambda: StopConfig(mode=StopMode.pct, value=2.0))
    take_profit: StopConfig = Field(
        default_factory=lambda: StopConfig(mode=StopMode.pct, value=4.0)
    )
    trailing_stop: StopConfig = Field(default_factory=StopConfig)
    daily_loss_limit_pct: float = Field(default=0.0, ge=0, description="0 = выкл")
    max_drawdown_pct: float = Field(default=0.0, ge=0, description="0 = выкл")

    # Поведение
    allowed_sides: AllowedSides = AllowedSides.both
    cooldown_sec: int = Field(default=0, ge=0)
    default_order_type: OrderTypeDefault = OrderTypeDefault.market
    limit_offset_bps: float = Field(default=0.0, ge=0)
    max_slippage_bps: float = Field(default=20.0, ge=0)
    time_in_force: TimeInForce = TimeInForce.GTC

    # Симулятор
    taker_fee_bps: float = Field(default=5.5, ge=0)
    maker_fee_bps: float = Field(default=2.0, ge=0)
    slippage_bps: float = Field(default=1.0, ge=0)
    apply_funding: bool = True
    latency_ms: int = Field(default=0, ge=0)

    # Уведомительные
    note: Literal[""] = ""

    model_config = {"extra": "forbid"}
