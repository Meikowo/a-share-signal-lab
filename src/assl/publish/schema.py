from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any

from assl.domain import Coverage, StockSignal


@dataclass(frozen=True, slots=True)
class PublicCoverage:
    universe_count: int
    covered_count: int
    missing_count: int
    coverage_ratio: float
    publishable: bool


@dataclass(frozen=True, slots=True)
class PublicCandidate:
    rank: int | None
    symbol: str
    name: str
    bucket: str | None
    grade: str
    signal_type: str
    signal_date: str | None
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
    reason: str
    confirm_price: float | None
    invalidation_price: float | None
    risk: str | None
    outcomes: tuple[dict[str, Any], ...]

    @classmethod
    def from_signal(cls, signal: StockSignal, rank: int | None) -> PublicCandidate:
        return cls(
            rank=rank,
            symbol=signal.instrument.symbol,
            name=signal.instrument.name,
            bucket=signal.public_bucket.value if signal.public_bucket else None,
            grade=signal.grade.value,
            signal_type=signal.channel.value,
            signal_date=signal.signal_date.isoformat() if signal.signal_date else None,
            dif=signal.dif,
            dea=signal.dea,
            macd_hist=signal.macd_hist,
            gap=signal.gap,
            convergence_speed=signal.convergence_speed,
            x1=signal.x1,
            x1_change_pct=signal.x1_change_pct,
            projected_days=signal.projected_days,
            ma20=signal.ma20,
            ma30=signal.ma30,
            ma60=signal.ma60,
            close_vs_ma20=signal.close_vs_ma20,
            close_vs_ma30=signal.close_vs_ma30,
            close_vs_ma60=signal.close_vs_ma60,
            volume_ratio_5_20=signal.volume_ratio_5_20,
            bottom_divergence=signal.bottom_divergence,
            top_divergence=signal.top_divergence,
            reason=signal.reason,
            confirm_price=signal.confirm_price,
            invalidation_price=signal.invalidation_price,
            risk=signal.risk,
            outcomes=(),
        )


@dataclass(frozen=True, slots=True)
class PublicSnapshot:
    schema_version: str
    as_of_date: str
    generated_at: str
    algorithm_version: str
    source: str
    coverage: PublicCoverage
    summary: dict[str, int]
    top10: tuple[PublicCandidate, ...]
    p1: tuple[PublicCandidate, ...]
    p2: tuple[PublicCandidate, ...]
    risk_watch: tuple[PublicCandidate, ...]
    outcome_summary: tuple[dict[str, Any], ...]
    disclaimer: str

    @classmethod
    def from_signals(
        cls,
        *,
        as_of_date: date,
        generated_at: datetime,
        algorithm_version: str,
        source: str,
        coverage: Coverage,
        top10: tuple[StockSignal, ...],
        p1: tuple[StockSignal, ...],
        p2: tuple[StockSignal, ...],
        risk_watch: tuple[StockSignal, ...],
        outcome_summary: tuple[dict[str, Any], ...],
    ) -> PublicSnapshot:
        ratio = coverage.covered_count / coverage.universe_count
        public_coverage = PublicCoverage(
            universe_count=coverage.universe_count,
            covered_count=coverage.covered_count,
            missing_count=len(coverage.missing_symbols),
            coverage_ratio=ratio,
            publishable=coverage.publishable,
        )
        return cls(
            schema_version="1",
            as_of_date=as_of_date.isoformat(),
            generated_at=generated_at.isoformat(),
            algorithm_version=algorithm_version,
            source=source,
            coverage=public_coverage,
            summary={
                "top10_count": len(top10),
                "p1_count": len(p1),
                "p2_count": len(p2),
                "risk_count": len(risk_watch),
            },
            top10=tuple(
                PublicCandidate.from_signal(signal, rank)
                for rank, signal in enumerate(top10, start=1)
            ),
            p1=tuple(PublicCandidate.from_signal(signal, None) for signal in p1),
            p2=tuple(PublicCandidate.from_signal(signal, None) for signal in p2),
            risk_watch=tuple(PublicCandidate.from_signal(signal, None) for signal in risk_watch),
            outcome_summary=outcome_summary,
            disclaimer="仅用于候选池与研究优先级，不构成确定买入建议。",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
