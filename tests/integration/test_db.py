import os
from datetime import UTC, date, datetime
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from assl.db import AsslRepository
from assl.domain import (
    Bar,
    Instrument,
    RunKey,
    WatchlistMember,
    WatchlistVersion,
)

pytestmark = pytest.mark.integration


def test_private_ledger_round_trip_and_idempotent_run():
    database_url = os.environ.get("ASSL_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("ASSL_TEST_DATABASE_URL is not configured")

    repository = AsslRepository(database_url)
    version_id = uuid4()
    version = WatchlistVersion(
        id=version_id,
        created_at=datetime.now(UTC),
        source="integration-test",
        item_count=2,
        content_sha256=uuid4().hex + uuid4().hex,
        note=None,
    )
    members = (
        WatchlistMember(Instrument.from_secid("1.600000", "浦发银行"), 2),
        WatchlistMember(Instrument.from_secid("0.000001", "平安银行"), 1),
    )
    bars = (
        Bar("600000", date(2026, 8, 11), 10, 11, 9, 10.5, 1000),
        Bar("000001", date(2026, 8, 11), 12, 13, 11, 12.5, 2000),
    )

    with psycopg.connect(
        database_url,
        prepare_threshold=None,
        row_factory=dict_row,
        autocommit=False,
    ) as connection:
        repository.insert_watchlist_version(connection, version, members)
        repository.upsert_bars(connection, bars, datetime.now(UTC))
        connection.execute(
            """
            insert into assl_private.algorithm_versions
                (id, code_sha, config, description)
            values ('integration-macd-v1', 'integration', %s, 'integration test')
            on conflict (id) do nothing
            """,
            (Jsonb({"fast": 12, "slow": 26, "signal": 9}),),
        )
        key = RunKey(date(2026, 8, 11), version_id, "integration-macd-v1")

        first = repository.start_run(connection, key, universe_count=2)
        second = repository.start_run(connection, key, universe_count=2)

        assert second == first
        assert repository.latest_watchlist(connection).id == version_id
        connection.rollback()
