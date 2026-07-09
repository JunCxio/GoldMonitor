import json
import os
import secrets
from datetime import datetime

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload
from goldmonitor.targets import normalize_thresholds, normalize_volatility_config


ALERT_PROFILE_LIMIT = 20
ALERT_PROFILE_NAME_LIMIT = 40
ALERT_PROFILE_DESCRIPTION_LIMIT = 120
ALERT_PROFILE_SETTING_KEYS = (
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
ALERT_PROFILE_TIME_SETTING_KEYS = ("alert_quiet_start", "alert_quiet_end")
ALERT_PROFILE_INTEGER_SETTING_KEYS = ("alert_cooldown_minutes",)
ALERT_PROFILE_BOOLEAN_SETTING_KEYS = tuple(
    key
    for key in ALERT_PROFILE_SETTING_KEYS
    if key not in ALERT_PROFILE_TIME_SETTING_KEYS + ALERT_PROFILE_INTEGER_SETTING_KEYS
)

THRESHOLD_KEYS = [
    f"{kind}_{mode}"
    for mode in ("usd", "rmb")
    for kind in ("upper_warning", "upper_critical", "lower_warning", "lower_critical")
]
DEFAULT_THRESHOLDS = {key: None for key in THRESHOLD_KEYS}


def generate_alert_profile_id():
    return "profile-" + secrets.token_hex(8)


def _now_iso(now_factory):
    return now_factory().isoformat(timespec="seconds")


def _valid_profile_id(value):
    return (
        isinstance(value, str)
        and value.startswith("profile-")
        and len(value) > len("profile-")
    )


def _new_profile_id(id_factory):
    if callable(id_factory):
        profile_id = str(id_factory() or "").strip()
        if _valid_profile_id(profile_id):
            return profile_id
    return generate_alert_profile_id()


def _normalize_text(value, limit):
    text = str(value or "").strip()
    if len(text) > limit:
        return text[:limit]
    return text


def _profile_id_from_item(item, existing, id_factory):
    raw_id = item.get("id")
    if raw_id in (None, ""):
        raw_id = existing.get("id")
    profile_id = str(raw_id or "").strip()
    if _valid_profile_id(profile_id):
        return profile_id
    return _new_profile_id(id_factory)


def _settings_from_mapping(value):
    if not isinstance(value, dict):
        return {}
    return {key: value[key] for key in ALERT_PROFILE_SETTING_KEYS if key in value}


def _coerce_bool_setting(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off", ""}:
            return False
        return bool(default)
    return bool(default)


def _coerce_int_setting(value, default=30, minimum=0, maximum=240):
    try:
        default_number = int(float(default))
    except (TypeError, ValueError):
        default_number = 30
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        number = default_number
    return max(minimum, min(maximum, number))


def _normalize_hhmm_setting(value):
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    if len(parts) != 2:
        return ""
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return ""
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return f"{hour:02d}:{minute:02d}"
    return ""


def _normalize_setting_value(key, value, default=None):
    if key in ALERT_PROFILE_BOOLEAN_SETTING_KEYS:
        return _coerce_bool_setting(value, default)
    if key in ALERT_PROFILE_INTEGER_SETTING_KEYS:
        return _coerce_int_setting(value, default)
    if key in ALERT_PROFILE_TIME_SETTING_KEYS:
        return _normalize_hhmm_setting(value)
    return value


def _merge_normalized_settings(settings, source):
    for key, value in _settings_from_mapping(source).items():
        settings[key] = _normalize_setting_value(key, value, settings.get(key))


def _normalize_profile_settings(item, existing, current_settings):
    settings = {}
    _merge_normalized_settings(settings, current_settings)
    _merge_normalized_settings(settings, existing.get("settings"))
    _merge_normalized_settings(settings, item.get("settings"))
    _merge_normalized_settings(settings, item)
    return settings


def _threshold_updates_from_item(item):
    if "thresholds" in item:
        thresholds = item.get("thresholds")
        return dict(thresholds) if isinstance(thresholds, dict) else {}
    return {key: item[key] for key in THRESHOLD_KEYS if key in item}


def _raw_volatility_from_item(item, thresholds, existing, current_volatility_config):
    if "volatility_config" in item:
        return item.get("volatility_config")
    if isinstance(thresholds, dict) and "volatility_config" in thresholds:
        return thresholds.get("volatility_config")
    if isinstance(existing.get("volatility_config"), dict):
        return existing.get("volatility_config")
    return current_volatility_config


def _normalize_profile_thresholds_and_volatility(
    item,
    threshold_defaults,
    current_volatility_config,
    existing,
):
    defaults = (
        dict(threshold_defaults)
        if isinstance(threshold_defaults, dict)
        else dict(DEFAULT_THRESHOLDS)
    )
    threshold_values = dict(existing.get("thresholds") or {})
    updates = _threshold_updates_from_item(item)
    threshold_values.update(updates)
    raw_volatility = _raw_volatility_from_item(item, updates, existing, current_volatility_config)

    normalized = normalize_thresholds(threshold_values, defaults, raw_volatility)
    thresholds = {key: normalized.get(key) for key in defaults if key != "volatility_config"}
    volatility_config = normalize_volatility_config(
        raw_volatility if raw_volatility is not None else normalized.get("volatility_config")
    )
    return thresholds, volatility_config


def normalize_alert_profile(
    item,
    threshold_defaults,
    current_volatility_config,
    current_settings,
    existing=None,
    now_factory=None,
    id_factory=None,
):
    if not isinstance(item, dict):
        return None

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    now = _now_iso(now_factory)

    name = _normalize_text(item.get("name", existing.get("name", "")), ALERT_PROFILE_NAME_LIMIT)
    if not name:
        return None

    description = _normalize_text(
        item.get("description", existing.get("description", "")),
        ALERT_PROFILE_DESCRIPTION_LIMIT,
    )
    thresholds, volatility_config = _normalize_profile_thresholds_and_volatility(
        item,
        threshold_defaults,
        current_volatility_config,
        existing,
    )

    return {
        "id": _profile_id_from_item(item, existing, id_factory),
        "name": name,
        "description": description,
        "thresholds": thresholds,
        "volatility_config": volatility_config,
        "settings": _normalize_profile_settings(item, existing, current_settings),
        "created_at": str(existing.get("created_at") or item.get("created_at") or now),
        "updated_at": now if existing else str(item.get("updated_at") or now),
        "last_applied_at": str(
            item.get("last_applied_at", existing.get("last_applied_at", "")) or ""
        ).strip(),
    }


def _items_by_id(items):
    if not isinstance(items, list):
        return {}
    return {
        str(item.get("id") or "").strip(): item
        for item in items
        if isinstance(item, dict) and _valid_profile_id(str(item.get("id") or "").strip())
    }


def normalize_alert_profiles(
    items,
    threshold_defaults,
    current_volatility_config,
    current_settings,
    existing_items=None,
    now_factory=None,
    id_factory=None,
):
    if not isinstance(items, list):
        return []

    normalized = []
    indexes_by_id = {}
    existing_by_id = _items_by_id(existing_items)
    for item in items:
        raw_id = ""
        if isinstance(item, dict):
            raw_id = str(item.get("id") or "").strip()
        existing = None
        if raw_id in indexes_by_id:
            existing = normalized[indexes_by_id[raw_id]]
        elif raw_id in existing_by_id:
            existing = existing_by_id[raw_id]
        profile = normalize_alert_profile(
            item,
            threshold_defaults,
            current_volatility_config,
            current_settings,
            existing=existing,
            now_factory=now_factory,
            id_factory=id_factory,
        )
        if profile is None:
            continue

        profile_id = profile.get("id")
        if profile_id in indexes_by_id:
            normalized[indexes_by_id[profile_id]] = profile
            continue
        if len(normalized) >= ALERT_PROFILE_LIMIT:
            continue
        indexes_by_id[profile_id] = len(normalized)
        normalized.append(profile)
    return normalized


def build_profile_from_state(
    data,
    thresholds,
    volatility_config,
    settings,
    now_factory=None,
    id_factory=None,
):
    data = data if isinstance(data, dict) else {}
    name = _normalize_text(data.get("name", ""), ALERT_PROFILE_NAME_LIMIT)
    if not name:
        raise ValueError("模板名称不能为空")

    threshold_defaults = {key: None for key in thresholds} if isinstance(thresholds, dict) else {}
    profile = normalize_alert_profile(
        {
            "name": name,
            "description": data.get("description", ""),
            "thresholds": thresholds,
            "volatility_config": volatility_config,
            "settings": settings,
        },
        threshold_defaults,
        volatility_config,
        settings,
        now_factory=now_factory,
        id_factory=id_factory,
    )
    if profile is None:
        raise ValueError("模板名称不能为空")
    return profile


def _current_volatility_config(thresholds, volatility_config):
    if volatility_config is None and isinstance(thresholds, dict):
        volatility_config = thresholds.get("volatility_config")
    return normalize_volatility_config(volatility_config)


def _threshold_defaults_from_state(thresholds):
    if isinstance(thresholds, dict):
        return {key: None for key in thresholds if key != "volatility_config"}
    return dict(DEFAULT_THRESHOLDS)


def _normalize_threshold_values(thresholds, threshold_defaults, volatility_config=None):
    normalized = normalize_thresholds(thresholds, threshold_defaults, volatility_config)
    return {key: normalized.get(key) for key in threshold_defaults if key != "volatility_config"}


def apply_profile_to_state(
    profile,
    current_thresholds,
    current_volatility_config,
    current_settings,
):
    if not _is_stored_profile_shape(profile):
        raise ValueError("未找到预警策略模板")

    threshold_defaults = _threshold_defaults_from_state(
        current_thresholds if isinstance(current_thresholds, dict) else profile.get("thresholds")
    )
    normalized_profile = normalize_alert_profile(
        profile,
        threshold_defaults,
        current_volatility_config,
        current_settings,
    )
    next_settings = dict(current_settings) if isinstance(current_settings, dict) else {}
    if normalized_profile is None:
        raise ValueError("未找到预警策略模板")

    next_settings.update(normalized_profile["settings"])
    return {
        "thresholds": dict(normalized_profile["thresholds"]),
        "volatility_config": dict(normalized_profile["volatility_config"]),
        "settings": next_settings,
    }


def _is_stored_profile_shape(profile):
    if not isinstance(profile, dict):
        return False
    profile_id = str(profile.get("id") or "").strip()
    name = str(profile.get("name") or "").strip()
    return (
        _valid_profile_id(profile_id)
        and bool(name)
        and isinstance(profile.get("thresholds"), dict)
        and isinstance(profile.get("volatility_config"), dict)
        and isinstance(profile.get("settings"), dict)
    )


def profile_matches_state(profile, thresholds, volatility_config, settings):
    threshold_defaults = _threshold_defaults_from_state(thresholds)
    normalized_profile = normalize_alert_profile(
        profile,
        threshold_defaults,
        volatility_config,
        settings,
    )
    if normalized_profile is None:
        return False

    if normalized_profile["thresholds"] != _normalize_threshold_values(
        thresholds,
        threshold_defaults,
        volatility_config,
    ):
        return False
    if normalized_profile["volatility_config"] != _current_volatility_config(
        thresholds,
        volatility_config,
    ):
        return False

    current_settings = settings if isinstance(settings, dict) else {}
    for key, value in normalized_profile["settings"].items():
        if current_settings.get(key) != value:
            return False
    return True


def alert_profiles_state(items, thresholds=None, volatility_config=None, settings=None):
    threshold_defaults = _threshold_defaults_from_state(thresholds)
    profiles = normalize_alert_profiles(
        items,
        threshold_defaults,
        volatility_config,
        settings,
    )
    state = {
        "items": profiles,
        "total": len(profiles),
        "limit": ALERT_PROFILE_LIMIT,
        "current_profile_id": "",
    }
    if thresholds is not None and settings is not None:
        for profile in profiles:
            if profile_matches_state(profile, thresholds, volatility_config, settings):
                state["current_profile_id"] = profile["id"]
                break
    return state


class AlertProfileStore:
    def __init__(
        self,
        json_path,
        threshold_defaults,
        current_volatility_config,
        current_settings,
        now_factory=None,
        id_factory=None,
    ):
        self.json_path = json_path
        self.threshold_defaults = threshold_defaults
        self.current_volatility_config = current_volatility_config
        self.current_settings = current_settings
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_alert_profile_id

    def normalize(self, items, existing_items=None):
        return normalize_alert_profiles(
            items,
            self.threshold_defaults,
            self.current_volatility_config,
            self.current_settings,
            existing_items=existing_items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
        )

    def load(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, items):
        existing = self.load()
        normalized = self.normalize(items, existing_items=existing)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        payload = wrap_item_payload(normalized)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized
