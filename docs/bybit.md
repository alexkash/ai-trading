# Bybit integration

The platform talks only to **Bybit V5 USDT Perpetuals** (linear category).

## REST endpoints used

| Endpoint                              | Used by                         |
|---------------------------------------|---------------------------------|
| `GET /v5/market/kline`                | `app/bybit/history.py` (backfill cache) |
| `GET /v5/market/funding/history`      | Funding data for backtests      |

Pagination: 1000 bars per page; loader fans out up to `history_concurrency`
(default 4) parallel requests covering missing windows. Results are stored in
the `candles` table keyed by `(symbol, timeframe, ts)`.

## WebSocket

Single shared client (`app/bybit/ws.py`) connects to
`wss://stream.bybit.com/v5/public/linear`. Live bots subscribe to:

- `kline.{interval}.{symbol}` — only `confirm=true` events drive `on_bar`.

The pybit callback runs on a worker thread; the platform hops back to the
asyncio loop with `loop.call_soon_threadsafe(...)` before dispatching to bot
handlers.

## Timeframes

```
1m 3m 5m 15m 30m 1h 2h 4h 6h 12h 1d 1w
```

Mapping is in `TF_TO_BYBIT` / `TF_TO_MS` (`app/bybit/client.py`).

## Authentication

Not needed for v1: paper trading uses public market data only. Live trading
with real money is **not** wired up.
