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


def test_export_dir_picker_payload_accepts_webview_folder_selection(monkeypatch, tmp_path):
    import app

    current_dir = tmp_path / "current"
    selected_dir = tmp_path / "selected"
    current_dir.mkdir()
    selected_dir.mkdir()
    captured = {}

    def fake_dialog(initial_dir):
        captured["initial_dir"] = initial_dir
        return (str(selected_dir),)

    payload = app.build_export_dir_picker_payload(
        fake_dialog,
        settings={**app.DEFAULT_SETTINGS, "export_dir": str(current_dir)},
    )

    assert payload == {
        "ok": True,
        "path": str(selected_dir),
        "message": f"已选择导出目录：{selected_dir}",
    }
    assert captured["initial_dir"] == str(current_dir)


def test_export_dir_picker_payload_handles_cancelled_selection(tmp_path):
    import app

    current_dir = tmp_path / "current"
    current_dir.mkdir()

    payload = app.build_export_dir_picker_payload(
        lambda initial_dir: None,
        settings={**app.DEFAULT_SETTINGS, "export_dir": str(current_dir)},
    )

    assert payload == {
        "ok": False,
        "cancelled": True,
        "message": "已取消选择导出目录。",
    }
