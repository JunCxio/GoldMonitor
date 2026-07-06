import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


DEFAULTS = {
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
    "risk_assistant_enabled": True,
    "risk_assistant_provider": "deepseek",
    "risk_assistant_depth": "standard",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-v4-pro",
    "deepseek_api_key": "",
    "openai_compatible_base_url": "",
    "openai_compatible_model": "",
    "openai_compatible_api_key": "",
    "risk_assistant_max_tokens": 1200,
    "risk_assistant_cooldown_seconds": 15,
    "risk_assistant_cache_minutes": 10,
    "export_dir": "",
}

OPTIONS = {
    "valid_smtp_encryptions": {"ssl", "tls"},
    "valid_close_behaviors": {"ask", "minimize_to_tray", "exit"},
    "valid_risk_assistant_providers": {"deepseek", "openai_compatible"},
    "valid_risk_assistant_depths": {"quick", "standard", "deep"},
    "valid_floating_display_modes": {"rmb_usd", "rmb_only", "usd_only"},
    "valid_floating_presets": {"minimal", "compact", "standard"},
    "default_email_subject_template": "subject",
    "default_email_body_template": "body",
    "risk_assistant_max_tokens": 1200,
}

SECRET_KEYS = ("smtp_password", "deepseek_api_key", "openai_compatible_api_key")


def test_normalize_settings_clamps_invalid_values_and_removes_legacy_update_keys():
    from goldmonitor.settings_store import normalize_settings

    normalized = normalize_settings({
        "floating_price_position_saved": True,
        "floating_price_x": "12.9",
        "floating_price_y": "bad",
        "floating_price_opacity": "10",
        "floating_price_display_mode": "bad",
        "floating_price_preset": "huge",
        "floating_price_always_on_top": True,
        "close_behavior": "bad",
        "close_remembered": True,
        "smtp_server": " smtp.example.com ",
        "smtp_encryption": "plain",
        "alert_cooldown_minutes": 999,
        "alert_quiet_start": "8:5",
        "alert_quiet_end": "25:00",
        "risk_assistant_provider": "unknown",
        "risk_assistant_depth": "slow",
        "deepseek_base_url": " https://api.deepseek.com/ ",
        "deepseek_api_key": " sk-test ",
        "risk_assistant_max_tokens": "9000",
        "risk_assistant_cooldown_seconds": "-5",
        "risk_assistant_cache_minutes": "90",
        "export_dir": " ~/GoldMonitorExports ",
        "update_manifest_url": "legacy",
        "update_auto_check_interval_hours": 1,
    }, DEFAULTS, OPTIONS)

    assert normalized["floating_price_position_saved"] is False
    assert normalized["floating_price_x"] is None
    assert normalized["floating_price_y"] is None
    assert normalized["floating_price_opacity"] == 50
    assert normalized["floating_price_display_mode"] == "rmb_usd"
    assert normalized["floating_price_preset"] == "compact"
    assert normalized["floating_price_always_on_top"] is True
    assert normalized["close_behavior"] == "ask"
    assert normalized["close_remembered"] is False
    assert normalized["smtp_server"] == "smtp.example.com"
    assert normalized["smtp_encryption"] == "ssl"
    assert normalized["alert_cooldown_minutes"] == 240
    assert normalized["alert_quiet_start"] == "08:05"
    assert normalized["alert_quiet_end"] == ""
    assert normalized["risk_assistant_provider"] == "deepseek"
    assert normalized["risk_assistant_depth"] == "standard"
    assert normalized["deepseek_base_url"] == "https://api.deepseek.com"
    assert normalized["deepseek_api_key"] == "sk-test"
    assert normalized["risk_assistant_max_tokens"] == 4000
    assert normalized["risk_assistant_cooldown_seconds"] == 0
    assert normalized["risk_assistant_cache_minutes"] == 60
    assert normalized["export_dir"] == "~/GoldMonitorExports"
    assert "update_manifest_url" not in normalized
    assert "update_auto_check_interval_hours" not in normalized


def test_settings_file_store_migrates_and_hides_secrets():
    from goldmonitor.settings_store import SettingsFileStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = str(Path(tmp_dir) / "settings.json")
        credential_store = {}

        def read_secret(key):
            return credential_store.get(key, "")

        def write_secret(key, value):
            if value:
                credential_store[key] = value
            else:
                credential_store.pop(key, None)
            return True

        store = SettingsFileStore(
            path,
            defaults=DEFAULTS,
            options=OPTIONS,
            secret_keys=SECRET_KEYS,
            read_secret=read_secret,
            write_secret=write_secret,
            credentials_required=True,
        )

        saved = store.save({
            "deepseek_api_key": "sk-secret",
            "openai_compatible_api_key": "sk-compatible",
            "smtp_password": "smtp-secret",
        })
        assert saved["deepseek_api_key"] == "sk-secret"
        assert credential_store["deepseek_api_key"] == "sk-secret"
        persisted = Path(path).read_text(encoding="utf-8")
        assert "sk-secret" not in persisted
        assert "sk-compatible" not in persisted
        assert "smtp-secret" not in persisted

        legacy_payload = json.loads(persisted)
        legacy_payload["deepseek_api_key"] = "legacy-secret"
        Path(path).write_text(json.dumps(legacy_payload, ensure_ascii=False), encoding="utf-8")
        credential_store.clear()
        loaded, error = store.load()
        assert error == ""
        assert loaded["deepseek_api_key"] == "legacy-secret"
        assert credential_store["deepseek_api_key"] == "legacy-secret"
        assert "legacy-secret" not in Path(path).read_text(encoding="utf-8")


def test_public_snapshot_masks_secrets_and_update_payload_preserves_existing_empty_values():
    from goldmonitor.settings_store import build_public_settings_snapshot, merge_settings_update

    current = dict(DEFAULTS)
    current.update({
        "deepseek_api_key": "sk-abcdef123456",
        "openai_compatible_api_key": "sk-compatible",
        "smtp_password": "smtp-secret",
    })
    public = build_public_settings_snapshot(
        current,
        secret_keys=SECRET_KEYS,
        platform="test",
        platform_capabilities={"platform": "test"},
    )
    rendered = json.dumps(public, ensure_ascii=False)
    assert "deepseek_api_key" not in public
    assert "smtp_password" not in public
    assert "sk-abcdef123456" not in rendered
    assert public["deepseek_api_key_configured"] is True
    assert public["deepseek_api_key_masked"] == "sk-a********3456"
    assert public["smtp_password_configured"] is True

    updated = merge_settings_update(
        current,
        {"deepseek_model": "deepseek-chat", "deepseek_api_key": ""},
        allowed_keys=set(DEFAULTS),
        secret_clear_flags={"deepseek_api_key": "deepseek_api_key_clear"},
    )
    assert updated["deepseek_model"] == "deepseek-chat"
    assert updated["deepseek_api_key"] == "sk-abcdef123456"

    cleared = merge_settings_update(
        current,
        {"deepseek_api_key": "", "deepseek_api_key_clear": True},
        allowed_keys=set(DEFAULTS),
        secret_clear_flags={"deepseek_api_key": "deepseek_api_key_clear"},
    )
    assert cleared["deepseek_api_key"] == ""


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("settings store module checks passed.")
