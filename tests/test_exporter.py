import json
from datetime import UTC, date, datetime

import pytest

from assl.domain import Coverage, Grade
from assl.publish.exporter import (
    ImmutableSnapshotError,
    export_public_bundle,
    persist_snapshot,
)
from assl.publish.schema import PublicSnapshot
from tests.test_ranking import make_signal


class FakeSnapshotRepo:
    def __init__(self):
        self.snapshots = {}
        self.public_outcomes = ()
        self.public_summary = ()
        self.market_regime_inputs = ()

    def get_snapshot_hash(self, connection, as_of_date, algorithm_version):
        row = self.snapshots.get((as_of_date.isoformat(), algorithm_version))
        return row[0] if row else None

    def insert_snapshot(self, connection, run_id, snapshot, digest):
        key = (snapshot.as_of_date, snapshot.algorithm_version)
        self.snapshots[key] = (digest, snapshot.to_dict())

    def list_snapshot_payloads(self, algorithm_version):
        return tuple(
            payload
            for (day, version), (_, payload) in sorted(self.snapshots.items())
            if version == algorithm_version
        )

    def list_public_candidate_outcomes(self, algorithm_version):
        return self.public_outcomes

    def list_public_outcome_summary(self, algorithm_version):
        return self.public_summary

    def list_market_regime_inputs(self, algorithm_version, sessions=22):
        assert sessions is None
        return self.market_regime_inputs


def test_published_snapshot_cannot_be_changed():
    repository = FakeSnapshotRepo()
    snapshot = fixture_snapshot(date(2026, 8, 11))

    digest = persist_snapshot(repository, object(), "run-1", snapshot)

    assert persist_snapshot(repository, object(), "run-1", snapshot) == digest
    changed = fixture_snapshot(date(2026, 8, 11), source="different")
    with pytest.raises(ImmutableSnapshotError):
        persist_snapshot(repository, object(), "run-1", changed)


def test_export_bundle_latest_points_to_newest_success(tmp_path):
    repository = FakeSnapshotRepo()
    for day in (date(2026, 8, 10), date(2026, 8, 11)):
        snapshot = fixture_snapshot(day)
        persist_snapshot(repository, object(), str(day), snapshot)

    manifest = export_public_bundle(repository, tmp_path, "macd-v1")

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["as_of_date"] == "2026-08-11"
    assert manifest.history_dates == ("2026-08-10", "2026-08-11")
    assert (tmp_path / "history" / "2026-08-10.json").exists()
    assert (tmp_path / "methodology.json").exists()
    assert (tmp_path / "experiments" / "market-regime.json").exists()


def test_export_bundle_keeps_baseline_available_when_regime_experiment_fails(tmp_path):
    class BrokenExperimentRepo(FakeSnapshotRepo):
        def list_market_regime_inputs(self, algorithm_version, sessions=22):
            raise RuntimeError("experiment query failed")

    repository = BrokenExperimentRepo()
    snapshot = fixture_snapshot(date(2026, 8, 11))
    persist_snapshot(repository, object(), "run-1", snapshot)

    export_public_bundle(repository, tmp_path, "macd-v1")

    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    experiment = json.loads(
        (tmp_path / "experiments" / "market-regime.json").read_text(encoding="utf-8")
    )
    assert latest["as_of_date"] == "2026-08-11"
    assert experiment["status"] == "unavailable"
    assert experiment["history"] == []


def test_export_bundle_attaches_mature_outcomes_without_mutating_snapshot(tmp_path):
    repository = FakeSnapshotRepo()
    day = date(2026, 8, 12)
    snapshot = fixture_snapshot(day)
    persist_snapshot(repository, object(), "run-1", snapshot)
    repository.public_outcomes = (
        {
            "as_of_date": day,
            "symbol": "600000",
            "horizon_days": 1,
            "entry_date": date(2026, 8, 13),
            "exit_date": date(2026, 8, 13),
            "net_return": 0.024,
            "mae": -0.013,
        },
    )
    repository.public_summary = (
        {
            "bucket": "all",
            "horizon_days": 1,
            "sample_count": 1,
            "win_rate": 1.0,
            "avg_net_return": 0.024,
            "avg_excess_return": 0.01,
            "avg_mae": -0.013,
        },
    )

    export_public_bundle(repository, tmp_path, "macd-v1")

    exported = json.loads(
        (tmp_path / "history" / "2026-08-12.json").read_text(encoding="utf-8")
    )
    assert exported["top10"][0]["outcomes"] == [
        {
            "horizon_days": 1,
            "entry_date": "2026-08-13",
            "exit_date": "2026-08-13",
            "net_return": 0.024,
            "mae": -0.013,
        }
    ]
    assert not repository.snapshots[("2026-08-12", "macd-v1")][1]["top10"][0][
        "outcomes"
    ]
    assert exported["outcome_summary"] == list(repository.public_summary)
    assert not repository.snapshots[("2026-08-12", "macd-v1")][1][
        "outcome_summary"
    ]


def test_export_fails_privacy_scan_before_manifest(tmp_path):
    repository = FakeSnapshotRepo()
    snapshot = fixture_snapshot(date(2026, 8, 11), source="postgresql://secret")
    persist_snapshot(repository, object(), "run", snapshot)

    with pytest.raises(ValueError, match="privacy"):
        export_public_bundle(repository, tmp_path, "macd-v1")

    assert not (tmp_path / "manifest.json").exists()


def fixture_snapshot(day, source="腾讯前复权日线"):
    signal = make_signal("600000", Grade.B_PLUS, priority=2)
    return PublicSnapshot.from_signals(
        as_of_date=day,
        generated_at=datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
        algorithm_version="macd-v1",
        source=source,
        coverage=Coverage(839, 828, tuple(str(i) for i in range(11)), None, True),
        top10=(signal,),
        p1=(),
        p2=(),
        risk_watch=(),
        outcome_summary=(),
    )
