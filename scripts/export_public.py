from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from assl.config import Settings
from assl.db import AsslRepository
from assl.market.sohu import SohuMarketActivityClient
from assl.publish.exporter import export_public_bundle


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export privacy-safe ASSL static data")
    parser.add_argument("output", type=Path)
    parser.add_argument("--algorithm-version", default="macd-v1.1")
    args = parser.parse_args(argv)
    repository = AsslRepository(Settings.from_env().database_url)
    export_public_bundle(
        repository,
        args.output,
        args.algorithm_version,
        market_activity_client=SohuMarketActivityClient(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
