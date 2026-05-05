from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.trading.base_bot import (
    Action,
    Bar,
    ClosePosition,
    Hold,
    OrderType,
    PlaceOrder,
    Side,
)
from app.trading.instance_config import (
    AllowedSides,
    InstanceConfig,
    StopConfig,
    StopMode,
)
from app.trading.paper_engine import PaperEngine


def _bar(ts: datetime, o: float, h: float, l: float, c: float) -> Bar:
    return Bar(ts=ts, symbol="BTCUSDT", timeframe="1h", open=o, high=h, low=l, close=c, volume=1.0)


def _config(**overrides) -> InstanceConfig:
    base = dict(
        initial_balance_usdt=1000.0,
        risk_per_trade=10.0,
        max_position_notional_usdt=100_000.0,
        leverage=1.0,
        stop_loss=StopConfig(mode=StopMode.off),
        take_profit=StopConfig(mode=StopMode.off),
        trailing_stop=StopConfig(mode=StopMode.off),
        slippage_bps=0.0,
        taker_fee_bps=10.0,
        maker_fee_bps=2.0,
        max_drawdown_pct=0.0,
        daily_loss_limit_pct=0.0,
        max_concurrent_positions=1,
        allowed_sides=AllowedSides.both,
    )
    base.update(overrides)
    return InstanceConfig(**base)


def _t(i: int) -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)


def test_market_long_then_close_records_pnl_and_fees() -> None:
    cfg = _config()
    eng = PaperEngine(cfg, bot_instance_id=1)
    b0, b1, b2 = _bar(_t(0), 100, 101, 99, 100), _bar(_t(1), 100, 105, 100, 105), _bar(_t(2), 105, 106, 100, 100)

    eng.apply(b0, b1, [PlaceOrder(side=Side.LONG, type=OrderType.MARKET)])
    assert len(eng.positions()) == 1

    eng.apply(b1, b2, [ClosePosition()])
    trades = eng.drain_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t.side == "long"
    assert t.entry_price == pytest.approx(100.0)
    # exit at next bar's close (paper_engine uses close for exit market fills)
    assert t.exit_price == pytest.approx(100.0)
    # fees: 10bps both legs on notional ≈ 100 * qty
    assert t.fee > 0
    assert t.pnl == pytest.approx(- t.fee)


def test_stop_loss_pct_triggers_on_low() -> None:
    cfg = _config(stop_loss=StopConfig(mode=StopMode.pct, value=2.0))
    eng = PaperEngine(cfg, bot_instance_id=1)
    b0 = _bar(_t(0), 100, 101, 99, 100)
    b1 = _bar(_t(1), 100, 102, 100, 101)        # entry at 100
    b2 = _bar(_t(2), 100, 100.5, 97, 98)        # low 97 < 98 (=100 - 2%) — SL hit at 98

    eng.apply(b0, b1, [PlaceOrder(side=Side.LONG, type=OrderType.MARKET)])
    eng.apply(b1, b2, [Hold()])

    trades = eng.drain_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t.exit_reason == "stop_loss"
    assert t.exit_price == pytest.approx(98.0)


def test_max_concurrent_positions_blocks_second_entry() -> None:
    cfg = _config(max_concurrent_positions=1)
    eng = PaperEngine(cfg, bot_instance_id=1)
    b0 = _bar(_t(0), 100, 101, 99, 100)
    b1 = _bar(_t(1), 100, 101, 99, 100)
    b2 = _bar(_t(2), 100, 101, 99, 100)

    eng.apply(b0, b1, [PlaceOrder(side=Side.LONG)])
    # Second LONG entry on the same symbol while one is open — same side ⇒ ignored.
    eng.apply(b1, b2, [PlaceOrder(side=Side.LONG)])
    assert len(eng.positions()) == 1
    eng.drain_trades()


def test_allowed_sides_long_only_rejects_short() -> None:
    cfg = _config(allowed_sides=AllowedSides.long_only)
    eng = PaperEngine(cfg, bot_instance_id=1)
    b0, b1 = _bar(_t(0), 100, 101, 99, 100), _bar(_t(1), 100, 101, 99, 100)
    eng.apply(b0, b1, [PlaceOrder(side=Side.SHORT)])
    assert eng.positions() == []


def test_summary_metrics_after_winning_trade() -> None:
    cfg = _config(taker_fee_bps=0.0, slippage_bps=0.0, leverage=1.0)
    eng = PaperEngine(cfg, bot_instance_id=1)
    b0 = _bar(_t(0), 100, 101, 99, 100)
    # entry on b1.open = 100
    b1 = _bar(_t(1), 100, 105, 100, 105)
    # exit market = b2.close
    b2 = _bar(_t(2), 105, 115, 105, 115)

    eng.apply(b0, b1, [PlaceOrder(side=Side.LONG)])
    eng.apply(b1, b2, [ClosePosition()])
    summary = eng.summary()
    assert summary.trade_count == 1
    assert summary.net_pnl > 0
    assert summary.win_rate == pytest.approx(100.0)
