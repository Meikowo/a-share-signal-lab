from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from assl.domain import Grade
from assl.outcomes import detect_signal_exit, evaluate_signal_exit
from tests.test_outcomes_fixed import benchmark_bars, stock_bars
from tests.test_ranking import make_signal


@pytest.mark.parametrize(
    ("reason", "expected_price"),
    [
        ("below_ma20_1_5pct", Decimal("10.200000")),
        ("gap_expanded_two_days", Decimal("10.200000")),
        ("top_divergence", Decimal("10.200000")),
    ],
)
def test_signal_exit_executes_next_open(reason, expected_price):
    frame, top_dates = indicators_for_trigger(reason)

    outcome = evaluate_signal_exit(
        make_signal("600000", Grade.B_PLUS, priority=1),
        stock_bars(),
        frame,
        benchmark_bars(),
        top_divergence_dates=top_dates,
    )

    assert outcome is not None
    assert outcome.exit_reason == reason
    assert outcome.detection_date == date(2026, 8, 13)
    assert outcome.exit_date == date(2026, 8, 14)
    assert outcome.exit_price == expected_price


def test_detection_never_exits_at_same_close():
    frame, top_dates = indicators_for_trigger("below_ma20_1_5pct")

    outcome = evaluate_signal_exit(
        make_signal("600000", Grade.B_PLUS, priority=1),
        stock_bars(),
        frame,
        benchmark_bars(),
        top_divergence_dates=top_dates,
    )

    assert outcome.detection_date < outcome.exit_date


def test_trigger_priority_prefers_price_break():
    frame, _ = indicators_for_trigger("below_ma20_1_5pct")
    frame["gap"] = [0.1, 0.2, 0.3]

    trigger = detect_signal_exit(frame, {date(2026, 8, 13)})

    assert trigger.reason == "below_ma20_1_5pct"


def indicators_for_trigger(reason):
    frame = pd.DataFrame(
        {
            "date": [date(2026, 8, 11), date(2026, 8, 12), date(2026, 8, 13)],
            "close": [10.5, 10.4, 10.3],
            "ma20": [10.0, 10.0, 10.0],
            "gap": [0.3, 0.2, 0.1],
        }
    )
    top_dates = set()
    if reason == "below_ma20_1_5pct":
        frame.loc[2, "close"] = 9.8
    elif reason == "gap_expanded_two_days":
        frame["gap"] = [0.1, 0.2, 0.3]
    else:
        top_dates.add(date(2026, 8, 13))
    return frame, top_dates
