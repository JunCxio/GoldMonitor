import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _event_payload(events, name):
    return next(event["args"][0] for event in events if event["name"] == name)


def _threshold_defaults(app):
    return {key: None for key in app.thresholds}


def _saved_profile(app, client, name="买入观察"):
    client.emit("save_alert_profile", {"name": name, "description": "回调时提醒"})
    events = client.get_received()
    saved_state = _event_payload(events, "alert_profiles_updated")
    return saved_state["items"][0]


def _prepare_state(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "ALERT_PROFILES_PATH", str(tmp_path / "alert_profiles.json"), raising=False)
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "SETTINGS_PATH", str(tmp_path / "settings.json"))
    monkeypatch.setattr(app, "set_startup_enabled", lambda enabled: (True, ""))
    monkeypatch.setattr(app, "alert_profiles", [], raising=False)
    monkeypatch.setattr(app, "alert_cooldown_state", {})

    thresholds = _threshold_defaults(app)
    thresholds.update({
        "upper_warning_rmb": 700.0,
        "upper_critical_rmb": 720.5,
        "lower_warning_usd": 2300.0,
    })
    monkeypatch.setattr(app, "thresholds", thresholds)
    monkeypatch.setattr(app, "volatility_config", {"enabled": True, "percent": 1.5, "minutes": 15})

    settings = dict(app.DEFAULT_SETTINGS)
    settings.update({
        "alert_sound_enabled": True,
        "alert_dialog_enabled": False,
        "alert_cooldown_minutes": 45,
        "alert_quiet_start": "22:00",
        "alert_quiet_end": "07:30",
        "email_warning_enabled": True,
        "email_critical_enabled": False,
        "email_volatility_enabled": True,
        "webhook_warning_enabled": False,
        "webhook_critical_enabled": True,
        "webhook_volatility_enabled": False,
        "smtp_server": "smtp.example.com",
    })
    monkeypatch.setattr(app, "app_settings", settings)
    return app


def _set_non_profile_runtime_state(app):
    app.thresholds["upper_warning_rmb"] = 610.0
    app.thresholds["upper_critical_rmb"] = None
    app.thresholds["lower_warning_usd"] = None
    app.volatility_config = {"enabled": False, "percent": None, "minutes": 10}
    app.app_settings["alert_sound_enabled"] = False
    app.app_settings["alert_cooldown_minutes"] = 5
    app.app_settings["smtp_server"] = "smtp.latest.example.com"
    app.app_settings["startup_enabled"] = True
    app.app_settings["floating_price_enabled"] = True
    app.alert_cooldown_state = {"upper_warning_rmb": {"last_sent_at": "2026-07-09T09:00:00"}}


def test_alert_profile_socket_save_apply_rename_delete_flow(monkeypatch, tmp_path):
    app = _prepare_state(monkeypatch, tmp_path)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    initial_events = client.get_received()
    initial_state = _event_payload(initial_events, "init_state")
    assert initial_state["alert_profiles"]["items"] == []

    profile = _saved_profile(app, client)

    assert len(app.alert_profiles) == 1
    assert profile["name"] == "买入观察"
    assert profile["description"] == "回调时提醒"
    assert profile["thresholds"]["upper_warning_rmb"] == 700.0
    assert profile["thresholds"]["upper_critical_rmb"] == 720.5
    assert profile["volatility_config"] == {"enabled": True, "percent": 1.5, "minutes": 15}
    assert profile["settings"]["alert_cooldown_minutes"] == 45
    assert "smtp_server" not in profile["settings"]
    assert Path(app.ALERT_PROFILES_PATH).exists()

    profile_id = profile["id"]
    _set_non_profile_runtime_state(app)
    app.app_settings["smtp_server"] = "smtp.example.com"
    monkeypatch.setattr(
        app,
        "set_startup_enabled",
        lambda enabled: (_ for _ in ()).throw(AssertionError("profile apply must not change startup")),
    )
    monkeypatch.setattr(
        app,
        "apply_floating_price_settings",
        lambda settings: (_ for _ in ()).throw(AssertionError("profile apply must not apply floating settings")),
    )

    client.emit("apply_alert_profile", {"id": profile_id})
    events = client.get_received()
    event_names = {event["name"] for event in events}
    applied_profiles = _event_payload(events, "alert_profiles_updated")

    assert {"thresholds_updated", "volatility_updated", "settings_updated", "alert_profiles_updated"} <= event_names
    assert app.thresholds["upper_warning_rmb"] == 700.0
    assert app.thresholds["upper_critical_rmb"] == 720.5
    assert app.thresholds["lower_warning_usd"] == 2300.0
    assert app.volatility_config == {"enabled": True, "percent": 1.5, "minutes": 15}
    assert app.get_settings_snapshot()["alert_sound_enabled"] is True
    assert app.get_settings_snapshot()["alert_cooldown_minutes"] == 45
    assert app.get_settings_snapshot()["smtp_server"] == "smtp.example.com"
    assert app.get_settings_snapshot()["startup_enabled"] is True
    assert app.get_settings_snapshot()["floating_price_enabled"] is True
    assert app.alert_cooldown_state == {}
    assert Path(app.THRESHOLDS_PATH).exists()
    assert Path(app.SETTINGS_PATH).exists()
    assert applied_profiles["current_profile_id"] == profile_id
    assert applied_profiles["items"][0]["last_applied_at"]

    client.emit("rename_alert_profile", {
        "id": profile_id,
        "name": "更新模板",
        "description": "更新描述",
    })
    events = client.get_received()
    renamed = _event_payload(events, "alert_profiles_updated")
    assert renamed["items"][0]["name"] == "更新模板"
    assert renamed["items"][0]["description"] == "更新描述"

    client.emit("delete_alert_profile", {"id": profile_id})
    events = client.get_received()
    deleted = _event_payload(events, "alert_profiles_updated")
    assert deleted["items"] == []
    assert deleted["total"] == 0
    assert Path(app.ALERT_PROFILES_PATH).exists()
    client.disconnect()


def test_alert_profile_socket_invalid_inputs_emit_errors(monkeypatch, tmp_path):
    app = _prepare_state(monkeypatch, tmp_path)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("save_alert_profile", {"name": "   "})
    events = client.get_received()
    assert _event_payload(events, "alert_profile_error")["message"] == "模板名称不能为空"

    client.emit("apply_alert_profile", {"id": "profile-missing"})
    events = client.get_received()
    assert _event_payload(events, "alert_profile_error")["message"] == "未找到预警策略模板"
    client.disconnect()


def test_apply_alert_profile_preserves_latest_unrelated_settings(monkeypatch, tmp_path):
    app = _prepare_state(monkeypatch, tmp_path)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    profile = _saved_profile(app, client, name="保留设置")

    original_save_thresholds = app.save_thresholds

    def save_thresholds_with_concurrent_settings_change(data=None):
        app.app_settings["smtp_server"] = "changed.example.com"
        app.app_settings["export_dir"] = "/tmp/changed"
        return original_save_thresholds(data)

    app.app_settings["smtp_server"] = "before-apply.example.com"
    app.app_settings["export_dir"] = "/tmp/before-apply"
    monkeypatch.setattr(app, "save_thresholds", save_thresholds_with_concurrent_settings_change)

    client.emit("apply_alert_profile", {"id": profile["id"]})
    client.get_received()

    settings = app.get_settings_snapshot()
    assert settings["alert_cooldown_minutes"] == 45
    assert settings["smtp_server"] == "changed.example.com"
    assert settings["export_dir"] == "/tmp/changed"
    client.disconnect()


def test_apply_alert_profile_settings_save_failure_rolls_back_runtime_state(monkeypatch, tmp_path):
    app = _prepare_state(monkeypatch, tmp_path)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    profile = _saved_profile(app, client, name="回滚设置")

    _set_non_profile_runtime_state(app)
    previous_thresholds = dict(app.thresholds)
    previous_volatility_config = dict(app.volatility_config)
    previous_settings = app.get_settings_snapshot()
    previous_alert_cooldown_state = dict(app.alert_cooldown_state)
    previous_profiles = [dict(item) for item in app.alert_profiles]

    def fail_save_alert_profile_settings(applied_settings):
        raise OSError("settings unavailable")

    monkeypatch.setattr(
        app,
        "save_alert_profile_settings",
        fail_save_alert_profile_settings,
        raising=False,
    )

    client.emit("apply_alert_profile", {"id": profile["id"]})
    events = client.get_received()

    assert _event_payload(events, "alert_profile_error")["message"] == "预警策略模板应用失败，请检查配置目录权限。"
    assert app.thresholds == previous_thresholds
    assert app.volatility_config == previous_volatility_config
    assert app.get_settings_snapshot() == previous_settings
    assert app.alert_cooldown_state == previous_alert_cooldown_state
    assert app.alert_profiles == previous_profiles
    client.disconnect()


def test_apply_alert_profile_rollback_failure_emits_partial_write_warning(monkeypatch, tmp_path):
    app = _prepare_state(monkeypatch, tmp_path)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    profile = _saved_profile(app, client, name="回滚失败")

    def fail_save_alert_profile_settings(applied_settings):
        raise OSError("settings unavailable")

    original_save_thresholds = app.save_thresholds
    save_threshold_calls = {"count": 0}

    def save_thresholds_with_failed_rollback(data=None):
        save_threshold_calls["count"] += 1
        if save_threshold_calls["count"] == 2:
            raise OSError("threshold rollback unavailable")
        return original_save_thresholds(data)

    monkeypatch.setattr(
        app,
        "save_alert_profile_settings",
        fail_save_alert_profile_settings,
        raising=False,
    )
    monkeypatch.setattr(app, "save_thresholds", save_thresholds_with_failed_rollback)

    client.emit("apply_alert_profile", {"id": profile["id"]})
    events = client.get_received()

    assert _event_payload(events, "alert_profile_error")["message"] == (
        "预警策略模板应用失败，且部分配置可能已写入，请导出诊断后检查配置目录权限。"
    )
    client.disconnect()
