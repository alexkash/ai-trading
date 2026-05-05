# AI Trading

Local platform for paper-trading bots on Bybit USDT Perpetuals.

- Live paper trading on the real Bybit WebSocket feed
- Backtest on historical candles (cached in SQLite)
- Modular bots — drop a `.py` in `bots/` (auto-discovered, hot-reloaded)
- Per-instance risk config (capital, leverage, stops, slippage, …)
- HTMX UI with live equity charts
- CSV/Parquet exports of trades, equity, signals, snapshots and candles

## Quickstart

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Open <http://localhost:8000>.

Generate a strategy skeleton:

```bash
uv run python -m app new-bot MyStrategy
# edit bots/my_strategy.py
```

Run a backtest from the CLI:

```bash
uv run python -m app backtest --bot-id 1 --from 2026-04-01 --to 2026-05-01
```

## Documentation

- [Writing bots](bots/README.md) — the only thing strategy authors must read
- [Architecture](docs/architecture.md)
- [Instance config reference](docs/instance_config.md)
- [Exports schema](docs/exports.md)
- [Bybit integration](docs/bybit.md)
- [Development](docs/development.md)
