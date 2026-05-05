"""Live paper-trading engine: shared WebSocket → bot.on_bar → PaperEngine."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.bybit.history import load_history
from app.bybit.ws import get_ws
from app.db import session_scope
from app.models.bot import BotInstance, BotStatus
from app.models.equity import EquityPoint
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


class LiveBotRunner:
    """Один инстанс бота в режиме live paper-trading."""

    def __init__(self, bot_instance_id: int) -> None:
        self.bot_instance_id = bot_instance_id
        self._engine: PaperEngine | None = None
        self._ctx: InMemoryContext | None = None
        self._bot = None
        self._symbol = ""
        self._tf = ""
        self._prev_bar: Bar | None = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        async with session_scope() as session:
            inst = await session.get(BotInstance, self.bot_instance_id)
            if inst is None:
                raise RuntimeError(f"bot {self.bot_instance_id} not found")
            entry = registry.get(inst.strategy)
            if entry is None:
                raise RuntimeError(f"strategy {inst.strategy} not found")
            cfg = InstanceConfig.model_validate(inst.instance_config or {})
            params = entry.params_schema.model_validate(inst.bot_params or {})
            self._symbol = inst.symbol
            self._tf = inst.primary_tf
            inst.status = BotStatus.live
            inst.last_error = None

        self._ctx = InMemoryContext(history_size=500)
        self._ctx.set_balance(cfg.initial_balance_usdt)
        self._engine = PaperEngine(cfg, bot_instance_id=self.bot_instance_id, run_id=None)
        self._bot = entry.cls(params=params, ctx=self._ctx)

        # warm up history (last 200 closed bars)
        end = datetime.now(timezone.utc)
        from app.bybit.client import TF_TO_MS
        warm_ms = TF_TO_MS[self._tf] * 200
        start = end.fromtimestamp((end.timestamp() * 1000 - warm_ms) / 1000.0, tz=timezone.utc)
        bars = await load_history(self._symbol, self._tf, start, end)
        for b in bars:
            self._ctx.push_bar(b)
        if bars:
            self._prev_bar = bars[-1]

        ws = get_ws()
        await ws.start()
        await ws.subscribe_kline(self._symbol, self._tf, self._on_bar)

    async def _on_bar(self, bar: Bar) -> None:
        if self._engine is None or self._bot is None or self._ctx is None:
            return
        async with self._lock:
            self._ctx.set_now(bar.ts)
            self._ctx.push_bar(bar)
            self._ctx.set_balance(self._engine.balance)

            prev = self._prev_bar or bar
            try:
                actions = self._bot.on_bar(prev)
            except Exception as e:  # noqa: BLE001
                await self._record_error(prev, e)
                self._prev_bar = bar
                return

            try:
                features = self._bot.features() or {}
                reasoning = self._bot.reasoning(actions)
            except Exception:  # noqa: BLE001
                features, reasoning = {}, ""

            self._engine.apply(prev, bar, actions)
            await self._persist(prev, bar, actions, features, reasoning)
            self._prev_bar = bar

    async def _record_error(self, bar: Bar, e: Exception) -> None:
        async with session_scope() as session:
            session.add(
                Signal(
                    bot_instance_id=self.bot_instance_id,
                    run_id=None,
                    ts=bar.ts,
                    symbol=bar.symbol,
                    timeframe=bar.timeframe,
                    bar_close=bar.close,
                    actions=[],
                    features={},
                    reasoning="",
                    snapshot=None,
                    error=f"{type(e).__name__}: {e}",
                )
            )
            inst = await session.get(BotInstance, self.bot_instance_id)
            if inst is not None:
                inst.last_error = f"{type(e).__name__}: {e}"

    async def _persist(
        self, prev: Bar, cur: Bar, actions, features: dict, reasoning: str
    ) -> None:
        async with session_scope() as session:
            for trade in self._engine.drain_trades():
                session.add(
                    Trade(
                        bot_instance_id=trade.bot_instance_id,
                        run_id=None,
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
            for ts, balance, equity, dd in self._engine.drain_equity():
                session.add(
                    EquityPoint(
                        bot_instance_id=self.bot_instance_id,
                        run_id=None,
                        ts=ts,
                        balance=balance,
                        equity=equity,
                        drawdown_pct=dd,
                    )
                )
            non_hold = [a for a in actions if type(a).__name__ != "Hold"]
            if non_hold:
                session.add(
                    Signal(
                        bot_instance_id=self.bot_instance_id,
                        run_id=None,
                        ts=prev.ts,
                        symbol=prev.symbol,
                        timeframe=prev.timeframe,
                        bar_close=prev.close,
                        actions=[_action_to_dict(a) for a in actions],
                        features=features,
                        reasoning=reasoning or "",
                        snapshot={"features": features},
                    )
                )
            inst = await session.get(BotInstance, self.bot_instance_id)
            if inst is not None:
                inst.balance = self._engine.balance
                inst.equity = self._engine.equity_at(cur.close)
                inst.realized_pnl = self._engine.summary().net_pnl
                inst.max_drawdown_pct = self._engine.summary().max_drawdown_pct


class LiveSupervisor:
    """Глобальный супервайзер живых ботов."""

    def __init__(self) -> None:
        self._runners: dict[int, LiveBotRunner] = {}

    async def start(self, bot_instance_id: int) -> None:
        if bot_instance_id in self._runners:
            return
        runner = LiveBotRunner(bot_instance_id)
        self._runners[bot_instance_id] = runner
        try:
            await runner.start()
        except Exception:
            self._runners.pop(bot_instance_id, None)
            raise

    async def stop(self, bot_instance_id: int) -> None:
        self._runners.pop(bot_instance_id, None)
        async with session_scope() as session:
            inst = await session.get(BotInstance, bot_instance_id)
            if inst is not None and inst.status == BotStatus.live:
                inst.status = BotStatus.idle

    def is_running(self, bot_instance_id: int) -> bool:
        return bot_instance_id in self._runners


supervisor = LiveSupervisor()
