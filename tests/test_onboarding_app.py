from datetime import datetime


def test_settings_normalization_preserves_onboarding_state():
    from goldmonitor.settings_store import normalize_settings

    defaults = {
        "onboarding_started": False,
        "onboarding_completed": False,
        "onboarding_version": 1,
        "onboarding_completed_at": "",
        "startup_enabled": False,
        "startup_to_tray": True,
        "floating_price_enabled": True,
        "floating_price_position_saved": False,
        "floating_price_x": None,
        "floating_price_y": None,
        "floating_price_opacity": 94,
        "floating_price_display_mode": "rmb_usd",
        "floating_price_preset": "compact",
        "floating_price_snap_edge": True,
        "floating_price_always_on_top": False,
        "floating_price_hide_on_fullscreen": True,
        "floating_price_lock_position": False,
        "close_behavior": "ask",
        "close_remembered": False,
        "alert_sound_enabled": True,
        "alert_dialog_enabled": True,
        "smtp_server": "",
        "smtp_port": "465",
        "smtp_encryption": "ssl",
        "smtp_sender": "",
        "smtp_password": "",
        "smtp_recipient": "",
        "webhook_enabled": False,
        "webhook_url": "",
        "webhook_warning_enabled": True,
        "webhook_critical_enabled": True,
        "webhook_volatility_enabled": True,
        "email_warning_enabled": True,
        "email_critical_enabled": True,
        "email_volatility_enabled": True,
        "alert_cooldown_minutes": 30,
        "alert_quiet_start": "",
        "alert_quiet_end": "",
        "email_subject_template": "subject",
        "email_body_template": "body",
        "daily_digest_enabled": False,
        "daily_digest_time": "20:00",
        "daily_digest_email_enabled": True,
        "daily_digest_webhook_enabled": False,
        "risk_assistant_enabled": True,
        "risk_assistant_provider": "deepseek",
        "risk_assistant_depth": "standard",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "model",
        "deepseek_api_key": "",
        "openai_compatible_base_url": "",
        "openai_compatible_model": "",
        "openai_compatible_api_key": "",
        "risk_assistant_max_tokens": 1200,
        "risk_assistant_cooldown_seconds": 15,
        "risk_assistant_cache_minutes": 10,
        "export_dir": "",
    }
    options = {
        "valid_floating_display_modes": {"rmb_usd", "rmb_only", "usd_only"},
        "valid_floating_presets": {"compact"},
        "valid_close_behaviors": {"ask", "minimize_to_tray", "exit"},
        "valid_smtp_encryptions": {"ssl", "tls"},
        "valid_risk_assistant_providers": {"deepseek"},
        "valid_risk_assistant_depths": {"standard"},
    }

    normalized = normalize_settings({
        "onboarding_started": 1,
        "onboarding_completed": True,
        "onboarding_version": "2",
        "onboarding_completed_at": "2026-07-27T12:00:00",
    }, defaults, options)

    assert normalized["onboarding_started"] is True
    assert normalized["onboarding_completed"] is True
    assert normalized["onboarding_version"] == 2
    assert normalized["onboarding_completed_at"] == "2026-07-27T12:00:00"


def test_complete_onboarding_only_applies_supported_preferences(monkeypatch):
    import app

    current = dict(app.DEFAULT_SETTINGS)
    applied = []
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: dict(current))
    monkeypatch.setattr(
        app,
        "apply_settings",
        lambda settings: (applied.append(dict(settings)) or dict(settings), None),
    )

    result = app.complete_onboarding({
        "floating_price_display_mode": "rmb_only",
        "startup_enabled": True,
        "alert_sound_enabled": False,
        "alert_cooldown_minutes": 60,
        "smtp_password": "must-not-import",
    })

    saved = applied[-1]
    assert result["ok"] is True
    assert saved["onboarding_started"] is True
    assert saved["onboarding_completed"] is True
    assert saved["onboarding_version"] == 1
    assert datetime.fromisoformat(saved["onboarding_completed_at"])
    assert saved["floating_price_display_mode"] == "rmb_only"
    assert saved["startup_enabled"] is True
    assert saved["alert_sound_enabled"] is False
    assert saved["alert_cooldown_minutes"] == 60
    assert saved["smtp_password"] == current["smtp_password"]


def test_onboarding_socket_completion_broadcasts_settings(monkeypatch):
    import app

    expected = {
        "ok": True,
        "settings": {"onboarding_completed": True},
        "startup_error": "",
        "message": "首次使用设置已保存。",
    }
    monkeypatch.setattr(app, "complete_onboarding", lambda data=None: expected)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    other = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    other.get_received()
    client.emit("complete_onboarding", {"startup_enabled": False})

    received = client.get_received()
    other_received = other.get_received()
    completed = next(item["args"][0] for item in received if item["name"] == "onboarding_completed")
    assert completed == expected
    assert any(item["name"] == "settings_updated" for item in received)
    assert any(item["name"] == "settings_updated" for item in other_received)
    assert not any(item["name"] == "onboarding_completed" for item in other_received)
    client.disconnect()
    other.disconnect()
