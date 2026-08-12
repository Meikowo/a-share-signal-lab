from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlgorithmConfig:
    version: str
    fast: int
    slow: int
    signal: int
    ma_windows: tuple[int, int, int]
    publish_coverage: float
    rounding_digits: int
    grade_order: tuple[str, ...]
    ranking_order: tuple[str, ...]

    @classmethod
    def macd_v1(cls) -> AlgorithmConfig:
        return cls(
            version="macd-v1",
            fast=12,
            slow=26,
            signal=9,
            ma_windows=(20, 30, 60),
            publish_coverage=0.98,
            rounding_digits=6,
            grade_order=("强S", "S", "A+", "A", "B+", "B", "未评级"),
            ranking_order=(
                "fundamental_priority",
                "grade",
                "signal_age_days",
                "dif_above_zero",
                "histogram_improvement",
                "ma_structure_score",
                "volume_score",
                "risk_score",
                "symbol",
            ),
        )


@dataclass(frozen=True, slots=True)
class Settings:
    database_url: str

    @classmethod
    def from_env(cls) -> Settings:
        database_url = os.environ.get("ASSL_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("ASSL_DATABASE_URL is required")
        return cls(database_url=database_url)
