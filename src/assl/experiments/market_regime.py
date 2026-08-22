from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import fmean, median, pstdev
from typing import Any

from assl.domain import Bar, MarketTurnover

EXPERIMENT_VERSION = "market-regime-v1.1"
BENCHMARK_SYMBOL = "000300"
SAMPLE_TYPES = ("historical_reconstruction", "forward_shadow")


@dataclass(frozen=True, slots=True)
class MarketRegimeInput:
    as_of_date: date
    universe_symbols: tuple[str, ...]
    histories: dict[str, tuple[Bar, ...]]
    sample_type: str = "historical_reconstruction"
    market_turnover: tuple[MarketTurnover, ...] = ()


@dataclass(frozen=True, slots=True)
class MarketRegimeAssessment:
    as_of_date: date
    score: float
    state: str
    components: dict[str, dict[str, float]]
    universe_count: int
    covered_count: int


def assess_market_regime(value: MarketRegimeInput) -> MarketRegimeAssessment:
    eligible = {
        symbol: bars
        for symbol in value.universe_symbols
        if (bars := _eligible_bars(value.histories.get(symbol, ()), value.as_of_date))
    }
    benchmark = _eligible_bars(
        value.histories.get(BENCHMARK_SYMBOL, ()), value.as_of_date
    )
    if not benchmark or len(benchmark) < 120:
        raise ValueError("market-regime experiment requires 120 completed CSI 300 bars")
    if not eligible:
        raise ValueError("market-regime experiment has no eligible watchlist histories")
    market_turnover = _eligible_market_turnover(value.market_turnover, value.as_of_date)
    if not market_turnover:
        raise ValueError("market-regime experiment requires 120 completed turnover sessions")
    benchmark_calendar = tuple(bar.trade_date for bar in benchmark[-120:])
    turnover_calendar = tuple(row.trade_date for row in market_turnover[-120:])
    if turnover_calendar != benchmark_calendar:
        raise ValueError("market turnover calendar does not match CSI 300")

    benchmark_closes = [bar.close for bar in benchmark]
    ma20 = fmean(benchmark_closes[-20:])
    ma60 = fmean(benchmark_closes[-60:])
    earlier_ma20 = fmean(benchmark_closes[-25:-5])
    earlier_ma60 = fmean(benchmark_closes[-65:-5])
    close = benchmark_closes[-1]
    close_vs_ma20 = close / ma20 - 1
    close_vs_ma60 = close / ma60 - 1
    ma20_slope_5d = ma20 / earlier_ma20 - 1
    ma60_slope_5d = ma60 / earlier_ma60 - 1
    returns = [
        current / previous - 1
        for previous, current in zip(benchmark_closes[-21:-1], benchmark_closes[-20:], strict=True)
    ]
    realized_vol_20 = pstdev(returns) * math.sqrt(252)
    trend_score = 8 * (close >= ma20) + 8 * (close >= ma60)
    trend_score += 7 * (ma20_slope_5d >= 0) + 7 * (ma60_slope_5d >= 0)

    above_ma20 = []
    above_ma60 = []
    advancing = []
    active_volume = []
    volume_ratios = []
    large_declines = []
    for bars in eligible.values():
        closes = [bar.close for bar in bars]
        volumes = [bar.volume for bar in bars]
        day_return = closes[-1] / closes[-2] - 1
        average_volume = fmean(volumes[-20:])
        volume_ratio = volumes[-1] / average_volume if average_volume > 0 else 0.0
        above_ma20.append(closes[-1] >= fmean(closes[-20:]))
        above_ma60.append(closes[-1] >= fmean(closes[-60:]))
        advancing.append(day_return > 0)
        active_volume.append(volume_ratio >= 1)
        volume_ratios.append(volume_ratio)
        large_declines.append(day_return <= -0.05)

    above_ma20_ratio = fmean(above_ma20)
    above_ma60_ratio = fmean(above_ma60)
    advancing_ratio = fmean(advancing)
    active_volume_ratio = fmean(active_volume)
    large_decline_ratio = fmean(large_declines)
    median_volume_ratio = median(volume_ratios)
    breadth_score = 15 * above_ma20_ratio + 15 * above_ma60_ratio
    turnover_amounts = [row.total_amount for row in market_turnover]
    total_market_amount = turnover_amounts[-1]
    turnover_ratio_5_20 = fmean(turnover_amounts[-5:]) / fmean(turnover_amounts[-20:])
    turnover_percentile_120 = _average_percentile_rank(
        turnover_amounts[-120:], total_market_amount
    )
    turnover_trend_health = _clamp((turnover_ratio_5_20 - 0.75) / 0.35)
    market_turnover_score = 5 * turnover_trend_health + 5 * turnover_percentile_120
    benchmark_day_return = benchmark_closes[-1] / benchmark_closes[-2] - 1
    turnover_stress_capped = benchmark_day_return <= -0.01 and large_decline_ratio >= 0.03
    if turnover_stress_capped:
        market_turnover_score = min(market_turnover_score, 4.0)
    participation_score = (
        7.5 * advancing_ratio + 7.5 * active_volume_ratio + market_turnover_score
    )
    volatility_health = 1 - _clamp((realized_vol_20 - 0.18) / 0.22)
    decline_health = 1 - _clamp(large_decline_ratio / 0.10)
    stress_score = 7.5 * volatility_health + 7.5 * decline_health
    score = round(trend_score + breadth_score + participation_score + stress_score, 1)
    state = "risk_on" if score >= 70 else "neutral" if score >= 45 else "risk_off"
    components = {
        "benchmark_trend": {
            "score": round(float(trend_score), 1),
            "max_score": 30.0,
            "close_vs_ma20": round(close_vs_ma20, 6),
            "close_vs_ma60": round(close_vs_ma60, 6),
            "ma20_slope_5d": round(ma20_slope_5d, 6),
            "ma60_slope_5d": round(ma60_slope_5d, 6),
            "realized_vol_20": round(realized_vol_20, 6),
        },
        "breadth": {
            "score": round(breadth_score, 1),
            "max_score": 30.0,
            "above_ma20_ratio": round(above_ma20_ratio, 6),
            "above_ma60_ratio": round(above_ma60_ratio, 6),
        },
        "participation": {
            "score": round(participation_score, 1),
            "max_score": 25.0,
            "advancing_ratio": round(advancing_ratio, 6),
            "active_volume_ratio": round(active_volume_ratio, 6),
            "median_volume_ratio_20": round(median_volume_ratio, 6),
            "total_market_amount": round(total_market_amount, 2),
            "market_turnover_ratio_5_20": round(turnover_ratio_5_20, 6),
            "market_turnover_percentile_120": round(turnover_percentile_120, 6),
            "market_turnover_score": round(market_turnover_score, 1),
            "market_turnover_max_score": 10.0,
            "market_turnover_stress_capped": float(turnover_stress_capped),
        },
        "stress": {
            "score": round(stress_score, 1),
            "max_score": 15.0,
            "large_decline_ratio": round(large_decline_ratio, 6),
            "realized_vol_20": round(realized_vol_20, 6),
        },
    }
    return MarketRegimeAssessment(
        value.as_of_date,
        score,
        state,
        components,
        len(value.universe_symbols),
        len(eligible),
    )


def build_market_regime_experiment(
    inputs: tuple[MarketRegimeInput, ...],
    payloads: tuple[dict[str, object], ...],
    algorithm_version: str,
) -> dict[str, object]:
    payload_by_date = {str(payload["as_of_date"]): payload for payload in payloads}
    all_history: list[dict[str, Any]] = []
    unavailable: list[dict[str, str]] = []
    for market_input in inputs:
        day = market_input.as_of_date.isoformat()
        payload = payload_by_date.get(day)
        if payload is None:
            continue
        sample_type = _sample_type(market_input.sample_type)
        try:
            assessment = assess_market_regime(market_input)
        except (ArithmeticError, ValueError):
            unavailable.append(
                {
                    "as_of_date": day,
                    "sample_type": sample_type,
                    "reason": "insufficient_market_data",
                }
            )
            continue
        all_history.append(_build_entry(assessment, payload, sample_type))
    all_history.sort(key=lambda row: row["as_of_date"])
    unavailable.sort(key=lambda row: row["as_of_date"])
    history = all_history[-22:]
    return {
        "schema_version": "2",
        "experiment_version": EXPERIMENT_VERSION,
        "algorithm_version": algorithm_version,
        "status": "available" if all_history or not unavailable else "unavailable",
        "latest_date": history[-1]["as_of_date"] if history else None,
        "history": history,
        "unavailable": unavailable[-22:],
        "outcome_comparison": _outcome_comparison(all_history, payload_by_date),
        "methodology": _methodology(),
    }


def unavailable_market_regime_report(
    algorithm_version: str,
) -> dict[str, object]:
    return {
        "schema_version": "2",
        "experiment_version": EXPERIMENT_VERSION,
        "algorithm_version": algorithm_version,
        "status": "unavailable",
        "latest_date": None,
        "history": [],
        "unavailable": [],
        "outcome_comparison": [],
        "methodology": _methodology(),
    }


def _build_entry(
    assessment: MarketRegimeAssessment,
    payload: dict[str, object],
    sample_type: str,
) -> dict[str, Any]:
    top10 = _candidate_list(payload.get("top10"))
    p1 = _candidate_list(payload.get("p1"))
    p2 = _candidate_list(payload.get("p2"))
    adjusted = _adjusted_top10(top10, assessment.state)
    decisions = [
        _decision(candidate, assessment.state, "top10", candidate in adjusted)
        for candidate in top10
    ]
    decisions.extend(_decision(candidate, assessment.state, "p1", False) for candidate in p1)
    decisions.extend(_decision(candidate, assessment.state, "p2", False) for candidate in p2)
    return {
        "as_of_date": assessment.as_of_date.isoformat(),
        "sample_type": sample_type,
        "score": assessment.score,
        "state": assessment.state,
        "universe_count": assessment.universe_count,
        "covered_count": assessment.covered_count,
        "components": assessment.components,
        "baseline_top10_count": len(top10),
        "adjusted_top10": [_public_candidate(candidate) for candidate in adjusted],
        "decisions": decisions,
        "policy": _policy(assessment.state),
    }


def _adjusted_top10(candidates: list[dict[str, Any]], state: str) -> list[dict[str, Any]]:
    if state == "risk_on":
        return candidates
    if state == "neutral":
        return sorted(
            candidates,
            key=lambda item: (
                item.get("signal_type") == "predictive_cross",
                item.get("grade") not in {"强S", "S"},
            ),
        )
    return [
        candidate
        for candidate in candidates
        if candidate.get("grade") in {"强S", "S"}
        and candidate.get("signal_type") in {"confirmed_trend", "bottom_divergence"}
    ]


def _decision(
    candidate: dict[str, Any],
    state: str,
    original_bucket: str,
    selected: bool,
) -> dict[str, object]:
    if original_bucket != "top10":
        action = "monitor" if state == "risk_on" else "observation"
        reason = "环境允许继续跟踪" if state == "risk_on" else "环境门槛提高，暂不晋级"
    elif state == "risk_off" and not selected:
        action, reason = "observation", "风险规避期仅作观察"
    elif state == "neutral" and candidate.get("signal_type") == "predictive_cross":
        action, reason = "downgrade", "中性环境下降低预测金叉优先级"
    elif state == "risk_off":
        action = "keep"
        reason = (
            "强共振底背离修复保留"
            if candidate.get("signal_type") == "bottom_divergence"
            else "强共振确认信号保留"
        )
    else:
        action, reason = "keep", "维持MACD基线优先级"
    return {
        **_public_candidate(candidate),
        "original_bucket": original_bucket,
        "action": action,
        "reason": reason,
    }


def _policy(state: str) -> str:
    if state == "risk_on":
        return "正常运行，允许确认信号及P1/P2继续观察"
    if state == "neutral":
        return "提高确认门槛，预测金叉降级，优先强共振"
    return "暂停预测金叉晋级，仅保留强共振确认或底背离修复信号"


def _outcome_comparison(
    history: list[dict[str, Any]],
    payload_by_date: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    horizons = (1, 5, 10, 20)
    baseline = {
        sample_type: {horizon: [] for horizon in horizons}
        for sample_type in SAMPLE_TYPES
    }
    adjusted = {
        sample_type: {horizon: [] for horizon in horizons}
        for sample_type in SAMPLE_TYPES
    }
    for entry in history:
        sample_type = _sample_type(str(entry["sample_type"]))
        payload = payload_by_date[str(entry["as_of_date"])]
        top10 = _candidate_list(payload.get("top10"))
        adjusted_symbols = {row["symbol"] for row in entry["adjusted_top10"]}
        for candidate in top10:
            for outcome in _candidate_list(candidate.get("outcomes")):
                horizon = int(outcome.get("horizon_days", 0))
                if horizon not in baseline[sample_type]:
                    continue
                baseline[sample_type][horizon].append(outcome)
                if candidate.get("symbol") in adjusted_symbols:
                    adjusted[sample_type][horizon].append(outcome)
    return [
        {
            "sample_type": sample_type,
            "horizon_days": horizon,
            "baseline": _aggregate_outcomes(baseline[sample_type][horizon]),
            "adjusted": _aggregate_outcomes(adjusted[sample_type][horizon]),
        }
        for sample_type in SAMPLE_TYPES
        for horizon in horizons
    ]


def _methodology() -> dict[str, object]:
    return {
        "benchmark": "沪深300",
        "universe": "当日自选池，仅公开聚合比例",
        "state_thresholds": {"risk_on": 70, "neutral": 45},
        "components": {
            "benchmark_trend": 30,
            "breadth": 30,
            "participation": 25,
            "stress": 15,
        },
        "participation_weights": {
            "advancing_ratio": 7.5,
            "watchlist_active_volume": 7.5,
            "total_market_turnover": 10,
        },
        "market_turnover_source": "搜狐证券上证指数与深证综指日成交额",
        "industry_diffusion": "待稳定行业分类数据后加入，不计入当前版本评分",
        "disclaimer": "影子实验，仅比较研究优先级，不构成交易建议。",
    }


def _sample_type(value: str) -> str:
    if value not in SAMPLE_TYPES:
        raise ValueError("unsupported market-regime sample type")
    return value


def _aggregate_outcomes(rows: list[dict[str, Any]]) -> dict[str, object]:
    if not rows:
        return {"sample_count": 0, "avg_net_return": None, "avg_mae": None}
    return {
        "sample_count": len(rows),
        "avg_net_return": round(fmean(float(row["net_return"]) for row in rows), 6),
        "avg_mae": round(fmean(float(row["mae"]) for row in rows), 6),
    }


def _eligible_bars(bars: tuple[Bar, ...], as_of_date: date) -> tuple[Bar, ...]:
    completed = tuple(
        sorted(
            (bar for bar in bars if bar.trade_date <= as_of_date),
            key=lambda item: item.trade_date,
        )
    )
    if len(completed) < 65 or completed[-1].trade_date != as_of_date:
        return ()
    return completed


def _candidate_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, dict)]


def _public_candidate(candidate: dict[str, Any]) -> dict[str, object]:
    return {
        "symbol": str(candidate.get("symbol", "")),
        "name": str(candidate.get("name", "")),
        "grade": str(candidate.get("grade", "")),
        "signal_type": str(candidate.get("signal_type", "")),
    }


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def _eligible_market_turnover(
    rows: tuple[MarketTurnover, ...], as_of_date: date
) -> tuple[MarketTurnover, ...]:
    completed = tuple(
        sorted(
            (row for row in rows if row.trade_date <= as_of_date),
            key=lambda item: item.trade_date,
        )
    )
    if len(completed) < 120 or completed[-1].trade_date != as_of_date:
        return ()
    return completed


def _average_percentile_rank(values: list[float], current: float) -> float:
    below = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return (below + 0.5 * equal) / len(values)
