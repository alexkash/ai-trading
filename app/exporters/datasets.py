"""Build pandas DataFrames for exports (trades / equity / signals / snapshots / candles)."""

from __future__ import annotations

import json
from datetime import timezone
from typing import Literal

import pandas as pd
from sqlalchemy import and_, select

from app.db import session_scope
from app.models.bot import BotInstance
from app.models.candle import Candle
from app.models.equity import EquityPoint
from app.models.run import Run
from app.models.signal import Signal
from app.models.trade import Trade

Scope = Literal["bot", "run"]


def _utc(ts):
    if ts is None:
        return None
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


async def trades_df(scope: Scope, ident: int) -> pd.DataFrame:
    async with session_scope() as session:
        if scope == "bot":
            stmt = select(Trade).where(Trade.bot_instance_id == ident).order_by(Trade.opened_at)
        else:
            stmt = select(Trade).where(Trade.run_id == ident).order_by(Trade.opened_at)
        rows = (await session.execute(stmt)).scalars().all()
    return pd.DataFrame(
        [
            {
                "id": r.id,
                "symbol": r.symbol,
                "side": r.side,
                "qty": r.qty,
                "leverage": r.leverage,
                "entry_price": r.entry_price,
                "exit_price": r.exit_price,
                "opened_at": _utc(r.opened_at),
                "closed_at": _utc(r.closed_at),
                "fee": r.fee,
                "funding": r.funding,
                "pnl": r.pnl,
                "pnl_pct": r.pnl_pct,
                "exit_reason": r.exit_reason,
                "tag": r.tag,
            }
            for r in rows
        ]
    )


async def equity_df(scope: Scope, ident: int) -> pd.DataFrame:
    async with session_scope() as session:
        if scope == "bot":
            stmt = (
                select(EquityPoint)
                .where(EquityPoint.bot_instance_id == ident)
                .order_by(EquityPoint.ts)
            )
        else:
            stmt = (
                select(EquityPoint).where(EquityPoint.run_id == ident).order_by(EquityPoint.ts)
            )
        rows = (await session.execute(stmt)).scalars().all()
    return pd.DataFrame(
        [
            {
                "ts": _utc(r.ts),
                "balance": r.balance,
                "equity": r.equity,
                "drawdown_pct": r.drawdown_pct,
            }
            for r in rows
        ]
    )


async def signals_df(scope: Scope, ident: int) -> pd.DataFrame:
    async with session_scope() as session:
        if scope == "bot":
            stmt = select(Signal).where(Signal.bot_instance_id == ident).order_by(Signal.ts)
        else:
            stmt = select(Signal).where(Signal.run_id == ident).order_by(Signal.ts)
        rows = (await session.execute(stmt)).scalars().all()
    return pd.DataFrame(
        [
            {
                "ts": _utc(r.ts),
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "bar_close": r.bar_close,
                "actions": json.dumps(r.actions, default=str),
                "features": json.dumps(r.features, default=str),
                "reasoning": r.reasoning,
                "error": r.error,
            }
            for r in rows
        ]
    )


async def snapshots_df(scope: Scope, ident: int) -> pd.DataFrame:
    """Один сигнал = одна строка с raw bars window и features inline.

    Сохраняем raw bars как JSON-строку (window) и фичи как отдельные колонки.
    Это «контекст принятия решения» — один пример для ML.
    """
    async with session_scope() as session:
        if scope == "bot":
            stmt = (
                select(Signal)
                .where(and_(Signal.bot_instance_id == ident, Signal.snapshot.isnot(None)))
                .order_by(Signal.ts)
            )
        else:
            stmt = (
                select(Signal)
                .where(and_(Signal.run_id == ident, Signal.snapshot.isnot(None)))
                .order_by(Signal.ts)
            )
        rows = (await session.execute(stmt)).scalars().all()

    records = []
    for r in rows:
        snap = r.snapshot or {}
        rec = {
            "ts": _utc(r.ts),
            "symbol": r.symbol,
            "timeframe": r.timeframe,
            "bar_close": r.bar_close,
            "actions": json.dumps(r.actions, default=str),
            "reasoning": r.reasoning,
            "window_bars": json.dumps(snap.get("bars", []), default=str),
        }
        for k, v in (snap.get("features") or r.features or {}).items():
            rec[f"f_{k}"] = v
        records.append(rec)
    return pd.DataFrame(records)


async def candles_df(scope: Scope, ident: int) -> pd.DataFrame:
    async with session_scope() as session:
        if scope == "bot":
            inst = await session.get(BotInstance, ident)
            if inst is None:
                return pd.DataFrame()
            stmt = (
                select(Candle)
                .where(and_(Candle.symbol == inst.symbol, Candle.timeframe == inst.primary_tf))
                .order_by(Candle.ts)
            )
        else:
            run = await session.get(Run, ident)
            if run is None:
                return pd.DataFrame()
            inst = await session.get(BotInstance, run.bot_instance_id)
            if inst is None:
                return pd.DataFrame()
            stmt = (
                select(Candle)
                .where(
                    and_(
                        Candle.symbol == inst.symbol,
                        Candle.timeframe == inst.primary_tf,
                        Candle.ts >= run.from_ts,
                        Candle.ts <= run.to_ts,
                    )
                )
                .order_by(Candle.ts)
            )
        rows = (await session.execute(stmt)).scalars().all()
    return pd.DataFrame(
        [
            {
                "ts": _utc(r.ts),
                "symbol": r.symbol,
                "timeframe": r.timeframe,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
            }
            for r in rows
        ]
    )


BUILDERS = {
    "trades": trades_df,
    "equity": equity_df,
    "signals": signals_df,
    "snapshots": snapshots_df,
    "candles": candles_df,
}
