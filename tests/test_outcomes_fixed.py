from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from assl.domain import Bar, Grade
from assl.outcomes import (
    OutcomeCandidateRef,
    evaluate_fixed_horizon,
    evaluate_fixed_horizon_ref,
    matured_horizons,
)
from tests.test_ranking import make_signal


def test_fixed_horizon_uses_t_plus_1_open_and_close():
    outcome = evaluate_fixed_horizon(
        make_signal("600000", Grade.B_PLUS, priority=1),
        stock_bars(),
        benchmark_bars(),
        horizon=1,
    )

    assert outcome is not None
    assert outcome.entry_date == date(2026, 8, 12)
    assert outcome.entry_price == Decimal("10.000000")
    assert outcome.exit_date == date(2026, 8, 12)
    assert outcome.exit_price == Decimal("10.500000")
    assert outcome.gross_return == Decimal("0.050000")
    assert outcome.net_return == Decimal("0.047902")


def test_missing_t_plus_1_open_is_not_fabricated():
    bars = tuple(bar for bar in stock_bars() if bar.trade_date != date(2026, 8, 12))

    assert (
        evaluate_fixed_horizon(
            make_signal("600000", Grade.B_PLUS, priority=1),
            bars,
            benchmark_bars(),
            horizon=1,
        )
        is None
    )


def test_matured_horizons_follow_completed_sessions():
    signal_date = date(2026, 8, 11)

    assert matured_horizons(signal_date, stock_bars()) == (1, 5)


def test_five_day_outcome_includes_benchmark_mfe_and_mae():
    outcome = evaluate_fixed_horizon(
        make_signal("600000", Grade.B_PLUS, priority=1),
        stock_bars(),
        benchmark_bars(),
        horizon=5,
    )

    assert outcome is not None
    assert outcome.exit_date == date(2026, 8, 18)
    assert outcome.benchmark_return is not None
    assert outcome.excess_return == outcome.net_return - outcome.benchmark_return
    assert outcome.mfe > 0
    assert outcome.mae < 0


def test_fixed_horizon_can_evaluate_persisted_candidate_reference():
    reference = OutcomeCandidateRef(
        run_id=UUID("00000000-0000-0000-0000-000000000123"),
        symbol="600000",
        signal_date=date(2026, 8, 11),
    )

    outcome = evaluate_fixed_horizon_ref(
        reference,
        stock_bars(),
        benchmark_bars(),
        horizon=5,
    )

    assert outcome is not None
    assert outcome.run_id == reference.run_id
    assert outcome.symbol == reference.symbol
    assert outcome.horizon_days == 5


def stock_bars():
    dates = [
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 14),
        date(2026, 8, 17),
        date(2026, 8, 18),
    ]
    return tuple(
        Bar("600000", day, 10 + index * 0.1, 11 + index * 0.1, 9.5, 10.5 + index * 0.1, 1000)
        for index, day in enumerate(dates)
    )


def benchmark_bars():
    start = date(2026, 8, 12)
    days = [
        start + timedelta(days=index)
        for index in range(7)
        if (start + timedelta(days=index)).weekday() < 5
    ]
    return tuple(
        Bar("000300", day, 100 + index, 102 + index, 99 + index, 101 + index, 1000)
        for index, day in enumerate(days)
    )
