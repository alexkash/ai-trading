"""Simulator: applies actions emitted by a bot to a virtual wallet.

Single position per symbol (no hedging). Linear USDT perpetuals.
Backtest: market fills at next bar's open ± slippage; limit fills if low<=price<=high.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.trading.base_bot import (
    Action,
    Bar,
    ClosePosition,
    Hold,
    OrderType,
    PlaceOrder,
    Position,
    Side,
)
from app.trading.instance_config import (
    AllowedSides,
    InstanceConfig,
    RiskMode,
    StopConfig,
    StopMode,
)

log = logging.getLogger(__name__)
BPS = 1.0 / 10_000.0


@dataclass
class FilledTrade:
    bot_instance_id: int
    run_id: int | None
    symbol: str
    side: str
    qty: float
    leverage: float
    entry_price: float
    exit_price: float
    opened_at: datetime
    closed_at: datetime
    fee: float
    funding: float
    pnl: float
    pnl_pct: float
    exit_reason: str
    tag: str | None


@dataclass
class _OpenLeg:
    symbol: str
    side: Side
    qty: float
    entry_price: float
    leverage: float
    opened_at: datetime
    fee_paid: float
    stop_loss: float | None
    take_profit: float | None
    tag: str | None
    pending_close: bool = False


@dataclass
class EngineSummary:
    net_pnl: float = 0.0
    roi_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade: float = 0.0
    trade_count: int = 0


@dataclass
class _EquityState:
    initial_balance: float
    balance: float
    peak_equity: float
    max_drawdown_pct: float = 0.0
    last_trade_ts: float = 0.0
    daily_baseline: float | None = None
    daily_baseline_day: int | None = None
    daily_locked: bool = False
    halted: bool = False


class PaperEngine:
    """Применяет действия бота к виртуальному кошельку, ведёт сделки и equity-кривую."""

    def __init__(
        self,
        config: InstanceConfig,
        bot_instance_id: int,
        run_id: int | None = None,
    ) -> None:
        self.cfg = config
        self.bot_instance_id = bot_instance_id
        self.run_id = run_id
        self._open: dict[str, _OpenLeg] = {}
        self._equity = _EquityState(
            initial_balance=config.initial_balance_usdt,
            balance=config.initial_balance_usdt,
            peak_equity=config.initial_balance_usdt,
        )
        self.trades: list[FilledTrade] = []
        self._equity_curve: list[tuple[datetime, float, float, float]] = []
        self._closed_pnls: list[float] = []

    # -- public state --
    @property
    def balance(self) -> float:
        return self._equity.balance

    def equity_at(self, last_price: float | None = None) -> float:
        unreal = self._unrealized(last_price) if last_price is not None else 0.0
        return self._equity.balance + unreal

    def positions(self) -> list[Position]:
        return [
            Position(
                symbol=leg.symbol,
                side="long" if leg.side is Side.LONG else "short",
                qty=leg.qty,
                avg_price=leg.entry_price,
                leverage=leg.leverage,
                unrealized_pnl=0.0,
            )
            for leg in self._open.values()
        ]

    # -- step --
    def apply(self, prev_bar: Bar, next_bar: Bar, actions: list[Action]) -> None:
        """Вызывается на каждом баре после bot.on_bar(prev_bar).

        ``next_bar`` используется как «реальный рынок» для исполнения ордеров.
        """
        if self._equity.halted:
            return

        self._roll_daily(next_bar.ts)

        # 1) protective exits using next bar's H/L
        self._check_protective_exits(next_bar)

        # 2) bot actions
        for action in actions:
            self._apply_action(action, next_bar)

        # 3) drawdown / daily limit gates
        equity = self.equity_at(next_bar.close)
        self._update_drawdown(equity)
        self._check_kill_switches(next_bar)

        # 4) write equity point for THIS bar
        peak = self._equity.peak_equity or 1.0
        dd = max(0.0, (peak - equity) / peak * 100.0)
        self._equity_curve.append((next_bar.ts, self._equity.balance, equity, dd))

    # -- equity history (drained by engines) --
    def drain_equity(self) -> list[tuple[datetime, float, float, float]]:
        out, self._equity_curve = self._equity_curve, []
        return out

    def drain_trades(self) -> list[FilledTrade]:
        out, self.trades = self.trades, []
        return out

    # -- summary --
    def summary(self) -> EngineSummary:
        s = EngineSummary(trade_count=len(self._closed_pnls))
        if not self._closed_pnls:
            return s
        s.net_pnl = sum(self._closed_pnls)
        s.roi_pct = s.net_pnl / max(self._equity.initial_balance, 1e-9) * 100.0
        wins = [p for p in self._closed_pnls if p > 0]
        losses = [p for p in self._closed_pnls if p < 0]
        s.win_rate = len(wins) / len(self._closed_pnls) * 100.0
        gross_loss = abs(sum(losses)) or 1e-9
        s.profit_factor = sum(wins) / gross_loss
        s.avg_trade = s.net_pnl / len(self._closed_pnls)
        s.max_drawdown_pct = self._equity.max_drawdown_pct
        return s

    # -- internals --
    def _apply_action(self, action: Action, bar: Bar) -> None:
        if isinstance(action, Hold):
            return
        if isinstance(action, ClosePosition):
            symbol = action.symbol or bar.symbol
            if symbol in self._open:
                self._close(symbol, self._fill_price(bar, OrderType.MARKET, None, "exit"), bar.ts,
                            "manual_close")
            return
        if isinstance(action, PlaceOrder):
            self._open_order(action, bar)
            return
        # CancelOrder is a no-op in v1 (no resting orders modelled)

    def _open_order(self, order: PlaceOrder, bar: Bar) -> None:
        if not self._allowed_side(order.side):
            return
        if self._equity.last_trade_ts and (
            time.time() - self._equity.last_trade_ts < self.cfg.cooldown_sec
        ):
            return
        if len(self._open) >= self.cfg.max_concurrent_positions:
            existing = self._open.get(bar.symbol)
            if existing is None:
                return
            # Reverse if requested
            if (existing.side is Side.LONG) != (order.side is Side.LONG):
                self._close(bar.symbol,
                            self._fill_price(bar, OrderType.MARKET, None, "exit"),
                            bar.ts, "reverse")
            else:
                return

        order_type = order.type or OrderType(self.cfg.default_order_type.value)
        fill_price = self._fill_price(bar, order_type, order.price, "entry")
        if fill_price is None:
            return

        notional = self._sizing_notional(order.qty, fill_price)
        if notional <= 0:
            return
        notional = min(notional, self.cfg.max_position_notional_usdt)
        qty = notional / fill_price

        fee_bps = self.cfg.taker_fee_bps if order_type is OrderType.MARKET else self.cfg.maker_fee_bps
        fee = notional * fee_bps * BPS
        # Entry fee is NOT applied to balance here; both fees are netted in _close.
        sl = order.stop_loss or self._derived_stop(self.cfg.stop_loss, fill_price, order.side, "sl",
                                                   bar)
        tp = order.take_profit or self._derived_stop(self.cfg.take_profit, fill_price, order.side,
                                                      "tp", bar)

        self._open[bar.symbol] = _OpenLeg(
            symbol=bar.symbol,
            side=order.side,
            qty=qty,
            entry_price=fill_price,
            leverage=self.cfg.leverage,
            opened_at=bar.ts,
            fee_paid=fee,
            stop_loss=sl,
            take_profit=tp,
            tag=order.tag,
        )

    def _close(self, symbol: str, exit_price: float, ts: datetime, reason: str) -> None:
        leg = self._open.pop(symbol, None)
        if leg is None:
            return
        notional = leg.qty * exit_price
        fee_exit = notional * self.cfg.taker_fee_bps * BPS
        direction = 1.0 if leg.side is Side.LONG else -1.0
        gross_pnl = (exit_price - leg.entry_price) * leg.qty * direction
        total_fee = leg.fee_paid + fee_exit
        net = gross_pnl - total_fee
        self._equity.balance += net
        self._closed_pnls.append(net)
        self._equity.last_trade_ts = time.time()

        self.trades.append(
            FilledTrade(
                bot_instance_id=self.bot_instance_id,
                run_id=self.run_id,
                symbol=symbol,
                side="long" if leg.side is Side.LONG else "short",
                qty=leg.qty,
                leverage=leg.leverage,
                entry_price=leg.entry_price,
                exit_price=exit_price,
                opened_at=leg.opened_at,
                closed_at=ts,
                fee=total_fee,
                funding=0.0,
                pnl=net,
                pnl_pct=net / max(leg.entry_price * leg.qty, 1e-9) * 100.0,
                exit_reason=reason,
                tag=leg.tag,
            )
        )

    def _check_protective_exits(self, bar: Bar) -> None:
        leg = self._open.get(bar.symbol)
        if leg is None:
            return
        # SL/TP using the bar's H/L
        if leg.stop_loss is not None:
            hit = bar.low <= leg.stop_loss if leg.side is Side.LONG else bar.high >= leg.stop_loss
            if hit:
                self._close(bar.symbol, leg.stop_loss, bar.ts, "stop_loss")
                return
        if leg.take_profit is not None:
            hit = bar.high >= leg.take_profit if leg.side is Side.LONG else bar.low <= leg.take_profit
            if hit:
                self._close(bar.symbol, leg.take_profit, bar.ts, "take_profit")

    def _fill_price(
        self, bar: Bar, order_type: OrderType, price: float | None, kind: str
    ) -> float | None:
        slip = self.cfg.slippage_bps * BPS
        if order_type is OrderType.MARKET:
            base = bar.open if kind == "entry" else bar.close
            return base * (1 + slip) if kind == "entry" else base * (1 - slip)
        # LIMIT
        if price is None:
            return None
        if bar.low <= price <= bar.high:
            return price
        return None

    def _sizing_notional(self, qty: float | None, price: float) -> float:
        if qty is not None and qty > 0:
            return qty * price
        equity = self._equity.balance
        if self.cfg.risk_mode is RiskMode.fixed_usdt:
            return self.cfg.risk_per_trade * self.cfg.leverage
        return equity * self.cfg.risk_per_trade / 100.0 * self.cfg.leverage

    def _allowed_side(self, side: Side) -> bool:
        match self.cfg.allowed_sides:
            case AllowedSides.long_only:
                return side is Side.LONG
            case AllowedSides.short_only:
                return side is Side.SHORT
            case _:
                return True

    def _derived_stop(
        self, stop: StopConfig, entry: float, side: Side, kind: str, bar: Bar
    ) -> float | None:
        if stop.mode is StopMode.off or stop.value <= 0:
            return None
        if stop.mode is StopMode.pct:
            delta = entry * stop.value / 100.0
        else:
            # ATR mode requires history; approximate using bar range as a fallback
            delta = (bar.high - bar.low) * stop.value
        if side is Side.LONG:
            return entry - delta if kind == "sl" else entry + delta
        return entry + delta if kind == "sl" else entry - delta

    def _update_drawdown(self, equity: float) -> None:
        self._equity.peak_equity = max(self._equity.peak_equity, equity)
        if self._equity.peak_equity > 0:
            dd = (self._equity.peak_equity - equity) / self._equity.peak_equity * 100.0
            self._equity.max_drawdown_pct = max(self._equity.max_drawdown_pct, dd)

    def _roll_daily(self, ts: datetime) -> None:
        day = ts.astimezone(timezone.utc).toordinal()
        if self._equity.daily_baseline_day != day:
            self._equity.daily_baseline = self.equity_at()
            self._equity.daily_baseline_day = day
            self._equity.daily_locked = False

    def _check_kill_switches(self, bar: Bar) -> None:
        if self.cfg.daily_loss_limit_pct > 0 and self._equity.daily_baseline:
            equity = self.equity_at(bar.close)
            loss_pct = (self._equity.daily_baseline - equity) / self._equity.daily_baseline * 100.0
            if loss_pct >= self.cfg.daily_loss_limit_pct and not self._equity.daily_locked:
                for symbol in list(self._open):
                    self._close(symbol, bar.close, bar.ts, "daily_loss_limit")
                self._equity.daily_locked = True
        if self.cfg.max_drawdown_pct > 0 and self._equity.max_drawdown_pct >= self.cfg.max_drawdown_pct:
            for symbol in list(self._open):
                self._close(symbol, bar.close, bar.ts, "max_drawdown")
            self._equity.halted = True

    def _unrealized(self, last_price: float) -> float:
        total = 0.0
        for leg in self._open.values():
            direction = 1.0 if leg.side is Side.LONG else -1.0
            total += (last_price - leg.entry_price) * leg.qty * direction
        return total
