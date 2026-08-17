from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict
from datetime import date, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from assl.config import AlgorithmConfig
from assl.domain import (
    Bar,
    Coverage,
    Instrument,
    RunError,
    RunKey,
    RunSummary,
    StockSignal,
    WatchlistMember,
    WatchlistVersion,
)
from assl.outcomes import CandidateOutcome, OutcomeCandidateRef
from assl.publish.schema import PublicSnapshot

_DATABASE_URL = re.compile(r"postgres(?:ql)?://\S+", re.IGNORECASE)


def _sanitize_error(value: str) -> str:
    return _DATABASE_URL.sub("[redacted-database-url]", value)[:1000]


def _execute_many(
    connection: Connection,
    statement: str,
    params_seq: Iterable[Sequence[object]],
) -> None:
    with connection.cursor() as cursor:
        cursor.executemany(statement, params_seq)


def _watchlist_version_from_row(row: object) -> WatchlistVersion:
    return WatchlistVersion(
        id=row["id"],
        created_at=row["created_at"],
        source=row["source"],
        item_count=row["item_count"],
        content_sha256=row["content_sha256"],
        note=row["note"],
    )


class AsslRepository:
    """Private PostgreSQL persistence for ASSL."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        # Transaction-mode Supavisor does not support named prepared statements.
        with psycopg.connect(
            self.database_url,
            prepare_threshold=None,
            row_factory=dict_row,
        ) as connection:
            with connection.transaction():
                yield connection

    def latest_watchlist(self, connection: Connection) -> WatchlistVersion | None:
        row = connection.execute(
            """
            select id, created_at, source, item_count, content_sha256, note
            from assl_private.watchlist_versions
            order by created_at desc, id desc
            limit 1
            """
        ).fetchone()
        if row is None:
            return None
        return _watchlist_version_from_row(row)

    def find_watchlist_by_hash(
        self, connection: Connection, content_sha256: str
    ) -> WatchlistVersion | None:
        row = connection.execute(
            """
            select id, created_at, source, item_count, content_sha256, note
            from assl_private.watchlist_versions
            where content_sha256 = %s
            limit 1
            """,
            (content_sha256,),
        ).fetchone()
        return _watchlist_version_from_row(row) if row is not None else None

    def load_watchlist_members(
        self, connection: Connection, version_id: UUID
    ) -> tuple[WatchlistMember, ...]:
        rows = connection.execute(
            """
            select symbol, name, exchange, fundamental_priority, theme_tags
            from assl_private.watchlist_members
            where watchlist_version_id = %s
            order by symbol
            """,
            (version_id,),
        ).fetchall()
        return tuple(
            WatchlistMember(
                instrument=Instrument(
                    symbol=row["symbol"],
                    name=row["name"],
                    exchange=row["exchange"],
                    secid=("1." if row["exchange"] == "SH" else "0.") + row["symbol"],
                ),
                fundamental_priority=row["fundamental_priority"],
                theme_tags=tuple(row["theme_tags"] or ()),
            )
            for row in rows
        )

    def insert_watchlist_version(
        self,
        connection: Connection,
        version: WatchlistVersion,
        members: Sequence[WatchlistMember],
    ) -> UUID:
        connection.execute(
            """
            insert into assl_private.watchlist_versions
                (id, created_at, source, item_count, content_sha256, note)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                version.id,
                version.created_at,
                version.source,
                version.item_count,
                version.content_sha256,
                version.note,
            ),
        )
        _execute_many(
            connection,
            """
            insert into assl_private.watchlist_members
                (watchlist_version_id, symbol, name, exchange,
                 fundamental_priority, theme_tags)
            values (%s, %s, %s, %s, %s, %s)
            """,
            (
                (
                    version.id,
                    member.instrument.symbol,
                    member.instrument.name,
                    member.instrument.exchange,
                    member.fundamental_priority,
                    Jsonb(list(member.theme_tags)),
                )
                for member in members
            ),
        )
        return version.id

    def ensure_algorithm_version(
        self,
        connection: Connection,
        config: AlgorithmConfig,
        code_sha: str,
    ) -> str:
        connection.execute(
            """
            insert into assl_private.algorithm_versions
                (id, code_sha, config, description)
            values (%s, %s, %s, %s)
            on conflict (id) do nothing
            """,
            (
                config.version,
                code_sha,
                Jsonb(asdict(config)),
                "ASSL deterministic MACD/divergence/predictive-cross configuration",
            ),
        )
        return config.version

    def find_run(
        self,
        connection: Connection,
        key: RunKey,
    ) -> RunSummary | None:
        row = connection.execute(
            """
            select id, as_of_date, status, universe_count, covered_count,
                   missing_symbols, source_timestamp, result_sha256
            from assl_private.screening_runs
            where as_of_date = %s
              and watchlist_version_id = %s
              and algorithm_version_id = %s
            """,
            (key.as_of_date, key.watchlist_version_id, key.algorithm_version_id),
        ).fetchone()
        if row is None:
            return None
        universe_count = row["universe_count"]
        covered_count = row["covered_count"]
        coverage = Coverage(
            universe_count=universe_count,
            covered_count=covered_count,
            missing_symbols=tuple(row["missing_symbols"] or ()),
            source_timestamp=row["source_timestamp"],
            publishable=row["status"] == "succeeded",
        )
        return RunSummary(
            run_id=row["id"],
            as_of_date=row["as_of_date"],
            status=row["status"],
            coverage=coverage,
            result_sha256=row["result_sha256"],
        )

    def latest_bar_dates(
        self,
        connection: Connection,
        symbols: Sequence[str],
    ) -> dict[str, date]:
        if not symbols:
            return {}
        rows = connection.execute(
            """
            select symbol, max(trade_date) as trade_date
            from assl_private.daily_bars
            where symbol = any(%s)
              and adjustment = 'qfq'
              and source = 'tencent'
            group by symbol
            """,
            (list(symbols),),
        ).fetchall()
        return {row["symbol"]: row["trade_date"] for row in rows}

    def recent_trade_dates(
        self,
        connection: Connection,
        symbol: str,
        end_date: date,
        limit: int,
    ) -> tuple[date, ...]:
        if limit < 1:
            raise ValueError("trade-date limit must be positive")
        rows = connection.execute(
            """
            select trade_date
            from assl_private.daily_bars
            where symbol = %s
              and trade_date <= %s
              and adjustment = 'qfq'
              and source = 'tencent'
            order by trade_date desc
            limit %s
            """,
            (symbol, end_date, limit),
        ).fetchall()
        return tuple(sorted(row["trade_date"] for row in rows))

    def load_bars(
        self,
        connection: Connection,
        symbols: Sequence[str],
        end_date: date,
        limit: int = 180,
    ) -> dict[str, tuple[Bar, ...]]:
        if not symbols:
            return {}
        rows = connection.execute(
            """
            select symbol, trade_date, open, high, low, close, volume
            from (
                select symbol, trade_date, open, high, low, close, volume,
                       row_number() over (
                           partition by symbol order by trade_date desc
                       ) as row_number
                from assl_private.daily_bars
                where symbol = any(%s)
                  and trade_date <= %s
                  and adjustment = 'qfq'
                  and source = 'tencent'
            ) recent
            where row_number <= %s
            order by symbol, trade_date
            """,
            (list(symbols), end_date, limit),
        ).fetchall()
        result: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
        for row in rows:
            result[row["symbol"]].append(
                Bar(
                    symbol=row["symbol"],
                    trade_date=row["trade_date"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return {symbol: tuple(bars) for symbol, bars in result.items()}

    def get_snapshot_hash(
        self,
        connection: Connection,
        as_of_date: date,
        algorithm_version: str,
    ) -> str | None:
        row = connection.execute(
            """
            select payload_sha256
            from assl_private.published_snapshots
            where as_of_date = %s and algorithm_version_id = %s
            """,
            (as_of_date, algorithm_version),
        ).fetchone()
        return row["payload_sha256"] if row is not None else None

    def insert_snapshot(
        self,
        connection: Connection,
        run_id: UUID,
        snapshot: PublicSnapshot,
        digest: str,
    ) -> None:
        connection.execute(
            """
            insert into assl_private.published_snapshots
                (run_id, as_of_date, algorithm_version_id, payload, payload_sha256)
            values (%s, %s, %s, %s, %s)
            """,
            (
                run_id,
                date.fromisoformat(snapshot.as_of_date),
                snapshot.algorithm_version,
                Jsonb(snapshot.to_dict()),
                digest,
            ),
        )

    def list_snapshot_payloads(
        self,
        algorithm_version: str,
        *,
        connection: Connection | None = None,
    ) -> tuple[dict[str, object], ...]:
        if connection is None:
            with self.transaction() as opened:
                return self.list_snapshot_payloads(algorithm_version, connection=opened)
        rows = connection.execute(
            """
            select payload
            from assl_private.published_snapshots
            where algorithm_version_id = %s
            order by as_of_date
            """,
            (algorithm_version,),
        ).fetchall()
        return tuple(row["payload"] for row in rows)

    def list_public_candidate_outcomes(
        self,
        algorithm_version: str,
        *,
        connection: Connection | None = None,
    ) -> tuple[dict[str, object], ...]:
        if connection is None:
            with self.transaction() as opened:
                return self.list_public_candidate_outcomes(
                    algorithm_version, connection=opened
                )
        rows = connection.execute(
            """
            select run.as_of_date,
                   outcome.symbol,
                   outcome.horizon_days,
                   outcome.entry_date,
                   outcome.exit_date,
                   outcome.net_return::double precision as net_return,
                   outcome.mae::double precision as mae
            from assl_private.candidate_outcomes outcome
            join assl_private.screening_runs run on run.id = outcome.run_id
            join assl_private.signal_results sr
              on sr.run_id = outcome.run_id and sr.symbol = outcome.symbol
            where run.algorithm_version_id = %s
              and run.status = 'succeeded'
              and outcome.model = 'fixed_horizon'
              and outcome.net_return is not null
              and outcome.entry_date > run.as_of_date
              and sr.public_bucket in ('top10', 'p1', 'p2')
            order by run.as_of_date, outcome.symbol, outcome.horizon_days
            """,
            (algorithm_version,),
        ).fetchall()
        return tuple(
            {
                "as_of_date": row["as_of_date"],
                "symbol": row["symbol"],
                "horizon_days": row["horizon_days"],
                "entry_date": row["entry_date"],
                "exit_date": row["exit_date"],
                "net_return": row["net_return"],
                "mae": row["mae"],
            }
            for row in rows
        )

    def list_public_outcome_summary(
        self,
        algorithm_version: str,
        *,
        connection: Connection | None = None,
    ) -> tuple[dict[str, object], ...]:
        if connection is None:
            with self.transaction() as opened:
                return self.list_public_outcome_summary(
                    algorithm_version, connection=opened
                )
        return self.outcome_summary(connection, algorithm_version)

    def upsert_bars(
        self,
        connection: Connection,
        bars: Sequence[Bar],
        source_timestamp: datetime,
    ) -> int:
        rows = tuple(
            (
                bar.symbol,
                bar.trade_date,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.volume,
                "qfq",
                "tencent",
                source_timestamp,
            )
            for bar in bars
        )
        if not rows:
            return 0
        _execute_many(
            connection,
            """
            insert into assl_private.daily_bars
                (symbol, trade_date, open, high, low, close, volume,
                 adjustment, source, source_timestamp)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (symbol, trade_date, adjustment, source) do update set
                open = excluded.open,
                high = excluded.high,
                low = excluded.low,
                close = excluded.close,
                volume = excluded.volume,
                source_timestamp = excluded.source_timestamp,
                ingested_at = now()
            where excluded.source_timestamp > daily_bars.source_timestamp
            """,
            rows,
        )
        return len(rows)

    def start_run(
        self,
        connection: Connection,
        key: RunKey,
        universe_count: int,
    ) -> UUID:
        proposed_id = uuid4()
        row = connection.execute(
            """
            insert into assl_private.screening_runs
                (id, as_of_date, watchlist_version_id, algorithm_version_id,
                 status, universe_count)
            values (%s, %s, %s, %s, 'running', %s)
            on conflict (as_of_date, watchlist_version_id, algorithm_version_id)
            do nothing
            returning id
            """,
            (
                proposed_id,
                key.as_of_date,
                key.watchlist_version_id,
                key.algorithm_version_id,
                universe_count,
            ),
        ).fetchone()
        if row is not None:
            return row["id"]

        existing = connection.execute(
            """
            select id
            from assl_private.screening_runs
            where as_of_date = %s
              and watchlist_version_id = %s
              and algorithm_version_id = %s
            """,
            (key.as_of_date, key.watchlist_version_id, key.algorithm_version_id),
        ).fetchone()
        if existing is None:
            raise RuntimeError("screening run conflict did not return an existing row")
        return existing["id"]

    def insert_signal_results(
        self,
        connection: Connection,
        run_id: UUID,
        ranked_signals: Sequence[tuple[int | None, StockSignal]],
    ) -> None:
        _execute_many(
            connection,
            """
            insert into assl_private.signal_results
                (run_id, symbol, overall_rank, public_bucket, signal_channel,
                 grade, signal_date, dif, dea, macd_hist, gap, gap_convergence,
                 x1, x1_change_pct, projected_days, ma20, ma30, ma60,
                 close_vs_ma20, close_vs_ma30, close_vs_ma60,
                 volume_ratio_5_20, bottom_divergence, top_divergence,
                 confirm_price, invalidation_price, details)
            values (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                (
                    run_id,
                    signal.instrument.symbol,
                    rank,
                    signal.public_bucket.value if signal.public_bucket else None,
                    signal.channel.value,
                    signal.grade.value,
                    signal.signal_date,
                    signal.dif,
                    signal.dea,
                    signal.macd_hist,
                    signal.gap,
                    signal.convergence_speed,
                    signal.x1,
                    signal.x1_change_pct,
                    signal.projected_days,
                    signal.ma20,
                    signal.ma30,
                    signal.ma60,
                    signal.close_vs_ma20,
                    signal.close_vs_ma30,
                    signal.close_vs_ma60,
                    signal.volume_ratio_5_20,
                    signal.bottom_divergence,
                    signal.top_divergence,
                    signal.confirm_price,
                    signal.invalidation_price,
                    Jsonb(
                        {
                            "reason": signal.reason,
                            "risk": signal.risk,
                            "prediction_tier": signal.prediction_tier,
                            "fundamental_priority": signal.fundamental_priority,
                            "signal_age_days": signal.signal_age_days,
                            "dif_above_zero": signal.dif_above_zero,
                            "histogram_improvement": signal.histogram_improvement,
                            "ma_structure_score": signal.ma_structure_score,
                            "volume_score": signal.volume_score,
                            "risk_score": signal.risk_score,
                        }
                    ),
                )
                for rank, signal in ranked_signals
            ),
        )

    def list_outcome_candidates(
        self,
        connection: Connection,
        algorithm_version: str,
        before_date: date,
    ) -> tuple[OutcomeCandidateRef, ...]:
        rows = connection.execute(
            """
            select sr.run_id, sr.symbol, sr.signal_date
            from assl_private.signal_results sr
            join assl_private.screening_runs run on run.id = sr.run_id
            where run.algorithm_version_id = %s
              and run.status = 'succeeded'
              and run.as_of_date < %s
              and sr.public_bucket in ('top10', 'p1', 'p2')
              and sr.signal_date is not null
            order by run.as_of_date, sr.symbol
            """,
            (algorithm_version, before_date),
        ).fetchall()
        return tuple(
            OutcomeCandidateRef(
                run_id=row["run_id"],
                symbol=row["symbol"],
                signal_date=row["signal_date"],
            )
            for row in rows
        )

    def upsert_candidate_outcomes(
        self,
        connection: Connection,
        outcomes: Sequence[CandidateOutcome],
    ) -> int:
        if not outcomes:
            return 0
        rows = tuple(
            (
                outcome.run_id,
                outcome.symbol,
                outcome.model,
                outcome.horizon_days,
                outcome.entry_date,
                outcome.entry_price,
                outcome.exit_date,
                outcome.exit_price,
                outcome.gross_return,
                outcome.net_return,
                outcome.benchmark_return,
                outcome.excess_return,
                outcome.mfe,
                outcome.mae,
                outcome.exit_reason,
                outcome.cost_model_version,
            )
            for outcome in outcomes
        )
        _execute_many(
            connection,
            """
            insert into assl_private.candidate_outcomes
                (run_id, symbol, model, horizon_days, entry_date, entry_price,
                 exit_date, exit_price, gross_return, net_return,
                 benchmark_return, excess_return, mfe, mae, exit_reason,
                 cost_model_version)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s)
            on conflict (run_id, symbol, model, horizon_days) do update set
                entry_date = excluded.entry_date,
                entry_price = excluded.entry_price,
                exit_date = excluded.exit_date,
                exit_price = excluded.exit_price,
                gross_return = excluded.gross_return,
                net_return = excluded.net_return,
                benchmark_return = excluded.benchmark_return,
                excess_return = excluded.excess_return,
                mfe = excluded.mfe,
                mae = excluded.mae,
                exit_reason = excluded.exit_reason,
                cost_model_version = excluded.cost_model_version,
                updated_at = now()
            """,
            rows,
        )
        return len(rows)

    def outcome_summary(
        self,
        connection: Connection,
        algorithm_version: str,
    ) -> tuple[dict[str, object], ...]:
        rows = connection.execute(
            """
            with eligible as (
                select sr.public_bucket::text as bucket,
                       outcome.horizon_days,
                       outcome.net_return,
                       outcome.excess_return,
                       outcome.mae
                from assl_private.candidate_outcomes outcome
                join assl_private.screening_runs run on run.id = outcome.run_id
                join assl_private.signal_results sr
                  on sr.run_id = outcome.run_id and sr.symbol = outcome.symbol
                where run.algorithm_version_id = %s
                  and run.status = 'succeeded'
                  and outcome.model = 'fixed_horizon'
                  and outcome.net_return is not null
                  and outcome.entry_date > run.as_of_date
                  and sr.public_bucket in ('top10', 'p1', 'p2')
            )
            select 'all' as bucket,
                   outcome.horizon_days,
                   count(*)::integer as sample_count,
                   avg((outcome.net_return > 0)::integer)::double precision as win_rate,
                   avg(outcome.net_return)::double precision as avg_net_return,
                   avg(outcome.excess_return)::double precision as avg_excess_return,
                   avg(outcome.mae)::double precision as avg_mae
            from eligible outcome
            group by outcome.horizon_days
            union all
            select outcome.bucket,
                   outcome.horizon_days,
                   count(*)::integer as sample_count,
                   avg((outcome.net_return > 0)::integer)::double precision as win_rate,
                   avg(outcome.net_return)::double precision as avg_net_return,
                   avg(outcome.excess_return)::double precision as avg_excess_return,
                   avg(outcome.mae)::double precision as avg_mae
            from eligible outcome
            group by outcome.bucket, outcome.horizon_days
            order by bucket, horizon_days
            """,
            (algorithm_version,),
        ).fetchall()
        return tuple(
            {
                "bucket": row["bucket"],
                "horizon_days": row["horizon_days"],
                "sample_count": row["sample_count"],
                "win_rate": row["win_rate"],
                "avg_net_return": row["avg_net_return"],
                "avg_excess_return": row["avg_excess_return"],
                "avg_mae": row["avg_mae"],
            }
            for row in rows
        )

    def finish_run(
        self,
        connection: Connection,
        run_id: UUID,
        status: str,
        coverage: Coverage,
        error: RunError | None = None,
        result_sha256: str | None = None,
    ) -> None:
        ratio = coverage.covered_count / coverage.universe_count
        connection.execute(
            """
            update assl_private.screening_runs set
                status = %s,
                covered_count = %s,
                coverage_ratio = %s,
                missing_symbols = %s,
                source_timestamp = %s,
                finished_at = now(),
                result_sha256 = %s,
                error_stage = %s,
                error_summary = %s
            where id = %s
            """,
            (
                status,
                coverage.covered_count,
                ratio,
                Jsonb(list(coverage.missing_symbols)),
                coverage.source_timestamp,
                result_sha256,
                error.stage if error else None,
                _sanitize_error(error.summary) if error else None,
                run_id,
            ),
        )
