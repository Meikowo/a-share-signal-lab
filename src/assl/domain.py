from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID


class SignalChannel(StrEnum):
    CONFIRMED_TREND = "confirmed_trend"
    BOTTOM_DIVERGENCE = "bottom_divergence"
    PREDICTIVE_CROSS = "predictive_cross"
    NEUTRAL = "neutral"


class Grade(StrEnum):
    STRONG_S = "强S"
    S = "S"
    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    UNRATED = "未评级"


class PublicBucket(StrEnum):
    TOP10 = "top10"
    P1 = "p1"
    P2 = "p2"
    RISK_WATCH = "risk_watch"


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    name: str
    exchange: str
    secid: str

    @property
    def tencent_symbol(self) -> str:
        return ("sh" if self.exchange == "SH" else "sz") + self.symbol

    @classmethod
    def from_secid(cls, secid: str, name: str) -> Instrument:
        try:
            market, symbol = secid.split(".", 1)
        except ValueError as exc:
            raise ValueError(f"not a supported A-share secid: {secid}") from exc

        is_she_a = market == "0" and symbol.startswith(
            ("000", "001", "002", "003", "300", "301")
        )
        is_sse_a = market == "1" and symbol.startswith(
            ("600", "601", "603", "605", "688", "689")
        )
        if len(symbol) != 6 or not symbol.isdigit() or not (is_she_a or is_sse_a):
            raise ValueError(f"not a supported A-share secid: {secid}")

        exchange = "SH" if market == "1" else "SZ"
        return cls(symbol=symbol, name=name.strip(), exchange=exchange, secid=secid)


@dataclass(frozen=True, slots=True)
class WatchlistMember:
    instrument: Instrument
    fundamental_priority: int = 0
    theme_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.fundamental_priority not in (0, 1, 2):
            raise ValueError("fundamental priority must be 0, 1, or 2")


@dataclass(frozen=True, slots=True)
class Bar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        prices = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(value) and value > 0 for value in prices):
            raise ValueError("OHLC prices must be finite and positive")
        if self.high < max(self.open, self.low, self.close):
            raise ValueError("high must be greater than or equal to open, low, and close")
        if self.low > min(self.open, self.high, self.close):
            raise ValueError("low must be less than or equal to open, high, and close")
        if not math.isfinite(self.volume) or self.volume < 0:
            raise ValueError("volume must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class Divergence:
    kind: str
    confirmed: bool
    first_index: int
    second_index: int
    first_price: float
    second_price: float
    first_indicator: float
    second_indicator: float


@dataclass(frozen=True, slots=True)
class Prediction:
    tier: str | None
    gap: float
    convergence_speed: float
    x1: float
    x1_change_pct: float
    projected_days: float
    valid: bool
    invalidation_reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WatchlistVersion:
    id: UUID
    created_at: datetime
    source: str
    item_count: int
    content_sha256: str
    note: str | None


@dataclass(frozen=True, slots=True)
class Coverage:
    universe_count: int
    covered_count: int
    missing_symbols: tuple[str, ...]
    source_timestamp: datetime | None
    publishable: bool


@dataclass(frozen=True, slots=True)
class RunKey:
    as_of_date: date
    watchlist_version_id: UUID
    algorithm_version_id: str


@dataclass(frozen=True, slots=True)
class RunError:
    stage: str
    summary: str


@dataclass(frozen=True, slots=True)
class StockSignal:
    instrument: Instrument
    as_of_date: date
    signal_date: date | None
    channel: SignalChannel
    grade: Grade
    public_bucket: PublicBucket | None
    prediction_tier: str | None
    fundamental_priority: int
    dif: float
    dea: float
    macd_hist: float
    gap: float
    convergence_speed: float | None
    x1: float | None
    x1_change_pct: float | None
    projected_days: float | None
    ma20: float | None
    ma30: float | None
    ma60: float | None
    close_vs_ma20: float | None
    close_vs_ma30: float | None
    close_vs_ma60: float | None
    volume_ratio_5_20: float | None
    bottom_divergence: bool
    top_divergence: bool
    signal_age_days: int
    dif_above_zero: bool
    histogram_improvement: float
    ma_structure_score: float
    volume_score: float
    risk_score: float
    reason: str
    confirm_price: float | None
    invalidation_price: float | None
    risk: str | None


@dataclass(frozen=True, slots=True)
class RankedScreen:
    top10: tuple[StockSignal, ...]
    p1: tuple[StockSignal, ...]
    p2: tuple[StockSignal, ...]
    risk_watch: tuple[StockSignal, ...]


@dataclass(frozen=True, slots=True)
class RunSummary:
    run_id: UUID
    as_of_date: date
    status: str
    coverage: Coverage
    result_sha256: str | None


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
