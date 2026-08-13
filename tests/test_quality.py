from datetime import UTC, date, datetime

import pytest

from assl.domain import Bar, Instrument
from assl.market.quality import DataQualityError, calculate_coverage, validate_bars


def bar(day: int, symbol: str = "600000") -> Bar:
    return Bar(symbol, date(2026, 8, day), 10, 11, 9, 10.5, 1000)


def test_validate_bars_rejects_duplicate_date():
    with pytest.raises(DataQualityError, match="duplicate"):
        validate_bars((bar(11), bar(11)), date(2026, 8, 11))


def test_validate_bars_rejects_out_of_order_and_future_rows():
    with pytest.raises(DataQualityError, match="ascending"):
        validate_bars((bar(11), bar(10)), date(2026, 8, 11))
    with pytest.raises(DataQualityError, match="cutoff"):
        validate_bars((bar(12),), date(2026, 8, 11))


def test_coverage_uses_configured_threshold_and_records_missing_symbols():
    universe = tuple(
        Instrument.from_secid(f"0.00{index:04d}", f"股票{index}")
        for index in range(1, 101)
    )
    fetched = {item.symbol: (bar(11, item.symbol),) for item in universe[:97]}

    coverage = calculate_coverage(
        universe,
        fetched,
        source_timestamp=datetime(2026, 8, 11, 7, 1, tzinfo=UTC),
        minimum_ratio=0.98,
    )

    assert coverage.covered_count == 97
    assert coverage.missing_symbols == ("000098", "000099", "000100")
    assert coverage.publishable is False


def test_coverage_is_publishable_at_exact_threshold():
    universe = tuple(
        Instrument.from_secid(f"0.00{index:04d}", f"股票{index}")
        for index in range(1, 101)
    )
    fetched = {item.symbol: (bar(11, item.symbol),) for item in universe[:98]}

    coverage = calculate_coverage(
        universe, fetched, source_timestamp=None, minimum_ratio=0.98
    )

    assert coverage.publishable is True
