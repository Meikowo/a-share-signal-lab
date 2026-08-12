import os
from datetime import date

import pytest

from assl.domain import Instrument
from assl.market.tencent import TencentClient

pytestmark = pytest.mark.network


def test_known_a_share_returns_completed_qfq_history():
    if os.environ.get("ASSL_RUN_LIVE_TENCENT") != "1":
        pytest.skip("set ASSL_RUN_LIVE_TENCENT=1 to run live market-data smoke")

    bars = TencentClient().fetch_daily(
        Instrument.from_secid("1.600000", "浦发银行"),
        start=date(2026, 1, 1),
        end=date(2026, 8, 11),
        count=180,
    )

    assert len(bars) >= 60
    assert bars[-1].trade_date == date(2026, 8, 11)
    assert all(bar.trade_date <= date(2026, 8, 11) for bar in bars)
