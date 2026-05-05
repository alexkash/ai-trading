"""Thin async wrapper over Bybit V5 REST endpoints used by the platform."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.config import settings

TF_TO_BYBIT = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "1d": "D",
    "1w": "W",
}

TF_TO_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "1w": 604_800_000,
}


class BybitREST:
    def __init__(self, base_url: str | None = None, category: str = "linear") -> None:
        self.base_url = base_url or settings.bybit_rest_url
        self.category = category
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=15.0)
        self._sem = asyncio.Semaphore(settings.history_concurrency)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_kline(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
        limit: int = 1000,
    ) -> list[list[Any]]:
        params = {
            "category": self.category,
            "symbol": symbol,
            "interval": interval,
            "start": start_ms,
            "end": end_ms,
            "limit": limit,
        }
        async with self._sem:
            r = await self._client.get("/v5/market/kline", params=params)
            r.raise_for_status()
            data = r.json()
        if data.get("retCode") != 0:
            raise RuntimeError(f"bybit kline error: {data.get('retMsg')}")
        return data.get("result", {}).get("list", [])

    async def get_funding_history(
        self, symbol: str, start_ms: int, end_ms: int, limit: int = 200
    ) -> list[dict[str, Any]]:
        params = {
            "category": self.category,
            "symbol": symbol,
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": limit,
        }
        async with self._sem:
            r = await self._client.get("/v5/market/funding/history", params=params)
            r.raise_for_status()
            data = r.json()
        return data.get("result", {}).get("list", [])
