from __future__ import annotations

from itertools import combinations

import pandas as pd

from assl.domain import Divergence


def confirmed_pivots(
    series: pd.Series,
    kind: str,
    window: int = 2,
    as_of_index: int | None = None,
) -> tuple[int, ...]:
    if kind not in {"low", "high"}:
        raise ValueError("pivot kind must be 'low' or 'high'")
    if window < 1:
        raise ValueError("pivot window must be positive")
    if len(series) < window * 2 + 1:
        return ()
    cutoff = len(series) - 1 if as_of_index is None else min(as_of_index, len(series) - 1)
    last_candidate = cutoff - window
    pivots: list[int] = []
    for index in range(window, last_candidate + 1):
        center = float(series.iloc[index])
        neighbors = tuple(
            float(series.iloc[position])
            for position in range(index - window, index + window + 1)
            if position != index
        )
        is_pivot = center < min(neighbors) if kind == "low" else center > max(neighbors)
        if is_pivot:
            pivots.append(index)
    return tuple(pivots)


def find_divergence(
    frame: pd.DataFrame,
    kind: str,
    lookback: int = 60,
) -> Divergence | None:
    if kind not in {"bottom", "top"}:
        raise ValueError("divergence kind must be 'bottom' or 'top'")
    required = {"low", "high", "dif", "macd_hist"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"divergence frame is missing columns: {sorted(missing)}")
    if len(frame) < 5:
        return None

    price_column = "low" if kind == "bottom" else "high"
    pivot_kind = "low" if kind == "bottom" else "high"
    start = max(0, len(frame) - lookback)
    pivots = tuple(
        index
        for index in confirmed_pivots(frame[price_column], pivot_kind, window=2)
        if index >= start
    )
    candidates: list[tuple[int, float, Divergence]] = []
    for first, second in combinations(pivots, 2):
        separation = second - first
        if separation < 5 or separation > 30:
            continue
        first_price = float(frame[price_column].iloc[first])
        second_price = float(frame[price_column].iloc[second])
        price_valid = (
            second_price <= first_price * 1.01
            if kind == "bottom"
            else second_price >= first_price
        )
        if not price_valid:
            continue

        for indicator in ("dif", "macd_hist"):
            first_value = float(frame[indicator].iloc[first])
            second_value = float(frame[indicator].iloc[second])
            improvement = (
                second_value - first_value
                if kind == "bottom"
                else first_value - second_value
            )
            if improvement <= 0:
                continue
            candidates.append(
                (
                    second,
                    improvement,
                    Divergence(
                        kind=kind,
                        confirmed=True,
                        first_index=first,
                        second_index=second,
                        first_price=first_price,
                        second_price=second_price,
                        first_indicator=first_value,
                        second_indicator=second_value,
                    ),
                )
            )
            break

    if not candidates:
        return None
    return max(candidates, key=lambda item: (item[0], item[1]))[2]
