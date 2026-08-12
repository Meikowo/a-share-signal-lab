from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from assl.domain import Bar, Coverage, Instrument


class DataQualityError(ValueError):
    """Raised when OHLCV data violates a deterministic quality contract."""


def validate_bars(bars: Sequence[Bar], cutoff: date) -> tuple[Bar, ...]:
    validated = tuple(bars)
    dates = tuple(bar.trade_date for bar in validated)
    if len(dates) != len(set(dates)):
        raise DataQualityError("duplicate trade date")
    if dates != tuple(sorted(dates)):
        raise DataQualityError("trade dates must be ascending")
    if any(day > cutoff for day in dates):
        raise DataQualityError("bar exceeds completed-market cutoff")
    return validated


def calculate_coverage(
    universe: Sequence[Instrument],
    fetched: Mapping[str, Sequence[Bar]],
    source_timestamp: datetime | None,
) -> Coverage:
    symbols = tuple(item.symbol for item in universe)
    covered = {symbol for symbol in symbols if fetched.get(symbol)}
    missing = tuple(sorted(set(symbols) - covered))
    universe_count = len(symbols)
    covered_count = len(covered)
    ratio = covered_count / universe_count if universe_count else 0.0
    return Coverage(
        universe_count=universe_count,
        covered_count=covered_count,
        missing_symbols=missing,
        source_timestamp=source_timestamp,
        publishable=universe_count > 0 and ratio >= 0.98,
    )
