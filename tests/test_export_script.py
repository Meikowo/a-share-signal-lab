import scripts.export_public as script


def test_export_script_uses_private_repository_and_writes_bundle(tmp_path, monkeypatch):
    captured = {}

    class FakeRepo:
        def __init__(self, database_url):
            captured["url"] = database_url

    def export(repository, output_dir, algorithm_version):
        captured["output"] = output_dir
        captured["version"] = algorithm_version
        output_dir.mkdir()
        (output_dir / "manifest.json").write_text("{}", encoding="utf-8")
        return object()

    monkeypatch.setenv("ASSL_DATABASE_URL", "private")
    monkeypatch.setattr(script, "AsslRepository", FakeRepo)
    monkeypatch.setattr(script, "export_public_bundle", export)

    assert script.main([str(tmp_path / "public")]) == 0
    assert captured["version"] == "macd-v1.1"
    assert captured["output"] == tmp_path / "public"
