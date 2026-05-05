# Writing your own bot

Strategies live in this directory. Drop a Python file here, inherit from
`BaseBot`, and the platform picks it up automatically. The hot-reloader watches
this folder, so most of the time you don't need to restart anything.

## Quickstart

```bash
uv run python -m app new-bot MyStrategy
```

That generates `bots/my_strategy.py` with a working EMA-crossover skeleton.
Open the file, edit the indicator logic, save — the new bot appears in
`http://localhost:8000/bots/new`.

## Contracts

Everything you need is in `app/trading/base_bot.py`. The platform guarantees:

- `on_bar` is called only on **closed** candles (Bybit `confirm=true`).
- Your bot **never** makes network calls or writes to the DB. Returning actions
  is enough — the platform applies them through the simulator and persists
  results.
- Every action is filtered by the user's **InstanceConfig**: position sizing,
  allowed sides, cooldowns, slippage. You can ask for whatever you want; the
  platform may reject it.
- An exception in `on_bar`/`on_tick` is captured into `Signal.error` and shown
  in the UI. The bot keeps running on the next bar.

### Types you receive

```python
@dataclass(frozen=True)
class Bar:
    ts: datetime; symbol: str; timeframe: str
    open: float; high: float; low: float; close: float; volume: float

@dataclass(frozen=True)
class Position:
    symbol: str
    side: Literal["long", "short"]
    qty: float; avg_price: float; leverage: float
    unrealized_pnl: float
    liquidation_price: float | None
```

### Types you return

`on_bar` returns a list of actions. The variants are:

- `PlaceOrder(side, qty=None, type=OrderType.MARKET, price=None, stop_loss=None, take_profit=None, tag=None)`
  - `qty=None` → platform sizes from `InstanceConfig.risk_per_trade`.
  - `type=OrderType.LIMIT` requires `price`.
- `CancelOrder(order_id)`
- `ClosePosition(symbol=None)` — `None` means the bot's current position.
- `Hold()` — no-op, useful for explicit "I considered this bar".

### `BotContext`

Passed in `__init__`. Read-only window into the platform:

```python
ctx.history(symbol, tf, n) -> list[Bar]    # last n closed bars
ctx.position(symbol=None) -> Position | None
ctx.open_orders(symbol=None) -> list[OpenOrder]
ctx.balance() -> float
ctx.now() -> datetime                      # current bar's close ts
ctx.log(level, msg, **kw) -> None
```

## `params_schema`

Pydantic schema → automatic UI form. Field types become widgets:

| Pydantic                | Widget                |
|-------------------------|-----------------------|
| `int` / `float`         | number input          |
| `bool`                  | checkbox              |
| `Enum` (or `StrEnum`)   | select                |
| `Literal[...]`          | (treated as `str`)    |
| `BaseModel` (nested)    | nested fieldset       |

Use `Field(ge=, le=, description=)` to surface bounds and tooltips.

```python
class MyParams(BaseModel):
    fast: int = Field(default=12, ge=2, le=200, description="Fast EMA")
    use_volume: bool = Field(default=False)
```

## Indicators

`app/trading/indicators.py` ships with `sma`, `ema`, `rsi`, `atr`, `macd`,
`bollinger`. They take and return `numpy` arrays — feed them `np.array([b.close
for b in ctx.history(...)])`.

Want something custom? Compute it inline. Don't reach for global mutable state
— keep all state on `self`.

## `features()` and `reasoning()`

Both are optional. They feed the **snapshot** export used to train models:

- `features()` returns a flat `dict[str, float]` of indicator values that drove
  this bar's decision. They become `f_<key>` columns in `snapshots.parquet`.
- `reasoning()` returns a short human string for the signals table — useful
  for visual review.

## InstanceConfig vs BotParams

| Where                | What                                              |
|----------------------|---------------------------------------------------|
| `params_schema`      | What you compute (indicator periods, thresholds)  |
| `InstanceConfig`     | How the user trades (risk %, leverage, stops, TF) |

You never pick `risk_per_trade` or `leverage` for the user. Read positions and
balance from `ctx`; let the platform translate your intent into actual sizing.

## Best practices

- Keep all state on `self` (don't use module globals).
- No `time.sleep`, no network calls, no file I/O in `on_bar`.
- Don't mutate `Bar` or `Position` — they're frozen.
- `on_bar` should be **idempotent** for a given history — re-running on the
  same window must produce the same actions.
- Long compute (heavy ML inference) — fine for backtest, but live bars on
  small TFs need ms-level latency.

## Common mistakes

- Forgot `params_schema` → registry skips your class.
- Returned `PlaceOrder(type=OrderType.LIMIT)` without `price` → simulator
  rejects the order.
- Used `bar.timeframe` as if it's an int — it's the string like `"5m"`.
- Pulled `ctx.history(...)` and got fewer bars than expected on live start —
  the warm-up only loads ~200 closed bars.

## Testing

```python
from datetime import datetime, timezone
from app.trading.context import InMemoryContext
from app.trading.base_bot import Bar
from bots.ema_crossover import EMACrossover, EMACrossoverParams

ctx = InMemoryContext()
bot = EMACrossover(EMACrossoverParams(fast=3, slow=5), ctx)

for i, close in enumerate([10, 11, 12, 13, 14, 15, 14, 13, 12, 11]):
    bar = Bar(
        ts=datetime(2026, 1, 1, i, tzinfo=timezone.utc),
        symbol="BTCUSDT", timeframe="1h",
        open=close, high=close, low=close, close=close, volume=1.0,
    )
    ctx.push_bar(bar)
    ctx.set_now(bar.ts)
    print(bot.on_bar(bar))
```

Run the platform's own tests:

```bash
uv run pytest
```
