import pytest

from assl.config import AlgorithmConfig, Settings


def test_macd_v1_has_frozen_parameters():
    cfg = AlgorithmConfig.macd_v1()

    assert cfg.version == "macd-v1.1"
    assert (cfg.fast, cfg.slow, cfg.signal) == (12, 26, 9)
    assert cfg.ma_windows == (20, 30, 60)
    assert cfg.publish_coverage == 0.97
    assert cfg.rounding_digits == 6
    assert cfg.grade_order == ("强S", "S", "A+", "A", "B+", "B", "未评级")
    assert cfg.ranking_order[0:3] == (
        "fundamental_priority",
        "grade",
        "signal_age_days",
    )


def test_settings_require_database_url(monkeypatch):
    monkeypatch.delenv("ASSL_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="ASSL_DATABASE_URL"):
        Settings.from_env()
