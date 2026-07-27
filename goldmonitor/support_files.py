import json
import os
from datetime import datetime

from goldmonitor.data_contracts import item_payload_metadata


ALERT_PROFILE_IMPORT_LIMIT = 20
ALERT_RULE_IMPORT_LIMIT = 500
CONFIG_BACKUP_SCHEMA_VERSION = 1


class ConfigBackupFormatError(ValueError):
    def __init__(self, message, metadata):
        super().__init__(message)
        self.metadata = dict(metadata)


def read_log_tail(log_path, max_lines=120):
    if not os.path.exists(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return [line.rstrip("\n") for line in lines[-max_lines:]]
    except OSError:
        return []


def json_payload_metadata(path):
    if not os.path.exists(path):
        return {
            "exists": False,
            "schema_version": 0,
            "expected_schema_version": 1,
            "format": "missing",
            "needs_migration": False,
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            metadata = item_payload_metadata(json.load(f))
        metadata["exists"] = True
        return metadata
    except (OSError, json.JSONDecodeError):
        return {
            "exists": True,
            "schema_version": 0,
            "expected_schema_version": 1,
            "format": "invalid",
            "needs_migration": True,
        }


def build_config_backup(app_version, settings, thresholds, alert_profiles=None, now_factory=None, alert_rules=None):
    if callable(alert_profiles) and now_factory is None:
        now_factory = alert_profiles
        alert_profiles = None
    now_factory = now_factory or datetime.now
    return {
        "schema_version": CONFIG_BACKUP_SCHEMA_VERSION,
        "app": "GoldMonitor",
        "version": app_version,
        "exported_at": now_factory().isoformat(timespec="seconds"),
        "settings": settings,
        "thresholds": thresholds,
        "alert_profiles": list(alert_profiles or []),
        "alert_rules": list(alert_rules or []),
    }


def _config_backup_metadata(
    schema_version,
    format_name,
    needs_migration,
    source_app_version="",
):
    return {
        "schema_version": schema_version,
        "expected_schema_version": CONFIG_BACKUP_SCHEMA_VERSION,
        "format": format_name,
        "needs_migration": needs_migration,
        "source_app_version": source_app_version,
    }


def normalize_config_backup(payload):
    if not isinstance(payload, dict):
        metadata = _config_backup_metadata(0, "invalid", False)
        raise ConfigBackupFormatError("备份文件格式无效", metadata)

    source_app_version = str(payload.get("version") or "")
    if "schema_version" not in payload:
        normalized = dict(payload)
        normalized["schema_version"] = CONFIG_BACKUP_SCHEMA_VERSION
        return normalized, _config_backup_metadata(
            0,
            "legacy_dict",
            True,
            source_app_version,
        )

    raw_version = payload.get("schema_version")
    if isinstance(raw_version, bool) or not isinstance(raw_version, int) or raw_version <= 0:
        metadata = _config_backup_metadata(
            0,
            "invalid_version",
            False,
            source_app_version,
        )
        raise ConfigBackupFormatError("备份文件版本无效", metadata)
    if raw_version > CONFIG_BACKUP_SCHEMA_VERSION:
        metadata = _config_backup_metadata(
            raw_version,
            "unsupported_version",
            False,
            source_app_version,
        )
        raise ConfigBackupFormatError(
            f"备份文件版本 {raw_version} 高于当前支持版本 {CONFIG_BACKUP_SCHEMA_VERSION}",
            metadata,
        )

    return dict(payload), _config_backup_metadata(
        raw_version,
        "versioned_dict",
        False,
        source_app_version,
    )


def _section_preview(payload, allowed_keys):
    if not isinstance(payload, dict):
        return [], []
    allowed = set(allowed_keys or ())
    accepted = sorted(key for key in payload if key in allowed)
    ignored = sorted(key for key in payload if key not in allowed)
    return accepted, ignored


def _secret_action(settings_payload, key):
    if not isinstance(settings_payload, dict) or key not in settings_payload:
        return "preserve_existing"
    value = settings_payload.get(key)
    if value in (None, ""):
        return "clear"
    return "import"


def _alert_profiles_preview(payload):
    if not isinstance(payload, list):
        return 0, []
    valid_count = 0
    indexes_by_id = {}
    ignored = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict) or not str(item.get("name") or "").strip():
            ignored.append(str(index))
            continue
        profile_id = str(item.get("id") or "").strip()
        if profile_id.startswith("profile-") and len(profile_id) > len("profile-"):
            if profile_id in indexes_by_id:
                ignored.append(str(indexes_by_id[profile_id]))
                indexes_by_id[profile_id] = index
                continue
        if valid_count >= ALERT_PROFILE_IMPORT_LIMIT:
            ignored.append(str(index))
            continue
        if profile_id.startswith("profile-") and len(profile_id) > len("profile-"):
            indexes_by_id[profile_id] = index
        valid_count += 1
    return valid_count, sorted(set(ignored), key=int)


def _alert_rules_preview(payload):
    if not isinstance(payload, list):
        return 0, []
    valid_count = 0
    seen = set()
    ignored = []
    for index, item in enumerate(payload):
        rule_id = str(item.get("id") or "").strip() if isinstance(item, dict) else ""
        kind = str(item.get("kind") or "").strip() if isinstance(item, dict) else ""
        if not rule_id.startswith("rule-") or not kind:
            ignored.append(str(index))
            continue
        if rule_id in seen or valid_count >= ALERT_RULE_IMPORT_LIMIT:
            ignored.append(str(index))
            continue
        seen.add(rule_id)
        valid_count += 1
    return valid_count, ignored


def build_config_import_preview(payload, settings_defaults, threshold_keys, secret_keys):
    try:
        normalized_payload, metadata = normalize_config_backup(payload)
    except ConfigBackupFormatError as exc:
        return {
            **exc.metadata,
            "ok": False,
            "importable": False,
            "sections": [],
            "missing_sections": ["settings", "thresholds", "alert_profiles", "alert_rules"],
            "ignored": {"settings": [], "thresholds": [], "alert_profiles": [], "alert_rules": []},
            "secret_actions": {},
            "counts": {"settings": 0, "thresholds": 0, "alert_profiles": 0, "alert_rules": 0},
            "message": str(exc),
        }

    settings_payload = normalized_payload.get("settings")
    thresholds_payload = normalized_payload.get("thresholds")
    alert_profiles_payload = normalized_payload.get("alert_profiles")
    alert_rules_payload = normalized_payload.get("alert_rules")
    secret_key_set = set(secret_keys or ())
    accepted_setting_keys = set(settings_defaults or ())
    if metadata["schema_version"] > 0:
        accepted_setting_keys -= secret_key_set
    settings_keys, ignored_settings = _section_preview(settings_payload, accepted_setting_keys)
    threshold_keys_found, ignored_thresholds = _section_preview(thresholds_payload, threshold_keys)
    alert_profiles_count, ignored_alert_profiles = _alert_profiles_preview(alert_profiles_payload)
    alert_rules_count, ignored_alert_rules = _alert_rules_preview(alert_rules_payload)

    sections = []
    missing_sections = []
    if isinstance(settings_payload, dict):
        if settings_keys:
            sections.append("settings")
    else:
        missing_sections.append("settings")
    if isinstance(thresholds_payload, dict):
        if threshold_keys_found:
            sections.append("thresholds")
    else:
        missing_sections.append("thresholds")
    if isinstance(alert_profiles_payload, list):
        if alert_profiles_count:
            sections.append("alert_profiles")
    else:
        missing_sections.append("alert_profiles")
    if isinstance(alert_rules_payload, list):
        if alert_rules_count:
            sections.append("alert_rules")
    else:
        missing_sections.append("alert_rules")

    importable = bool(sections)
    message = "配置导入预检通过" if importable else "备份中没有可导入的配置"
    return {
        **metadata,
        "ok": importable,
        "importable": importable,
        "sections": sections,
        "missing_sections": missing_sections,
        "ignored": {
            "settings": ignored_settings,
            "thresholds": ignored_thresholds,
            "alert_profiles": ignored_alert_profiles,
            "alert_rules": ignored_alert_rules,
        },
        "secret_actions": {
            key: (
                _secret_action(settings_payload, key)
                if metadata["schema_version"] == 0
                else "preserve_existing"
            )
            for key in sorted(secret_key_set)
        },
        "counts": {
            "settings": len(settings_keys),
            "thresholds": len(threshold_keys_found),
            "alert_profiles": alert_profiles_count,
            "alert_rules": alert_rules_count,
        },
        "message": message,
    }


def save_export_file(export_dir, filename, content):
    os.makedirs(export_dir, exist_ok=True)
    safe_name = os.path.basename(filename)
    path = os.path.join(export_dir, safe_name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def build_open_folder_plan(path, os_name=None, sys_platform=None):
    os_name = os.name if os_name is None else os_name
    if os_name == "nt":
        return {"kind": "startfile", "path": path}
    if sys_platform == "darwin":
        return {"kind": "popen", "args": ["open", path], "kwargs": {"close_fds": True}}
    return {"kind": "popen", "args": ["xdg-open", path], "kwargs": {"close_fds": True}}
