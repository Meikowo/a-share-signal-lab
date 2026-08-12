import json
from datetime import UTC, date, datetime

from assl.domain import Coverage, Grade
from assl.publish.schema import PublicSnapshot
from tests.test_ranking import make_signal

ALLOWED_ROOT = {
    "schema_version",
    "as_of_date",
    "generated_at",
    "algorithm_version",
    "source",
    "coverage",
    "summary",
    "top10",
    "p1",
    "p2",
    "risk_watch",
    "outcome_summary",
    "disclaimer",
}
FORBIDDEN = {
    "watchlist_version_id",
    "fundamental_priority",
    "theme_tags",
    "database_url",
    "raw_bars",
    "all_signals",
}


def test_public_snapshot_has_only_allowlisted_root_fields():
    signal = make_signal("600000", Grade.B_PLUS, priority=2)

    snapshot = PublicSnapshot.from_signals(
        as_of_date=date(2026, 8, 11),
        generated_at=datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
        algorithm_version="macd-v1",
        source="腾讯前复权日线",
        coverage=Coverage(839, 828, tuple(str(i) for i in range(11)), None, True),
        top10=(signal,),
        p1=(),
        p2=(),
        risk_watch=(),
        outcome_summary=(),
    )

    payload = snapshot.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)
    assert set(payload) == ALLOWED_ROOT
    assert not FORBIDDEN.intersection(encoded)
    assert payload["top10"][0]["symbol"] == "600000"
    assert "fundamental_priority" not in payload["top10"][0]


def test_candidate_serialization_has_exact_public_fields():
    signal = make_signal("600000", Grade.B_PLUS, priority=2)
    snapshot = PublicSnapshot.from_signals(
        as_of_date=date(2026, 8, 11),
        generated_at=datetime(2026, 8, 12, 6, 0, tzinfo=UTC),
        algorithm_version="macd-v1",
        source="腾讯前复权日线",
        coverage=Coverage(1, 1, (), None, True),
        top10=(signal,),
        p1=(),
        p2=(),
        risk_watch=(),
        outcome_summary=(),
    )

    candidate = snapshot.to_dict()["top10"][0]
    assert set(candidate) == {
        "rank",
        "symbol",
        "name",
        "bucket",
        "grade",
        "signal_type",
        "signal_date",
        "dif",
        "dea",
        "macd_hist",
        "gap",
        "convergence_speed",
        "x1",
        "x1_change_pct",
        "projected_days",
        "ma20",
        "ma30",
        "ma60",
        "close_vs_ma20",
        "close_vs_ma30",
        "close_vs_ma60",
        "volume_ratio_5_20",
        "bottom_divergence",
        "top_divergence",
        "reason",
        "confirm_price",
        "invalidation_price",
        "risk",
        "outcomes",
    }
