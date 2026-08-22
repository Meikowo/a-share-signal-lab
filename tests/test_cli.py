from contextlib import contextmanager
from datetime import date

import assl.cli as cli_module
from assl.domain import Coverage, RunSummary


def test_run_daily_cli_parses_date_and_offline(monkeypatch, capsys):
    captured = {}

    class FakePipeline:
        def __init__(self, repository, market, config):
            pass

        def run(self, as_of_date, offline=False, execution_mode="forward_shadow"):
            captured["date"] = as_of_date
            captured["offline"] = offline
            captured["execution_mode"] = execution_mode
            return RunSummary(
                run_id="run-1",
                as_of_date=as_of_date,
                status="succeeded",
                coverage=Coverage(2, 2, (), None, True),
                result_sha256="a" * 64,
            )

    monkeypatch.setenv("ASSL_DATABASE_URL", "unused")
    monkeypatch.setattr(cli_module, "DailyPipeline", FakePipeline)
    monkeypatch.setattr(cli_module, "AsslRepository", lambda value: object())
    monkeypatch.setattr(cli_module, "TencentClient", lambda: object())

    exit_code = cli_module.main(
        ["run-daily", "--as-of", "2026-08-11", "--offline"]
    )

    assert exit_code == 0
    assert captured == {
        "date": date(2026, 8, 11),
        "offline": True,
        "execution_mode": "historical_reconstruction",
    }
    assert "status=succeeded" in capsys.readouterr().out


def test_backfill_cli_runs_cached_sessions_oldest_first(monkeypatch, capsys):
    dates = (date(2026, 7, 13), date(2026, 7, 14), date(2026, 7, 15))
    called = []

    class FakeRepository:
        @contextmanager
        def transaction(self):
            yield self

        def recent_trade_dates(self, connection, symbol, end_date, limit):
            assert symbol == "000300"
            assert end_date == date(2026, 8, 14)
            assert limit == 3
            return dates

    class FakePipeline:
        def __init__(self, repository, market, config):
            pass

        def latest_completed_date(self):
            return date(2026, 8, 14)

        def run(self, as_of_date, offline=False, execution_mode="forward_shadow"):
            called.append((as_of_date, offline, execution_mode))
            return RunSummary(
                run_id=f"run-{as_of_date}",
                as_of_date=as_of_date,
                status="succeeded",
                coverage=Coverage(2, 2, (), None, True),
                result_sha256="a" * 64,
            )

    monkeypatch.setenv("ASSL_DATABASE_URL", "unused")
    monkeypatch.setattr(cli_module, "DailyPipeline", FakePipeline)
    monkeypatch.setattr(cli_module, "AsslRepository", lambda value: FakeRepository())
    monkeypatch.setattr(cli_module, "TencentClient", lambda: object())

    exit_code = cli_module.main(["backfill", "--sessions", "3"])

    assert exit_code == 0
    assert called == [(day, True, "historical_reconstruction") for day in dates]
    assert "completed=3/3" in capsys.readouterr().out
