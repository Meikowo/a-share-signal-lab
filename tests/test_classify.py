import math
from datetime import date, timedelta

import pandas as pd
import pytest

from assl.config import AlgorithmConfig
from assl.domain import Grade, Instrument, SignalChannel
from assl.signals.classify import choose_grade, classify_stock
from assl.signals.indicators import add_indicators


@pytest.mark.parametrize(
    ("bottom", "cross", "tier", "extras", "grade"),
    [
        (True, True, None, 3, Grade.STRONG_S),
        (True, True, None, 0, Grade.S),
        (True, False, "P1", 0, Grade.A_PLUS),
        (True, False, "P2", 0, Grade.A),
        (False, True, None, 0, Grade.B_PLUS),
        (False, False, "P1", 0, Grade.B),
    ],
)
def test_grade_matrix(bottom, cross, tier, extras, grade):
    assert choose_grade(bottom, cross, tier, extras) is grade


def test_classify_stock_marks_recent_confirmed_cross():
    closes = [100.0] * 70 + [99.0, 98.0, 97.0, 98.0, 100.0, 103.0]
    frame = _ohlcv_frame(closes)
    enriched = add_indicators(frame, AlgorithmConfig.macd_v1())

    signal = classify_stock(
        Instrument.from_secid("1.600000", "浦发银行"),
        enriched,
        fundamental_priority=2,
        config=AlgorithmConfig.macd_v1(),
    )

    assert signal.channel in {
        SignalChannel.CONFIRMED_TREND,
        SignalChannel.BOTTOM_DIVERGENCE,
    }
    assert signal.fundamental_priority == 2
    assert signal.as_of_date == enriched.iloc[-1]["date"]


def test_classify_stock_never_emits_nonfinite_projection():
    closes = [100.0 - index * 0.2 for index in range(80)]
    enriched = add_indicators(_ohlcv_frame(closes), AlgorithmConfig.macd_v1())
    enriched.loc[enriched.index[-3:], "dif"] = [-0.1, -0.2, -0.3]
    enriched.loc[enriched.index[-3:], "dea"] = [0.0, 0.0, 0.0]
    enriched.loc[enriched.index[-3:], "macd_hist"] = [-0.2, -0.4, -0.6]

    signal = classify_stock(
        Instrument.from_secid("1.600000", "浦发银行"),
        enriched,
        fundamental_priority=0,
        config=AlgorithmConfig.macd_v1(),
    )

    assert signal.projected_days is None or math.isfinite(signal.projected_days)


def _ohlcv_frame(closes):
    start = date(2026, 1, 1)
    return pd.DataFrame(
        {
            "date": [start + timedelta(days=index) for index in range(len(closes))],
            "open": closes,
            "high": [value + 0.5 for value in closes],
            "low": [value - 0.5 for value in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        }
    )
