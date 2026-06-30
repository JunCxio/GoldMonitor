import json
import os
from datetime import datetime

from goldmonitor.data_contracts import item_payload_metadata


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


def build_config_backup(app_version, settings, thresholds, now_factory=None):
    now_factory = now_factory or datetime.now
    return {
        "app": "GoldMonitor",
        "version": app_version,
        "exported_at": now_factory().isoformat(timespec="seconds"),
        "settings": settings,
        "thresholds": thresholds,
    }


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


def build_config_import_preview(payload, settings_defaults, threshold_keys, secret_keys):
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "importable": False,
            "sections": [],
            "missing_sections": ["settings", "thresholds"],
            "ignored": {"settings": [], "thresholds": []},
            "secret_actions": {},
            "counts": {"settings": 0, "thresholds": 0},
            "message": "备份文件格式无效",
        }

    settings_payload = payload.get("settings")
    thresholds_payload = payload.get("thresholds")
    settings_keys, ignored_settings = _section_preview(settings_payload, settings_defaults)
    threshold_keys_found, ignored_thresholds = _section_preview(thresholds_payload, threshold_keys)

    sections = []
    missing_sections = []
    if isinstance(settings_payload, dict):
        sections.append("settings")
    else:
        missing_sections.append("settings")
    if isinstance(thresholds_payload, dict):
        sections.append("thresholds")
    else:
        missing_sections.append("thresholds")

    importable = bool(sections)
    message = "配置导入预检通过" if importable else "备份中没有可导入的配置"
    return {
        "ok": importable,
        "importable": importable,
        "sections": sections,
        "missing_sections": missing_sections,
        "ignored": {
            "settings": ignored_settings,
            "thresholds": ignored_thresholds,
        },
        "secret_actions": {
            key: _secret_action(settings_payload, key)
            for key in sorted(set(secret_keys or ()))
        },
        "counts": {
            "settings": len(settings_keys),
            "thresholds": len(threshold_keys_found),
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
