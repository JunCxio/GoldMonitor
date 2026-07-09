import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_preview_import_config_socket_event_reports_summary_without_saving(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)

    payload = {
        "settings": {
            "smtp_server": "smtp.example.com",
            "smtp_password_configured": True,
            "unknown_setting": "ignored",
        },
        "thresholds": {
            "upper_warning_rmb": 700,
            "unknown_threshold": 1,
        },
        "alert_profiles": [
            {"id": "profile-imported", "name": "导入模板", "thresholds": {"upper_warning_rmb": 720}},
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("preview_import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    preview = next(event["args"][0] for event in events if event["name"] == "config_import_previewed")

    assert preview["ok"] is True
    assert preview["importable"] is True
    assert preview["sections"] == ["settings", "thresholds", "alert_profiles"]
    assert "alert_profiles" in preview["sections"]
    assert preview["counts"]["alert_profiles"] == 1
    assert preview["ignored"]["settings"] == ["smtp_password_configured", "unknown_setting"]
    assert preview["ignored"]["thresholds"] == ["unknown_threshold"]
    assert preview["secret_actions"]["smtp_password"] == "preserve_existing"
    assert not Path(app.SETTINGS_PATH).exists()
    assert not Path(app.THRESHOLDS_PATH).exists()
    assert not Path(app.ALERT_PROFILES_PATH).exists()
    client.disconnect()


def test_import_config_socket_event_still_imports_directly(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))

    payload = {
        "settings": {"smtp_server": "smtp.example.com"},
        "thresholds": {"upper_warning_rmb": 700},
        "alert_profiles": [
            {"id": "profile-imported", "name": "导入模板", "thresholds": {"upper_warning_rmb": 720}},
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is True
    assert result["imported"] == ["settings", "thresholds", "alert_profiles"]
    assert Path(app.SETTINGS_PATH).exists()
    assert Path(app.THRESHOLDS_PATH).exists()
    assert Path(app.ALERT_PROFILES_PATH).exists()
    client.disconnect()


def test_import_config_socket_event_imports_alert_profiles_only(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)

    payload = {
        "alert_profiles": [
            {"id": "profile-imported", "name": "导入模板", "thresholds": {"upper_warning_rmb": 720}},
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is True
    assert result["imported"] == ["alert_profiles"]
    assert not Path(app.SETTINGS_PATH).exists()
    assert not Path(app.THRESHOLDS_PATH).exists()
    assert Path(app.ALERT_PROFILES_PATH).exists()
    client.disconnect()
