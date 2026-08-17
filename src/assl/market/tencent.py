from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from assl.domain import Bar, Instrument
from assl.market.quality import validate_bars

TENCENT_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
HEADERS = {
    "Referer": "https://gu.qq.com/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/140 Safari/537.36"
    ),
}
RETRY_DELAYS = (0.7, 1.4, 2.8, 5.6)


@dataclass(frozen=True, slots=True)
class ParsedDaily:
    bars: tuple[Bar, ...]
    name: str
    adjustment: str
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class FetchBatch:
    bars_by_symbol: Mapping[str, tuple[Bar, ...]]
    names_by_symbol: Mapping[str, str]
    fallback_symbols: tuple[str, ...]
    errors: Mapping[str, str]
    source_timestamp: datetime


def parse_tencent_payload(
    symbol: str,
    payload: Mapping[str, Any],
    cutoff: date,
) -> ParsedDaily:
    node = (payload.get("data") or {}).get(symbol)
    if not isinstance(node, Mapping):
        raise ValueError(f"Tencent response is missing symbol node {symbol}")

    qfq_rows = node.get("qfqday") or []
    fallback_used = not bool(qfq_rows)
    raw_rows = qfq_rows or node.get("day") or []
    code = symbol[2:]
    bars: list[Bar] = []
    for row in raw_rows:
        if not isinstance(row, list | tuple) or len(row) < 6:
            continue
        trade_date = date.fromisoformat(str(row[0]))
        if trade_date > cutoff:
            continue
        bars.append(
            Bar(
                symbol=code,
                trade_date=trade_date,
                open=float(row[1]),
                close=float(row[2]),
                high=float(row[3]),
                low=float(row[4]),
                volume=float(row[5]),
            )
        )

    qt = node.get("qt") or {}
    quote = qt.get(symbol) if isinstance(qt, Mapping) else None
    name = str(quote[1]).strip() if isinstance(quote, list) and len(quote) > 1 else ""
    return ParsedDaily(
        bars=validate_bars(tuple(bars), cutoff),
        name=name,
        adjustment="day" if fallback_used else "qfq",
        fallback_used=fallback_used,
    )


class TencentClient:
    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_workers: int = 8,
    ) -> None:
        if max_workers < 1 or max_workers > 8:
            raise ValueError("max_workers must be between 1 and 8")
        self.client = client or httpx.Client(
            timeout=20,
            headers=HEADERS,
            trust_env=False,
        )
        self.sleep = sleep
        self.max_workers = max_workers

    def fetch_daily(
        self,
        instrument: Instrument,
        start: date,
        end: date,
        count: int,
    ) -> tuple[Bar, ...]:
        return self._fetch_parsed(instrument, start, end, count).bars

    def fetch_many(
        self,
        instruments: Sequence[Instrument],
        cutoff: date,
        existing_latest: Mapping[str, date],
        count: int = 180,
    ) -> FetchBatch:
        bars_by_symbol: dict[str, tuple[Bar, ...]] = {}
        names_by_symbol: dict[str, str] = {}
        fallback_symbols: list[str] = []
        errors: dict[str, str] = {}
        source_timestamp = datetime.now(UTC)

        def fetch(item: Instrument) -> ParsedDaily:
            latest = existing_latest.get(item.symbol)
            start = latest + timedelta(days=1) if latest else cutoff - timedelta(days=400)
            return self._fetch_parsed(item, start, cutoff, count)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(fetch, item): item for item in instruments}
            for future in as_completed(futures):
                item = futures[future]
                try:
                    result = future.result()
                    if result.name:
                        names_by_symbol[item.symbol] = result.name
                    is_csi300_index = item.secid == "1.000300"
                    if result.fallback_used and not is_csi300_index:
                        fallback_symbols.append(item.symbol)
                        errors[item.symbol] = "qfq_unavailable"
                        continue
                    bars_by_symbol[item.symbol] = result.bars
                except Exception as exc:  # noqa: BLE001
                    errors[item.symbol] = _safe_error(exc)

        return FetchBatch(
            bars_by_symbol=bars_by_symbol,
            names_by_symbol=names_by_symbol,
            fallback_symbols=tuple(sorted(fallback_symbols)),
            errors=errors,
            source_timestamp=source_timestamp,
        )

    def _fetch_parsed(
        self,
        instrument: Instrument,
        start: date,
        end: date,
        count: int,
    ) -> ParsedDaily:
        params = {
            "param": (
                f"{instrument.tencent_symbol},day,{start:%Y-%m-%d},"
                f"{end:%Y-%m-%d},{count},qfq"
            )
        }
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                response = self.client.get(TENCENT_URL, params=params)
                response.raise_for_status()
                return parse_tencent_payload(
                    instrument.tencent_symbol, response.json(), cutoff=end
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                retryable_error: Exception = exc
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429 and exc.response.status_code < 500:
                    raise
                retryable_error = exc
            if attempt == len(RETRY_DELAYS):
                raise RuntimeError(_safe_error(retryable_error)) from retryable_error
            self.sleep(RETRY_DELAYS[attempt])
        raise AssertionError("unreachable")


def _safe_error(error: Exception) -> str:
    return f"{type(error).__name__}: {error}"[:500]
