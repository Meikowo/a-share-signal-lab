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
        if summary.status not in {"succeeded", "skk}wг»h‘йм¶»§q«^t	HHМњ
JNЫX\™Ъ[ЋЊ]]ОЬY[™ОЌњМњKњYЩKZXY\ћЩ\Ь^N™›^Ш[YЫ‹Z][\О™›^Y[™Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋЫX\™Ъ[‹X›ЭЫNЊМK™^YXњ›ЭЮЩ›Ыќ\Ъ^™NЊLЫ]\‹\ЬXЪ[™О‹ЊN[NЩ›Ыќ]ЩZYЪЌМШЫЫЬЋ€ОNN_KњYЩKZXY\€^Щ›Ыќ\Ъ^™NЊЋ\ЫX\™Ъ[ЋЋЫ]\‹\ЬXЪ[™О‹KЊЩ[_K™]K\[Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЋN\ЬY[™ОЋ\MЩ›Ыќ\Ъ^™NЊLњШЫЫЬЋ€НMM_K™]K\[Ь[ћЩ\Ь^Nљ[›[™KX›ШЪОЭЪYЌњЪZYЪЌњШ›Ь™\‹\Y]\ОЌL	NШXЪЩЬ›Э[™€МNXMNЫX\™Ъ[‹\љYЪЌЬKљ\›ЮШXЪЩЬ›Э[™€МNNNШЫЫЬЋ€Щ™™ЋШ›Ь™\‹\Y]\ОЊMњЬY[™ОЌЩ\Ь^N™›^Ш[YЫ‹Z][\ОЩ[ќ\ЋЪќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋЫZ[‹ZZYЪЊЌ\Kљ\›ЛZЪXЪЩ\ћЩ›Ыќ\Ъ^™NЊL\ШЫЫЬЋ€ШXX_Kљ\›ИћЩ›Ыќ\Ъ^™NЊМњЫ[™KZZYЪЊKЊНNЫ]\‹\ЬXЪ[™О‹KЊ[NЫX\™Ъ[ЋЊMKљ\›И€[^Щ›Ыќ\Э[N››Ь›X[ШЫЫЬЋ€ЩLШMMЊџKљ\›ИЫX\™Ъ[ЋЊШЫЫЬЋ€ШXXNЩ›Ыќ\Ъ^™NЊLЬЫ[™KZZYЪЊKЌОЫX^]ЪYЌMМKљ\›Л\љ[™ЮЭЪYЊMњЪZYЪЊMњШ›Ь™\ЋЊ\ЫЫYНMMNШ›Ь™\‹\Y]\ОЌL	NЩ\Ь^N™›^Щ›^Y\™XЭ[ЫЋЫЫ[[ЋЪќ\ЭYћKXЫЫќ[ќЩ[ќ\ЋЭ^X[YЫЋЩ[ќ\ЋШ›Ю\ЪYЭОљ[њЩ]ЬМЊЊЊKљ\›Л\љ[™ИЭ›Ы™ЮЩ›Ыќ\Ъ^™NЊЌЬKљ\›Л\љ[™ИЬ[ћЩ›Ыќ\Ъ^™NЊL\ШЫЫЬЋ€ШXXNЫX\™Ъ[‹]ЬЌKљ\›Л\љ[™ИЫX[Щ›Ыќ\Ъ^™NЊLШЫЫЬЋ€НННОЫX\™Ъ[‹]ЬЊЬK›Y]љXЛYЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОњ™\X]
YњЉNШ›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊMЫX\™Ъ[ЋЊNЫЭ™\™›ЭОљY[џK›Y]љXЮЬY[™ОЊЊњЌШ›Ь™\‹\љYЪЊ\ЫЫY\ЉK[[™JNЬЬЪ][ЫЋњ™[]]™_K›Y]љXО›\ЭXЪ[Ш›Ь™\ЋЊK›Y]љXИЭ›Ы™ЮЩ\Ь^N›ШЪОЩ›Ыќ\Ъ^™NЊЌ\K›Y]љXИЬ[ћЩ\Ь^N›ШЪОЩ›Ыќ]ЩZYЪЌЊЩ›Ыќ\Ъ^™NЊLњЫX\™Ъ[‹]ЬЌЬK›Y]љXИЫX[ШЫЫЬЋ€ОNNNЩ›Ыќ\Ъ^™NЊLK›Y]љXЛXШЩ[ќЭ›Ы™ЮШЫЫЬЋќ\ЉK]\
_K›Y]љXЛњљ\ЪИЭ›Ы™ЮШЫЫЬЋќ\ЉK[Ь[™ЩJ_KњЩXЭ[Ы‹ZXYЩ\Ь^N™›^Ш[YЫ‹Z][\О™[™Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋЫX\™Ъ[ЋЊMњKњЩXЭ[Ы‹ZXY‹ќШ]Ъ\ЩXЭ[Ы€ћЩ›Ыќ\Ъ^™NЊЊЫX\™Ъ[ЋЌЬK™љ[\њЮШXЪЩЬ›Э[™ќ\ЉK\ЫЩќ
NШ›Ь™\‹\Y]\ОЋ\ЬY[™ОЊЬK™љ[\њИќ]ЫћШ›Ь™\ЋЊШXЪЩЬ›Э[™ќ[њЬ\™[ќШЫЫЬЋ€НННОЩ›Ыќ\Ъ^™NЊL\ЬY[™ОЌЬLњШ›Ь™\‹\Y]\ОЌЬШЭ\њЫЬЋњЪ[ќ\џK™љ[\њИќ]Ы‹њЩ[XЭYШXЪЩЬ›Э[™€Щ™™ЋШЫЫЬЋ€МLLNШ›Ю\ЪYЭОЊ\ЬМLџKШ[™Y]K]X›^Ш›Ь™\‹]ЬЊ\ЫЫYМЊЊџKќX›KZXYШ[™Y]K\›ЭЮЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОЊ™њ€KЊНYњ€KЌYњ€KЊYњ€ЋШ[YЫ‹Z][\ОЩ[ќ\ЋЩШ\ЊЊKќX›KZXYЬY[™ОЊLњMњШЫЫЬЋ€ОNNNЩ›Ыќ\Ъ^™NЊLKШ[™Y]K\›ЭЮЭЪYЊL	NШ›Ь™\ЋЊШ›Ь™\‹]ЬЊ\ЫЫY\ЉK[[™JNШXЪЩЬ›Э[™€Щ™™ЋЭ^X[YЫЋ›YќЬY[™ОЊMЬMњШЭ\њЫЬЋњЪ[ќ\ЋШЫЫЬЋ€МNNNKШ[™Y]K\›ЭОљЭ™\ћШXЪЩЬ›Э[™€ЩYY_KШ[™Y]K\›ЭИЬ[ћЫZ[‹]ЪYЊKњЭШЪЮЩ\Ь^N™›^Ш[YЫ‹Z][\ОЩ[ќ\ЋЩШ\ЊLЬKњЭШЪИ^Щ›Ыќ\Э[N››Ь›X[ШЫЫЬЋ€ШXXNЩ›Ыќ\Ъ^™NЊLњЭЪYЊNKњЭШЪИћЩ›Ыќ\Ъ^™NЊMKњЭШЪИ€ЫX[Щ\Ь^N›ШЪОШЫЫЬЋ€ОNNNЩ›Ыќ]ЩZYЪЌЩ›Ыќ\Ъ^™NЊLЫX\™Ъ[‹]ЬЌKYЩ^Щ\Ь^Nљ[›[™KX›ШЪОШ›Ь™\ЋЊ\ЫЫYЩШ›Ь™\‹\Y]\ОЌњЬY[™ОЊЬЬЩ›Ыќ\Ъ^™NЊLЩ›Ыќ\Э[N››Ь›X[Щ›Ыќ]ЩZYЪЌМK™ЬYKyo.”Л™ЬYKTЮШ›Ь™\‹XЫЫЬЋ€ЩMXЌШЌШЫЫЬЋќ\ЉK]\
NШXЪЩЬ›Э[™€Щ™™ЌЩЌџK™ЬYKPW
Л™ЬYKP^Ш›Ь™\‹XЫЫЬЋ€ЩY™YNШЫЫЬЋ€ШMXЊYNШXЪЩЬ›Э[™€Щ™™YЌKШ[™Y]K\›ЭИЬ[ЏњЫX[Щ\Ь^N›ШЪОШЫЫЬЋ€ОNNNЩ›Ыќ\Ъ^™NЊLЫX\™Ъ[‹]ЬЌ\ЭЪ]K\ЬXЩN››ЭЬ\ЫЭ™\™›ЭОљY[ЋЭ^[Э™\™›ЭО™[\Ъ\ЯK›Y]љXЬИ‹›]™[ИћЩ›Ыќ\Ъ^™NЊL\K\њ›ЭЮЩ›Ыќ\Ъ^™NЊNШЫЫЬЋ€ШXX_K™[\^ЬY[™ОЌЭ^X[YЫЋЩ[ќ\ЋШЫЫЬЋ€ОNN_KќШ]Ъ\ЩXЭ[ЫћЫX\™Ъ[ЋЌK›Z[љKYЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОњ™\X]
YњЉNЩШ\ЊLЫX\™Ъ[‹]ЬЊMњK›Z[љKXШ\™Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊLњШXЪЩЬ›Э[™€Щ™™ЋЬY[™ОЊNЭ^X[YЫЋ›YќШЭ\њЫЬЋњЪ[ќ\џK›Z[љKXШ\™љЭ™\ћШ›Ь™\‹XЫЫЬЋ€ШџK›Z[љKXШ\™™ЬY^Щ›Ш]њљYЪШЫЫЬЋ€ШMXЊYNЩ›Ыќ\Ъ^™NЊLK›Z[љKXШ\™ћЩ\Ь^N›ШЪЯK›Z[љKXШ\™ЫX[Щ\Ь^N›ШЪОШЫЫЬЋ€ОNNNЫX\™Ъ[‹]ЬЌ\K›Z[љKXШ\™[^Щ\Ь^N›ШЪОЩ›Ыќ\Э[N››Ь›X[Щ›Ыќ\Ъ^™NЊL\ЫX\™Ъ[‹]ЬЊMњKњљ\ЪЛ\ЩXЭ[ЫћШ›Ь™\ЋЊ\ЫЫYЩY™MШXЪЩЬ›Э[™€Щ™™YЌNШ›Ь™\‹\Y]\ОЊLЬЬY[™ОЊЊЊњЩ\Ь^N™›^Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋШ[YЫ‹Z][\ОЩ[ќ\џKњљ\ЪЛ\ЩXЭ[ЫЏ™]Ћ™љ\њЭXЪ[Щ\Ь^N™›^ЩШ\ЊLњШ[YЫ‹Z][\ОЩ[ќ\џKњљ\ЪЛZXЫЫћЭЪYЊЋЪZYЪЊЋШ›Ь™\‹\Y]\ОЌL	NЩ\Ь^N™ЬљYЬXЩKZ][\ОЩ[ќ\ЋШXЪЩЬ›Э[™€ЩЊЩMЋШЫЫЬЋ€ОXMXLЊЩ›Ыќ]ЩZYЪЌМKњљ\ЪЛ\ЩXЭ[Ы€ћЩ›Ыќ\Ъ^™NЊLњKњљ\ЪЛ\ЩXЭ[Ы€ЫX\™Ъ[ЋЊЬШЫЫЬЋ€ОMMЩЋNЩ›Ыќ\Ъ^™NЊLKњљ\ЪЛ\ЩXЭ[Ы€ќ]ЫћШ›Ь™\ЋЊШXЪЩЬ›Э[™ќ[њЬ\™[ќЭ^X[YЫЋ›YќЩ›Ыќ\Ъ^™NЊL\ЫX\™Ъ[‹[YќЊLњШЭ\њЫЬЋњЪ[ќ\џKњљ\ЪЛ\ЩXЭ[Ы€ќ]Ы€ЫX[Щ\Ь^N›ШЪОШЫЫЬЋ€ОXЌШНЊNЫX^]ЪYЊNЫЭ™\™›ЭОљY[ЋЭ^[Э™\™›ЭО™[\Ъ\ОЭЪ]K\ЬXЩN››ЭЬ\K™\ШЫZ[Y\ћЭ^X[YЫЋЩ[ќ\ЋШЫЫЬЋ€ООООЩ›Ыќ\Ъ^™NЊL\Ы[™KZZYЪЊKЌОЫX\™Ъ[‹]ЬЌMЬY[™Л]ЬЊЌШ›Ь™\‹]ЬЊ\ЫЫY\ЉK[[™J_K™\ШЫZ[Y\€ЫX[Щ›Ыќ\Ъ^™NЊLШЫЫЬЋ€ШXX_K›[Щ[XXЪЩ›ЬЬЬЪ][ЫЋ™љ^YЪ[њЩ]ЊШXЪЩЬ›Э[™€МЋЩ\Ь^N™›^Ъќ\ЭYћKXЫЫќ[ќ™›^Y[™Ю‹Z[™^ЌLK›[Щ[ЭЪY›Z[ЉLЊL	JNЪZYЪЊL	NШXЪЩЬ›Э[™€Щ™™ЋЬY[™ОЊОЫЭ™\™›ЭО]]ОЫЭ][™NЊШ›Ю\ЪYЭО‹LЊЊМџK›[Щ[ЫЬЩ^Щ›Ш]њљYЪШ›Ь™\ЋЊШXЪЩЬ›Э[™ќ\ЉK\ЫЩќ
NШ›Ь™\‹\Y]\ОЌL	NЭЪYЊНЪZYЪЊНЩ›Ыќ\Ъ^™NЊЊШЭ\њЫЬЋњЪ[ќ\џK›[Щ[ћЩ›Ыќ\Ъ^™NЊЋЫX\™Ъ[ЋЊMЌ\K›[Щ[€ЫX[Щ›Ыќ\Ъ^™NЊL\ШЫЫЬЋ€ОNNNЩ›Ыќ]ЩZYЪЌЫX\™Ъ[‹[YќЊLK›[Щ[\Э[[X\ћ^ЬY[™ОЊNШXЪЩЬ›Э[™ќ\ЉK\ЫЩќ
NШ›Ь™\‹\Y]\ОЊLњK›[Щ[\Э[[X\ћHЩ›Ыќ\Ъ^™NЊLњЫ[™KZZYЪЊKЌЋЫX\™Ъ[ЋЊLK™]Z[YЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњЋЩШ\Њ\ШXЪЩЬ›Э[™ќ\ЉK[[™JNШ›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊLњЫЭ™\™›ЭОљY[ЋЫX\™Ъ[ЋЊЊK™]Z[YЬљY™]ћШXЪЩЬ›Э[™€Щ™™ЋЬY[™ОЊMњK™]Z[YЬљYЬ[‹›]™[YЬљYЬ[ћЩ\Ь^N›ШЪОШЫЫЬЋ€ОNNNЩ›Ыќ\Ъ^™NЊLK™]Z[YЬљYЭ›Ы™ЮЩ\Ь^N›ШЪОЩ›Ыќ\Ъ^™NЊLЬЫX\™Ъ[‹]ЬЌњK›]™[YЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњЋЩШ\ЊLK›]™[YЬљY™]ћЬY[™ОЊNШ›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊLњK›]™[YЬљYЭ›Ы™ЮЩ\Ь^N›ШЪОЫX\™Ъ[‹]ЬЌњKњљ\ЪЛ[›Э^ШXЪЩЬ›Э[™€Щ™™ЌЩYЋШЫЫЬЋ€ОЌMLYЋШ›Ь™\‹\Y]\ОЊLЬY[™ОЊMЩ›Ыќ\Ъ^™NЊL\ЫX\™Ъ[‹]ЬЊM\Kњљ[X\ћ^ЭЪYЊL	NШ›Ь™\ЋЊШXЪЩЬ›Э[™€МNNNШЫЫЬЋ€Щ™™ЋШ›Ь™\‹\Y]\ОЊLЬY[™ОЊLњЫX\™Ъ[‹]ЬЊЌШЭ\њЫЬЋњЪ[ќ\џKњZ[‹XШ\™Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊM\ЬY[™ОЊМњKњZ[‹XШ\™X™[Щ\Ь^N™›^Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋШ[YЫ‹Z][\ОЩ[ќ\ЋШЫЫЬЋ€НННОЩ›Ыќ\Ъ^™NЊLњKњZ[‹XШ\™Щ[XЭЬY[™ОЋLњШ›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЋШXЪЩЬ›Э[™€Щ™™џKњZ[‹XШ\™ћЫX\™Ъ[‹]ЬЊНKњZ[‹XШ\™ШЫЫЬЋ€НННОЫ[™KZZYЪЊKЌОЩ›Ыќ\Ъ^™NЊLЬKќ[Y[[™^ЫX\™Ъ[‹]ЬЊН\Ш›Ь™\‹[YќЊ\ЫЫY\ЉK[[™JNЩ\Ь^N™ЬљYЩШ\ЊЊњЬY[™Л[YќЊЌKќ[Y[[™H]ћЬЬЪ][ЫЋњ™[]]™_Kќ[Y[[™H]ЏњЬ[ћЬЬЪ][ЫЋXњЫЫ]NЭЪYЋ\ЪZYЪЋ\Ш›Ь™\‹\Y]\ОЌL	NШXЪЩЬ›Э[™€МNNNЫYќ‹LЋ\ЭЬЌKќ[Y[[™HћЩ›Ыќ\Ъ^™NЊLЬKќ[Y[[™HЫX[Щ\Ь^N›ШЪОШЫЫЬЋ€ОNNNЫX\™Ъ[‹]ЬЊЬK›Э]ЫЫYK]X›^ЫX\™Ъ[‹]ЬЊЋШ›Ь™\‹]ЬЊ\ЫЫYМЊЊџK›Э]ЫЫYK]X›O™]ћЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОњ™\X]
YњЉNЬY[™ОЊLЬШ›Ь™\‹X›ЭЫNЊ\ЫЫY\ЉK[[™JNЩ›Ыќ\Ъ^™NЊLњK›]]YШЫЫЬЋ€ОNN_K™[\KXЪ\ќЭ^X[YЫЋЩ[ќ\ЋШXЪЩЬ›Э[™ќ\ЉK\ЫЩќ
NШ›Ь™\‹\Y]\ОЊLњЫX\™Ъ[‹]ЬЊЋЬY[™ОЌK™[\KXЪ\ќЬ[ћЩ›Ыќ\Ъ^™NЊМњШЫЫЬЋ€ШXX_K™[\KXЪ\ќћЩ\Ь^N›ШЪОЫX\™Ъ[‹]ЬЊLњK›Y]ЩYЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњЋЩШ\ЊLњK›Y]ЩYЬљY\ќXЫ^Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊM\ЬY[™ОЊЋK›Y]ЩYЬљY^Щ›Ыќ\Э[N››Ь›X[ШЫЫЬЋ€ШXXNЩ›Ыќ\Ъ^™NЊL\K›Y]ЩYЬљYћЩ›Ыќ\Ъ^™NЊMЬЫX\™Ъ[‹]ЬЊЋK›Y]ЩYЬљYЩ›Ыќ\Ъ^™NЊLњЫ[™KZZYЪЊKЋШЫЫЬЋ€НННЯK›Y]Щ[›Э^ЫX\™Ъ[‹]ЬЊLњKњЭ]^ЫZ[‹ZZYЪЋљЩ\Ь^N™›^Щ›^Y\™XЭ[ЫЋЫЫ[[ЋШ[YЫ‹Z][\ОЩ[ќ\ЋЪќ\ЭYћKXЫЫќ[ќЩ[ќ\ЋЭ^X[YЫЋЩ[ќ\џKњЭ]HШЫЫЬЋ€ОKњЭ]H^ШЫЫЬЋ€МЊЊџKњЬ[›™\ћЭЪYЊМЪZYЪЊМШ›Ь™\ЋЊњЫЫYЩШ›Ь™\‹]ЬXЫЫЬЋ€МЊЊЋШ›Ь™\‹\Y]\ОЌL	NШ[љ[X][ЫЋњЬ[€ЋИ[™X\€[™љ[љ]_PЩ^Yњ[Y\ИЬ[ћЭЮЭ[њЩ›Ь›Nњ›Э]JНЊYК__CBђYYXJX^]ЪYЋL
^ЛњЪYX\ћЬЬЪ][ЫЋњЭXЪЮNЭЬЊЭЪYЊL	NЪZYЪЌЊЩ›^Y\™XЭ[ЫЋњ›ЭОШ[YЫ‹Z][\ОЩ[ќ\ЋЬY[™ОЋ\MШ›Ь™\‹\љYЪЊШ›Ь™\‹X›ЭЫNЊ\ЫЫY\ЉK[[™J_Kњ[™ЬY[™ОЊKњ[™ЫX[њЪYKY›ЫЭЩ\Ь^N››Ы™_KњЪYX\€]ћЩ\Ь^N™›^ЫX\™Ъ[‹[Yќ]]ЯKњЪYX\€]€^Щ›Ыќ\Ъ^™NЊЬY[™ОЋ\KњЪYX\€]€H^Щ›Ыќ\Ъ^™NЊMњKњЪYX\€]€KXЭ]™NYќ\ћШЫЫќ[ќ€€ЋЭЪYЌЪZYЪЌШXЪЩЬ›Э[™€МЊЊЋШ›Ь™\‹\Y]\ОЌL	_[XZ[ћЫX\™Ъ[‹[YќЊKЫЫќ[ќЭЪYШ[КL	HHНњ
NЬY[™Л]ЬЊЋKљ\›ЮЬY[™ОЊЋKљ\›Л\љ[™ЮЩ\Ь^N››Ы™_K›Y]љXЛYЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњџK›Y]љXО›ќXЪ[
Љ^Ш›Ь™\‹\љYЪЊK›Y]љXО›ќXЪ[
[ЉМЉ^Ш›Ь™\‹X›ЭЫNЊ\ЫЫY\ЉK[[™J_KќX›KZXYЩ\Ь^N››Ы™_KШ[™Y]K\›ЭЮЩЬљY][\]KXЫЫ[[њОЊKЌЩњ€Yњ€ЌњЩШ\ЊLKШ[™Y]K\›ЭП‹›Y]љXЬЛШ[™Y]K\›ЭП‹›]™[ЮЩ\Ь^N››Ы™_K›Z[љKYЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњџKњљ\ЪЛ\ЩXЭ[ЫћШ[YЫ‹Z][\О™›^\Э\ќЩШ\ЊMњKњљ\ЪЛ\ЩXЭ[ЫЏ™]Ћ›\ЭXЪ[Щ\Ь^N››Ы™__CB‹ќ[Y[[™Hќ]ЫћЬЬЪ][ЫЋњ™[]]™NШ›Ь™\ЋЊШXЪЩЬ›Э[™ќ[њЬ\™[ќЭ^X[YЫЋ›YќЬY[™ОЊШЫЫЬЋљ[љ\љ]ШЭ\њЫЬЋњЪ[ќ\џKќ[Y[[™Hќ]ЫЏњЬ[ћЬЬЪ][ЫЋXњЫЫ]NЭЪYЋ\ЪZYЪЋ\Ш›Ь™\‹\Y]\ОЌL	NШXЪЩЬ›Э[™€ШXXNЫYќ‹LЋ\ЭЬЌKќ[Y[[™Hќ]Ы‹њЩ[XЭYњЬ[ћШXЪЩЬ›Э[™€МNNNШ›Ю\ЪYЭОЊЩXЩXЩXЯKќ[Y[[™Hќ]ЫЋљЭ™\€ћЭ^YXЫЬ][ЫЋќ[™\›[™_B‹›X‹X\Щ[[™^Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊM\ЬY[™ОЊЋМЩ\Ь^N™›^Ш[YЫ‹Z][\ОЩ[ќ\ЋЪќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋШXЪЩЬ›Э[™€ЩYY_K›X‹X\Щ[[™HћЩ›Ыќ\Ъ^™NЊЊ\ЫX\™Ъ[ЋЋ\K›X‹X\Щ[[™HЩ›Ыќ\Ъ^™NЊLњШЫЫЬЋ€НННОЫX\™Ъ[ЋЊЫ[™KZZYЪЊKЌЯKњЭ]\ЛXЪ\Щ\Ь^Nљ[›[™KX›ШЪОШ›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЋN\ЬY[™ОЌ\\ШЫЫЬЋ€НННОШXЪЩЬ›Э[™€Щ™™ЋЩ›Ыќ\Ъ^™NЊLЭЪ]K\ЬXЩN››ЭЬ\KњЭ]\ЛXЪ\›]™^ШЫЫЬЋќ\ЉKYЭЫЉNШ›Ь™\‹XЫЫЬЋ€ШЋY™ШXЪЩЬ›Э[™€ЩЌ™ЩЋ_K›X‹ZXY[™ЮЩ\Ь^N™›^Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[ЋШ[YЫ‹Z][\О™[™ЫX\™Ъ[ЋЌMњK›X‹ZXY[™ИћЩ›Ыќ\Ъ^™NЊЊЫX\™Ъ[ЋЌЬK›X‹ZXY[™ИЩ›Ыќ\Ъ^™NЊL\ШЫЫЬЋ€ОNNNЫX\™Ъ[ЋЊK™^\љ[Y[ќYЬљYЩ\Ь^N™ЬљYЩЬљY][\]KXЫЫ[[њОЊYњ€YњЋЩШ\ЊLњK™^\љ[Y[ќYЬљY\ќXЫ^Ш›Ь™\ЋЊ\ЫЫY\ЉK[[™JNШ›Ь™\‹\Y]\ОЊM\ЬY[™ОЊЌ\ЫZ[‹ZZYЪЊЊLЩ\Ь^N™›^Щ›^Y\™XЭ[ЫЋЫЫ[[џK™^\љ[Y[ќYЬљY\ќXЫO™]ћЩ\Ь^N™›^Ъќ\ЭYћKXЫЫќ[ќњЬXЩKX™]ЩY[џK™^\љ[Y[ќYЬљY^Щ›Ыќ\Э[N››Ь›X[ШЫЫЬЋ€ШXXNЩ›Ыќ\Ъ^™NЊL\K™^\љ[Y[ќYЬљYћЩ›Ыќ\Ъ^™NЊMЬЫX\™Ъ[ЋЊЋK™^\љ[Y[ќYЬљYЩ›Ыќ\Ъ^™NЊLњЫ[™KZZYЪЊKЌОШЫЫЬЋ€НННОЫX\™Ъ[ЋЊK™^\љ[Y[ќYЬљY›ЫЭ\ћЫX\™Ъ[‹]Ь]]ОЬY[™Л]ЬЊЌШЫЫЬЋ€ШXXNЩ›Ыќ\Ъ^™NЊLK›X‹\ќ[^ЫX\™Ъ[‹]ЬЊLњШ›Ь™\‹[YќЊЬЫЫYМЊЊЋШXЪЩЬ›Э[™ќ\ЉK\ЫЩќ
NЬY[™ОЊЊЌШ›Ь™\‹\Y]\ОЌLњLњK›X‹\ќ[HћЩ›Ыќ\Ъ^™NЊLњK›X‹\ќ[HЩ›Ыќ\Ъ^™NЊL\Ы[™KZZYЪЊKЌОШЫЫЬЋ€НННОЫX\™Ъ[ЋЌњBђYYXJX^]ЪYЌLЊ
^ЛњYЩKZXY\ћШ[YЫ‹Z][\О™›^\Э\ќЩШ\ЊMњKњYЩKZXY\€^Щ›Ыќ\Ъ^™NЊЌK™]K\[Щ›Ыќ\Ъ^™NЊLKљ\›ЮЫZ[‹ZZYЪЊЊЊKљ\›ИћЩ›Ыќ\Ъ^™NЊЌ\K›Y]љXЮЬY[™ОЊNK›Y]љXИЭ›Ы™ЮЩ›Ыќ\Ъ^™NЊЊњKњЩXЭ[Ы‹ZXYЩ\Ь^N›ШЪЯK™љ[\њЮЩ\Ь^Nљ[›[™KY›^ЫX\™Ъ[‹]ЬЊMKШ[™Y]K\›ЭЮЬY[™ОЊM\K›Z[љKYЬљY›Y]ЩYЬљY™^\љ[Y[ќYЬљYЩЬљY][\]KXЫЫ[[њОЊYњџK›[Щ[ЬY[™ОЊЌњЊK™]Z[YЬљYЩЬљY][\]KXЫЫ[[њОЊYњџKњљ\ЪЛ\ЩXЭ[ЫћЩ\Ь^N›ШЪЯKњZ[‹XШ\™ЬY[™ОЊЊњK›Э]ЫЫYK]X›O™]ћЩЬљY][\]KXЫЫ[[њОЊYњ€YњџK›Э]ЫЫYK]X›O™]ЏЉЋ›ќXЪ[
ЉМК^Щ\Ь^N››Ы™_K›X‹X\Щ[[™K›X‹ZXY[™ЮШ[YЫ‹Z][\О™›^\Э\ќЩШ\ЊMњK›X‹ZXY[™ЮЩ\Ь^N›ШЪЯK›X‹ZXY[™ИЫX\™Ъ[‹]ЬЋ_B