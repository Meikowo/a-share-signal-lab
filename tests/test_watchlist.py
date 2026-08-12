import json
from pathlib import Path

import pytest

from assl.watchlist import (
    diff_watchlists,
    load_watchlist,
    normalize_watchlist,
    watchlist_hash,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_normalize_keeps_only_a_shares_and_deduplicates():
    payload = [
        {"secid": "1.600000", "name": "浦发银行"},
        {"secid": "1.600000", "name": "浦发银行"},
        {"secid": "1.510300", "name": "ETF"},
        {"secid": "90.BK0475", "name": "板块"},
    ]

    rows = normalize_watchlist(payload)

    assert [(row.instrument.symbol, row.instrument.exchange) for row in rows] == [
        ("600000", "SH")
    ]


def test_normalize_derives_code_and_preserves_private_metadata():
    rows = normalize_watchlist(
        [
            {
                "secid": "0.000001",
                "code": "",
                "name": "平安银行",
                "fundamental_priority": 2,
                "theme_tags": ["银行", "红利", "银行"],
            }
        ]
    )

    assert rows[0].instrument.symbol == "000001"
    assert rows[0].fundamental_priority == 2
    assert rows[0].theme_tags == ("红利", "银行")


def test_normalize_uses_symbol_when_export_omits_name():
    rows = normalize_watchlist([{"secid": "1.605133", "name": ""}])

    assert rows[0].instrument.name == "605133"


def test_normalize_rejects_conflicting_duplicate_metadata():
    payload = [
        {"secid": "1.600000", "name": "浦发银行", "fundamental_priority": 1},
        {"secid": "1.600000", "name": "浦发银行", "fundamental_priority": 2},
    ]

    with pytest.raises(ValueError, match="conflicting duplicate.*600000"):
        normalize_watchlist(payload)


def test_diff_is_deterministic_and_detects_metadata_change():
    old = load_watchlist(FIXTURES / "watchlist_old.json")
    new = load_watchlist(FIXTURES / "watchlist_new.json")

    diff = diff_watchlists(old, new)

    assert [item.instrument.symbol for item in diff.added] == ["000002"]
    assert [item.instrument.symbol for item in diff.removed] == ["000001"]
    assert [item.after.instrument.symbol for item in diff.changed] == ["600000"]


def test_hash_is_independent_of_input_order():
    payload = json.loads((FIXTURES / "watchlist_old.json").read_text("utf-8"))

    assert watchlist_hash(normalize_watchlist(payload)) == watchlist_hash(
        normalize_watchlist(list(reversed(payload)))
    )


def test_load_watchlist_reports_json_line_and_column(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('[{"secid":}]', encoding="utf-8")

    with pytest.raises(ValueError, match=r"line 1, column \d+"):
        load_watchlist(path)
