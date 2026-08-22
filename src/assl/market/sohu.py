from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import date, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from assl.domain import MarketTurnover

SOHU_HISTORY_URL = "https://q.stock.sohu.com/hisHq"
HEADERS = {
    "Referer": "https://q.stock.sohu.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    ),
}
SHANGHAI_COMPOSITE = "zs_000001"
SHENZHEN_COMPOSITE = "zs_399106"
RETRY_DELAYS = (0.7, 1.4, 2.8)
REQUEST_GAP_SECONDS = 0.25
AMOUNT_UNIT = 10_000.0


class SohuMarketActivityClient:
    """Read exchange-wide daily turnover for the shadow experiment."""

    def __init__(
        self,
        *,
        fetch_json: Callable[[str, Mapping[str, str]], Any] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.fetch_json = fetch_json or _fetch_json
        self.sleep = sleep

    def fetch_daily(self, end: date, *, count: int = 180) -> tuple[MarketTurnover, ...]:
        if count < 120:
            raise ValueError("market activity requires at least 120 sessions")
        shanghai = self._fetch_amounts(SHANGHAI_COMPOSITE, end, count)
        self.sleep(REQUEST_GAP_SECONDS)
        shenzhen = self._fetch_amounts(SHENZHEN_COMPOSITE, end, count)
        if set(shanghai) != set(shenzhen):
            raise ValueError("exchange turnover dates do not align")
        aligned_dates = sorted(shanghai)
        if not aligned_dates:
            raise ValueError("no market turnover dates")
        return tuple(
            MarketTurnover(day, shanghai[day], shenzhen[day])
            for day in aligned_dates[-count:]
        )

    def _fetch_amounts(self, code: str, end: date, count: int) -> dict[date, float]:
        start = end - timedelta(days=max(365, count * 2))
        params = {
            "code": code,
            "start": start.strftime("%Y%m%d"),
            "end": end.strftime("%Y%m%d"),
            "stat": "1",
            "order": "D",
            "period": "d",
        }
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                payload = self.fetch_json(SOHU_HISTORY_URL, params)
                break
            except HTTPError as error:
                if error.code != 429 and error.code < 500:
                    raise
                retryable_error: Exception = error
            except (OSError, TimeoutError, URLError) as error:
                retryable_error = error
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(
                    f"market activity request failed: {type(retryable_error).__name__}"
                ) from retryable_error
            self.sleep(RETRY_DELAYS[attempt])
        else:
            raise AssertionError("unreachable")
        return _parse_amount_rows(payload, end)


def _fetch_json(url: str, params: Mapping[str, str]) -> Any:
    request = Request(f"{url}?{urlencode(params)}", headers=HEADERS)
    with urlopen(request, timeout=20) as response:  # noqa: S310
        return json.loads(response.read().decode("gb18030"))


def _parse_amount_rows(payload: Any, cutoff: date) -> dict[date, float]:
    if not isinstance(payload, Sequence) or isinstance(payload, (str, bytes)):
        raise ValueError("Sohu response is not a list")
    if not payload or not isinstance(payload[0], Mapping):
        raise ValueError("Sohu response is missing market data")
    node = payload[0]
    if node.get("status") != 0:
        raise ValueError("Sohu response reports a market data error")
    rows = node.get("hq")
    if not isinstance(rows, list):
        raise ValueError("Sohu response is missing daily turnover rows")
    amounts: dict[date, float] = {}
    for raw in rows:
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            continue
        if len(raw) < 9:
            continue
        trade_day = date.fromisoformat(str(raw[0]))
        amount = float(raw[8]) * AMOUNT_UNIT
        if trade_day <= cutoff and amount > 0:
            amounts[trade_day] = amount
    if not amounts:
        raise ValueError("Sohu response has no valid turnover amounts")
    return amounts
