from __future__ import annotations

import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path

import typer

from app.config import BOTS_DIR

cli = typer.Typer(help="AI Trading CLI")


_TEMPLATE = '''"""{class_name} — describe what your strategy does in one sentence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.trading.base_bot import (
    Action,
    Bar,
    BaseBot,
    Hold,
    OrderType,
    PlaceOrder,
    Side,
)
from app.trading.indicators import ema


class {class_name}Params(BaseModel):
    fast: int = Field(default=10, ge=1, le=500, description="Fast EMA period")
    slow: int = Field(default=30, ge=2, le=1000, description="Slow EMA period")


class {class_name}(BaseBot):
    name = "{class_name}"
    description = "Edit me — short description shown in the UI."
    params_schema = {class_name}Params

    def __init__(self, params, ctx):
        super().__init__(params, ctx)
        self._last_signal: str = ""

    def on_bar(self, bar: Bar) -> list[Action]:
        history = self.ctx.history(bar.symbol, bar.timeframe, max(self.params.slow + 5, 50))
        if len(history) < self.params.slow + 1:
            return [Hold()]

        import numpy as np
        closes = np.array([b.close for b in history], dtype=float)
        fast = ema(closes, self.params.fast)
        slow = ema(closes, self.params.slow)

        prev_diff = fast[-2] - slow[-2]
        cur_diff = fast[-1] - slow[-1]
        position = self.ctx.position(bar.symbol)

        if prev_diff <= 0 < cur_diff and position is None:
            self._last_signal = "long"
            return [PlaceOrder(side=Side.LONG, type=OrderType.MARKET, tag="ema_long")]
        if prev_diff >= 0 > cur_diff and position is None:
            self._last_signal = "short"
            return [PlaceOrder(side=Side.SHORT, type=OrderType.MARKET, tag="ema_short")]
        return [Hold()]

    def features(self) -> dict[str, float]:
        return {{}}

    def reasoning(self, actions) -> str:
        return f"signal={{self._last_signal}}"
'''


def _to_snake(name: str) -> str:
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
    return re.sub(r"[^a-z0-9_]", "_", s)


@cli.command("new-bot")
def new_bot(class_name: str = typer.Argument(..., help="ClassName for the new strategy")) -> None:
    """Generate a strategy skeleton in bots/<snake>.py."""
    if not re.match(r"^[A-Za-z][A-Za-z0-9_]*$", class_name):
        typer.echo("class_name must be a valid Python identifier (CamelCase)")
        raise typer.Exit(1)

    target = BOTS_DIR / f"{_to_snake(class_name)}.py"
    if target.exists():
        typer.echo(f"refuse to overwrite {target}")
        raise typer.Exit(1)

    BOTS_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(_TEMPLATE.format(class_name=class_name))
    typer.echo(f"created {target}")


@cli.command("backtest")
def backtest_cmd(
    bot_id: int = typer.Option(..., "--bot-id"),
    from_date: str = typer.Option(..., "--from"),
    to_date: str = typer.Option(..., "--to"),
) -> None:
    """Run a backtest synchronously and print summary."""
    from app.trading.backtest_engine import run_backtest, schedule_backtest
    from app.db import session_scope
    from app.models.run import Run
    from app.trading.registry import registry

    registry.reload()

    async def main() -> None:
        from_ts = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        to_ts = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)
        run_id = await schedule_backtest(bot_id, from_ts, to_ts)
        await run_backtest(run_id)
        async with session_scope() as session:
            run = await session.get(Run, run_id)
            typer.echo(f"run #{run_id} status={run.status} progress={run.progress:.0%}")
            typer.echo(f"metrics={run.metrics}")

    asyncio.run(main())


if __name__ == "__main__":
    cli()
