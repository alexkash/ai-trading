from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, ClassVar, Literal, Protocol, TypeAlias, runtime_checkable

from pydantic import BaseModel


@dataclass(frozen=True)
class Bar:
    ts: datetime
    symbol: str
    timeframe: str
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Tick:
    ts: datetime
    symbol: str
    last: float
    bid: float
    ask: float
    bid_size: float
    ask_size: float


@dataclass(frozen=True)
class Position:
    symbol: str
    side: Literal["long", "short"]
    qty: float
    avg_price: float
    leverage: float
    unrealized_pnl: float
    liquidation_price: float | None = None


@dataclass(frozen=True)
class OpenOrder:
    order_id: str
    symbol: str
    side: Literal["long", "short"]
    qty: float
    price: float | None
    type: Literal["market", "limit"]
    created_at: datetime


class Side(StrEnum):
    LONG = "long"
    SHORT = "short"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class PlaceOrder:
    side: Side
    qty: float | None = None
    type: OrderType = OrderType.MARKET
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    tag: str | None = None


@dataclass(frozen=True)
class CancelOrder:
    order_id: str


@dataclass(frozen=True)
class ClosePosition:
    symbol: str | None = None


@dataclass(frozen=True)
class Hold:
    pass


Action: TypeAlias = PlaceOrder | CancelOrder | ClosePosition | Hold


@runtime_checkable
class BotContext(Protocol):
    def history(self, symbol: str, tf: str, n: int) -> list[Bar]: ...
    def position(self, symbol: str | None = None) -> Position | None: ...
    def open_orders(self, symbol: str | None = None) -> list[OpenOrder]: ...
    def balance(self) -> float: ...
    def now(self) -> datetime: ...
    def log(self, level: str, msg: str, **kw: Any) -> None: ...


class BaseBot(ABC):
    """Базовый класс для всех стратегий.

    Подкласс лежит в bots/<file>.py и автоматически подхватывается реестром.
    Гарантии платформы:
      * on_bar вызывается только на закрытых барах.
      * Бот не делает сетевых вызовов и не пишет в БД.
      * Возвращаемые действия фильтруются через InstanceConfig.
      * Исключения логируются в Signal.error и не валят процесс.
    """

    name: ClassVar[str]
    description: ClassVar[str] = ""
    params_schema: ClassVar[type[BaseModel]]
    supported_timeframes: ClassVar[list[str]] = ["1m", "5m", "15m", "1h", "4h", "1d"]
    supports_multi_symbol: ClassVar[bool] = False

    def __init__(self, params: BaseModel, ctx: BotContext) -> None:
        self.params = params
        self.ctx = ctx

    @abstractmethod
    def on_bar(self, bar: Bar) -> list[Action]:
        ...

    def on_tick(self, tick: Tick) -> list[Action]:  # noqa: ARG002
        return []

    def features(self) -> dict[str, float]:
        return {}

    def reasoning(self, actions: list[Action]) -> str:  # noqa: ARG002
        return ""
