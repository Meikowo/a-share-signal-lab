from datetime import date

import assl.cli as cli_module
from assl.domain import Coverage, RunSummary


def test_run_daily_cli_parses_date_and_offline(monkeypatch, capsys):
    captured = {}

    class FakePipeline:
        def __init__(self, repository, market, config):
            pass

        def run(self, as_of_date, offline=False):
            captured["date"] = as_of_date
            captured["offline"] = offline
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
    assert captured == {"date": date(2026, 8, 11), "offline": True}
    assert "status=succeeded" in capsys.readouterr().out
