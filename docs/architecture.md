# Architecture

```
+----------------------------+
|        FastAPI app         |
|   /bots, /runs, /exports   |
|        Jinja2 + HTMX       |
+--------------+-------------+
               |
   +-----------+-----------+----------------+
   |                       |                |
   v                       v                v
+--------+         +---------------+   +-----------+
| SQLite |         | LiveSupervisor |   | Backtest  |
+--------+         |  (asyncio)     |   |  task     |
                   +-------+--------+   +-----+-----+
                           |                 |
                  +--------+----+    +-------+----+
                  |   PaperEngine |  | PaperEngine |
                  +--------+------+  +------+------+
                           |                |
                           v                v
                   +---------------+  +--------------+
                   | Bot strategy  |  | Bot strategy |
                   |  (bots/*.py)  |  |  (bots/*.py) |
                   +-------+-------+  +------+-------+
                           |                 |
                           v                 v
              +--------------------------+  +-------------------+
              |  shared BybitWS (live)   |  |  candle cache     |
              |  WS kline + tickers      |  |  + REST history   |
              +--------------------------+  +-------------------+
```

Modules:

| Path                          | Responsibility                                         |
|-------------------------------|--------------------------------------------------------|
| `app/main.py`                 | FastAPI app, lifespan, mounts                          |
| `app/routers/bots.py`         | `/bots` UI, create/start/stop/backtest                 |
| `app/routers/runs.py`         | `/runs/{id}` UI, progress, equity JSON                 |
| `app/routers/exports.py`      | CSV/Parquet streaming exports                          |
| `app/trading/base_bot.py`     | Stable contracts: Bar, Tick, Action, BotContext, BaseBot |
| `app/trading/registry.py`     | Discover BaseBot subclasses in `bots/`                 |
| `app/trading/context.py`      | InMemoryContext: bar window + state for bots           |
| `app/trading/paper_engine.py` | Order simulator: fees, slippage, stops, drawdown gates |
| `app/trading/backtest_engine.py` | Sequential backtest pipeline                       |
| `app/trading/live_engine.py`  | Live runner + supervisor on shared WS                  |
| `app/bybit/client.py`         | REST V5 wrapper                                        |
| `app/bybit/history.py`        | Cached candle loader (SQLite + REST)                   |
| `app/bybit/ws.py`             | Shared V5 public WebSocket (linear)                    |
| `app/exporters/datasets.py`   | DataFrame builders for each export kind                |

The single guarantee that ties everything together: **bots only return
actions**. They never touch the DB or the network. That keeps strategy code
trivially testable (`InMemoryContext` + a list of fake bars) and lets the
platform enforce risk configuration uniformly.
