# Exports

URL: `GET /exports/{scope}/{ident}/{kind}.{format}`

- `scope` ∈ `{bot, run}` — `bot` aggregates live data; `run` is one backtest.
- `kind` ∈ `{trades, equity, signals, snapshots, candles}`
- `format` ∈ `{csv, parquet}`

All timestamps are UTC.

## `trades`

| Column        | Type     | Notes                                  |
|---------------|----------|----------------------------------------|
| id            | int      |                                        |
| symbol        | str      |                                        |
| side          | str      | `long` / `short`                       |
| qty           | float    | Base coin (linear contract size).      |
| leverage      | float    |                                        |
| entry_price   | float    |                                        |
| exit_price    | float?   | Null if still open.                    |
| opened_at     | datetime |                                        |
| closed_at     | datetime?|                                        |
| fee           | float    | Sum of entry + exit fees, USDT.        |
| funding       | float    | Funding paid/received during the trade.|
| pnl           | float    | Net realized PnL, USDT.                |
| pnl_pct       | float    | `pnl / notional * 100`.                |
| exit_reason   | str?     | `take_profit` / `stop_loss` / `manual_close` / `daily_loss_limit` / ... |
| tag           | str?     | Bot-supplied tag from `PlaceOrder`.    |

## `equity`

| Column        | Type     | Notes                                                   |
|---------------|----------|---------------------------------------------------------|
| ts            | datetime | Bar close time.                                         |
| balance       | float    | Realized cash balance.                                  |
| equity        | float    | Balance + unrealized PnL of open positions.             |
| drawdown_pct  | float    | `(peak - equity) / peak * 100`.                          |

## `signals`

One row per bar where the bot returned at least one non-`Hold` action **or**
threw an exception.

| Column     | Type      | Notes                                            |
|------------|-----------|--------------------------------------------------|
| ts         | datetime  | The bar's close time.                            |
| symbol     | str       |                                                  |
| timeframe  | str       |                                                  |
| bar_close  | float     |                                                  |
| actions    | json str  | Each action serialized with its type.            |
| features   | json str  | Output of `bot.features()` at that bar.          |
| reasoning  | str       | Output of `bot.reasoning(actions)`.              |
| error      | str?      | Set if `on_bar` raised.                          |

## `snapshots`

The main artifact for ML — one row per signal, joining the **window of bars**
the bot saw with the **features** it computed and the **action** it picked.

| Column            | Type          | Notes                                                    |
|-------------------|---------------|----------------------------------------------------------|
| ts                | datetime      |                                                          |
| symbol            | str           |                                                          |
| timeframe         | str           |                                                          |
| bar_close         | float         |                                                          |
| actions           | json str      |                                                          |
| reasoning         | str           |                                                          |
| window_bars       | json str      | Last 64 closed OHLCV bars at decision time.              |
| f_<feature>       | float         | One column per key returned from `features()`.           |

Load in pandas:

```python
import pandas as pd, json
df = pd.read_parquet("snapshots.parquet")
df["window"] = df["window_bars"].map(json.loads)
```

## `candles`

Raw OHLCV history used by the run/bot. For `scope=bot` this is the entire cache
for the bot's symbol and TF; for `scope=run` it is restricted to the run's
window.
