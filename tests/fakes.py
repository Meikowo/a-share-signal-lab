from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from assl.domain import Coverage, RunSummary, WatchlistVersion


class FakeRepository:
    def __init__(self, members, bars_by_symbol):
        self.members = tuple(members)
        self.bars_by_symbol = {symbol: tuple(bars) for symbol, bars in bars_by_symbol.items()}
        self.version = WatchlistVersion(
            id=UUID("00000000-0000-0000-0000-000000000101"),
            created_at=datetime(2026, 8, 11, tzinfo=UTC),
            source="test",
            item_count=len(self.members),
            content_sha256="a" * 64,
            note=None,
        )
        self.runs = {}
        self.run_count = 0
        self.signal_results = []
        self.snapshots = {}
        self.finished = []
        self.outcome_candidates = ()
        self.outcomes = []
        self.run_modes = []

    @contextmanager
    def transaction(self):
        yield self

    def latest_watchlist(self, connection):
        return self.version

    def load_watchlist_members(self, connection, version_id):
        return self.members

    def ensure_algorithm_version(self, connection, config, code_sha):
        return config.version

    def find_run(self, connection, key):
        return self.runs.get(key)

    def start_run(self, connection, key, universe_count, execution_mode="forward_shadow"):
        self.run_modes.append(execution_mode)
        if key in self.runs:
            return self.runs[key].run_id
        run_id = uuid4()
        self.runs[key] = RunSummary(
            run_id=run_id,
            as_of_date=key.as_of_date,
            status="running",
            coverage=Coverage(universe_count, 0, (), None, False),
            result_sha256=None,
        )
        self.run_count += 1
        return run_id

    def latest_bar_dates(self, connection, symbols):
        return {
            symbol: self.bars_by_symbol[symbol][-1].trade_date
            for symbol in symbols
            if self.bars_by_symbol.get(symbol)
        }

    def upsert_bars(self, connection, bars, source_timestamp):
        for bar in bars:
            current = {item.trade_date: item for item in self.bars_by_symbol.get(bar.symbol, ())}
            current[bar.trade_date] = bar
            self.bars_by_symbol[bar.symbol] = tuple(current[key] for key in sorted(current))
        return len(bars)

    def load_bars(self, connection, symbols, end_date, limit=180):
        return {
            symbol: tuple(
                bar for bar in self.bars_by_symbol.get(symbol, ()) if bar.trade_date <= end_date
            )[-limit:]
            for symbol in symbols
        }

    def insert_signal_results(self, connection, run_id, ranked_signals):
        self.signal_results.extend(ranked_signals)

    def finish_run(self, connection, run_id, status, coverage, error=None, result_sha256=None):
        self.finished.append((run_id, status, coverage, error, result_sha256))
        key = next(key for key, value in self.runs.items() if value.run_id == run_id)
        self.runs[key] = replace(
            self.runs[key],
            status=status,
            coverage=coverage,
            result_sha256=result_sha256,
        )

    def get_snapshot_hash(self, connection, as_of_date, algorithm_version):
        row = self.snapshots.get((as_of_date.isoformat(), algorithm_version))
        return row[0] if row else None

    def insert_snapshot(self, connection, run_id, snapshot, digest):
        self.snapshots[(snapshot.as_of_date, snapshot.algorithm_version)] = (
            digest,
            snapshot.to_dict(),
        )

    def list_outcome_candidates(self, connection, algorithm_version, before_date):
        return tuple(
            candidate
            for candidate in self.outcome_candidates
            if candidate.selection_date < before_date
        )

    def upsert_candidate_outcomes(self, connection, outcomes):
        self.outcomes.extend(outcomes)
        return len(outcomes)

    def outcome_summary(self, connection, algorithm_version):
        return ()


class FakeMarket:
    def __init__(self, batch):
        self.batch = batch
        self.calls = 0

    def fetch_many(self, instruments, cutoff, existing_latest):
        self.calls += 1
        return self.batch
