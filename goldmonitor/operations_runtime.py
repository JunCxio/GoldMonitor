import json
import os
import secrets
import sqlite3
import subprocess
import time
from contextlib import ExitStack
from datetime import datetime

from goldmonitor import data_archive as data_archive_core


def build_config_backup(
    *,
    app_version,
    settings,
    settings_defaults,
    secret_keys,
    thresholds,
    volatility_config,
    alert_profiles,
    alert_rules,
    builder,
    now_factory=datetime.now,
):
    restorable_settings = {
        key: settings.get(key, default_value)
        for key, default_value in settings_defaults.items()
        if key not in secret_keys
    }
    public_rules = [
        {key: value for key, value in rule.items() if key != "state"}
        for rule in alert_rules
    ]
    return builder(
        app_version,
        restorable_settings,
        {
            **{key: thresholds.get(key) for key in thresholds},
            "volatility_config": dict(volatility_config),
        },
        alert_profiles=alert_profiles,
        now_factory=now_factory,
        alert_rules=public_rules,
    )


def resolve_export_dir(settings, default_dir):
    raw_dir = settings.get("export_dir") if isinstance(settings, dict) else ""
    export_dir = str(raw_dir or "").strip()
    if not export_dir:
        return default_dir
    return os.path.abspath(os.path.expandvars(os.path.expanduser(export_dir)))


def probe_export_dir_writable(export_dir):
    os.makedirs(export_dir, exist_ok=True)
    probe_path = os.path.join(export_dir, ".goldmonitor-write-check")
    with open(probe_path, "w", encoding="utf-8") as file_handle:
        file_handle.write("ok")
    try:
        os.remove(probe_path)
    except OSError:
        pass


def build_export_dir_check(export_dir, *, actions, probe_writer=None):
    writer = probe_writer or probe_export_dir_writable
    try:
        writer(export_dir)
        return {
            "ok": True,
            "path": export_dir,
            "status": "writable",
            "message": f"导出目录可写：{export_dir}",
            "actions": [],
        }
    except OSError as exc:
        return {
            "ok": False,
            "path": export_dir,
            "status": "unwritable",
            "message": f"导出目录不可写：{export_dir}。请重新选择目录、使用默认目录，或检查权限后重试。",
            "error": str(exc),
            "actions": list(actions),
        }


def export_dir_dialog_initial_dir(export_dir, *, home_dir):
    if os.path.isdir(export_dir):
        return export_dir
    parent = os.path.dirname(export_dir)
    if parent and os.path.isdir(parent):
        return parent
    return home_dir


def normalize_export_dir_selection(selection):
    if not selection:
        return ""
    selected = selection[0] if isinstance(selection, (list, tuple)) else selection
    selected_dir = str(selected or "").strip()
    if not selected_dir:
        return ""
    return os.path.abspath(os.path.expandvars(os.path.expanduser(selected_dir)))


def build_export_dir_picker_payload(dialog, initial_dir):
    selected_dir = normalize_export_dir_selection(dialog(initial_dir))
    if not selected_dir:
        return {
            "ok": False,
            "cancelled": True,
            "message": "已取消选择导出目录。",
        }
    return {
        "ok": True,
        "path": selected_dir,
        "message": f"已选择导出目录：{selected_dir}",
    }


def export_failure_category(exc):
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, NotADirectoryError):
        return "invalid_path"
    if isinstance(exc, FileNotFoundError):
        return "path_missing"
    return "write_failed"


def export_failure_message(category, export_dir):
    if category == "permission_denied":
        return f"导出目录不可写：{export_dir}。请重新选择目录、使用默认目录，或检查权限后重试。"
    if category == "invalid_path":
        return f"导出路径不是有效目录：{export_dir}。请重新选择导出目录后重试。"
    if category == "path_missing":
        return f"导出目录不存在或无法创建：{export_dir}。请检查上级目录权限后重试。"
    return f"导出文件写入失败：{export_dir}。请检查目录权限、磁盘空间或文件占用后重试。"


def build_export_failure_status(filename, export_dir, exc, *, now_factory=datetime.now):
    category = export_failure_category(exc)
    return {
        "ok": False,
        "status": "failed",
        "filename": os.path.basename(str(filename or "")),
        "export_dir": export_dir,
        "category": category,
        "message": export_failure_message(category, export_dir),
        "error": str(exc),
        "exception": exc.__class__.__name__,
        "timestamp": now_factory().isoformat(timespec="seconds"),
    }


def build_export_status_snapshot(directory_status, last_export):
    return {
        "directory": directory_status,
        "last_export": last_export,
    }


def build_export_error_payload(default_message, last_export, directory_status):
    status = last_export if isinstance(last_export, dict) and last_export.get("ok") is False else {}
    return {
        "ok": False,
        "message": status.get("message") or default_message,
        "error_detail": status,
        "export_dir_check": directory_status,
    }


def build_open_exports_folder_error_payload(
    export_dir,
    exc,
    *,
    directory_status,
    now_factory=datetime.now,
):
    category = export_failure_category(exc)
    detail = {
        "ok": False,
        "status": "failed",
        "operation": "open_exports_folder",
        "export_dir": export_dir,
        "category": category,
        "message": f"无法打开导出目录：{export_dir}。请检查目录权限，或手动打开该路径。",
        "error": str(exc),
        "exception": exc.__class__.__name__,
        "timestamp": now_factory().isoformat(timespec="seconds"),
    }
    return {
        "ok": False,
        "message": detail["message"],
        "error_detail": detail,
        "export_dir_check": directory_status,
    }


def save_export_file(
    filename,
    content,
    *,
    export_dir,
    writer,
    set_status,
    now_factory=datetime.now,
):
    safe_name = os.path.basename(str(filename or ""))
    try:
        saved_path = writer(export_dir, filename, content)
    except OSError as exc:
        set_status(build_export_failure_status(
            safe_name,
            export_dir,
            exc,
            now_factory=now_factory,
        ))
        raise
    set_status({
        "ok": True,
        "status": "success",
        "filename": safe_name,
        "saved_path": saved_path,
        "export_dir": export_dir,
        "message": f"已导出：{saved_path}",
        "timestamp": now_factory().isoformat(timespec="seconds"),
    })
    return saved_path


def data_archive_filename(now):
    return f"GoldMonitor-full-backup-{now.strftime('%Y%m%d-%H%M%S')}.zip"


def create_data_archive(
    *,
    now,
    export_dir,
    settings,
    archive_lock,
    state_locks=(),
    manager,
    set_status,
    directory_status,
):
    filename = data_archive_filename(now)
    destination_path = os.path.join(export_dir, filename)
    settings_content = json.dumps(
        settings,
        ensure_ascii=False,
        indent=2,
    ).encode("utf-8")
    try:
        with archive_lock, ExitStack() as stack:
            for state_lock in state_locks or ():
                stack.enter_context(state_lock)
            result = manager.create(
                destination_path,
                content_overrides={"settings": settings_content},
            )
    except (OSError, sqlite3.Error, data_archive_core.DataArchiveError) as exc:
        set_status(build_export_failure_status(
            filename,
            export_dir,
            exc,
            now_factory=lambda: now,
        ))
        raise
    set_status({
        "ok": True,
        "status": "success",
        "filename": filename,
        "saved_path": result["path"],
        "export_dir": export_dir,
        "message": f"完整数据归档已保存：{result['path']}",
        "timestamp": now.isoformat(timespec="seconds"),
    })
    return {
        "ok": True,
        "saved_path": result["path"],
        "filename": result["filename"],
        "files": result["files"],
        "bytes": result["bytes"],
        "contains_sensitive_data": result["contains_sensitive_data"],
        "message": f"已归档 {result['files']} 项本地数据",
        "export_dir_check": directory_status,
    }


def cleanup_uploads(uploads, lock, ttl_seconds, *, now_monotonic=None, remove=os.remove):
    current = time.monotonic() if now_monotonic is None else float(now_monotonic)
    expired_paths = []
    with lock:
        for token, item in list(uploads.items()):
            if current - float(item.get("created_at") or 0) <= ttl_seconds:
                continue
            expired_paths.append(str(item.get("path") or ""))
            uploads.pop(token, None)
    for path in expired_paths:
        try:
            remove(path)
        except FileNotFoundError:
            pass


def store_upload(
    uploads,
    lock,
    path,
    preview,
    *,
    cleanup,
    token_factory=lambda: secrets.token_urlsafe(24),
    monotonic_factory=time.monotonic,
):
    cleanup()
    token = token_factory()
    with lock:
        uploads[token] = {
            "path": path,
            "preview": dict(preview),
            "created_at": monotonic_factory(),
        }
    return token


def consume_upload(uploads, lock, token, *, cleanup):
    cleanup()
    with lock:
        return uploads.pop(str(token or ""), None)


def open_exports_folder(
    export_dir,
    *,
    build_plan,
    os_name,
    sys_platform,
    startfile=None,
    popen=subprocess.Popen,
):
    os.makedirs(export_dir, exist_ok=True)
    plan = build_plan(export_dir, os_name=os_name, sys_platform=sys_platform)
    if plan["kind"] == "startfile":
        if startfile is None:
            raise OSError("系统不支持 startfile")
        startfile(plan["path"])
        return
    popen(plan["args"], **plan["kwargs"])
