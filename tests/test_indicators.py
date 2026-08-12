from pathlib import Path

import pandas as pd
import pytest

from assl.config import AlgorithmConfig
from assl.signals.indicators import add_indicators, crossed_up, strengthening_intervals

FIXTURE = Path(__file__).parent / "fixtures" / "indicator_bars.csv"


def test_indicator_fixture_matches_frozen_values():
    frame = pd.read_csv(FIXTURE, parse_dates=["date"])

    out = add_indicators(frame, AlgorithmConfig.macd_v1())

    last = out.iloc[-1]
    assert last["dif"] == pytest.approx(1.375945386735, abs=1e-6)
    assert last["dea"] == pytest.approx(1.390098704449, abs=1e-6)
    assert last["macd_hist"] == pytest.approx(-0.028306635428, abs=1e-6)
    assert last["ma20"] == pytest.approx(113.9, abs=1e-6)
    assert last["ma30"] == pytest.approx(112.89, abs=1e-6)
    assert last["ma60"] == pytest.approx(109.895, abs=1e-6)
    assert last["volume_ratio_5_20"] == pytest.approx(1.0, abs=1e-6)


def test_constant_close_has_zero_macd():
    frame = pd.DataFrame({"close": [10.0] * 80, "volume": [1000.0] * 80})

    out = add_indicators(frame, AlgorithmConfig.macd_v1())

    assert out[["dif", "dea", "macd_hist"]].to_numpy().max() == 0
    assert out[["dif", "dea", "macd_hist"]].to_numpy().min() == 0


def test_crossed_up_requires_previous_and_current_points():
    assert crossed_up(pd.Series([1.0]), pd.Series([0.0]), lookback=3) == ()
    assert crossed_up(
        pd.Series([-1.0, 1.0, 2.0]),
        pd.Series([0.0, 0.0, 0.0]),
        lookback=3,
    ) == (1,)


def test_strengthening_intervals_caps_at_three():
    assert strengthening_intervals(pd.Series([-5, -4, -3, -2, -1]), maximum=3) == 3
    assert strengthening_intervals(pd.Series([1, 2, 1]), maximum=3) == 0
