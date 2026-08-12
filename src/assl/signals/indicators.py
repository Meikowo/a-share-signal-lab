from __future__ import annotations

import math

import pandas as pd

from assl.config import AlgorithmConfig


def add_indicators(frame: pd.DataFrame, config: AlgorithmConfig) -> pd.DataFrame:
    missing = {"close", "volume"} - set(frame.columns)
    if missing:
        raise ValueError(f"indicator frame is missing columns: {sorted(missing)}")

    out = frame.copy()
    close = pd.to_numeric(out["close"], errors="raise")
    volume = pd.to_numeric(out["volume"], errors="raise")
    out["ema_fast"] = close.ewm(span=config.fast, adjust=False).mean()
    out["ema_slow"] = close.ewm(span=config.slow, adjust=False).mean()
    out["dif"] = out["ema_fast"] - out["ema_slow"]
    out["dea"] = out["dif"].ewm(span=config.signal, adjust=False).mean()
    out["macd_hist"] = 2 * (out["dif"] - out["dea"])
    for window in config.ma_windows:
        out[f"ma{window}"] = close.rolling(window=window).mean()
    out["volume_ratio_5_20"] = volume.rolling(5).mean() / volume.rolling(20).mean()
    return out


def crossed_up(a: pd.Series, b: pd.Series, lookback: int) -> tuple[int, ...]:
    if lookback < 1:
        raise ValueError("lookback must be positive")
    if len(a) != len(b):
        raise ValueError("crossing series must have equal length")
    start = max(1, len(a) - lookback)
    crossings: list[int] = []
    for index in range(start, len(a)):
        values = (a.iloc[index - 1], b.iloc[index - 1], a.iloc[index], b.iloc[index])
        if not all(math.isfinite(float(value)) for value in values):
            continue
        if a.iloc[index - 1] < b.iloc[index - 1] and a.iloc[index] >= b.iloc[index]:
            crossings.append(index)
    return tuple(crossings)


def strengthening_intervals(hist: pd.Series, maximum: int = 3) -> int:
    if maximum < 1:
        raise ValueError("maximum must be positive")
    count = 0
    for index in range(len(hist) - 1, 0, -1):
        current = float(hist.iloc[index])
        previous = float(hist.iloc[index - 1])
        if not (math.isfinite(current) and math.isfinite(previous)) or current <= previous:
            break
        count += 1
        if count == maximum:
            break
    return count
