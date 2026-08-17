from __future__ import annotations

import math

import pandas as pd

from assl.config import AlgorithmConfig
from assl.domain import Grade, Instrument, SignalChannel, StockSignal
from assl.signals.divergence import find_divergence
from assl.signals.indicators import crossed_up
from assl.signals.predictive import evaluate_prediction


def choose_grade(
    bottom_divergence: bool,
    confirmed_cross: bool,
    prediction_tier: str | None,
    extra_confirmations: int,
) -> Grade:
    if bottom_divergence and confirmed_cross:
        return Grade.STRONG_S if extra_confirmations >= 2 else Grade.S
    if bottom_divergence and prediction_tier == "P1":
        return Grade.A_PLUS
    if bottom_divergence and prediction_tier == "P2":
        return Grade.A
    if bottom_divergence:
        return Grade.A
    if confirmed_cross:
        return Grade.B_PLUS
    if prediction_tier in {"P1", "P2"}:
        return Grade.B
    return Grade.UNRATED


def classify_stock(
    instrument: Instrument,
    frame: pd.DataFrame,
    fundamental_priority: int,
    config: AlgorithmConfig,
) -> StockSignal:
    required = {
        "date",
        "high",
        "low",
        "close",
        "dif",
        "dea",
        "macd_hist",
        "ema_fast",
        "ema_slow",
        "ma20",
        "ma30",
        "ma60",
        "volume_ratio_5_20",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"classification frame is missing columns: {sorted(missing)}")
    if len(frame) < max(config.ma_windows):
        raise ValueError("classification requires at least 60 daily bars")

    bottom = find_divergence(frame, "bottom", lookback=60)
    top = find_divergence(frame, "top", lookback=60)
    bottom_confirmed = bool(bottom and _divergence_has_repair(frame, bottom.second_index))
    top_recent = bool(top and top.second_index >= len(frame) - 12)

    cross_positions = crossed_up(frame["dif"], frame["dea"], lookback=3)
    confirmed_cross = bool(cross_positions)
    zero_cross = bool(
        crossed_up(frame["dif"], pd.Series(0.0, index=frame.index), lookback=5)
    )
    last = frame.iloc[-1]
    close = float(last["close"])
    dif = float(last["dif"])
    dea = float(last["dea"])
    hist = float(last["macd_hist"])
    ma20 = float(last["ma20"])
    ma30 = float(last["ma30"])
    ma60 = float(last["ma60"])
    volume_ratio = float(last["volume_ratio_5_20"])
    above_all_mas = close >= max(ma20, ma30, ma60)
    extras = sum((zero_cross or dif >= 0, above_all_mas, volume_ratio >= 1.0))

    prediction = None
    if dif < dea:
        prediction = evaluate_prediction(frame, top_divergence_risk=top_recent)
    prediction_tier = prediction.tier if prediction else None
    grade = choose_grade(
        bottom_confirmed,
        confirmed_cross,
        prediction_tier,
        extras,
    )

    if confirmed_cross:
        channel = SignalChannel.CONFIRMED_TREND
        signal_index = cross_positions[-1]
        reason = "近3个交易日确认MACD金叉"
    elif bottom_confirmed:
        channel = SignalChannel.BOTTOM_DIVERGENCE
        signal_index = bottom.second_index
        reason = "已确认底背离并出现指标修复"
    elif prediction_tier:
        channel = SignalChannel.PREDICTIVE_CROSS
        signal_index = len(frame) - 1
        reason = f"{prediction_tier}条件性潜在金叉"
    else:
        channel = SignalChannel.NEUTRAL
        signal_index = len(frame) - 1
        reason = "当前无正向MACD候选信号"

    if bottom_confirmed and confirmed_cross:
        reason = "已确认底背离与近3日MACD金叉共振"
    elif bottom_confirmed and prediction_tier:
        reason = f"已确认底背离与{prediction_tier}潜在金叉共振"

    dates = pd.to_datetime(frame["date"])
    as_of_date = dates.iloc[-1].date()
    signal_date = dates.iloc[signal_index].date()
    histogram_improvement = hist - float(frame["macd_hist"].iloc[-2])
    ma_structure_score = _ma_structure_score(frame, close, ma20, ma30, ma60)
    close_vs_ma20 = close / ma20 - 1.0
    close_vs_ma30 = close / ma30 - 1.0
    close_vs_ma60 = close / ma60 - 1.0
    risk = "近期已确认顶背离，仅列风险观察" if top_recent else None
    if prediction and prediction.invalidation_reasons and not prediction_tier:
        detail = ",".join(prediction.invalidation_reasons)
        risk = f"预测金叉未满足: {detail}" if risk is None else f"{risk}; {detail}"

    return StockSignal(
        instrument=instrument,
        as_of_date=as_of_date,
        signal_date=signal_date,
        channel=channel,
        grade=grade,
        public_bucket=None,
        prediction_tier=prediction_tier,
        fundamental_priority=fundamental_priority,
        dif=dif,
        dea=dea,
        macd_hist=hist,
        gap=dea - dif,
        convergence_speed=prediction.convergence_speed if prediction else None,
        x1=prediction.x1 if prediction else None,
        x1_change_pct=prediction.x1_change_pct if prediction else None,
        projected_days=(
            _finite_or_none(prediction.projected_days) if prediction else None
        ),
        ma20=ma20,
        ma30=ma30,
        ma60=ma60,
        close_vs_ma20=close_vs_ma20,
        close_vs_ma30=close_vs_ma30,
        close_vs_ma60=close_vs_ma60,
        volume_ratio_5_20=volume_ratio,
        bottom_divergence=bottom_confirmed,
        top_divergence=top_recent,
        signal_age_days=len(frame) - 1 - signal_index,
        dif_above_zero=dif >= 0,
        histogram_improvement=histogram_improvement,
        ma_structure_score=ma_structure_score,
        volume_score=volume_ratio,
        risk_score=1.0 if top_recent else 0.0,
        reason=reason,
        confirm_price=prediction.x1 if prediction_tier else close,
        invalidation_price=ma20 * 0.985,
        risk=risk,
    )


def _divergence_has_repair(frame: pd.DataFrame, second_index: int) -> bool:
    if second_index >= len(frame) - 1:
        return False
    later = frame.iloc[second_index + 1 :]
    return bool(
        (later["dif"] > float(frame["dif"].iloc[second_index])).any()
        or (later["macd_hist"] > float(frame["macd_hist"].iloc[second_index])).any()
    )


def _ma_structure_score(
    frame: pd.DataFrame,
    close: float,
    ma20: float,
    ma30: float,
    ma60: float,
) -> float:
    if not all(math.isfinite(value) and value > 0 for value in (ma20, ma30, ma60)):
        return -math.inf
    score = sum(close >= value for value in (ma20, ma30, ma60)) / 3.0
    score += 0.5 if ma20 >= ma30 >= ma60 else 0.0
    score += 0.25 if ma20 >= float(frame["ma20"].iloc[-3]) else 0.0
    return score


def _finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None
