import json
from pathlib import Path
from types import SimpleNamespace
import threading


def _defaults():
    return {
        "startup_enabled": False,
        "startup_to_tray": True,
        "floating_price_enabled": True,
        "floating_price_windows_mode": "floating",
        "floating_price_taskbar_target": "auto",
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
        "notification_auto_retry_enabled": False,
        "risk_assistant_enabled": True,
        "risk_assistant_provider": "deepseek",
        "risk_assistant_depth": "standard",
        "deepseek_base_url": "https://api.deepseek.com",
        "deepseek_model": "deepseek-chat",
        "deepseek_api_key": "",
        "openai_compatible_base_url": "",
        "openai_compatible_model": "",
        "openai_compatible_api_key": "",
        "risk_assistant_max_tokens": 1200,
        "risk_assistant_cooldown_seconds": 15,
        "risk_assistant_cache_minutes": 10,
        "market_source_enabled": {"gold": ["gold"], "forex": ["forex"]},
        "market_source_order": {"gold": ["gold"], "forex": ["forex"]},
        "export_dir": "",
    }


def _options():
    return {
        "valid_smtp_encryptions": {"ssl", "tls"},
        "valid_close_behaviors": {"ask", "minimize_to_tray", "exit"},
        "valid_risk_assistant_providers": {"deepseek", "openai_compatible"},
        "valid_risk_assistant_depths": {"quick", "standard", "deep"},
        "valid_floating_display_modes": {"rmb_usd", "rmb_only", "usd_only"},
        "valid_floating_windows_modes": {"floating", "taskbar", "both"},
        "valid_floating_presets": {"minimal", "compact", "standard"},
        "default_email_subject_template": "subject",
        "default_email_body_template": "body",
        "risk_assistant_max_tokens": 1200,
        "market_source_defaults": {"gold": ["gold"], "forex": ["forex"]},
    }


def _runtime(tmp_path, secrets=None):
    from goldmonitor.settings_runtime import SettingsRuntime

    defaults = _defaults()
    state = SimpleNamespace(
        settings_lock=threading.RLock(),
        app_settings=dict(defaults),
        last_settings_error="initial",
        taskbar_layout_state={"visible": True, "reason": "ready"},
    )
    secret_store = secrets if isinstance(secrets, dict) else {}

    def write_secret(key, value):
        if value:
            secret_store[key] = value
        else:
            secret_store.pop(key, None)
        return True

    runtime = SettingsRuntime(
        state,
        settings_path=str(tmp_path / "settings.json"),
        defaults=defaults,
        options=_options(),
        secret_keys=("smtp_password", "deepseek_api_key", "openai_compatible_api_key"),
        read_secret=lambda key: secret_store.get(key, ""),
        write_secret=write_secret,
        credentials_required=True,
        platform_name=lambda: "windows",
        platform_capabilities=lambda: {"has_taskbar_price": True},
        default_export_dir=str(tmp_path / "exports"),
        resolve_export_dir=lambda settings: settings.get("export_dir") or str(tmp_path / "exports"),
        build_export_dir_check=lambda settings: {"ok": True, "path": settings.get("export_dir") or str(tmp_path / "exports")},
        taskbar_discovery_state=lambda: {"available": True, "visible": False},
    )
    return runtime, state, secret_store


def test_settings_runtime_owns_save_load_and_public_snapshot(tmp_path):
    runtime, state, secrets = _runtime(tmp_path)

    saved = runtime.save({
        **state.app_settings,
        "smtp_server": "smtp.example.com",
        "smtp_password": "secret-value",
        "export_dir": str(tmp_path / "custom"),
    })

    assert saved["smtp_password"] == "secret-value"
    assert secrets["smtp_password"] == "secret-value"
    persisted = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
    assert persisted["smtp_password"] == ""

    loaded = runtime.load()
    assert loaded["smtp_password"] == "secret-value"
    assert state.last_settings_error is None

    public = runtime.public_snapshot()
    assert public["platform"] == "windows"
    assert public["platform_capabilities"] == {"has_taskbar_price": True}
    assert public["smtp_password_configured"] is True
    assert "smtp_password" not in public
    assert public["export_dir_effective"] == str(tmp_path / "custom")
    assert public["taskbar_price_state"] == {
        "available": True,
        "visible": True,
        "reason": "ready",
    }


def test_settings_runtime_records_load_error_and_returns_normalized_defaults(tmp_path):
    runtime, state, _secrets = _runtime(tmp_path)
    settings_path = Path(runtime.settings_path)
    settings_path.write_text("{invalid", encoding="utf-8")

    loaded = runtime.load()

    assert loaded["floating_price_preset"] == "compact"
    assert state.last_settings_error
    assert json.loads(settings_path.read_text(encoding="utf-8"))["close_behavior"] == "ask"
