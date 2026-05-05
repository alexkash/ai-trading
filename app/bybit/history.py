"""Historical candle loader with SQLite cache."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.bybit.client import TF_TO_BYBIT, TF_TO_MS, BybitREST
from app.db import session_scope
from app.models.candle import Candle
from app.trading.base_bot import Bar

log = logging.getLogger(__name__)


def _row_to_bar(symbol: str, tf: str, row: list) -> Bar:
    # Bybit kline row: [start, open, high, low, close, volume, turnover]
    ts_ms = int(row[0])
    return Bar(
        ts=datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc),
        symbol=symbol,
        timeframe=tf,
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )


async def _persist_candles(symbol: str, tf: str, bars: list[Bar]) -> None:
    if not bars:
        return
    rows = [
        {
            "symbol": b.symbol,
            "timeframe": b.timeframe,
            "ts": b.ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "turnover": 0.0,
        }
        for b in bars
    ]
    async with session_scope() as session:
        stmt = sqlite_insert(Candle).values(rows).on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "ts"]
        )
        await session.execute(stmt)


async def _load_from_cache(symbol: str, tf: str, start: datetime, end: datetime) -> list[Bar]:
    async with session_scope() as session:
        stmt = (
            select(Candle)
            .where(
                and_(
                    Candle.symbol == symbol,
                    Candle.timeframe == tf,
                    Candle.ts >= start,
                    Candle.ts <= end,
                )
            )
            .order_by(Candle.ts)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
    return [
        Bar(
            ts=r.ts.replace(tzinfo=timezone.utc) if r.ts.tzinfo is None else r.ts,
            symbol=r.symbol,
            timeframe=r.timeframe,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in rows
    ]


async def load_history(
    symbol: str, tf: str, start: datetime, end: datetime, *, refresh: bool = False
) -> list[Bar]:
    """Загружает свечи [start, end] для (symbol, tf), используя кэш SQLite.

    Если ``refresh`` или есть «дыра» в кэше — добирает свечи через REST.
    """
    if tf not in TF_TO_BYBIT:
        raise ValueError(f"unsupported timeframe: {tf}")

    interval = TF_TO_BYBIT[tf]
    step_ms = TF_TO_MS[tf]
    page_size = 1000
    page_span_ms = step_ms * page_size

    cached = [] if refresh else await _load_from_cache(symbol, tf, start, end)
    have = {b.ts for b in cached}

    expected_ts = []
    cur = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    while cur <= end_ms:
        expected_ts.append(datetime.fromtimestamp(cur / 1000.0, tz=timezone.utc))
        cur += step_ms

    missing = [ts for ts in expected_ts if ts not in have]
    if not missing:
        return sorted(cached, key=lambda b: b.ts)

    rest = BybitREST()
    try:
        ranges: list[tuple[int, int]] = []
        block_start = int(missing[0].timestamp() * 1000)
        block_end = block_start + page_span_ms
        for ts in missing[1:]:
            tms = int(ts.timestamp() * 1000)
            if tms <= block_end:
                block_end = max(block_end, tms + step_ms)
                continue
            ranges.append((block_start, block_end))
            block_start = tms
            block_end = tms + page_span_ms
        ranges.append((block_start, block_end))

        async def fetch_range(s: int, e: int) -> list[Bar]:
            out: list[Bar] = []
            cursor_start = s
            while cursor_start < e:
                page_end = min(cursor_start + page_span_ms, e)
                rows = await rest.get_kline(symbol, interval, cursor_start, page_end, page_size)
                if not rows:
                    break
                bars = [_row_to_bar(symbol, tf, r) for r in rows]
                bars.sort(key=lambda b: b.ts)
                out.extend(bars)
                # advance past last received bar
                last_ms = int(bars[-1].ts.timestamp() * 1000)
                next_start = last_ms + step_ms
                if next_start <= cursor_start:
                    break
                cursor_start = next_start
            return out

        results = await asyncio.gather(*(fetch_range(s, e) for s, e in ranges))
    finally:
        await rest.close()

    fetched: list[Bar] = []
    for chunk in results:
        fetched.extend(chunk)
    fetched = [b for b in fetched if start <= b.ts <= end]
    await _persist_candles(symbol, tf, fetched)

    merged = {b.ts: b for b in cached}
    for b in fetched:
        merged[b.ts] = b
    return sorted(merged.values(), key=lambda b: b.ts)
