from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

import assl.pipeline as pipeline_module
from assl.config import AlgorithmConfig
from assl.domain import (
    Bar,
    Grade,
    Instrument,
    PublicBucket,
    SignalChannel,
    StockSignal,
    WatchlistMember,
)
from assl.market.tencent import FetchBatch
from assl.outcomes import OutcomeCandidateRef
from assl.pipeline import DailyPipeline
from tests.fakes import FakeMarket, FakeRepository


def test_run_uses_last_completed_date_and_is_idempotent(monkeypatch):
    members = _members(2)
    bars = {member.instrument.symbol: _bars(member.instrument.symbol) for member in members}
    repository = FakeRepository(members, bars)
    market = FakeMarket(_batch({}))
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)

    def clock():
        return datetime(2026, 8, 12, 6, 0, tzinfo=UTC)

    pipeline = DailyPipeline(repository, market, AlgorithmConfig.macd_v1(), clock=clock)

    first = pipeline.run()
    second = pipeline.run()

    assert first.as_of_date == date(2026, 8, 11)
    assert second.run_id == first.run_id
    assert repository.run_count == 1
    assert market.calls == 1
    assert len(repository.snapshots) == 1


def test_low_coverage_fails_without_signal_persistence(monkeypatch):
    members = _members(100)
    bars = {member.instrument.symbol: _bars(member.instrument.symbol) for member in members[:97]}
    repository = FakeRepository(members, bars)
    market = FakeMarket(_batch({}))
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)

    summary = DailyPipeline(repository, market, AlgorithmConfig.macd_v1()).run(date(2026, 8, 11))

    assert summary.status == "failed"
    assert repository.signal_results == []
    assert summary.coverage.covered_count == 97


def test_failed_low_coverage_run_can_retry_after_missing_bars_arrive(monkeypatch):
    members = _members(100)
    bars = {member.instrument.symbol: _bars(member.instrument.symbol) for member in members[:97]}
    repository = FakeRepository(members, bars)
    market = FakeMarket(_batch({}))
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)
    pipeline = DailyPipeline(repository, market, AlgorithmConfig.macd_v1())

    first = pipeline.run(date(2026, 8, 11))
    market.batch = _batch(
        {
            member.instrument.symbol: _bars(member.instrument.symbol)
            for member in members[97:]
        }
    )
    second = pipeline.run(date(2026, 8, 11))

    assert first.status == "failed"
    assert second.status == "succeeded"
    assert second.run_id == first.run_id
    assert market.calls == 2
    assert repository.run_count == 1


def test_offline_run_never_calls_market(monkeypatch):
    members = _members(2)
    bars = {member.instrument.symbol: _bars(member.instrument.symbol) for member in members}
    repository = FakeRepository(members, bars)
    market = FakeMarket(_batch({}))
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)

    summary = DailyPipeline(repository, market, AlgorithmConfig.macd_v1()).run(
        date(2026, 8, 11), offline=True
    )

    assert summary.status == "succeeded"
    assert market.calls == 0


def test_explicit_future_date_is_rejected():
    members = _members(1)
    repository = FakeRepository(members, {})
    pipeline = DailyPipeline(
        repository,
        FakeMarket(_batch({})),
        AlgorithmConfig.macd_v1(),
        clock=lambda: datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="completed"):
        pipeline.run(date(2026, 8, 12))


def test_daily_run_backfills_matured_fixed_horizon_outcomes(monkeypatch):
    members = _members(1)
    stock_bars = _bars(members[0].instrument.symbol)
    benchmark_bars = tuple(
        Bar("000300", bar.trade_date, 20, 21, 19, 20.5, 2000) for bar in stock_bars
    )
    repository = FakeRepository(
        members,
        {members[0].instrument.symbol: stock_bars, "000300": benchmark_bars},
    )
    repository.outcome_candidates = (
        OutcomeCandidateRef(
            run_id=UUID("00000000-0000-0000-0000-000000000123"),
            symbol=members[0].instrument.symbol,
            signal_date=date(2026, 8, 3),
        ),
    )
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)

    summary = DailyPipeline(
        repository,
        FakeMarket(_batch({})),
        AlgorithmConfig.macd_v1(),
    ).run(date(2026, 8, 11), offline=True)

    assert summary.status == "succeeded"
    assert {outcome.horizon_days for outcome in repository.outcomes} == {1, 5}


def test_automatic_run_uses_latest_available_market_date_on_holiday(monkeypatch):
    members = _members(1)
    cached = tuple(
        bar for bar in _bars(members[0].instrument.symbol) if bar.trade_date <= date(2026, 8, 7)
    )
    repository = FakeRepository(members, {members[0].instrument.symbol: cached})
    monkeypatch.setattr(pipeline_module, "classify_stock", _classify)
    pipeline = DailyPipeline(
        repository,
        FakeMarket(_batch({})),
        AlgorithmConfig.macd_v1(),
        clock=lambda: datetime(2026, 8, 10, 22, 0, tzinfo=UTC),
    )

    summary = pipeline.run()

    assert summary.as_of_date == date(2026, 8, 7)
    assert summary.status == "succeeded"


def _members(count):
    return tuple(
        WatchlistMember(
            Instrument.from_secid(f"0.00{index:04d}", f"股票{index}"),
            fundamental_priority=index % 3,
        )
        for index in range(1, count + 1)
    )


def _bars(symbol):
    start = date(2026, 4, 1)
    return tuple(
        Bar(symbol, start + timedelta(days=index), 10, 11, 9, 10.5, 1000)
        for index in range(133)
        if (start + timedelta(days=index)).weekday() < 5
    )


def _batch(bars_by_symbol):
    return FetchBatch(
        bars_by_symbol=bars_by_symbol,
        names_by_symbol={},
        fallback_symbols=(),
        errors={},
        source_timestamp=datetime(2026, 8, 11, 15, 1, tzinfo=UTC),
    )


def _classify(instrument, frame, fundamental_priority, config):
    return StockSignal(
        instrument=instrument,
        as_of_date=date(2026, 8, 11),
        signal_date=date(2026, 8, 11),
        channel=SignalChannel.CONFIRMED_TREND,
        grade=Grade.B_PLUS,
        public_bucket=PublicBucket.TOP10,
        prediction_tier=None,
        fundamental_priority=fundamental_priority,
        dif=0.1,
        dea=0.05,
        macd_hist=0.1,
        gap=-0.05,
        convergence_speed=None,
        x1=None,
        x1_change_pct=None,
        projected_days=None,
        ma20=10,
        ma30=10,
        ma60=10,
        close_vs_ma20=0.05,
        close_vs_ma30=0.05,
        close_vs_ma60=0.05,
        volume_ratio_5_20=1,
        bottom_divergence=False,
        top_divergence=False,
        signal_age_days=0,
        dif_above_zero=True,
        histogram_improvement=0.1,
        ma_structure_score=1,
        volume_score=1,
        risk_score=0,
        reason="test",
        confirm_price=10.5,
        invalidation_price=9.85,
        risk=None,
    )
