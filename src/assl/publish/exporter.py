from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import mkdtemp

from assl.domain import canonical_json, content_sha256
from assl.publish.privacy import scan_public_tree
from assl.publish.schema import PublicSnapshot


class ImmutableSnapshotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExportManifest:
    algorithm_version: str
    latest_date: str
    history_dates: tuple[str, ...]
    file_sha256: dict[str, str]
    generated_at: datetime


def persist_snapshot(
    repository,
    connection,
    run_id,
    snapshot: PublicSnapshot,
) -> str:
    digest = content_sha256(snapshot.to_dict())
    existing = repository.get_snapshot_hash(
        connection,
        date.fromisoformat(snapshot.as_of_date),
        snapshot.algorithm_version,
    )
    if existing is not None:
        if existing != digest:
            raise ImmutableSnapshotError(
                "published snapshot differs for the same date and algorithm version"
            )
        return existing
    repository.insert_snapshot(connection, run_id, snapshot, digest)
    return digest


def export_public_bundle(
    repository,
    output_dir: Path,
    algorithm_version: str,
    *,
    private_symbols: tuple[str, ...] = (),
) -> ExportManifest:
    payloads = repository.list_snapshot_payloads(algorithm_version)
    if not payloads:
        raise ValueError("no successful snapshots are available to export")
    sorted_payloads = sorted(payloads, key=lambda payload: payload["as_of_date"])
    history_dates = tuple(payload["as_of_date"] for payload in sorted_payloads)
    generated_at = datetime.now(UTC)
    temporary = Path(mkdtemp(prefix="assl-public-", dir=output_dir.parent))
    try:
        history_dir = temporary / "history"
        history_dir.mkdir(parents=True)
        for payload in sorted_payloads:
            _write_json(history_dir / f"{payload['as_of_date']}.json", payload)
        _write_json(temporary / "history" / "index.json", list(history_dates))
        _write_json(temporary / "latest.json", sorted_payloads[-1])
        _write_json(temporary / "methodology.json", _methodology(algorithm_version))

        files = sorted(path for path in temporary.rglob("*") if path.is_file())
        file_hashes = {
            path.relative_to(temporary).as_posix(): content_sha256(
                json.loads(path.read_text(encoding="utf-8"))
            )
            for path in files
        }
        manifest = ExportManifest(
            algorithm_version=algorithm_version,
            latest_date=history_dates[-1],
            history_dates=history_dates,
            file_sha256=file_hashes,
            generated_at=generated_at,
        )
        _write_json(
            temporary / "manifest.json",
            {
                "schema_version": "1",
                "algorithm_version": manifest.algorithm_version,
                "latest_date": manifest.latest_date,
                "history_dates": list(manifest.history_dates),
                "generated_at": manifest.generated_at.isoformat(),
                "file_sha256": manifest.file_sha256,
            },
        )
        public_symbols = tuple(
            candidate["symbol"]
            for payload in sorted_payloads
            for bucket in ("top10", "p1", "p2", "risk_watch")
            for candidate in payload[bucket]
        )
        report = scan_public_tree(
            temporary,
            private_symbols=private_symbols,
            public_symbols=public_symbols,
        )
        if not report.safe:
            raise ValueError(f"privacy scan failed: {','.join(report.reasons)}")

        if output_dir.exists():
            backup = output_dir.with_name(output_dir.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            output_dir.replace(backup)
            temporary.replace(output_dir)
            shutil.rmtree(backup)
        else:
            temporary.replace(output_dir)
        return manifest
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _methodology(algorithm_version: str) -> dict[str, object]:
    return {
        "algorithm_version": algorithm_version,
        "macd": {"fast": 12, "slow": 26, "signal": 9},
        "moving_averages": [20, 30, 60],
        "entry": "T+1 open for outcome evaluation",
        "cost_model": "10 bps entry plus 10 bps exit",
        "benchmark": "CSI 300",
        "source": "Tencent qfq daily OHLCV",
        "disclaimer": "研究候选池，不构成投资建议。",
    }
