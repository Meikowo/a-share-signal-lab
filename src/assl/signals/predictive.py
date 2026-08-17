from __future__ import annotations

import math

import pandas as pd

from assl.domain import Prediction


def next_cross_price(*, ema_fast: float, ema_slow: float, dea: float) -> float:
    alpha_fast = 2.0 / 13.0
    alpha_slow = 2.0 / 27.0
    slope = alpha_fast - alpha_slow
    intercept = (1.0 - alpha_fast) * ema_fast - (1.0 - alpha_slow) * ema_slow
    x1 = (dea - intercept) / slope

    next_fast = alpha_fast * x1 + (1.0 - alpha_fast) * ema_fast
    next_slow = alpha_slow * x1 + (1.0 - alpha_slow) * ema_slow
    next_dif = next_fast - next_slow
    alpha_signal = 2.0 / 10.0
    next_dea = alpha_signal * next_dif + (1.0 - alpha_signal) * dea
    if not math.isclose(next_dif, next_dea, abs_tol=1e-10):
        raise ArithmeticError("next-cross inversion failed validation")
    return x1


def evaluate_prediction(
    frame: pd.DataFrame,
    top_divergence_risk: bool,
) -> Prediction:
    required = {
        "close",
        "dif",
        "dea",
        "macd_hist",
        "ema_fast",
        "ema_slow",
        "ma20",
        "volume_ratio_5_20",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"prediction frame is missing columns: {sorted(missing)}")
    if len(frame) < 3:
        raise ValueError("predictive cross requires at least three indicator rows")

    recent = frame.iloc[-3:]
    dif = recent["dif"].astype(float).tolist()
    dea = recent["dea"].astype(float).tolist()
    hist = recent["macd_hist"].astype(float).tolist()
    gaps = [dea[index] - dif[index] for index in range(3)]
    convergence_speed = ((gaps[0] - gaps[1]) + (gaps[1] - gaps[2])) / 2.0
    gap = gaps[-1]
    projected_days = gap / convergence_speed if convergence_speed > 0 else math.inf
    last = recent.iloc[-1]
    close = float(last["close"])
    x1 = next_cross_price(
        ema_fast=float(last["ema_fast"]),
        ema_slow=float(last["ema_slow"]),
        dea=float(last["dea"]),
    )
    x1_change_pct = x1 / close - 1.0

    avg_delta_dif = ((dif[1] - dif[0]) + (dif[2] - dif[1])) / 2.0
    avg_delta_dea = ((dea[1] - dea[0]) + (dea[2] - dea[1])) / 2.0
    reasons: list[str] = []
    if not (gap > 0 and gaps[2] < gaps[1] < gaps[0]):
        reasons.append("gap_not_shrinking")
    if not (hist[0] < hist[1] < hist[2] < 0):
        reasons.append("green_hist_not_shortening")
    if not dif[2] > dif[1]:
        reasons.append("dif_not_rising")
    if convergence_speed <= 0 or avg_delta_dif <= avg_delta_dea:
        reasons.append("convergence_too_slow")
    ma20 = recent["ma20"].astype(float).tolist()
    if close < ma20[-1] * 0.97:
        reasons.append("below_ma20_floor")
    if ma20[-1] < ma20[0] * 0.995:
        reasons.append("ma20_deteriorating")
    if float(last["volume_ratio_5_20"]) < 0.70:
        reasons.append("low_volume")
    if top_divergence_risk:
        reasons.append("top_divergence_risk")

    tier: str | None = None
    if not reasons:
        tolerance = max(1e-12, abs(close) * 1e-12)
        if projected_days <= 1.5 + 1e-12 and x1 <= close * 1.015 + tolerance:
            tier = "P1"
        elif projected_days <= 3.0 + 1e-12 and x1 <= close * 1.03 + tolerance:
            tier = "P2"
        else:
            reasons.append("convergence_too_slow")

    return Prediction(
        tier=tier,
        gap=gap,
        convergence_speed=convergence_speed,
        x1=x1,
        x1_change_pct=x1_change_pct,
        projected_days=projected_days,
        valid=tier is not None,
        invalidation_reasons=tuple(reasons),
    )
