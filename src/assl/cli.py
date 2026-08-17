from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import uuid4

from assl.config import AlgorithmConfig, Settings
from assl.db import AsslRepository
from assl.domain import WatchlistVersion
from assl.market.tencent import TencentClient
from assl.pipeline import DailyPipeline
from assl.watchlist import diff_watchlists, load_watchlist, watchlist_hash


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assl",
        description="A-Share Signal Lab private screening pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command")
    sync = subparsers.add_parser(
        "sync-watchlist",
        help="Preview or apply an immutable private watchlist version.",
    )
    sync.add_argument("path", type=Path, help="JSON export to normalize and compare")
    sync.add_argument("--apply", action="store_true", help="Persist the new version")
    sync.add_argument("--source", default="manual-sync", help="Private source label")
    run_daily = subparsers.add_parser(
        "run-daily",
        help="Run one idempotent private daily screening.",
    )
    run_daily.add_argument("--as-of", type=date.fromisoformat)
    run_daily.add_argument(
        "--offline",
        action="store_true",
        help="Use only cached qfq bars and forbid market-data requests.",
    )
    backfill = subparsers.add_parser(
        "backfill",
        help="Reconstruct recent sessions from cached qfq bars.",
    )
    backfill.add_argument(
        "--sessions",
        type=_session_count,
        default=22,
        help="Number of recent trading sessions to reconstruct (1-62).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "sync-watchlist":
        return _sync_watchlist(args)
    if args.command == "run-daily":
        return _run_daily(args)
    if args.command == "backfill":
        return _backfill(args)
    return 0


def _sync_watchlist(args: argparse.Namespace) -> int:
    members = load_watchlist(args.path)
    digest = watchlist_hash(members)
    repository = AsslRepository(Settings.from_env().database_url)

    with repository.transaction() as connection:
        latest = repository.latest_watchlist(connection)
        old_members = (
            repository.load_watchlist_members(connection, latest.id) if latest else ()
        )
        diff = diff_watchlists(old_members, members)
        print(
            f"old={len(old_members)} new={len(members)} "
            f"added={len(diff.added)} removed={len(diff.removed)} "
            f"changed={len(diff.changed)}"
        )
        changed_symbols = sorted(
            {item.instrument.symbol for item in (*diff.added, *diff.removed)}
            | {item.after.instrument.symbol for item in diff.changed}
        )
        if changed_symbols:
            preview = changed_symbols[:20]
            print(
                f"changed symbols (showing {len(preview)}/{len(changed_symbols)}): "
                + ",".join(preview)
            )

        if not args.apply:
            print("dry-run: no database changes")
            return 0

        existing = repository.find_watchlist_by_hash(connection, digest)
        if existing is not None:
            print(f"identical watchlist already exists: version={existing.id}")
            return 0

        version = WatchlistVersion(
            id=uuid4(),
            created_at=datetime.now(UTC),
            source=args.source,
            item_count=len(members),
            content_sha256=digest,
            note=f"previous_version={latest.id}" if latest else None,
        )
        repository.insert_watchlist_version(connection, version, members)
        print(f"applied version={version.id} items={version.item_count}")
        return 0


def _run_daily(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    pipeline = DailyPipeline(
        AsslRepository(settings.database_url),
        TencentClient(),
        AlgorithmConfig.macd_v1(),
    )
    summary = pipeline.run(args.as_of, offline=args.offline)
    print(
        f"status={summary.status} as_of={summary.as_of_date} "
        f"coverage={summary.coverage.covered_count}/"
        f"{summary.coverage.universe_count} run={summary.run_id}"
    )
    return 0 if summary.status in {"succeeded", "skipped"} else 1


def _backfill(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    repository = AsslRepository(settings.database_url)
    pipeline = DailyPipeline(repository, TencentClient(), AlgorithmConfig.macd_v1())
    end_date = pipeline.latest_completed_date()
    with repository.transaction() as connection:
        dates = repository.recent_trade_dates(
            connection, "000300", end_date, args.sessions
        )
    if not dates:
        print("completed=0/0 error=no cached CSI 300 trading calendar")
        return 1

    completed = 0
    for day in dates:
        summary = pipeline.run(day, offline=True)
        if summary.status not in {"succeeded", "skipped"}:
            print(f"completed={completed}/{len(dates)} failed_as_of={day}")
            return 1
        completed += 1
    print(
        f"completed={completed}/{len(dates)} first={dates[0]} last={dates[-1]} "
        "mode=retrospective-current-watchlist"
    )
    return 0


def _session_count(value: str) -> int:
    sessions = int(value)
    if sessions < 1 or sessions > 62:
        raise argparse.ArgumentTypeError("sessions must be between 1 and 62")
    return sessions


if __name__ == "__main__":
    raise SystemExit(main())
