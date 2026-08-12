import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from assl.domain import Bar, Instrument
from assl.market.tencent import ParsedDaily, TencentClient, parse_tencent_payload

FIXTURE = Path(__file__).parent / "fixtures" / "tencent_qfq.json"


def fixture_payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_qfq_prefers_qfqday_and_obeys_cutoff():
    result = parse_tencent_payload(
        "sh600000", fixture_payload(), cutoff=date(2026, 8, 11)
    )

    assert result.bars[-1].trade_date == date(2026, 8, 11)
    assert result.bars[-1].close == 10.60
    assert all(bar.trade_date <= date(2026, 8, 11) for bar in result.bars)
    assert result.name == "浦发银行"
    assert result.fallback_used is False


def test_parse_records_unadjusted_fallback():
    payload = fixture_payload()
    payload["data"]["sh600000"]["qfqday"] = []

    result = parse_tencent_payload(
        "sh600000", payload, cutoff=date(2026, 8, 11)
    )

    assert result.fallback_used is True
    assert result.adjustment == "day"


@respx.mock
def test_fetch_daily_builds_exact_qfq_request_and_retries_429():
    route = respx.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(200, json=fixture_payload()),
        ]
    )
    delays = []
    client = TencentClient(sleep=delays.append)
    instrument = Instrument.from_secid("1.600000", "浦发银行")

    bars = client.fetch_daily(
        instrument,
        start=date(2026, 1, 1),
        end=date(2026, 8, 11),
        count=180,
    )

    assert len(route.calls) == 2
    request = route.calls[-1].request
    assert request.url.params["param"] == (
        "sh600000,day,2026-01-01,2026-08-11,180,qfq"
    )
    assert bars[-1].trade_date == date(2026, 8, 11)
    assert delays == [0.7]


def test_parse_rejects_missing_symbol_node():
    with pytest.raises(ValueError, match="sh600000"):
        parse_tencent_payload("sh600000", {"data": {}}, date(2026, 8, 11))


def test_fetch_many_records_but_excludes_unadjusted_fallback(monkeypatch):
    instrument = Instrument.from_secid("1.600000", "浦发银行")
    fallback = ParsedDaily(
        bars=parse_tencent_payload(
            "sh600000",
            {
                "data": {
                    "sh600000": {
                        "day": [["2026-08-11", "10", "10", "10", "10", "1"]]
                    }
                }
            },
            date(2026, 8, 11),
        ).bars,
        name="浦发银行",
        adjustment="day",
        fallback_used=True,
    )
    client = TencentClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: None)))
    monkeypatch.setattr(client, "_fetch_parsed", lambda *args: fallback)

    batch = client.fetch_many((instrument,), date(2026, 8, 11), {})

    assert batch.fallback_symbols == ("600000",)
    assert "600000" not in batch.bars_by_symbol
    assert batch.errors["600000"] == "qfq_unavailable"


def test_fetch_many_accepts_raw_csi300_index_as_adjustment_equivalent(monkeypatch):
    instrument = Instrument("000300", "沪深300", "SH", "1.000300")
    fallback = ParsedDaily(
        bars=(Bar("000300", date(2026, 8, 11), 4000, 4010, 3990, 4005, 1),),
        name="沪深300",
        adjustment="day",
        fallback_used=True,
    )
    client = TencentClient(client=httpx.Client(transport=httpx.MockTransport(lambda r: None)))
    monkeypatch.setattr(client, "_fetch_parsed", lambda *args: fallback)

    batch = client.fetch_many((instrument,), date(2026, 8, 11), {})

    assert batch.bars_by_symbol["000300"] == fallback.bars
    assert batch.fallback_symbols == ()
    assert batch.errors == {}
