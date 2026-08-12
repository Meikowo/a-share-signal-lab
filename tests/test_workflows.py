from pathlib import Path


def test_daily_workflow_has_schedule_manual_trigger_and_concurrency():
    text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")

    assert "schedule:" in text
    assert "workflow_dispatch:" in text
    assert 'cron: "17 22 * * 0-4"' in text
    assert "cancel-in-progress: false" in text
    assert "ASSL_DATABASE_URL:" in text
    assert "contents: read" in text


def test_ci_runs_lint_and_unit_tests_on_push_and_pull_request():
    text = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "pull_request:" in text
    assert "push:" in text
    assert "ruff check" in text
    assert 'pytest -m "not integration and not network"' in text


def test_daily_workflow_never_echoes_database_secret():
    text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")

    assert "echo $ASSL_DATABASE_URL" not in text
    assert "${{ secrets.ASSL_DATABASE_URL }}" in text
