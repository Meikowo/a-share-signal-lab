from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import replace

from assl.domain import Grade, PublicBucket, RankedScreen, SignalChannel, StockSignal

GRADE_ORDER = {
    Grade.STRONG_S: 0,
    Grade.S: 1,
    Grade.A_PLUS: 2,
    Grade.A: 3,
    Grade.B_PLUS: 4,
    Grade.B: 5,
    Grade.UNRATED: 6,
}


def rank_screen(
    signals: Sequence[StockSignal],
    limit: int = 10,
    risk_limit: int = 5,
) -> RankedScreen:
    if limit < 1 or risk_limit < 1:
        raise ValueError("ranking limits must be positive")
    symbols = [signal.instrument.symbol for signal in signals]
    if len(symbols) != len(set(symbols)):
        raise ValueError("ranking input contains duplicate symbols")

    positive = sorted(
        (
            signal
            for signal in signals
            if not signal.top_divergence
            and signal.channel is not SignalChannel.NEUTRAL
            and signal.grade is not Grade.UNRATED
        ),
        key=_sort_key,
    )
    risky = sorted(
        (signal for signal in signals if signal.top_divergence),
        key=_sort_key,
    )

    top10 = tuple(
        replace(signal, public_bucket=PublicBucket.TOP10)
        for signal in positive[:limit]
    )
    selected = {signal.instrument.symbol for signal in top10}
    remaining = [
        signal for signal in positive if signal.instrument.symbol not in selected
    ]
    p1 = tuple(
        replace(signal, public_bucket=PublicBucket.P1)
        for signal in remaining
        if signal.prediction_tier == "P1"
    )
    p1_symbols = {signal.instrument.symbol for signal in p1}
    p2 = tuple(
        replace(signal, public_bucket=PublicBucket.P2)
        for signal in remaining
        if signal.prediction_tier == "P2"
        and signal.instrument.symbol not in p1_symbols
    )
    risk_watch = tuple(
        replace(signal, public_bucket=PublicBucket.RISK_WATCH)
        for signal in risky[:risk_limit]
    )
    return RankedScreen(top10=top10, p1=p1, p2=p2, risk_watch=risk_watch)


def _sort_key(signal: StockSignal) -> tuple[object, ...]:
    return (
        -signal.fundamental_priority,
        GRADE_ORDER[signal.grade],
        signal.signal_age_days,
        -int(signal.dif_above_zero),
        -_finite(signal.histogram_improvement),
        -_finite(signal.ma_structure_score),
        -_finite(signal.volume_score),
        _finite(signal.risk_score, fallback=math.inf),
        signal.instrument.symbol,
    )


def _finite(value: float, fallback: float = -math.inf) -> float:
    return value if math.isfinite(value) else fallback
