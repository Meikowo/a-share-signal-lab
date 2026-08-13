from pathlib import Path


def test_daily_workflow_builds_and_deploys_pages_after_privacy_scan():
    text = Path(".github/workflows/daily.yml").read_text(encoding="utf-8")

    assert "pages: write" in text
    assert "id-token: write" in text
    assert "npm install --no-audit --no-fund" in text
    assert "npm ci" not in text
    assert "npm run build" in text
    assert "assl.publish.privacy" in text
    assert "actions/upload-pages-artifact" in text
    assert "actions/deploy-pages" in text
    assert "needs: screen" in text
    assert text.index("npm run test:run") < text.index("rm -rf web/public/data/fixture")


def test_repository_never_commits_generated_production_data():
    text = Path(".gitignore").read_text(encoding="utf-8")

    assert "public-data/" in text
    assert "web/public/data/*" in text
