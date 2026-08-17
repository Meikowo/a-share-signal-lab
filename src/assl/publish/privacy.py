from __future__ import annotations

import re
import sys
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path

TEXT_SUFFIXES = {".json", ".js", ".css", ".html", ".map", ".txt"}
PRIVATE_NAMES = {"watchlist", "raw_bars", "signal_results", ".env", "dump"}
PATTERNS = {
    "database_url": re.compile(r"(?:postgres(?:ql)?://|database_url)", re.IGNORECASE),
    "supabase_secret": re.compile(r"sb_secret_", re.IGNORECASE),
    "authorization_header": re.compile(r"authorization\s*[:=]", re.IGNORECASE),
    "private_field": re.compile(
        r"fundamental_priority|theme_tags|watchlist_version_id|all_signals|raw_bars",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True, slots=True)
class PrivacyReport:
    safe: bool
    paths: tuple[Path, ...]
    reasons: tuple[str, ...]


def scan_public_tree(
    root: Path,
    private_symbols: Collection[str],
    public_symbols: Collection[str] = (),
) -> PrivacyReport:
    violations: list[tuple[Path, str]] = []
    private_only = set(private_symbols) - set(public_symbols)
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if any(token in lower_name for token in PRIVATE_NAMES):
            violations.append((path, "private_filename"))
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for reason, pattern in PATTERNS.items():
            if pattern.search(text):
                violations.append((path, reason))
        symbol_count = sum(symbol in text for symbol in private_only)
        if symbol_count > 20:
            violations.append((path, "private_universe_cluster"))

    paths = tuple(dict.fromkeys(path for path, _ in violations))
    reasons = tuple(dict.fromkeys(reason for _, reason in violations))
    return PrivacyReport(safe=not violations, paths=paths, reasons=reasons)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m assl.publish.privacy PATH", file=sys.stderr)
        return 4
    report = scan_public_tree(Path(args[0]), private_symbols=())
    if not report.safe:
        for path, reason in zip(report.paths, report.reasons, strict=False):
            print(f"privacy violation: {path}: {reason}", file=sys.stderr)
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
