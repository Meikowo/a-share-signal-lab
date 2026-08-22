from datetime import date, timedelta

from assl.domain import Bar
from assl.experiments.market_regime import (
    MarketRegimeInput,
    assess_market_regime,
    build_market_regime_experiment,
)


def test_rising_benchmark_and_broad_participation_classify_risk_on():
    market_input = _market_input(direction=1.0, advancing=True, active=True)

    assessment = assess_market_regime(market_input)

    assert assessment.state == "risk_on"
    assert assessment.score >= 70
    assert assessment.components["breadth"]["above_ma20_ratio"] == 1.0
    assert assessment.components["breadth"]["above_ma60_ratio"] == 1.0
    assert assessment.components["participation"]["advancing_ratio"] == 1.0


def test_falling_benchmark_narrow_breadth_and_stress_classify_risk_off():
    market_input = _market_input(direction=-1.0, advancing=False, active=False)

    assessment = assess_market_regime(market_input)

    assert assessment.state == "risk_off"
    assert assessment.score < 45
    assert assessment.components["breadth"]["above_ma20_ratio"] == 0.0
    assert assessment.components["stress"]["large_decline_ratio"] == 1.0


def test_risk_off_adjustment_keeps_only_strong_confirmed_resonance():
    day = date(2026, 8, 21)
    inputs = (_market_input(direction=-1.0, advancing=False, active=False, day=day),)
    payloads = (
        {
            "as_of_date": day.isoformat(),
            "top10": [
                _candidate("600001", "强S", "confirmed_trend", 0.10),
                _candidate("600002", "A", "predictive_cross", -0.20),
            ],
            "p1": [],
            "p2": [],
        },
    )

    report = build_market_regime_experiment(inputs, payloads, "macd-v1.1")

    entry = report["history"][0]
    assert entry["baseline_top10_count"] == 2
    assert [item["symbol"] for item in entry["adjusted_top10"]] == ["600001"]
    assert entry["decisions"] == [
        {
            "symbol": "600001",
            "name": "股票600001",
            "grade": "强S",
            "signal_type": "confirmed_trend",
            "original_bucket": "top10",
            "action": "keep",
            "reason": "强共振确认信号保留",
        },
        {
            "symbol": "600002",
            "name": "股票600002",
            "grade": "A",
            "signal_type": "predictive_cross",
            "original_bucket": "top10",
            "action": "observation",
            "reason": "风险规避期仅作观察",
        },
    ]
    comparison = next(
        row
        for row in report["outcome_comparison"]
        if row["sample_type"] == "historical_reconstruction"
        and row["horizon_days"] == 5
    )
    assert comparison["horizon_days"] == 5
    assert comparison["baseline"]["sample_count"] == 2
    assert comparison["baseline"]["avg_net_return"] == -0.05
    assert comparison["adjusted"]["sample_count"] == 1
    assert comparison["adjusted"]["avg_net_return"] == 0.1
    assert {row["horizon_days"] for row in report["outcome_comparison"]} == {
        1,
        5,
        10,
        20,
    }


def test_market_regime_ignores_future_bars():
    market_input = _market_input(direction=1.0, advancing=True, active=True)
    future_day = market_input.as_of_date + timedelta(days=3)
    histories = {
        symbol: (*bars, Bar(symbol, future_day, 1, 2, 0.5, 1, 999999))
        for symbol, bars in market_input.histories.items()
    }

    with_future = assess_market_regime(
        MarketRegimeInput(
            market_input.as_of_date,
            market_input.universe_symbols,
            histories,
        )
    )

    assert with_future == assess_market_regime(market_input)


def test_experiment_fails_soft_when_one_date_lacks_benchmark_history():
    day = date(2026, 8, 21)
    invalid = MarketRegimeInput(day, ("600001",), {"600001": ()})
    payload = {"as_of_date": day.isoformat(), "top10": [], "p1": [], "p2": []}

    report = build_market_regime_experiment((invalid,), (payload,), "macd-v1.1")

    assert report["history"] == []
    assert report["unavailable"] == [
        {
            "as_of_date": day.isoformat(),
            "sample_type": "historical_reconstruction",
            "reason": "insufficient_market_data",
        }
    ]


def test_outcome_comparison_separates_reconstruction_from_forward_shadow():
    first_day = date(2026, 8, 20)
    second_day = date(2026, 8, 21)
    reconstruction = _market_input(
        direction=-1.0, advancing=False, active=False, day=first_day
    )
    forward = _market_input(
        direction=-1.0, advancing=False, active=False, day=second_day
    )
    forward = MarketRegimeInput(
        forward.as_of_date,
        forward.universe_symbols,
        forward.histories,
        "forward_shadow",
    )
    payloads = (
        {
            "as_of_date": first_day.isoformat(),
            "top10": [_candidate("600001", "强S", "confirmed_trend", -0.1)],
            "p1": [],
            "p2": [],
        },
        {
            "as_of_date": second_day.isoformat(),
            "top10": [_candidate("600001", "强S", "confirmed_trend", 0.2)],
            "p1": [],
            "p2": [],
        },
    )

    report = build_market_regime_experiment(
        (reconstruction, forward), payloads, "macd-v1.1"
    )

    t5 = {
        row["sample_type"]: row
        for row in report["outcome_comparison"]
        if row["horizon_days"] == 5
    }
    assert t5["historical_reconstruction"]["baseline"]["avg_net_return"] == -0.1
    assert t5["forward_shadow"]["baseline"]["avg_net_return"] == 0.2
    assert {entry["sample_type"] for entry in report["history"]} == {
        "historical_reconstruction",
        "forward_shadow",
    }


def test_risk_off_keeps_strong_bottom_divergence_repair():
    day = date(2026, 8, 21)
    payload = {
        "as_of_date": day.isoformat(),
        "top10": [_candidate("600001", "S", "bottom_divergence", 0.1)],
        "p1": [],
        "p2": [],
    }

    report = build_market_regime_experiment(
        (_market_input(direction=-1, advancing=False, active=False, day=day),),
        (payload,),
        "macd-v1.1",
    )

    assert report["history"][0]["adjusted_top10"][0]["symbol"] == "600001"
    assert report["history"][0]["decisions"][0]["reason"] == "强共振底背离修复保留"


def _candidate(symbol: str, grade: str, signal_type: str, net_return: float):
    return {
        "symbol": symbol,
        "name": f"股票{symbol}",
        "grade": grade,
        "signal_type": signal_type,
        "bucket": "top10",
        "outcomes": [
            {
                "horizon_days": 5,
                "net_return": net_return,
                "mae": min(net_return, -0.03),
            }
        ],
    }


def _market_input(
    *,
    direction: float,
    advancing: bool,
    active: bool,
    day: date = date(2026, 8, 21),
) -> MarketRegimeInput:
    symbols = tuple(f"6000{index:02d}" for index in range(1, 11))
    histories = {
        symbol: _bars(
            symbol,
            day,
            direction=direction,
            final_jump=0.08 if advancing else -0.08,
            active=active,
        )
        for symbol in symbols
    }
    histories["000300"] = _bars(
        "000300",
        day,
        direction=direction,
        final_jump=0.02 if direction > 0 else -0.08,
        active=active,
    )
    return MarketRegimeInput(day, symbols, histories, "historical_reconstruction")


def _bars(
    symbol: str,
    end: date,
    *,
    direction: float,
    final_jump: float,
    active: bool,
) -> tuple[Bar, ...]:
    dates = []
    cursor = end
    while len(dates) < 70:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    dates.reverse()
    closes = [100 + direction * index for index in range(len(dates))]
    closes[-1] = closes[-2] * (1 + final_jump)
    volumes = [1000.0] * len(dates)
    volumes[-1] = 1600.0 if active else 400.0
    return tuple(
        Bar(symbol, trade_day, close, close * 1.01, close * 0.99, close, volume)
        for trade_day, close, volume in zip(dates, closes, volumes, strict=True)
    )
