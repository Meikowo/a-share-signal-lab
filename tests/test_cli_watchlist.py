import json
from contextlib import contextmanager
from uuid import UUID

import assl.cli as cli_module
from assl.domain import WatchlistVersion


class FakeRepository:
    def __init__(self, latest=None, old_members=(), existing=None):
        self.latest = latest
        self.old_members = old_members
        self.existing = existing
        self.inserted = []

    @contextmanager
    def transaction(self):
        yield object()

    def latest_watchlist(self, connection):
        return self.latest

    def load_watchlist_members(self, connection, version_id):
        return self.old_members

    def find_watchlist_by_hash(self, connection, content_sha256):
        return self.existing

    def insert_watchlist_version(self, connection, version, members):
        self.inserted.append((version, members))
        return version.id


def test_sync_watchlist_defaults_to_dry_run_and_caps_change_preview(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "watchlist.json"
    path.write_text(
        json.dumps(
            [
                {"secid": f"0.00{index:04d}", "name": f"股票{index}"}
                for index in range(1, 26)
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    repository = FakeRepository()
    monkeypatch.setenv("ASSL_DATABASE_URL", "unused")
    monkeypatch.setattr(cli_module, "AsslRepository", lambda database_url: repository)

    exit_code = cli_module.main(["sync-watchlist", str(path), "--source", "test"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "dry-run" in output
    assert "new=25 added=25 removed=0 changed=0" in output
    assert "showing 20/25" in output
    assert "000025" not in output
    assert repository.inserted == []


def test_sync_watchlist_apply_inserts_immutable_version(
    tmp_path, monkeypatch, capsys
):
    path = tmp_path / "watchlist.json"
    path.write_text(
        '[{"secid":"1.600000","name":"浦发银行"}]', encoding="utf-8"
    )
    repository = FakeRepository()
    monkeypatch.setenv("ASSL_DATABASE_URL", "unused")
    monkeypatch.setattr(cli_module, "AsslRepository", lambda database_url: repository)

    exit_code = cli_module.main(
        ["sync-watchlist", str(path), "--source", "manual", "--apply"]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "applied version=" in output
    assert len(repository.inserted) == 1
    version, members = repository.inserted[0]
    assert version.source == "manual"
    assert version.item_count == 1
    assert members[0].instrument.symbol == "600000"


def test_sync_watchlist_apply_reuses_identical_hash(tmp_path, monkeypatch, capsys):
    path = tmp_path / "watchlist.json"
    path.write_text(
        '[{"secid":"1.600000","name":"浦发银行"}]', encoding="utf-8"
    )
    existing = WatchlistVersion(
        id=UUID("00000000-0000-0000-0000-000000000041"),
        created_at=None,
        source="earlier",
        item_count=1,
        content_sha256="c" * 64,
        note=None,
    )
    repository = FakeRepository(existing=existing)
    monkeypatch.setenv("ASSL_DATABASE_URL", "unused")
    monkeypatch.setattr(cli_module, "AsslRepository", lambda database_url: repository)

    exit_code = cli_module.main(["sync-watchlist", str(path), "--apply"])

    assert exit_code == 0
    assert "already exists" in capsys.readouterr().out
    assert repository.inserted == []
