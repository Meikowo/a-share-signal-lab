from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assl.domain import Instrument, WatchlistMember, content_sha256


@dataclass(frozen=True, slots=True)
class WatchlistChange:
    before: WatchlistMember
    after: WatchlistMember


@dataclass(frozen=True, slots=True)
class WatchlistDiff:
    added: tuple[WatchlistMember, ...]
    removed: tuple[WatchlistMember, ...]
    changed: tuple[WatchlistChange, ...]


def normalize_watchlist(payload: object) -> tuple[WatchlistMember, ...]:
    rows = _extract_rows(payload)
    members: dict[str, WatchlistMember] = {}
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ValueError(f"watchlist row {index + 1} must be an object")
        secid = str(raw.get("secid", "")).strip()
        name = str(raw.get("name", "")).strip()
        if not secid:
            raise ValueError(f"watchlist row {index + 1} is missing secid")

        try:
            instrument = Instrument.from_secid(secid, name or secid.rsplit(".", 1)[-1])
        except ValueError:
            # The source export can include ETFs, indices, and sector boards.
            continue

        supplied_code = str(raw.get("code", "")).strip()
        if supplied_code and supplied_code != instrument.symbol:
            raise ValueError(
                f"code {supplied_code} conflicts with secid {secid} at row {index + 1}"
            )
        priority = raw.get("fundamental_priority", 0)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ValueError(f"fundamental priority at row {index + 1} must be an integer")
        tags = _normalize_tags(raw.get("theme_tags", ()), index)
        member = WatchlistMember(instrument, priority, tags)

        existing = members.get(instrument.symbol)
        if existing is not None and existing != member:
            raise ValueError(f"conflicting duplicate symbol {instrument.symbol}")
        members[instrument.symbol] = member

    if not members:
        raise ValueError("watchlist contains no supported A-shares")
    return tuple(members[symbol] for symbol in sorted(members))


def load_watchlist(path: str | Path) -> tuple[WatchlistMember, ...]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    return normalize_watchlist(payload)


def diff_watchlists(
    old: Sequence[WatchlistMember],
    new: Sequence[WatchlistMember],
) -> WatchlistDiff:
    old_by_symbol = {member.instrument.symbol: member for member in old}
    new_by_symbol = {member.instrument.symbol: member for member in new}
    added_symbols = sorted(new_by_symbol.keys() - old_by_symbol.keys())
    removed_symbols = sorted(old_by_symbol.keys() - new_by_symbol.keys())
    shared_symbols = sorted(old_by_symbol.keys() & new_by_symbol.keys())
    return WatchlistDiff(
        added=tuple(new_by_symbol[symbol] for symbol in added_symbols),
        removed=tuple(old_by_symbol[symbol] for symbol in removed_symbols),
        changed=tuple(
            WatchlistChange(old_by_symbol[symbol], new_by_symbol[symbol])
            for symbol in shared_symbols
            if old_by_symbol[symbol] != new_by_symbol[symbol]
        ),
    )


def watchlist_hash(members: Sequence[WatchlistMember]) -> str:
    records = [
        {
            "symbol": member.instrument.symbol,
            "name": member.instrument.name,
            "exchange": member.instrument.exchange,
            "secid": member.instrument.secid,
            "fundamental_priority": member.fundamental_priority,
            "theme_tags": list(member.theme_tags),
        }
        for member in sorted(members, key=lambda item: item.instrument.symbol)
    ]
    return content_sha256(records)


def _extract_rows(payload: object) -> Sequence[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in ("items", "data", "watchlist"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("watchlist JSON must be an array or contain an items array")


def _normalize_tags(value: object, index: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list | tuple):
        raise ValueError(f"theme_tags at row {index + 1} must be an array")
    tags: set[str] = set()
    for tag in value:
        if not isinstance(tag, str) or not tag.strip():
            raise ValueError(f"theme_tags at row {index + 1} must contain strings")
        tags.add(tag.strip())
    return tuple(sorted(tags))
