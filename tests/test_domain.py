from datetime import date

import pytest

from assl.domain import Bar, Instrument, WatchlistMember, canonical_json, content_sha256


def test_canonical_json_is_order_independent():
    assert canonical_json({"b": 2, "a": 1}) == '{"a":1,"b":2}'
    assert content_sha256({"b": 2, "a": 1}) == content_sha256({"a": 1, "b": 2})


def test_bar_rejects_high_below_close():
    with pytest.raises(ValueError, match="high"):
        Bar("600000", date(2026, 8, 11), 10, 9, 8, 10, 100)


def test_bar_rejects_negative_volume():
    with pytest.raises(ValueError, match="volume"):
        Bar("600000", date(2026, 8, 11), 10, 11, 8, 10, -1)


def test_instrument_normalizes_shanghai_exchange():
    item = Instrument.from_secid("1.600000", "浦发银行")

    assert (item.symbol, item.exchange, item.tencent_symbol) == (
        "600000",
        "SH",
        "sh600000",
    )


def test_instrument_normalizes_shenzhen_exchange():
    item = Instrument.from_secid("0.000001", "平安银行")

    assert (item.symbol, item.exchange, item.tencent_symbol) == (
        "000001",
        "SZ",
        "sz000001",
    )


@pytest.mark.parametrize("secid", ["1.510300", "90.BK0475", "0.399001", "1.60000"])
def test_instrument_rejects_non_a_share_secid(secid):
    with pytest.raises(ValueError, match="A-share"):
        Instrument.from_secid(secid, "not-an-a-share")


def test_watchlist_member_rejects_priority_outside_private_scale():
    instrument = Instrument.from_secid("1.600000", "浦发银行")

    with pytest.raises(ValueError, match="priority"):
        WatchlistMember(instrument, fundamental_priority=3)
