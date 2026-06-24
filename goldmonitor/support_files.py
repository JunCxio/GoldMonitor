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
