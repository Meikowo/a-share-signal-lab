from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID

import pandas as pd

from assl.domain import Bar, StockSignal

SIX_PLACES = Decimal("0.000001")
ZERO_UUID = UUID(int=0)


@dataclass(frozen=True, slots=True)
class CandidateOutcome:
    run_id: UUID
    symbol: str
    model: str
    horizon_days: int | None
    entry_date: date | None
    entry_price: Decimal | None
    detection_date: date | None
    exit_date: date | None
    exit_price: Decimal | None
    gross_return: Decimal | None
    net_return: Decimal | None
    benchmark_return: Decimal | None
    excess_return: Decimal | None
    mfe: Decimal | None
    mae: Decimal | None
    exit_reason: str | None
    non_evaluable_reason: str | None
    cost_model_version: str


@dataclass(frozen=True, slots=True)
class OutcomeCandidateRef:
    run_id: UUID
    symbol: str
    detection_date: date


@dataclass(frozen=True, slots=True)
class ExitTrigger:
    reason: str
    detection_date: date


def matured_horizons(
    detection_date: date,
    bars: tuple[Bar, ...],
) -> tuple[int, ...]:
    completed = len({bar.trade_date for bar in bars if bar.trade_date > detection_date})
    return tuple(horizon for horizon in (1, 5, 10, 20) if completed >= horizon)


def evaluate_fixed_horizon(
    signal: StockSignal,
    bars: tuple[Bar, ...],
    benchmark_bars: tuple[Bar, ...],
    horizon: int,
    cost_bps: int = 10,
    *,
    run_id: UUID = ZERO_UUID,
) -> CandidateOutcome | None:
    return evaluate_fixed_horizon_ref(
        OutcomeCandidateRef(run_id, signal.instrument.symbol, signal.as_of_date),
        bars,
        benchmark_bars,
        horizon,
        cost_bps,
    )


def evaluate_fixed_horizon_ref(
    candidate: OutcomeCandidateRef,
    bars: tuple[Bar, ...],
    benchmark_bars: tuple[Bar, ...],
    horizon: int,
    cost_bps: int = 10,
) -> CandidateOutcome | None:
    if horizon not in (1, 5, 10, 20):
        raise ValueError("horizon must be 1, 5, 10, or 20")

    benchmark_after = sorted(
        (bar for bar in benchmark_bars if bar.trade_date > candidate.detection_date),
        key=lambda bar: bar.trade_date,
    )
    if len(benchmark_after) < horizon:
        return None
    entry_date = benchmark_after[0].trade_date
    exit_date = benchmark_after[horizon - 1].trade_date
    stock_by_date = {bar.trade_date: bar for bar in bars}
    benchmark_by_date = {bar.trade_date: bar for bar in benchmark_bars}
    entry_bar = stock_by_date.get(entry_date)
    exit_bar = stock_by_date.get(exit_date)
    benchmark_entry = benchmark_by_date.get(entry_date)
    benchmark_exit = benchmark_by_date.get(exit_date)
    if not all((entry_bar, exit_bar, benchmark_entry, benchmark_exit)):
        return None
    if entry_bar.open <= 0 or exit_bar.close <= 0:
        return None

    entry_price = _decimal(entry_bar.open)
    exit_price = _decimal(exit_bar.close)
    cost = Decimal(cost_bps) / Decimal(10000)
    adjusted_entry = entry_price * (Decimal(1) + cost)
    adjusted_exit = exit_price * (Decimal(1) - cost)
    gross_return = _return(exit_price, entry_price)
    net_return = _return(adjusted_exit, adjusted_entry)
    benchmark_return = _return(_decimal(benchmark_exit.close), _decimal(benchmark_entry.open))
    interval = [bar for bar in bars if entry_date <= bar.trade_date <= exit_date]
    mfe = max(_return(_decimal(bar.high), adjusted_entry) for bar in interval)
    mae = min(_return(_decimal(bar.low), adjusted_entry) for bar in interval)
    return CandidateOutcome(
        run_id=candidate.run_id,
        symbol=candidate.symbol,
        model="fixed_horizon",
        horizon_days=horizon,
        entry_date=entry_date,
        entry_price=_quantize(entry_price),
        detection_date=exit_date,
        exit_date=exit_date,
        exit_price=_quantize(exit_price),
        gross_return=gross_return,
        net_return=net_return,
        benchmark_return=benchmark_return,
        excess_return=_quantize(net_return - benchmark_return),
        mfe=mfe,
        mae=mae,
        exit_reason=f"fixed_{horizon}d",
        non_evaluable_reason=None,
        cost_model_version="cost-v1",
    )


def detect_signal_exit(
    indicator_frame: pd.DataFrame,
    top_divergence_dates: set[date],
) -> ExitTrigger | None:
    required = {"date", "close", "ma20", "gap"}
    missing = required - set(indicator_frame.columns)
    if missing:
        raise ValueError(f"exit frame is missing columns: {sorted(missing)}")
    if len(indicator_frame) < 2:
        return None

    dates = pd.to_datetime(indicator_frame["date"])
    for index in range(1, len(indicator_frame)):
        detection_date = dates.iloc[index].date()
        close = float(indicator_frame["close"].iloc[index])
        ma20 = float(indicator_frame["ma20"].iloc[index])
        if close < ma20 * 0.985:
            return ExitTrigger("below_ma20_1_5pct", detection_date)
        if index >= 2:
            gaps = indicator_frame["gap"].astype(float)
            if gaps.iloc[index] > gaps.iloc[index - 1] > gaps.iloc[index - 2]:
                return ExitTrigger("gap_expanded_two_days", detection_date)
        if detection_date in top_divergence_dates:
            return ExitTrigger("top_divergence", detection_date)
    return None


def evaluate_signal_exit(
    signal: StockSignal,
    bars: tuple[Bar, ...],
    indicator_frame: pd.DataFrame,
    benchmark_bars: tuple[Bar, ...],
    cost_bps: int = 10,
    *,
    top_divergence_dates: set[date] | None = None,
    run_id: UUID = ZERO_UUID,
) -> CandidateOutcome | None:
    if signal.signal_date is None:
        return None
    stock_after = sorted(
        (bar for bar in bars if bar.trade_date > signal.signal_date),
        key=lambda bar: bar.trade_date,
    )
    if not stock_after:
        return None
    entry_bar = stock_after[0]
    if entry_bar.open <= 0:
        return None
    trigger = detect_signal_exit(indicator_frame, top_divergence_dates or set())
    if trigger is None:
        return None
    if trigger.detection_date < entry_bar.trade_date:
        return None
    exit_bar = next((bar for bar in stock_after if bar.trade_date > trigger.detection_date), None)
    if exit_bar is None or exit_bar.open <= 0:
        return None

    benchmark_by_date = {bar.trade_date: bar for bar in benchmark_bars}
    benchmark_entry = benchmark_by_date.get(entry_bar.trade_date)
    benchmark_exit = benchmark_by_date.get(exit_bar.trade_date)
    if benchmark_entry is None or benchmark_exit is None:
        return None

    entry_price = _decimal(entry_bar.open)
    exit_price = _decimal(exit_bar.open)
    cost = Decimal(cost_bps) / Decimal(10000)
    adjusted_entry = entry_price * (Decimal(1) + cost)
    adjusted_exit = exit_price * (Decimal(1) - cost)
    gross_return = _return(exit_price, entry_price)
    net_return = _return(adjusted_exit, adjusted_entry)
    benchmark_return = _return(_decimal(benchmark_exit.open), _decimal(benchmark_entry.open))
    interval = [
        bar for bar in bars if entry_bar.trade_date <= bar.trade_date <= exit_bar.trade_date
    ]
    return CandidateOutcome(
        run_id=run_id,
        symbol=signal.instrument.symbol,
        model="signal_exit",
        horizon_days=None,
        entry_date=entry_bar.trade_date,
        entry_price=_quantize(entry_price),
        detection_date=trigger.detection_date,
        exit_date=exit_bar.trade_date,
        exit_price=_quantize(exit_price),
        gross_return=gross_return,
        net_return=net_return,
        benchmark_return=benchmark_return,
        excess_return=_quantize(net_return - benchmark_return),
        mfe=max(_return(_decimal(bar.high), adjusted_entry) for bar in interval),
        mae=min(_return(_decimal(bar.low), adjusted_entry) for bar in interval),
        exit_reason=trigger.reason,
        non_evaluable_reason=None,
        cost_model_version="cost-v1",
    )


def _decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _return(exit_price: Decimal, entry_price: Decimal) -> Decimal:
    return _quantize(exit_price / entry_price - Decimal(1))


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(SIX_PLACES, rounding=ROUND_HALF_EVEN)
