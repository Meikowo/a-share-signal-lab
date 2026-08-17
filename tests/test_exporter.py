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
