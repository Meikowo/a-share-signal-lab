from contextlib import contextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import assl.db as db_module
from assl.config import AlgorithmConfig
from assl.db import AsslRepository
from assl.domain import (
    Bar,
    Coverage,
    Grade,
    Instrument,
    PublicBucket,
    RunError,
    RunKey,
    SignalChannel,
    StockSignal,
    WatchlistMember,
    WatchlistVersion,
)
from assl.experiments.market_regime import MarketRegimeInput
from assl.outcomes import CandidateOutcome


class Result:
    def __init__(self, row=None, rowcount=0, rows=None):
        self.row = row
        self.rowcount = rowcount
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class RecordingConnection:
    def __init__(self, results=()):
        self.results = list(results)
        self.statements = []
        self.batches = []
        self.transaction_entries = 0

    @contextmanager
    def transaction(self):
        self.transaction_entries += 1
        yield self

    def execute(self, statement, params=None):
        self.statements.append((str(statement), params))
        return self.results.pop(0) if self.results else Result()

    def cursor(self):
        return RecordingCursor(self)


class RecordingCursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def executemany(self, statement, params_seq):
        batches = self.connection.batches
        batches.append((str(statement), list(params_seq)))
        return Result(rowcount=len(batches[-1][1]))


class ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def test_market_regime_inputs_use_each_runs_historical_watchlist(monkeypatch):
    version_id = UUID("00000000-0000-0000-0000-000000000081")
    day = date(2026, 8, 21)
    prior_day = date(2026, 8, 20)
    connection = RecordingConnection(
        [
            Result(
                rows=[
                    {
                        "as_of_date": prior_day,
                        "watchlist_version_id": version_id,
                        "sample_type": "historical_reconstruction",
                    },
                    {
                        "as_of_date": day,
                        "watchlist_version_id": version_id,
                        "sample_type": "forward_shadow",
                    },
                ]
            )
        ]
    )
    repository = AsslRepository("unused")
    member = WatchlistMember(Instrument.from_secid("1.600000", "浦发银行"))
    stock_bar = Bar("600000", day, 10, 11, 9, 10.5, 1000)
    benchmark_bar = Bar("000300", day, 100, 101, 99, 100.5, 2000)

    monkeypatch.setattr(
        AsslRepository,
        "load_watchlist_members",
        lambda self, opened, received: (member,) if received == version_id else (),
    )
    load_calls = []
    monkeypatch.setattr(
        AsslRepository,
        "load_bars",
        lambda self, opened, symbols, end_date, limit=180: load_calls.append(
            (symbols, end_date, limit)
        )
        or {"600000": (stock_bar,), "000300": (benchmark_bar,)},
    )

    inputs = repository.list_market_regime_inputs(
        "macd-v1.1", sessions=None, connection=connection
    )

    assert inputs == (
        MarketRegimeInput(
            prior_day,
            ("600000",),
            {"600000": (stock_bar,), "000300": (benchmark_bar,)},
            "historical_reconstruction",
        ),
        MarketRegimeInput(
            as_of_date=day,
            universe_symbols=("600000",),
            histories={"600000": (stock_bar,), "000300": (benchmark_bar,)},
            sample_type="forward_shadow",
        ),
    )
    assert len(load_calls) == 1
    assert load_calls[0][2] == 121
    statement, params = connection.statements[0]
    assert "watchlist_version_id" in statement
    assert "execution_mode as sample_type" in statement.lower()
    assert "source_timestamp" not in statement.lower()
    assert params == ("macd-v1.1", None)


def test_transaction_disables_prepared_statements(monkeypatch):
    connection = RecordingConnection()
    captured = {}

    def connect(database_url, **kwargs):
        captured["database_url"] = database_url
        captured.update(kwargs)
        return ConnectionContext(connection)

    monkeypatch.setattr(db_module.psycopg, "connect", connect)
    repository = AsslRepository("postgresql://private-database")

    with repository.transaction() as opened:
        assert opened is connection

    assert captured["database_url"] == "postgresql://private-database"
    assert captured["prepare_threshold"] is None
    assert connection.transaction_entries == 1


def test_latest_watchlist_maps_database_row():
    version_id = UUID("00000000-0000-0000-0000-000000000001")
    created_at = datetime(2026, 8, 12, tzinfo=UTC)
    connection = RecordingConnection(
        [
            Result(
                {
                    "id": version_id,
                    "created_at": created_at,
                    "source": "manual-sync",
                    "item_count": 839,
                    "content_sha256": "a" * 64,
                    "note": None,
                }
            )
        ]
    )

    version = AsslRepository("unused").latest_watchlist(connection)

    assert version is not None
    assert version.id == version_id
    assert version.created_at == created_at
    assert version.item_count == 839
    assert "order by created_at desc" in connection.statements[0][0].lower()


def test_latest_watchlist_returns_none_for_empty_database():
    connection = RecordingConnection([Result(None)])

    assert AsslRepository("unused").latest_watchlist(connection) is None


def test_recent_trade_dates_returns_limited_sessions_in_chronological_order():
    connection = RecordingConnection(
        [
            Result(
                rows=[
                    {"trade_date": date(2026, 8, 14)},
                    {"trade_date": date(2026, 8, 13)},
                    {"trade_date": date(2026, 8, 12)},
                ]
            )
        ]
    )

    dates = AsslRepository("unused").recent_trade_dates(
        connection, "000300", date(2026, 8, 14), 3
    )

    assert dates == (
        date(2026, 8, 12),
        date(2026, 8, 13),
        date(2026, 8, 14),
    )
    sql, params = connection.statements[0]
    assert "order by trade_date desc" in sql.lower()
    assert params == ("000300", date(2026, 8, 14), 3)


def test_load_watchlist_members_maps_private_metadata():
    version_id = UUID("00000000-0000-0000-0000-000000000001")
    connection = RecordingConnection(
        [
            Result(
                rows=[
                    {
                        "symbol": "600000",
                        "name": "浦发银行",
                        "exchange": "SH",
                        "fundamental_priority": 2,
                        "theme_tags": ["银行", "红利"],
                    }
                ]
            )
        ]
    )

    members = AsslRepository("unused").load_watchlist_members(connection, version_id)

    assert members[0].instrument.secid == "1.600000"
    assert members[0].fundamental_priority == 2
    assert members[0].theme_tags == ("银行", "红利")


def test_find_watchlist_by_hash_reuses_row_mapping():
    version_id = UUID("00000000-0000-0000-0000-000000000001")
    created_at = datetime(2026, 8, 12, tzinfo=UTC)
    connection = RecordingConnection(
        [
            Result(
                {
                    "id": version_id,
                    "created_at": created_at,
                    "source": "manual-sync",
                    "item_count": 839,
                    "content_sha256": "a" * 64,
                    "note": None,
                }
            )
        ]
    )

    version = AsslRepository("unused").find_watchlist_by_hash(connection, "a" * 64)

    assert version is not None
    assert version.id == version_id
    assert "content_sha256 = %s" in connection.statements[0][0].lower()


def test_ensure_algorithm_version_is_idempotent():
    connection = RecordingConnection()

    version = AsslRepository("unused").ensure_algorithm_version(
        connection, AlgorithmConfig.macd_v1(), code_sha="abc123"
    )

    assert version == "macd-v1.1"
    sql, params = connection.statements[0]
    assert "insert into assl_private.algorithm_versions" in sql.lower()
    assert "on conflict (id) do nothing" in sql.lower()
    assert params[0:2] == ("macd-v1.1", "abc123")


def test_find_run_maps_persisted_summary():
    run_id = UUID("00000000-0000-0000-0000-000000000021")
    key = RunKey(
        date(2026, 8, 11),
        UUID("00000000-0000-0000-0000-000000000011"),
        "macd-v1",
    )
    connection = RecordingConnection(
        [
            Result(
                {
                    "id": run_id,
                    "as_of_date": date(2026, 8, 11),
                    "status": "succeeded",
                    "universe_count": 100,
                    "covered_count": 97,
                    "missing_symbols": ["000098", "000099", "000100"],
                    "source_timestamp": datetime(2026, 8, 11, 7, 1, tzinfo=UTC),
                    "result_sha256": "d" * 64,
                }
            )
        ]
    )

    summary = AsslRepository("unused").find_run(connection, key)

    assert summary is not None
    assert summary.run_id == run_id
    assert summary.coverage.publishable is True
    assert summary.result_sha256 == "d" * 64


def test_latest_bar_dates_and_load_bars_map_rows():
    connection = RecordingConnection(
        [
            Result(rows=[{"symbol": "600000", "trade_date": date(2026, 8, 11)}]),
            Result(
                rows=[
                    {
                        "symbol": "600000",
                        "trade_date": date(2026, 8, 11),
                        "open": 10,
                        "high": 11,
                        "low": 9,
                        "close": 10.5,
                        "volume": 1000,
                    }
                ]
            ),
        ]
    )
    repository = AsslRepository("unused")

    latest = repository.latest_bar_dates(connection, ("600000", "000001"))
    bars = repository.load_bars(connection, ("600000", "000001"), date(2026, 8, 11), limit=180)

    assert latest == {"600000": date(2026, 8, 11)}
    assert bars["600000"][0].close == 10.5
    assert bars["000001"] == ()


def test_snapshot_repository_methods_use_immutable_key():
    connection = RecordingConnection(
        [
            Result({"payload_sha256": "e" * 64}),
            Result(rows=[{"payload": {"as_of_date": "2026-08-11"}}]),
        ]
    )
    repository = AsslRepository("unused")

    digest = repository.get_snapshot_hash(connection, date(2026, 8, 11), "macd-v1")
    payloads = repository.list_snapshot_payloads("macd-v1", connection=connection)

    assert digest == "e" * 64
    assert payloads == ({"as_of_date": "2026-08-11"},)
    assert "as_of_date = %s" in connection.statements[0][0].lower()


def test_list_public_candidate_outcomes_returns_only_public_fields():
    connection = RecordingConnection(
        [
            Result(
                rows=[
                    {
                        "as_of_date": date(2026, 8, 12),
                        "symbol": "600000",
                        "horizon_days": 1,
                        "entry_date": date(2026, 8, 13),
                        "exit_date": date(2026, 8, 13),
                        "net_return": 0.024,
                        "mae": -0.013,
                    }
                ]
            )
        ]
    )

    outcomes = AsslRepository("unused").list_public_candidate_outcomes(
        "macd-v1", connection=connection
    )

    assert outcomes == (
        {
            "as_of_date": date(2026, 8, 12),
            "symbol": "600000",
            "horizon_days": 1,
            "entry_date": date(2026, 8, 13),
            "exit_date": date(2026, 8, 13),
            "net_return": 0.024,
            "mae": -0.013,
        },
    )
    sql = connection.statements[0][0].lower()
    assert "outcome.model = 'fixed_horizon'" in sql
    assert "public_bucket in ('top10', 'p1', 'p2')" in sql
    assert "outcome.net_return::double precision" in sql
    assert "outcome.mae::double precision" in sql
    assert "outcome.entry_date > run.as_of_date" in sql


def test_insert_snapshot_writes_json_payload():
    from assl.publish.schema import PublicSnapshot

    snapshot = PublicSnapshot.from_signals(
        as_of_date=date(2026, 8, 11),
        generated_at=datetime(2026, 8, 12, tzinfo=UTC),
        algorithm_version="macd-v1",
        source="腾讯前复权日线",
        coverage=Coverage(1, 1, (), None, True),
        top10=(),
        p1=(),
        p2=(),
        risk_watch=(),
        outcome_summary=(),
    )
    connection = RecordingConnection()

    AsslRepository("unused").insert_snapshot(
        connection,
        UUID("00000000-0000-0000-0000-000000000021"),
        snapshot,
        "f" * 64,
    )

    assert "insert into assl_private.published_snapshots" in connection.statements[0][0].lower()


def test_insert_watchlist_version_writes_version_and_private_metadata():
    version = WatchlistVersion(
        id=UUID("00000000-0000-0000-0000-000000000011"),
        created_at=datetime(2026, 8, 12, tzinfo=UTC),
        source="manual-sync",
        item_count=1,
        content_sha256="b" * 64,
        note="first import",
    )
    member = WatchlistMember(
        Instrument.from_secid("1.600000", "浦发银行"),
        fundamental_priority=2,
        theme_tags=("银行", "红利"),
    )
    connection = RecordingConnection()

    AsslRepository("unused").insert_watchlist_version(connection, version, (member,))

    assert "insert into assl_private.watchlist_versions" in connection.statements[0][0].lower()
    assert connection.statements[0][1][0] == version.id
    assert "insert into assl_private.watchlist_members" in connection.batches[0][0].lower()
    member_params = connection.batches[0][1][0]
    assert member_params[1:5] == ("600000", "浦发银行", "SH", 2)


def test_upsert_bars_updates_only_for_newer_source_timestamp():
    connection = RecordingConnection()
    bar = Bar("600000", date(2026, 8, 11), 10, 11, 9, 10.5, 1000)
    timestamp = datetime(2026, 8, 11, 15, 1, tzinfo=UTC)

    count = AsslRepository("unused").upsert_bars(connection, (bar,), timestamp)

    sql, rows = connection.batches[0]
    assert "on conflict (symbol, trade_date, adjustment, source)" in sql.lower()
    assert "excluded.source_timestamp > daily_bars.source_timestamp" in sql.lower()
    assert rows[0][-3:] == ("qfq", "tencent", timestamp)
    assert count == 1


def test_start_run_returns_existing_id_after_unique_conflict():
    existing_id = UUID("00000000-0000-0000-0000-000000000021")
    key = RunKey(
        date(2026, 8, 11),
        UUID("00000000-0000-0000-0000-000000000011"),
        "macd-v1",
    )
    connection = RecordingConnection([Result(None), Result({"id": existing_id})])

    run_id = AsslRepository("unused").start_run(
        connection,
        key,
        universe_count=839,
        execution_mode="historical_reconstruction",
    )

    assert run_id == existing_id
    insert_sql = connection.statements[0][0].lower()
    assert "on conflict" in insert_sql
    assert "do update set execution_mode = excluded.execution_mode" in insert_sql
    assert "screening_runs.status = 'failed'" in insert_sql
    assert connection.statements[0][1][-1] == "historical_reconstruction"
    assert "select id" in connection.statements[1][0].lower()


def test_finish_run_persists_coverage_and_sanitized_error():
    connection = RecordingConnection()
    run_id = UUID("00000000-0000-0000-0000-000000000021")
    coverage = Coverage(
        universe_count=2,
        covered_count=1,
        missing_symbols=("000001",),
        source_timestamp=datetime(2026, 8, 11, 7, 1, tzinfo=UTC),
        publishable=False,
    )

    AsslRepository("unused").finish_run(
        connection,
        run_id,
        "failed",
        coverage,
        RunError("fetch_bars", "database_url=postgresql://secret"),
    )

    params = connection.statements[0][1]
    assert params[0:3] == ("failed", 1, 0.5)
    assert params[-3] == "fetch_bars"
    assert "postgresql://" not in params[-2]


def test_insert_signal_results_uses_one_batch():
    connection = RecordingConnection()
    run_id = UUID("00000000-0000-0000-0000-000000000021")
    signal = _stock_signal()

    AsslRepository("unused").insert_signal_results(connection, run_id, ((1, signal),))

    sql, rows = connection.batches[0]
    assert "insert into assl_private.signal_results" in sql.lower()
    assert len(rows) == 1
    assert rows[0][0:4] == (run_id, "600000", 1, "top10")


def test_outcome_repository_lists_candidates_upserts_and_summarizes():
    run_id = UUID("00000000-0000-0000-0000-000000000021")
    connection = RecordingConnection(
        [
            Result(
                rows=[
                    {
                        "run_id": run_id,
                        "symbol": "600000",
                        "selection_date": date(2026, 8, 4),
                    }
                ]
            ),
            Result(
                rows=[
                    {
                        "bucket": "all",
                        "horizon_days": 5,
                        "sample_count": 8,
                        "win_rate": 0.625,
                        "avg_net_return": 0.0123,
                        "avg_excess_return": 0.0042,
                        "avg_mae": -0.031,
                    }
                ]
            ),
        ]
    )
    repository = AsslRepository("unused")

    candidates = repository.list_outcome_candidates(
        connection, "macd-v1", before_date=date(2026, 8, 11)
    )
    repository.upsert_candidate_outcomes(
        connection,
        (
            CandidateOutcome(
                run_id=run_id,
                symbol="600000",
                model="fixed_horizon",
                horizon_days=5,
                entry_date=date(2026, 8, 4),
                entry_price=Decimal("10"),
                detection_date=date(2026, 8, 10),
                exit_date=date(2026, 8, 10),
                exit_price=Decimal("11"),
                gross_return=Decimal("0.1"),
                net_return=Decimal("0.098"),
                benchmark_return=Decimal("0.02"),
                excess_return=Decimal("0.078"),
                mfe=Decimal("0.11"),
                mae=Decimal("-0.03"),
                exit_reason="fixed_5d",
                non_evaluable_reason=None,
                cost_model_version="cost-v1",
            ),
        ),
    )
    summary = repository.outcome_summary(connection, "macd-v1")

    assert candidates[0].symbol == "600000"
    assert getattr(candidates[0], "selection_date", None) == date(2026, 8, 4)
    assert "public_bucket in ('top10', 'p1', 'p2')" in connection.statements[0][0].lower()
    candidate_sql = connection.statements[0][0].lower()
    assert "run.as_of_date as selection_date" in candidate_sql
    assert "sr.signal_date" not in candidate_sql
    assert "on conflict (run_id, symbol, model, horizon_days)" in connection.batches[0][0].lower()
    assert summary[0]["sample_count"] == 8
    assert summary[0]["bucket"] == "all"
    assert summary[0]["avg_mae"] == -0.031
    summary_sql = connection.statements[1][0].lower()
    assert "signal_results" in summary_sql
    assert "avg(outcome.mae)" in summary_sql
    assert "outcome.entry_date > run.as_of_date" in summary_sql


def _stock_signal() -> StockSignal:
    return StockSignal(
        instrument=Instrument.from_secid("1.600000", "浦发银行"),
        as_of_date=date(2026, 8, 11),
        signal_date=date(2026, 8, 11),
        channel=SignalChannel.CONFIRMED_TREND,
        grade=Grade.B_PLUS,
        public_bucket=PublicBucket.TOP10,
        prediction_tier=None,
        fundamental_priority=2,
        dif=0.1,
        dea=0.05,
        macd_hist=0.1,
        gap=-0.05,
        convergence_speed=None,
        x1=None,
        x1_change_pct=None,
        projected_days=None,
        ma20=10,
        ma30=9.8,
        ma60=9.5,
        close_vs_ma20=0.05,
        close_vs_ma30=0.07,
        close_vs_ma60=0.1,
        volume_ratio_5_20=1.2,
        bottom_divergence=False,
        top_divergence=False,
        signal_age_days=0,
        dif_above_zero=True,
        histogram_improvement=0.2,
        ma_structure_score=1,
        volume_score=1.2,
        risk_score=0,
        reason="近3日确认金叉",
        confirm_price=10.6,
        invalidation_price=9.85,
        risk=None,
    )
