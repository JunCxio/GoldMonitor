import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_custom_export_dir_controls_saved_exports(monkeypatch, tmp_path):
    import app

    default_dir = tmp_path / "default-exports"
    custom_dir = tmp_path / "custom-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(default_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": str(custom_dir)})

    saved = app.save_export_file("../report.md", "hello")

    assert saved == str(custom_dir / "report.md")
    assert (custom_dir / "report.md").read_text(encoding="utf-8") == "hello"
    assert not (default_dir / "report.md").exists()


def test_public_settings_and_diagnostics_expose_effective_export_dir(monkeypatch, tmp_path):
    import app

    default_dir = tmp_path / "default-exports"
    custom_dir = tmp_path / "custom-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(default_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": str(custom_dir)})
    monkeypatch.setattr(app, "read_log_tail", lambda: [])

    public = app.public_settings_snapshot()
    diagnostics = json.loads(app.build_diagnostics_report())

    assert public["export_dir"] == str(custom_dir)
    assert public["export_dir_default"] == str(default_dir)
    assert public["export_dir_effective"] == str(custom_dir)
    assert diagnostics["paths"]["exports"] == str(custom_dir)


def test_blank_export_dir_falls_back_to_default(monkeypatch, tmp_path):
    import app

    default_dir = tmp_path / "default-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(default_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})

    saved = app.save_export_file("report.md", "hello")

    assert saved == str(default_dir / "report.md")
    assert app.public_settings_snapshot()["export_dir_effective"] == str(default_dir)
