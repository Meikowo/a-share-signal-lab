import random
from dataclasses import replace
from datetime import date

from assl.domain import (
    Grade,
    Instrument,
    PublicBucket,
    SignalChannel,
    StockSignal,
)
from assl.ranking import rank_screen


def test_ranking_is_deterministic_across_input_order():
    signals = [
        make_signal("600003", Grade.B_PLUS, priority=1),
        make_signal("600001", Grade.S, priority=1, bottom=True),
        make_signal("600002", Grade.A_PLUS, priority=2, bottom=True, tier="P1"),
        make_signal("600004", Grade.B, priority=0, tier="P2"),
    ]
    shuffled = signals.copy()
    random.Random(42).shuffle(shuffled)

    first = rank_screen(signals)
    second = rank_screen(shuffled)

    assert symbols(first.top10) == symbols(second.top10)
    assert symbols(first.top10) == ["600002", "600001", "600003", "600004"]


def test_recent_top_divergence_is_only_in_risk_watch():
    risky = make_signal("600001", Grade.STRONG_S, priority=2, top=True, bottom=True)
    safe = make_signal("600002", Grade.B_PLUS, priority=1)

    ranked = rank_screen((risky, safe))

    assert symbols(ranked.top10) == ["600002"]
    assert symbols(ranked.risk_watch) == ["600001"]
    assert ranked.risk_watch[0].public_bucket is PublicBucket.RISK_WATCH


def test_each_symbol_occupies_only_its_highest_public_bucket():
    signals = [
        make_signal(f"60{index:04d}", Grade.B_PLUS, priority=1)
        for index in range(1, 11)
    ]
    signals.extend(
        [
            make_signal("601001", Grade.B, priority=0, tier="P1"),
            make_signal("601002", Grade.B, priority=0, tier="P2"),
        ]
    )

    ranked = rank_screen(signals, limit=10)

    groups = symbols(ranked.top10 + ranked.p1 + ranked.p2 + ranked.risk_watch)
    assert len(groups) == len(set(groups))
    assert symbols(ranked.p1) == ["601001"]
    assert symbols(ranked.p2) == ["601002"]


def make_signal(
    symbol,
    grade,
    *,
    priority,
    bottom=False,
    top=False,
    tier=None,
):
    signal = StockSignal(
        instrument=Instrument.from_secid(f"1.{symbol}", symbol),
        as_of_date=date(2026, 8, 11),
        signal_date=date(2026, 8, 11),
        channel=(
            SignalChannel.PREDICTIVE_CROSS
            if tier
            else SignalChannel.CONFIRMED_TREND
        ),
        grade=grade,
        public_bucket=None,
        prediction_tier=tier,
        fundamental_priority=priority,
        dif=0.1,
        dea=0.05,
        macd_hist=0.1,
        gap=-0.05,
        convergence_speed=0.1 if tier else None,
        x1=10.1 if tier else None,
        x1_change_pct=0.01 if tier else None,
        projected_days=1.0 if tier == "P1" else 2.0 if tier else None,
        ma20=10,
        ma30=9.8,
        ma60=9.5,
        close_vs_ma20=0.05,
        close_vs_ma30=0.07,
        close_vs_ma60=0.1,
        volume_ratio_5_20=1.2,
        bottom_divergence=bottom,
        top_divergence=top,
        signal_age_days=0,
        dif_above_zero=True,
        histogram_improvement=0.2,
        ma_structure_score=1,
        volume_score=1.2,
        risk_score=1 if top else 0,
        reason="test",
        confirm_price=10.1,
        invalidation_price=9.8,
        risk="top divergence" if top else None,
    )
    return replace(signal)


def symbols(signals):
    return [signal.instrument.symbol for signal in signals]
