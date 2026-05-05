"""Sequential backtest of a bot over a time window using cached candles."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bybit.history import load_history
from app.db import session_scope
from app.models.bot import BotInstance
from app.models.equity import EquityPoint
from app.models.run import Run, RunStatus
from app.models.signal import Signal
from app.models.trade import Trade
from app.trading.base_bot import Bar
from app.trading.context import InMemoryContext
from app.trading.instance_config import InstanceConfig
from app.trading.paper_engine import PaperEngine
from app.trading.registry import registry

log = logging.getLogger(__name__)


def _action_to_dict(action) -> dict:
    return {"type": type(action).__name__, **{
        k: (v.value if hasattr(v, "value") else v)
        for k, v in vars(action).items()
    }}


async def _flush(
    session: AsyncSession,
    run_id: int,
    bot_id: int,
    engine: PaperEngine,
) -> None:
    for trade in engine.drain_trades():
        session.add(
            Trade(
                bot_instance_id=trade.bot_instance_id,
                run_id=trade.run_id,
                symbol=trade.symbol,
                side=trade.side,
                qty=trade.qty,
                leverage=trade.leverage,
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                opened_at=trade.opened_at,
                closed_at=trade.closed_at,
                fee=trade.fee,
                funding=trade.funding,
                pnl=trade.pnl,
                pnl_pct=trade.pnl_pct,
                exit_reason=trade.exit_reason,
                tag=trade.tag,
            )
        )
    for ts, balance, equity, dd in engine.drain_equity():
        session.add(
            EquityPoint(
                bot_instance_id=bot_id,
                run_id=run_id,
                ts=ts,
                balance=balance,
                equity=equity,
                drawdown_pct=dd,
            )
        )


async def run_backtest(run_id: int) -> None:
    async with session_scope() as session:
        run = await session.get(Run, run_id)
        if run is None:
            raise RuntimeError(f"run {run_id} not found")
        bot = await session.get(BotInstance, run.bot_instance_id)
        if bot is None:
            raise RuntimeError(f"bot instance {run.bot_instance_id} not found")
        run.status = RunStatus.running
        config_snapshot = run.config_snapshot or {}
        bot_strategy = bot.strategy
        bot_params = bot.bot_params
        instance_cfg_dict = bot.instance_config or {}
        symbol = bot.symbol
        tf = bot.primary_tf
        from_ts = run.from_ts
        to_ts = run.to_ts
        bot_id = bot.id

    entry = registry.get(bot_strategy)
    if entry is None:
        async with session_scope() as session:
            run = await session.get(Run, run_id)
            run.status = RunStatus.failed
            run.error = f"unknown strategy: {bot_strategy}"
        return

    cfg = InstanceConfig.model_validate(instance_cfg_dict or {})
    params = entry.params_schema.model_validate(bot_params or {})
    ctx = InMemoryContext(history_size=500)
    ctx.set_balance(cfg.initial_balance_usdt)
    bot_obj = entry.cls(params=params, ctx=ctx)
    engine = PaperEngine(cfg, bot_instance_id=bot_id, run_id=run_id)

    log.info("backtest run=%s strategy=%s symbol=%s tf=%s", run_id, bot_strategy, symbol, tf)

    if from_ts.tzinfo is None:
        from_ts = from_ts.replace(tzinfo=timezone.utc)
    if to_ts.tzinfo is None:
        to_ts = to_ts.replace(tzinfo=timezone.utc)
    bars = await load_history(symbol, tf, from_ts, to_ts)
    if len(bars) < 2:
        async with session_scope() as session:
            run = await session.get(Run, run_id)
            run.status = RunStatus.failed
            run.error = "not enough candles in selected range"
        return

    total = len(bars) - 1
    flush_every = 200

    async with session_scope() as session:
        for i in range(total):
            cur, nxt = bars[i], bars[i + 1]
            ctx.set_now(cur.ts)
            ctx.push_bar(cur)
            ctx.set_balance(engine.balance)
            ctx.set_position(_position_for(engine, symbol), symbol)

            try:
                actions = bot_obj.on_bar(cur)
            except Exception as e:  # noqa: BLE001
                session.add(
                    Signal(
                        bot_instance_id=bot_id,
                        run_id=run_id,
                        ts=cur.ts,
                        symbol=symbol,
                        timeframe=tf,
                        bar_close=cur.close,
                        actions=[],
                        features={},
                        reasoning="",
                        snapshot=None,
                        error=f"{type(e).__name__}: {e}",
                    )
                )
                continue

            try:
                features = bot_obj.features() or {}
                reasoning = bot_obj.reasoning(actions)
            except Exception:  # noqa: BLE001
                features, reasoning = {}, ""

            engine.apply(cur, nxt, actions)

            if any(_should_log(a) for a in actions):
                snapshot = _build_snapshot(ctx, symbol, tf, features)
                session.add(
                    Signal(
                        bot_instance_id=bot_id,
                        run_id=run_id,
                        ts=cur.ts,
                        symbol=symbol,
                        timeframe=tf,
                        bar_close=cur.close,
                        actions=[_action_to_dict(a) for a in actions],
                        features=features,
                        reasoning=reasoning or "",
                        snapshot=snapshot,
                    )
                )

            if (i + 1) % flush_every == 0:
                await _flush(session, run_id, bot_id, engine)
                progress = (i + 1) / total
                run = await session.get(Run, run_id)
                run.progress = progress
                await session.flush()

        await _flush(session, run_id, bot_id, engine)
        run = await session.get(Run, run_id)
        summary = engine.summary()
        run.metrics = {
            "net_pnl": summary.net_pnl,
            "roi_pct": summary.roi_pct,
            "max_drawdown_pct": summary.max_drawdown_pct,
            "win_rate": summary.win_rate,
            "profit_factor": summary.profit_factor,
            "avg_trade": summary.avg_trade,
            "trade_count": summary.trade_count,
        }
        run.progress = 1.0
        run.status = RunStatus.done
        run.finished_at = datetime.now(timezone.utc)
        run.config_snapshot = {
            "params": bot_params,
            "instance_config": json.loads(cfg.model_dump_json()),
        }
        bot = await session.get(BotInstance, bot_id)
        bot.equity = engine.equity_at(bars[-1].close)
        bot.realized_pnl = summary.net_pnl
        bot.max_drawdown_pct = summary.max_drawdown_pct


def _position_for(engine: PaperEngine, symbol: str):
    for p in engine.positions():
        if p.symbol == symbol:
            return p
    return None


def _should_log(action) -> bool:
    return type(action).__name__ != "Hold"


def _build_snapshot(ctx: InMemoryContext, symbol: str, tf: str, features: dict) -> dict:
    bars = ctx.history(symbol, tf, 64)
    return {
        "bars": [
            {
                "ts": b.ts.isoformat(),
                "open": b.open,
                "high": b.high,
                "low": b.low,
                "close": b.close,
                "volume": b.volume,
            }
            for b in bars
        ],
        "features": features,
    }


async def schedule_backtest(
    bot_instance_id: int,
    from_ts: datetime,
    to_ts: datetime,
) -> int:
    """Создаёт Run в pending и возвращает его id; вызов запуска — отдельно."""
    async with session_scope() as session:
        run = Run(
            bot_instance_id=bot_instance_id,
            from_ts=from_ts,
            to_ts=to_ts,
            status=RunStatus.pending,
            progress=0.0,
            config_snapshot={},
            metrics={},
        )
        session.add(run)
        await session.flush()
        return run.id
