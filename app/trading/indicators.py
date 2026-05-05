"""Technical indicators usable inside bots.

All functions accept and return ``numpy`` arrays so they can be combined cheaply.
"""

from __future__ import annotations

import numpy as np


def sma(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) < period:
        return np.full_like(values, np.nan, dtype=float)
    weights = np.ones(period) / period
    out = np.convolve(values, weights, mode="valid")
    return np.concatenate([np.full(period - 1, np.nan), out])


def ema(values: np.ndarray, period: int) -> np.ndarray:
    if len(values) == 0:
        return values.astype(float)
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    out[: period - 1] = np.nan
    return out


def rsi(values: np.ndarray, period: int = 14) -> np.ndarray:
    if len(values) <= period:
        return np.full_like(values, np.nan, dtype=float)
    delta = np.diff(values, prepend=values[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.zeros_like(values, dtype=float)
    avg_loss = np.zeros_like(values, dtype=float)
    avg_gain[period] = gain[1 : period + 1].mean()
    avg_loss[period] = loss[1 : period + 1].mean()
    for i in range(period + 1, len(values)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.inf), where=avg_loss != 0)
    out = 100.0 - 100.0 / (1.0 + rs)
    out[:period] = np.nan
    return out


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    if len(close) < 2:
        return np.full_like(close, np.nan, dtype=float)
    prev_close = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum.reduce([high - low, np.abs(high - prev_close), np.abs(low - prev_close)])
    return ema(tr, period)


def macd(
    values: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    macd_line = ema(values, fast) - ema(values, slow)
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def bollinger(
    values: np.ndarray, period: int = 20, std: float = 2.0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    mid = sma(values, period)
    out_std = np.full_like(values, np.nan, dtype=float)
    for i in range(period - 1, len(values)):
        out_std[i] = values[i - period + 1 : i + 1].std()
    return mid - std * out_std, mid, mid + std * out_std
