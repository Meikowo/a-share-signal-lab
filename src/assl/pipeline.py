from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

from assl.config import AlgorithmConfig
from assl.domain import (
    Bar,
    Coverage,
    Instrument,
    RunError,
    RunKey,
    RunSummary,
    StockSignal,
    content_sha256,
)
from assl.market.quality import calculate_coverage
from assl.outcomes import CandidateOutcome, evaluate_fixed_horizon_ref, matured_horizons
from assl.publish.exporter import persist_snapshot
from assl.publish.schema import PublicSnapshot
from assl.ranking import rank_screen
from assl.signals.classify import classify_stock
from assl.signals.indicators import add_indicators

CHINA_TZ = ZoneInfo("Asia/Shanghai")


class DailyPipeline:
    def __init__(
        self,
        repository,
        market,
        config: AlgorithmConfig,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.repository = repository
        self.market = market
        self.config = config
        self.clock = clock

    def run(
        self,
        as_of_date: date | None = None,
        *,
        offline: bool = False,
    ) -> RunSummary:
        latest_completed = self._latest_completed_date()
        if as_of_date is not None and as_of_date > latest_completed:
            raise ValueError(
                f"as-of date {as_of_date} is later than completed session {latest_completed}"
            )
        resolved_date = as_of_date or latest_completed
        stage = "load_watchlist"
        run_id = None
        universe_count = 0
        coverage = Coverage(0, 0, (), None, False)

        try:
            with self.repository.transaction() as connection:
                version = self.repository.latest_watchlist(connection)
                if version is None:
                    raise RuntimeError("no private watchlist version is available")
                members = self.repository.load_watchlist_members(connection, version.id)
                universe_count = len(members)
                if universe_count == 0:
                    raise RuntimeError("latest private watchlist is empty")
                self.repository.ensure_algorithm_version(
                    connection,
                    self.config,
                    code_sha=os.environ.get("GITHUB_SHA", "local"),
                )
                instruments = tuple(member.instrument for member in members)
                symbols = tuple(item.symbol for item in instruments)
                benchmark = _benchmark_instrument()
                latest_dates = self.repository.latest_bar_dates(
                    connection, (*symbols, benchmark.symbol)
                )
                preliminary_date = as_of_date or max(
                    (day for day in latest_dates.values() if day <= latest_completed),
                    default=resolved_date,
                )
                existing = self.repository.find_run(
                    connection,
                    RunKey(preliminary_date, version.id, self.config.version),
                )
                if existing is not None and existing.status != "failed":
                    return existing

            source_timestamp = None
            if not offline:
                stage = "fetch_bars"
                fetch_cutoff = as_of_date or latest_completed
                batch = self.market.fetch_many(
                    (*instruments, benchmark), fetch_cutoff, latest_dates
                )
                source_timestamp = batch.source_timestamp
                fetched_bars = tuple(
                    bar for symbol_bars in batch.bars_by_symbol.values() for bar in symbol_bars
                )
                if as_of_date is None:
                    resolved_date = _latest_market_date(
                        latest_completed,
                        fetched_bars,
                        tuple(latest_dates.values()),
                    )
                if fetched_bars:
                    with self.repository.transaction() as connection:
                        self.repository.upsert_bars(
                            connection, fetched_bars, batch.source_timestamp
                        )

            with self.repository.transaction() as connection:
                key = RunKey(resolved_date, version.id, self.config.version)
                existing = self.repository.find_run(connection, key)
                if existing is not None and existing.status != "failed":
                    return existing
                run_id = self.repository.start_run(
                    connection, key, universe_count=universe_count
                )

            stage = "validate_data"
            with self.repository.transaction() as connection:
                histories = self.repository.load_bars(connection, symbols, resolved_date, limit=180)
            eligible = {
                symbol: bars
                for symbol, bars in histories.items()
                if len(bars) >= 60 and bars[-1].trade_date == resolved_date
            }
            coverage = calculate_coverage(instruments, eligible, source_timestamp)
            if not coverage.publishable:
                error = RunError(
                    "validate_data",
                    f"coverage {coverage.covered_count}/{coverage.universe_count} is below 98%",
                )
                with self.repository.transaction() as connection:
                    self.repository.finish_run(connection, run_id, "failed", coverage, error)
                return RunSummary(run_id, resolved_date, "failed", coverage, None)

            stage = "evaluate_outcomes"
            outcomes = self._evaluate_outcomes(resolved_date)

            stage = "compute_signals"
            priority_by_symbol = {
                member.instrument.symbol: member.fundamental_priority for member in members
            }
            instrument_by_symbol = {item.symbol: item for item in instruments}
            signals: list[StockSignal] = []
            for symbol in sorted(eligible):
                frame = _bars_frame(eligible[symbol])
                enriched = add_indicators(frame, self.config)
                signals.append(
                    classify_stock(
                        instrument_by_symbol[symbol],
                        enriched,
                        priority_by_symbol[symbol],
                        self.config,
                    )
                )

            stage = "rank"
            ranked = rank_screen(signals)
            bucketed = {
                signal.instrument.symbol: signal
                for signal in (
                    *ranked.top10,
                    *ranked.p1,
                    *ranked.p2,
                    *ranked.risk_watch,
                )
            }
            top_ranks = {
                signal.instrument.symbol: index
                for index, signal in enumerate(ranked.top10, start=1)
            }
            persisted = tuple(
                (
                    top_ranks.get(signal.instrument.symbol),
                    bucketed.get(signal.instrument.symbol, signal),
                )
                for signal in sorted(signals, key=lambda item: item.instrument.symbol)
            )
            result_hash = _result_hash(persisted)

            stage = "persist"
            with self.repository.transaction() as connection:
                self.repository.insert_signal_results(connection, run_id, persisted)
                self.repository.upsert_candidate_outcomes(connection, outcomes)
                outcome_summary = self.repository.outcome_summary(
                    connection, self.config.version
                )
                snapshot = PublicSnapshot.from_signals(
                    as_of_date=resolved_date,
                    generated_at=self.clock(),
                    algorithm_version=self.config.version,
                    source="Tencent qfq daily OHLCV",
                    coverage=coverage,
                    top10=ranked.top10,
                    p1=ranked.p1,
                    p2=ranked.p2,
                    risk_watch=ranked.risk_watch,
                    outcome_summary=outcome_summary,
                )
                persist_snapshot(self.repository, connection, run_id, snapshot)
                self.repository.finish_run(
                    connection,
                    run_id,
                    "succeeded",
                    coverage,
                    result_sha256=result_hash,
                )
            return RunSummary(run_id, resolved_date, "succeeded", coverage, result_hash)
        except Exception as exc:  # noqa: BLE001
            if run_id is None:
                raise
            error = RunError(stage, f"{type(exc).__name__}: {exc}")
            if coverage.universe_count == 0:
                coverage = Coverage(universe_count, 0, (), None, False)
            with self.repository.transaction() as connection:
                self.repository.finish_run(connection, run_id, "failed", coverage, error)
            return RunSummary(run_id, resolved_date, "failed", coverage, None)

    def _evaluate_outcomes(self, as_of_date: date) -> tuple[CandidateOutcome, ...]:
        with self.repository.transaction() as connection:
            candidates = self.repository.list_outcome_candidates(
                connection,
                self.config.version,
                before_date=as_of_date,
            )
        if not candidates:
            return ()

        benchmark = _benchmark_instrument()
        symbols = tuple(sorted({candidate.symbol for candidate in candidates}))
        with self.repository.transaction() as connection:
            histories = self.repository.load_bars(
                connection,
                (*symbols, benchmark.symbol),
                as_of_date,
                limit=260,
            )
        benchmark_bars = histories.get(benchmark.symbol, ())
        if not benchmark_bars:
            return ()

        outcomes = []
        for candidate in candidates:
            stock_bars = histories.get(candidate.symbol, ())
            for horizon in matured_horizons(candidate.signal_date, benchmark_bars):
                outcome = evaluate_fixed_horizon_ref(
                    candidate,
                    stock_bars,
                    benchmark_bars,
                    horizon,
                )
                if outcome is not None:
                    outcomes.append(outcome)
        return tuple(outcomes)

    def _latest_completed_date(self) -> date:
        now = self.clock().astimezone(CHINA_TZ)
        candidate = now.date()
        if now.time() < time(16, 0):
            candidate -= timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate


def _bars_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": [bar.trade_date for bar in bars],
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        }
    )


def _result_hash(rows: tuple[tuple[int | None, StockSignal], ...]) -> str:
    payload = [
        {
            "rank": rank,
            "symbol": signal.instrument.symbol,
            "bucket": signal.public_bucket.value if signal.public_bucket else None,
            "channel": signal.channel.value,
            "grade": signal.grade.value,
            "prediction_tier": signal.prediction_tier,
            "dif": signal.dif,
            "dea": signal.dea,
            "macd_hist": signal.macd_hist,
            "x1": signal.x1,
        }
        for rank, signal in rows
    ]
    return content_sha256(payload)


def _benchmark_instrument() -> Instrument:
    return Instrument(
        symbol="000300",
        name="沪深300",
        exchange="SH",
        secid="1.000300",
    )


def _latest_market_date(
    cutoff: date,
    fetched_bars: Sequence[Bar],
    cached_dates: tuple[date, ...],
) -> date:
    available = [bar.trade_date for bar in fetched_bars if bar.trade_date <= cutoff]
    available.extend(day for day in cached_dates if day <= cutoff)
    return max(available, default=cutoff)
