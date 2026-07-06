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


def test_export_status_records_success_and_diagnostics(monkeypatch, tmp_path):
    import app

    default_dir = tmp_path / "default-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(default_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})
    monkeypatch.setattr(app, "read_log_tail", lambda: [])
    app.reset_last_export_status()

    saved = app.save_export_file("report.md", "hello")
    status = app.get_last_export_status()
    diagnostics = json.loads(app.build_diagnostics_report())
    clipboard = app.build_diagnostics_clipboard_text(diagnostics)

    assert saved == str(default_dir / "report.md")
    assert status["ok"] is True
    assert status["filename"] == "report.md"
    assert status["saved_path"] == str(default_dir / "report.md")
    assert status["export_dir"] == str(default_dir)
    assert diagnostics["export_status"]["directory"]["ok"] is True
    assert diagnostics["export_status"]["last_export"]["ok"] is True
    assert diagnostics["export_status"]["last_export"]["saved_path"] == str(default_dir / "report.md")
    assert "导出状态" in clipboard
    assert "最近导出: 成功" in clipboard


def test_export_status_records_failure_reason_and_diagnostics(monkeypatch, tmp_path):
    import app

    export_dir = tmp_path / "blocked-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(export_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})
    monkeypatch.setattr(app, "read_log_tail", lambda: [])

    def failing_save_export_file(_export_dir, _filename, _content):
        raise PermissionError("readonly")

    monkeypatch.setattr(app.support_files_core, "save_export_file", failing_save_export_file)
    app.reset_last_export_status()

    try:
        app.save_export_file("report.md", "hello")
    except PermissionError:
        pass

    status = app.get_last_export_status()
    diagnostics = json.loads(app.build_diagnostics_report())
    clipboard = app.build_diagnostics_clipboard_text(diagnostics)

    assert status["ok"] is False
    assert status["filename"] == "report.md"
    assert status["export_dir"] == str(export_dir)
    assert status["category"] == "permission_denied"
    assert "导出目录不可写" in status["message"]
    assert diagnostics["export_status"]["last_export"]["ok"] is False
    assert diagnostics["export_status"]["last_export"]["category"] == "permission_denied"
    assert "最近失败原因: 导出目录不可写" in clipboard


def test_export_error_payload_ignores_stale_success_status(monkeypatch, tmp_path):
    import app

    default_dir = tmp_path / "default-exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(default_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})
    app.reset_last_export_status()

    app.save_export_file("report.md", "hello")
    payload = app.build_export_error_payload("导出失败，请检查目录权限。")

    assert payload["message"] == "导出失败，请检查目录权限。"
    assert payload["error_detail"] == {}
    assert payload["export_dir_check"]["ok"] is True


def test_diagnostics_export_writes_json_object(monkeypatch, tmp_path):
    import app

    export_dir = tmp_path / "exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(export_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})
    monkeypatch.setattr(app, "read_log_tail", lambda: [])

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("get_diagnostics")
    events = client.get_received()
    payload = next(event["args"][0] for event in events if event["name"] == "diagnostics_ready")
    saved_text = Path(payload["saved_path"]).read_text(encoding="utf-8")
    content_report = json.loads(payload["content"])
    saved_report = json.loads(saved_text)

    assert payload["ok"] is True
    assert isinstance(content_report, dict)
    assert isinstance(saved_report, dict)
    assert content_report["app"] == app.APP_NAME
    assert saved_report["app"] == app.APP_NAME
    assert saved_text == payload["content"]
    client.disconnect()


def test_open_exports_folder_error_includes_diagnostics(monkeypatch, tmp_path):
    import app

    export_dir = tmp_path / "exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(export_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})

    def failing_open_exports_folder():
        raise PermissionError("blocked")

    monkeypatch.setattr(app, "open_exports_folder", failing_open_exports_folder)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("open_exports_folder")
    events = client.get_received()
    payload = next(event["args"][0] for event in events if event["name"] == "exports_folder_opened")

    assert payload["ok"] is False
    assert "打开导出目录" in payload["message"]
    assert payload["error_detail"]["category"] == "permission_denied"
    assert payload["error_detail"]["export_dir"] == str(export_dir)
    assert payload["export_dir_check"]["path"] == str(export_dir)
    client.disconnect()


def test_open_exports_folder_success_includes_export_dir(monkeypatch, tmp_path):
    import app

    export_dir = tmp_path / "exports"
    monkeypatch.setattr(app, "EXPORT_DIR", str(export_dir))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": ""})
    monkeypatch.setattr(app, "open_exports_folder", lambda: None)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("open_exports_folder")
    events = client.get_received()
    payload = next(event["args"][0] for event in events if event["name"] == "exports_folder_opened")

    assert payload["ok"] is True
    assert payload["export_dir"] == str(export_dir)
    assert "已打开导出目录" in payload["message"]
    client.disconnect()


def test_export_dir_check_reports_writable_directory(tmp_path):
    import app

    export_dir = tmp_path / "exports"

    check = app.build_export_dir_check(
        {**app.DEFAULT_SETTINGS, "export_dir": str(export_dir)},
    )

    assert check["ok"] is True
    assert check["path"] == str(export_dir)
    assert check["status"] == "writable"
    assert check["message"] == f"导出目录可写：{export_dir}"


def test_export_dir_check_reports_missing_write_permission(tmp_path):
    import app

    export_dir = tmp_path / "exports"

    def failing_probe(path):
        raise PermissionError("readonly")

    check = app.build_export_dir_check(
        {**app.DEFAULT_SETTINGS, "export_dir": str(export_dir)},
        probe_writer=failing_probe,
    )

    assert check["ok"] is False
    assert check["path"] == str(export_dir)
    assert check["status"] == "unwritable"
    assert "导出目录不可写" in check["message"]
    assert check["actions"] == ["choose_export_dir", "use_default_export_dir", "open_export_dir"]


def test_update_settings_rejects_unwritable_export_dir(monkeypatch, tmp_path):
    import app

    settings_path = tmp_path / "settings.json"
    previous_dir = tmp_path / "previous"
    blocked_dir = tmp_path / "blocked"
    monkeypatch.setattr(app, "SETTINGS_PATH", str(settings_path))
    monkeypatch.setattr(app, "EXPORT_DIR", str(tmp_path / "default-exports"))
    monkeypatch.setattr(app, "app_settings", {**app.DEFAULT_SETTINGS, "export_dir": str(previous_dir)})
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "apply_floating_price_settings", lambda settings=None: None)
    monkeypatch.setattr(app, "build_export_dir_check", lambda settings=None: {
        "ok": False,
        "path": str(blocked_dir),
        "status": "unwritable",
        "message": f"导出目录不可写：{blocked_dir}",
        "actions": ["choose_export_dir", "use_default_export_dir", "open_export_dir"],
    })

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("update_settings", {"export_dir": str(blocked_dir)})
    events = client.get_received()
    error = next(event["args"][0] for event in events if event["name"] == "settings_error")
    updated = next(event["args"][0] for event in events if event["name"] == "settings_updated")

    assert error["message"] == f"导出目录不可写：{blocked_dir}"
    assert error["export_dir_check"]["status"] == "unwritable"
    assert updated["export_dir"] == str(previous_dir)
    assert app.app_settings["export_dir"] == str(previous_dir)
    assert not settings_path.exists()
    client.disconnect()


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
