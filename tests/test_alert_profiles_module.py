import json
import inspect
from datetime import datetime
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


THRESHOLD_KEYS = [
    f"{kind}_{mode}"
    for mode in ("usd", "rmb")
    for kind in ("upper_warning", "upper_critical", "lower_warning", "lower_critical")
]


def fixed_now():
    return datetime(2026, 7, 9, 10, 0, 0)


def defaults():
    return {key: None for key in THRESHOLD_KEYS}


def settings_snapshot():
    return {
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
        "smtp_password": "secret",
        "webhook_url": "https://example.com/hook",
    }


def profile_thresholds():
    thresholds = defaults()
    thresholds.update({
        "upper_warning_rmb": "700",
        "upper_critical_rmb": "720.5",
        "lower_warning_usd": "2300",
    })
    return thresholds


def volatility_snapshot():
    return {"enabled": True, "percent": "1.5", "minutes": "15"}


def stored_volatility_snapshot():
    return {"percent": 1.5, "minutes": 15, "enabled": True}


def default_volatility():
    return {"percent": None, "minutes": 10, "enabled": False}


def test_alert_profile_public_api_matches_planned_contract():
    from goldmonitor.alert_profiles import (
        ALERT_PROFILE_SETTING_KEYS,
        AlertProfileStore,
        normalize_alert_profile,
        normalize_alert_profiles,
    )

    assert ALERT_PROFILE_SETTING_KEYS == (
        "alert_sound_enabled",
        "alert_dialog_enabled",
        "alert_cooldown_minutes",
        "alert_quiet_start",
        "alert_quiet_end",
        "email_warning_enabled",
        "email_critical_enabled",
        "email_volatility_enabled",
        "webhook_warning_enabled",
        "webhook_critical_enabled",
        "webhook_volatility_enabled",
    )
    assert str(inspect.signature(normalize_alert_profile)) == (
        "(item, threshold_defaults, current_volatility_config, current_settings, "
        "existing=None, now_factory=None, id_factory=None)"
    )
    assert str(inspect.signature(normalize_alert_profiles)) == (
        "(items, threshold_defaults, current_volatility_config, current_settings, "
        "existing_items=None, now_factory=None, id_factory=None)"
    )
    assert str(inspect.signature(AlertProfileStore.__init__)) == (
        "(self, json_path, threshold_defaults, current_volatility_config, "
        "current_settings, now_factory=None, id_factory=None)"
    )


def test_build_profile_from_state_keeps_only_alert_strategy_fields():
    from goldmonitor.alert_profiles import build_profile_from_state

    profile = build_profile_from_state(
        {"name": "买入观察", "description": "回调时提醒"},
        profile_thresholds(),
        volatility_snapshot(),
        settings_snapshot(),
        now_factory=fixed_now,
        id_factory=lambda: "profile-fixed",
    )

    assert profile["id"] == "profile-fixed"
    assert profile["name"] == "买入观察"
    assert profile["description"] == "回调时提醒"
    assert profile["thresholds"]["upper_warning_rmb"] == 700.0
    assert profile["thresholds"]["upper_critical_rmb"] == 720.5
    assert profile["thresholds"]["lower_warning_usd"] == 2300.0
    assert profile["volatility_config"] == stored_volatility_snapshot()
    assert profile["settings"]["alert_cooldown_minutes"] == 45
    assert "smtp_password" not in profile["settings"]
    assert "webhook_url" not in profile["settings"]
    assert profile["created_at"] == "2026-07-09T10:00:00"
    assert profile["updated_at"] == "2026-07-09T10:00:00"
    assert profile["last_applied_at"] == ""

    with pytest.raises(ValueError, match="模板名称不能为空"):
        build_profile_from_state(
            {"name": "   "},
            defaults(),
            {"enabled": False, "percent": None, "minutes": 10},
            settings_snapshot(),
            now_factory=fixed_now,
            id_factory=lambda: "profile-fixed",
        )


def test_normalize_alert_profiles_deduplicates_limits_and_preserves_timestamps():
    from goldmonitor.alert_profiles import ALERT_PROFILE_LIMIT, normalize_alert_profiles

    existing_items = [
        {
            "id": "profile-a",
            "name": "原名称",
            "created_at": "2026-07-01T09:00:00",
            "updated_at": "2026-07-01T09:05:00",
            "thresholds": {"upper_warning_rmb": "680"},
            "volatility_config": {"enabled": True, "percent": "1", "minutes": "10"},
            "settings": {"alert_sound_enabled": False},
        }
    ]
    raw_items = [
        {
            "id": "profile-a",
            "name": "中间名称",
            "thresholds": {"upper_warning_rmb": "690", "unexpected_badmode": "1"},
            "settings": {"alert_sound_enabled": True},
        },
        {
            "id": "profile-a",
            "name": "更新名称",
            "thresholds": {"upper_warning_rmb": "700"},
            "volatility_config": {"enabled": True, "percent": "bad", "minutes": "15"},
            "settings": {
                "alert_cooldown_minutes": "60",
                "smtp_password": "secret",
            },
        },
        {"id": "profile-empty", "name": "   "},
    ]
    raw_items.extend(
        {
            "id": f"profile-extra-{index}",
            "name": f"模板 {index}",
            "thresholds": {"lower_warning_usd": str(2200 + index)},
        }
        for index in range(25)
    )

    profiles = normalize_alert_profiles(
        raw_items,
        defaults(),
        default_volatility(),
        settings_snapshot(),
        existing_items=existing_items,
        now_factory=fixed_now,
    )
    profile_a = next(profile for profile in profiles if profile["id"] == "profile-a")

    assert len(profiles) == ALERT_PROFILE_LIMIT
    assert [profile["id"] for profile in profiles].count("profile-a") == 1
    assert all(profile["name"].strip() for profile in profiles)
    assert profile_a["name"] == "更新名称"
    assert profile_a["created_at"] == "2026-07-01T09:00:00"
    assert profile_a["updated_at"] == "2026-07-09T10:00:00"
    assert profile_a["thresholds"]["upper_warning_rmb"] == 700.0
    assert "unexpected_badmode" not in profile_a["thresholds"]
    assert profile_a["volatility_config"] == {"percent": None, "minutes": 15, "enabled": False}
    assert "smtp_password" not in profile_a["settings"]


def test_apply_profile_to_state_preserves_unrelated_settings_and_matches():
    from goldmonitor.alert_profiles import (
        apply_profile_to_state,
        build_profile_from_state,
        profile_matches_state,
    )

    profile = build_profile_from_state(
        {"name": "买入观察", "description": "回调时提醒"},
        profile_thresholds(),
        volatility_snapshot(),
        settings_snapshot(),
        now_factory=fixed_now,
        id_factory=lambda: "profile-fixed",
    )
    current_thresholds = defaults()
    current_thresholds["upper_warning_rmb"] = 660
    current_settings = {
        "alert_sound_enabled": False,
        "alert_cooldown_minutes": 5,
        "smtp_server": "smtp.current.example.com",
    }

    applied = apply_profile_to_state(
        profile,
        current_thresholds,
        {"enabled": True, "percent": "3", "minutes": "30"},
        current_settings,
    )

    assert applied["thresholds"]["upper_warning_rmb"] == 700.0
    assert applied["thresholds"]["upper_critical_rmb"] == 720.5
    assert applied["volatility_config"] == stored_volatility_snapshot()
    assert applied["settings"]["alert_cooldown_minutes"] == 45
    assert applied["settings"]["smtp_server"] == "smtp.current.example.com"
    assert profile_matches_state(
        profile,
        applied["thresholds"],
        applied["volatility_config"],
        applied["settings"],
    ) is True

    with pytest.raises(ValueError, match="未找到预警策略模板"):
        apply_profile_to_state(None, current_thresholds, default_volatility(), current_settings)
    with pytest.raises(ValueError, match="未找到预警策略模板"):
        apply_profile_to_state(
            {"name": "x"},
            current_thresholds,
            default_volatility(),
            current_settings,
        )


def test_alert_profile_settings_are_normalized_before_store_and_apply():
    from goldmonitor.alert_profiles import apply_profile_to_state, build_profile_from_state

    raw_settings = settings_snapshot()
    raw_settings.update({
        "alert_sound_enabled": "false",
        "webhook_critical_enabled": "yes",
        "alert_cooldown_minutes": "999",
        "alert_quiet_start": "8:5",
        "alert_quiet_end": "invalid",
    })

    profile = build_profile_from_state(
        {"name": "归一化设置", "description": ""},
        profile_thresholds(),
        volatility_snapshot(),
        raw_settings,
        now_factory=fixed_now,
        id_factory=lambda: "profile-normalized",
    )

    assert profile["settings"]["alert_sound_enabled"] is False
    assert profile["settings"]["webhook_critical_enabled"] is True
    assert profile["settings"]["alert_cooldown_minutes"] == 240
    assert profile["settings"]["alert_quiet_start"] == "08:05"
    assert profile["settings"]["alert_quiet_end"] == ""

    applied = apply_profile_to_state(
        profile,
        defaults(),
        default_volatility(),
        settings_snapshot(),
    )

    assert applied["settings"]["alert_sound_enabled"] is False
    assert applied["settings"]["webhook_critical_enabled"] is True
    assert applied["settings"]["alert_cooldown_minutes"] == 240
    assert applied["settings"]["alert_quiet_start"] == "08:05"
    assert applied["settings"]["alert_quiet_end"] == ""


def test_alert_profiles_state_uses_current_profile_id_contract():
    from goldmonitor.alert_profiles import alert_profiles_state, build_profile_from_state

    profile = build_profile_from_state(
        {"name": "买入观察", "description": "回调时提醒"},
        profile_thresholds(),
        volatility_snapshot(),
        settings_snapshot(),
        now_factory=fixed_now,
        id_factory=lambda: "profile-fixed",
    )

    state = alert_profiles_state(
        [profile],
        thresholds=profile["thresholds"],
        volatility_config=profile["volatility_config"],
        settings=profile["settings"],
    )

    assert state["current_profile_id"] == "profile-fixed"
    assert "matched_profile_id" not in state

    default_state = alert_profiles_state([profile])
    assert default_state["current_profile_id"] == ""
    assert "matched_profile_id" not in default_state


def test_alert_profile_store_writes_versioned_payload_and_round_trips(tmp_path):
    from goldmonitor.alert_profiles import AlertProfileStore, build_profile_from_state

    profile = build_profile_from_state(
        {"name": "买入观察", "description": "回调时提醒"},
        profile_thresholds(),
        volatility_snapshot(),
        settings_snapshot(),
        now_factory=fixed_now,
        id_factory=lambda: "profile-fixed",
    )
    store = AlertProfileStore(
        str(tmp_path / "alert_profiles.json"),
        defaults(),
        default_volatility(),
        settings_snapshot(),
        now_factory=fixed_now,
    )

    saved = store.save([profile])
    updated = store.save([
        {
            "id": "profile-fixed",
            "name": "更新名称",
            "thresholds": {"upper_warning_rmb": "710"},
        }
    ])
    with open(tmp_path / "alert_profiles.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    loaded = store.load()

    assert payload["schema_version"] == 1
    assert updated[0]["created_at"] == saved[0]["created_at"]
    assert updated[0]["updated_at"] == "2026-07-09T10:00:00"
    assert updated[0]["thresholds"]["upper_warning_rmb"] == 710.0
    assert payload["items"] == updated
    assert loaded == updated


def test_alert_profile_store_loads_legacy_list_and_handles_invalid_json(tmp_path):
    from goldmonitor.alert_profiles import AlertProfileStore, build_profile_from_state

    profile = build_profile_from_state(
        {"name": "旧格式模板", "description": ""},
        profile_thresholds(),
        volatility_snapshot(),
        settings_snapshot(),
        now_factory=fixed_now,
        id_factory=lambda: "profile-legacy",
    )
    path = tmp_path / "alert_profiles.json"
    store = AlertProfileStore(
        str(path),
        defaults(),
        default_volatility(),
        settings_snapshot(),
        now_factory=fixed_now,
    )

    with open(path, "w", encoding="utf-8") as f:
        json.dump([profile], f, ensure_ascii=False)

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0]["id"] == "profile-legacy"
    assert loaded[0]["thresholds"]["upper_warning_rmb"] == 700.0

    with open(path, "w", encoding="utf-8") as f:
        f.write("{ invalid json")

    assert store.load() == []
