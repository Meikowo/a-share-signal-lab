
import pytest

from assl.publish.privacy import scan_public_tree


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ('{"database_url":"postgresql://user:pass@example/db"}', "database_url"),
        ('{"key":"sb_secret_abcdefghijklmnopqrstuvwxyz"}', "supabase_secret"),
        ('{"fundamental_priority":2}', "private_field"),
    ],
)
def test_scanner_blocks_credentials_and_private_fields(tmp_path, content, reason):
    (tmp_path / "leak.json").write_text(content, encoding="utf-8")

    report = scan_public_tree(tmp_path, private_symbols=())

    assert reason in report.reasons
    assert report.safe is False


def test_scanner_blocks_private_universe_cluster(tmp_path):
    symbols = [f"00{index:04d}" for index in range(1, 25)]
    (tmp_path / "bundle.json").write_text(str(symbols), encoding="utf-8")

    report = scan_public_tree(tmp_path, private_symbols=symbols)

    assert "private_universe_cluster" in report.reasons


def test_scanner_allows_public_candidate_symbols(tmp_path):
    symbols = [f"00{index:04d}" for index in range(1, 25)]
    (tmp_path / "latest.json").write_text(str(symbols), encoding="utf-8")

    report = scan_public_tree(
        tmp_path,
        private_symbols=symbols,
        public_symbols=symbols,
    )

    assert report.safe is True


def test_scanner_blocks_private_filename(tmp_path):
    (tmp_path / "watchlist.json").write_text("{}", encoding="utf-8")

    report = scan_public_tree(tmp_path, private_symbols=())

    assert "private_filename" in report.reasons
