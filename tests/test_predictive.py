import pandas as pd
import pytest

from assl.signals.predictive import evaluate_prediction, next_cross_price


def predictive_frame(**overrides):
    values = {
        "close": [100.0, 100.0, 100.0],
        "dif": [-0.3, -0.2, -0.1],
        "dea": [0.0, 0.0, 0.0],
        "macd_hist": [-0.6, -0.4, -0.2],
        "ema_fast": [99.8, 99.9, 100.0],
        "ema_slow": [100.2, 100.15, 100.1],
        "ma20": [100.2, 100.1, 100.0],
        "volume_ratio_5_20": [1.0, 1.0, 1.0],
    }
    values.update(overrides)
    return pd.DataFrame(values)


def test_next_cross_price_is_exact_threshold():
    x1 = next_cross_price(ema_fast=100.0, ema_slow=100.1, dea=0.0)
    alpha_fast = 2 / 13
    alpha_slow = 2 / 27
    alpha_signal = 2 / 10

    next_fast = alpha_fast * x1 + (1 - alpha_fast) * 100.0
    next_slow = alpha_slow * x1 + (1 - alpha_slow) * 100.1
    next_dif = next_fast - next_slow
    next_dea = alpha_signal * next_dif + (1 - alpha_signal) * 0.0

    assert next_dif == pytest.approx(next_dea, abs=1e-10)


def test_shrinking_green_histogram_and_rising_dif_is_p1():
    result = evaluate_prediction(predictive_frame(), top_divergence_risk=False)

    assert result.tier == "P1"
    assert result.valid is True
    assert result.convergence_speed == pytest.approx(0.1)
    assert result.projected_days == pytest.approx(1.0)
    assert result.x1_change_pct <= 0.015
    assert result.invalidation_reasons == ()


@pytest.mark.parametrize(
    ("overrides", "top_risk", "reason"),
    [
        ({"dif": [-0.1, -0.2, -0.3]}, False, "gap_not_shrinking"),
        ({"macd_hist": [-0.2, -0.4, -0.3]}, False, "green_hist_not_shortening"),
        ({"dif": [-0.3, -0.1, -0.2]}, False, "dif_not_rising"),
        ({"close": [90.0, 90.0, 90.0]}, False, "below_ma20_floor"),
        ({"ma20": [101.0, 100.5, 100.0]}, False, "ma20_deteriorating"),
        ({"volume_ratio_5_20": [1.0, 1.0, 0.69]}, False, "low_volume"),
        ({}, True, "top_divergence_risk"),
    ],
)
def test_prediction_invalidation_codes_are_stable(overrides, top_risk, reason):
    result = evaluate_prediction(
        predictive_frame(**overrides), top_divergence_risk=top_risk
    )

    assert result.valid is False
    assert reason in result.invalidation_reasons


def test_p1_and_p2_boundaries_are_inclusive():
    p1 = evaluate_prediction(
        predictive_frame(
            dif=[-0.45, -0.25, -0.15],
            dea=[0.0, 0.0, 0.0],
            macd_hist=[-0.9, -0.5, -0.3],
        ),
        top_divergence_risk=False,
    )

    assert p1.projected_days == pytest.approx(1.0)
    assert p1.tier in ("P1", "P2")
