import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def _isolate_alert_rule_store(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "ALERT_RULES_PATH", str(tmp_path / "alert_rules.json"))
    monkeypatch.setattr(app, "alert_rules", [])
    monkeypatch.setattr(app, "alert_rule_migration_status", {"completed": True, "source_version": "1.0.7"})
    monkeypatch.setattr(app, "alert_rules_load_error", "")
    monkeypatch.setattr(app, "alert_rules_invalid_count", 0)


def test_build_config_backup_exports_only_restorable_non_secret_settings(monkeypatch):
    import app

    settings = dict(app.DEFAULT_SETTINGS)
    settings.update({
        "smtp_password": "smtp-secret",
        "deepseek_api_key": "deepseek-secret",
        "openai_compatible_api_key": "compatible-secret",
    })
    monkeypatch.setattr(app, "app_settings", settings)

    backup = app.build_config_backup()

    assert backup["schema_version"] == 1
    assert set(backup["settings"]) == set(app.DEFAULT_SETTINGS) - set(app.SECRET_SETTING_KEYS)
    assert not set(app.SECRET_SETTING_KEYS) & set(backup["settings"])
    assert "smtp_password_configured" not in backup["settings"]
    assert "deepseek_api_key_masked" not in backup["settings"]
    assert "platform_capabilities" not in backup["settings"]
    assert "export_dir_effective" not in backup["settings"]


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
    assert Path(app.ALERT_RULES_PATH).exists()
    assert not Path(app.THRESHOLDS_PATH).exists()
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


def test_import_config_persists_normalized_alert_profiles_without_sensitive_fields(monkeypatch, tmp_path):
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
            {
                "id": "profile-imported",
                "name": "导入模板",
                "thresholds": {"upper_warning_rmb": "720.5"},
                "volatility_config": {"enabled": "true", "percent": "1.5", "minutes": "15"},
                "settings": {
                    "alert_cooldown_minutes": "45",
                    "email_warning_enabled": "false",
                    "smtp_password": "secret",
                    "webhook_url": "https://example.com/hook",
                },
            },
            {"id": "profile-invalid", "name": ""},
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is True
    assert result["imported"] == ["alert_profiles"]
    saved_payload = json.loads(Path(app.ALERT_PROFILES_PATH).read_text(encoding="utf-8"))
    saved_profile = saved_payload["items"][0]
    assert len(saved_payload["items"]) == 1
    assert saved_profile["thresholds"]["upper_warning_rmb"] == 720.5
    assert saved_profile["volatility_config"] == {"percent": 1.5, "minutes": 15, "enabled": True}
    assert saved_profile["settings"]["alert_cooldown_minutes"] == 45
    assert saved_profile["settings"]["email_warning_enabled"] is False
    assert "smtp_password" not in saved_profile["settings"]
    assert "webhook_url" not in saved_profile["settings"]
    client.disconnect()


def test_import_config_normalizes_partial_alert_profiles_after_imported_state(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    app.thresholds["upper_warning_rmb"] = 650.0
    app.app_settings["alert_cooldown_minutes"] = 30

    payload = {
        "settings": {
            "alert_cooldown_minutes": 90,
            "email_warning_enabled": False,
        },
        "thresholds": {
            "upper_warning_rmb": 700,
            "volatility_config": {"enabled": True, "percent": 1.8, "minutes": 20},
        },
        "alert_profiles": [
            {
                "id": "profile-imported",
                "name": "随导入状态补齐",
                "volatility_config": {"percent": 2.2},
            },
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is True
    saved_payload = json.loads(Path(app.ALERT_PROFILES_PATH).read_text(encoding="utf-8"))
    saved_profile = saved_payload["items"][0]
    assert saved_profile["thresholds"]["upper_warning_rmb"] == 700.0
    assert saved_profile["volatility_config"] == {"percent": 2.2, "minutes": 20, "enabled": True}
    assert saved_profile["settings"]["alert_cooldown_minutes"] == 90
    assert saved_profile["settings"]["email_warning_enabled"] is False
    client.disconnect()


def test_import_config_duplicate_alert_profile_id_keeps_later_item(monkeypatch, tmp_path):
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
            {"id": "profile-duplicate", "name": "第一版", "thresholds": {"upper_warning_rmb": 650}},
            {"id": "profile-duplicate", "name": "第二版", "thresholds": {"upper_warning_rmb": 720}},
        ],
    }
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {"payload": json.dumps(payload, ensure_ascii=False)})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is True
    saved_payload = json.loads(Path(app.ALERT_PROFILES_PATH).read_text(encoding="utf-8"))
    assert len(saved_payload["items"]) == 1
    assert saved_payload["items"][0]["name"] == "第二版"
    assert saved_payload["items"][0]["thresholds"]["upper_warning_rmb"] == 720.0
    client.disconnect()


def test_import_config_rolls_back_settings_when_threshold_save_fails(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    startup_calls = []
    floating_calls = []

    def record_startup(enabled):
        startup_calls.append(enabled)
        return True, ""

    monkeypatch.setattr(app, "set_startup_enabled", record_startup)
    monkeypatch.setattr(
        app,
        "apply_floating_price_settings",
        lambda settings=None: floating_calls.append(settings),
    )

    original_smtp_server = "smtp.old.example.com"
    app.app_settings["smtp_server"] = original_smtp_server
    real_save_alert_rules = app.save_alert_rules

    def fail_save_alert_rules(items=None):
        raise OSError("alert rule write failed")

    monkeypatch.setattr(app, "save_alert_rules", fail_save_alert_rules)
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {
        "payload": json.dumps({
            "settings": {"smtp_server": "smtp.new.example.com"},
            "thresholds": {"upper_warning_rmb": 700},
        }, ensure_ascii=False),
    })
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    emitted_names = [event["name"] for event in events]
    assert result["ok"] is False
    assert "settings_updated" not in emitted_names
    assert "thresholds_updated" not in emitted_names
    assert app.app_settings["smtp_server"] == original_smtp_server
    assert app.thresholds["upper_warning_rmb"] is None
    assert startup_calls == []
    assert floating_calls == []
    monkeypatch.setattr(app, "save_alert_rules", real_save_alert_rules)
    client.disconnect()


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": 1, "settings": {}, "thresholds": {}, "alert_profiles": []},
        {
            "schema_version": 1,
            "settings": {"unknown_setting": True},
            "thresholds": {"unknown_threshold": 1},
        },
    ],
)
def test_import_config_rejects_empty_or_unknown_only_sections(monkeypatch, tmp_path, payload):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)

    preview = app.preview_config_backup(payload)

    assert preview["ok"] is False
    assert preview["importable"] is False
    assert preview["sections"] == []
    with pytest.raises(ValueError, match="备份中没有可导入的配置"):
        app.restore_config_backup(payload)
    assert not Path(app.SETTINGS_PATH).exists()
    assert not Path(app.THRESHOLDS_PATH).exists()
    assert not Path(app.ALERT_RULES_PATH).exists()
    assert not Path(app.ALERT_PROFILES_PATH).exists()


def test_import_config_rejects_future_schema_in_preview_and_restore():
    import app

    payload = {
        "schema_version": 2,
        "settings": {"smtp_server": "smtp.example.com"},
    }

    preview = app.preview_config_backup(payload)

    assert preview["ok"] is False
    assert preview["importable"] is False
    assert preview["schema_version"] == 2
    assert preview["expected_schema_version"] == 1
    with pytest.raises(ValueError, match="版本"):
        app.restore_config_backup(payload)


def test_import_config_preserves_secrets_in_versioned_backup(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    current_settings = dict(app.DEFAULT_SETTINGS)
    current_settings.update({
        "smtp_server": "smtp.old.example.com",
        "smtp_password": "smtp-existing-secret",
        "deepseek_api_key": "deepseek-existing-secret",
    })
    credential_store = {
        "smtp_password": "smtp-existing-secret",
        "deepseek_api_key": "deepseek-existing-secret",
    }
    monkeypatch.setattr(app, "app_settings", current_settings)
    monkeypatch.setattr(app, "_credential_test_store", credential_store)
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "apply_floating_price_settings", lambda settings=None: None)
    payload = {
        "schema_version": 1,
        "settings": {
            "smtp_server": "smtp.new.example.com",
            "smtp_password": "smtp-injected-secret",
            "deepseek_api_key": "deepseek-injected-secret",
        },
    }

    preview = app.preview_config_backup(payload)
    result = app.restore_config_backup(payload)

    assert preview["ok"] is True
    assert preview["counts"]["settings"] == 1
    assert preview["ignored"]["settings"] == ["deepseek_api_key", "smtp_password"]
    assert preview["secret_actions"]["smtp_password"] == "preserve_existing"
    assert result == {"ok": True, "imported": ["settings"]}
    assert app.app_settings["smtp_server"] == "smtp.new.example.com"
    assert app.app_settings["smtp_password"] == "smtp-existing-secret"
    assert app.app_settings["deepseek_api_key"] == "deepseek-existing-secret"
    assert credential_store["smtp_password"] == "smtp-existing-secret"
    assert credential_store["deepseek_api_key"] == "deepseek-existing-secret"


def test_import_config_rejects_versioned_plaintext_secrets_only(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    payload = {
        "schema_version": 1,
        "settings": {"smtp_password": "smtp-injected-secret"},
    }

    preview = app.preview_config_backup(payload)

    assert preview["ok"] is False
    assert preview["importable"] is False
    assert preview["ignored"]["settings"] == ["smtp_password"]
    with pytest.raises(ValueError, match="备份中没有可导入的配置"):
        app.restore_config_backup(payload)
    assert not Path(app.SETTINGS_PATH).exists()


def test_import_config_accepts_plaintext_secrets_from_legacy_backup(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "_credential_test_store", {})
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "apply_floating_price_settings", lambda settings=None: None)
    payload = {
        "settings": {
            "smtp_password": "legacy-smtp-secret",
            "deepseek_api_key": "legacy-deepseek-secret",
        },
    }

    preview = app.preview_config_backup(payload)
    result = app.restore_config_backup(payload)

    assert preview["schema_version"] == 0
    assert preview["counts"]["settings"] == 2
    assert preview["secret_actions"]["smtp_password"] == "import"
    assert result == {"ok": True, "imported": ["settings"]}
    assert app.app_settings["smtp_password"] == "legacy-smtp-secret"
    assert app.app_settings["deepseek_api_key"] == "legacy-deepseek-secret"


def test_import_config_rolls_back_files_when_alert_profiles_save_fails(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    startup_calls = []
    floating_calls = []

    def record_startup(enabled):
        startup_calls.append(enabled)
        return True, ""

    monkeypatch.setattr(app, "set_startup_enabled", record_startup)
    monkeypatch.setattr(
        app,
        "apply_floating_price_settings",
        lambda settings=None: floating_calls.append(settings),
    )

    app.app_settings["smtp_server"] = "smtp.old.example.com"
    app.thresholds["upper_warning_rmb"] = 650.0
    old_profile = {"id": "profile-old", "name": "旧模板", "thresholds": {"upper_warning_rmb": 650}}
    app.save_settings(dict(app.app_settings))
    app.alert_rules = app.save_alert_rules(
        app._rules_for_legacy_threshold_snapshot(app.thresholds, app.volatility_config)
    )
    app.alert_profiles = app.save_alert_profiles([old_profile])

    real_save_alert_profiles = app.save_alert_profiles
    calls = {"count": 0}

    def fail_first_save_alert_profiles(items=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("alert profiles write failed")
        return real_save_alert_profiles(items)

    monkeypatch.setattr(app, "save_alert_profiles", fail_first_save_alert_profiles)
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {
        "payload": json.dumps({
            "settings": {"smtp_server": "smtp.new.example.com"},
            "thresholds": {"upper_warning_rmb": 700},
            "alert_profiles": [{"id": "profile-new", "name": "新模板"}],
        }, ensure_ascii=False),
    })
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    emitted_names = [event["name"] for event in events]
    settings_payload = json.loads(Path(app.SETTINGS_PATH).read_text(encoding="utf-8"))
    alert_rules_payload = json.loads(Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8"))
    profiles_payload = json.loads(Path(app.ALERT_PROFILES_PATH).read_text(encoding="utf-8"))
    assert result["ok"] is False
    assert "settings_updated" not in emitted_names
    assert "thresholds_updated" not in emitted_names
    assert "alert_profiles_updated" not in emitted_names
    assert app.app_settings["smtp_server"] == "smtp.old.example.com"
    assert app.thresholds["upper_warning_rmb"] == 650.0
    assert app.alert_profiles[0]["id"] == "profile-old"
    assert settings_payload["smtp_server"] == "smtp.old.example.com"
    assert alert_rules_payload["items"][0]["condition"]["value"] == 650.0
    assert profiles_payload["items"][0]["id"] == "profile-old"
    assert startup_calls == []
    assert floating_calls == []
    client.disconnect()


def test_import_config_rolls_back_created_files_when_no_previous_files(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "app_settings", dict(app.DEFAULT_SETTINGS))
    monkeypatch.setattr(app, "thresholds", {key: None for key in app.thresholds})
    monkeypatch.setattr(app, "volatility_config", {"enabled": False, "percent": None, "minutes": 10})
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))

    real_save_alert_profiles = app.save_alert_profiles
    calls = {"count": 0}

    def fail_first_save_alert_profiles(items=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("alert profiles write failed")
        return real_save_alert_profiles(items)

    monkeypatch.setattr(app, "save_alert_profiles", fail_first_save_alert_profiles)
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("import_config", {
        "payload": json.dumps({
            "settings": {"smtp_server": "smtp.new.example.com"},
            "thresholds": {"upper_warning_rmb": 700},
            "alert_profiles": [{"id": "profile-new", "name": "新模板"}],
        }, ensure_ascii=False),
    })
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "config_import_result")

    assert result["ok"] is False
    assert not Path(app.SETTINGS_PATH).exists()
    assert not Path(app.THRESHOLDS_PATH).exists()
    assert not Path(app.ALERT_RULES_PATH).exists()
    assert not Path(app.ALERT_PROFILES_PATH).exists()
    assert app.app_settings["smtp_server"] == app.DEFAULT_SETTINGS["smtp_server"]
    assert app.thresholds["upper_warning_rmb"] is None
    assert app.alert_profiles == []
    client.disconnect()
