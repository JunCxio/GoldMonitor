import json
import logging
import secrets
import sqlite3
import threading
import time

from flask import request
from flask_socketio import emit


def register_operations_handlers(
    socketio,
    *,
    get_source_health_state,
    public_settings_snapshot,
    update_market_source_preferences,
    reset_market_source_preferences,
    fetch_price_once,
    retry_market_source,
    now_factory,
    build_config_backup,
    save_export_file,
    build_export_error_payload,
    create_data_archive,
    data_archive_errors,
    diagnose_price_history_maintenance,
    preview_price_history_repair,
    execute_price_history_repair,
    preview_config_backup,
    restore_config_backup,
    reset_to_default_settings,
    build_diagnostics_report,
    build_diagnostics_clipboard_text,
    resolve_export_dir,
    open_exports_folder,
    build_open_exports_folder_error_payload,
    emit_alert,
    get_update_status,
    emit_update_status,
    current_version,
    record_update_status,
    download_update_installer,
    launch_update_installer,
    get_background_task_status,
    run_background_task_now,
    thread_factory=threading.Thread,
):
    price_history_repair_previews = {}
    price_history_repair_preview_lock = threading.Lock()

    def store_price_history_repair_preview(action, preview):
        now = time.monotonic()
        preview_token = secrets.token_urlsafe(18)
        with price_history_repair_preview_lock:
            stale_tokens = [
                token
                for token, item in price_history_repair_previews.items()
                if now - item["created_at"] > 300
            ]
            for token in stale_tokens:
                price_history_repair_previews.pop(token, None)
            price_history_repair_previews[preview_token] = {
                "sid": request.sid,
                "action": action,
                "effects": dict(preview.get("effects") or {}),
                "revision": str(preview.get("revision") or ""),
                "created_at": now,
            }
        return preview_token

    def consume_price_history_repair_preview(preview_token, action):
        with price_history_repair_preview_lock:
            item = price_history_repair_previews.pop(preview_token, None)
        if not item:
            return None
        if (
            item["sid"] != request.sid
            or item["action"] != action
            or time.monotonic() - item["created_at"] > 300
        ):
            return None
        return item

    def recheck_price_history_background_task():
        try:
            result = run_background_task_now("price_history_health")
            result = result if isinstance(result, dict) else {"ran": False}
        except Exception:
            logging.exception("历史数据修复完成后的后台复检失败")
            result = {
                "ran": False,
                "reason": "error",
                "message": "历史数据后台状态复检失败",
            }
        try:
            socketio.emit(
                "background_task_status",
                get_background_task_status(),
            )
        except Exception:
            logging.exception("广播历史数据后台复检状态失败")
        return result

    @socketio.on("get_background_task_status")
    def on_get_background_task_status():
        emit("background_task_status", get_background_task_status())


    @socketio.on("run_background_task")
    def on_run_background_task(data=None):
        task_name = (
            str(data.get("name") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        sid = request.sid
        emit("background_task_run_result", {
            "ok": None,
            "pending": True,
            "name": task_name,
            "message": "正在检查后台任务...",
        })

        def run_task():
            try:
                result = run_background_task_now(task_name)
                task = result.get("task") if isinstance(result, dict) else None
                task = task if isinstance(task, dict) else {}
                reason = (
                    str(result.get("reason") or "")
                    if isinstance(result, dict)
                    else ""
                )
                if reason == "running":
                    payload = {
                        "ok": False,
                        "name": task_name,
                        "reason": reason,
                        "task": task,
                        "message": "该任务正在运行，请稍后再试。",
                    }
                else:
                    payload = {
                        "ok": task.get("state") != "error",
                        "name": task_name,
                        "task": task,
                        "message": str(task.get("last_message") or "后台任务检查完成。"),
                    }
            except ValueError as exc:
                payload = {
                    "ok": False,
                    "name": task_name,
                    "message": f"{exc}。",
                }
            except Exception:
                logging.exception("立即检查后台任务失败: %s", task_name or "<empty>")
                payload = {
                    "ok": False,
                    "name": task_name,
                    "message": "后台任务检查失败，请稍后重试。",
                }
            socketio.emit("background_task_run_result", payload, room=sid)
            socketio.emit(
                "background_task_status",
                get_background_task_status(),
                room=sid,
            )

        thread_factory(target=run_task, daemon=True).start()


    @socketio.on("get_source_health")
    def on_get_source_health():
        emit("source_health_updated", get_source_health_state())


    @socketio.on("update_market_sources")
    def on_update_market_sources(data=None):
        try:
            preferences = update_market_source_preferences(data)
        except ValueError as exc:
            emit("market_sources_error", {"message": str(exc)})
            emit("source_health_updated", get_source_health_state())
            return
        except OSError:
            emit("market_sources_error", {"message": "数据源配置保存失败，请检查配置目录权限。"})
            emit("source_health_updated", get_source_health_state())
            return
        state = get_source_health_state()
        socketio.emit("settings_updated", public_settings_snapshot())
        socketio.emit("source_health_updated", state)
        emit("market_sources_updated", {
            "ok": True,
            "preferences": preferences,
            "message": "数据源配置已保存，将按新顺序刷新行情。",
        })
        thread_factory(target=fetch_price_once, daemon=True).start()


    @socketio.on("reset_market_sources")
    def on_reset_market_sources():
        try:
            preferences = reset_market_source_preferences()
        except OSError:
            emit("market_sources_error", {"message": "默认数据源配置恢复失败，请检查配置目录权限。"})
            return
        socketio.emit("settings_updated", public_settings_snapshot())
        socketio.emit("source_health_updated", get_source_health_state())
        emit("market_sources_updated", {
            "ok": True,
            "preferences": preferences,
            "message": "已恢复默认数据源顺序。",
        })
        thread_factory(target=fetch_price_once, daemon=True).start()


    @socketio.on("retry_market_source")
    def on_retry_market_source(data=None):
        source_key = str(data.get("key") or "").strip() if isinstance(data, dict) else ""
        if not source_key:
            emit("market_sources_error", {"message": "请选择需要探测的数据源。"})
            return

        emit("market_source_retry_result", {
            "ok": None,
            "pending": True,
            "key": source_key,
            "message": "正在探测数据源...",
        })

        def run_retry():
            try:
                result = retry_market_source(source_key)
            except ValueError as exc:
                result = {"ok": False, "key": source_key, "message": str(exc)}
            socketio.emit("market_source_retry_result", result)
            if isinstance(result.get("source_health"), dict):
                socketio.emit("source_health_updated", result["source_health"])

        thread_factory(target=run_retry, daemon=True).start()


    @socketio.on("export_config")
    def on_export_config():
        filename = f"GoldMonitor-config-{now_factory().strftime('%Y%m%d-%H%M%S')}.json"
        try:
            content = json.dumps(build_config_backup(), ensure_ascii=False, indent=2)
            saved_path = save_export_file(filename, content)
            emit("config_backup_ready", {
                "ok": True,
                "filename": filename,
                "content": content,
                "saved_path": saved_path,
            })
        except OSError:
            emit("config_backup_ready", build_export_error_payload("配置导出失败，请检查导出目录权限。"))


    @socketio.on("export_data_archive")
    def on_export_data_archive():
        try:
            emit("data_archive_exported", create_data_archive())
        except data_archive_errors as exc:
            logging.warning("完整数据归档失败: %s", exc)
            emit("data_archive_export_error", build_export_error_payload("完整数据归档失败，请检查导出目录和本地数据文件。"))


    @socketio.on("get_price_history_maintenance")
    def on_get_price_history_maintenance():
        try:
            emit(
                "price_history_maintenance_updated",
                diagnose_price_history_maintenance(),
            )
        except (OSError, sqlite3.Error):
            logging.exception("历史数据诊断失败")
            emit("price_history_maintenance_error", {
                "message": "历史数据诊断失败，请检查本地数据目录权限。",
            })


    @socketio.on("preview_price_history_repair")
    def on_preview_price_history_repair(data=None):
        action = data.get("action") if isinstance(data, dict) else ""
        try:
            preview = preview_price_history_repair(action)
            if preview.get("executable"):
                preview["preview_token"] = store_price_history_repair_preview(
                    action,
                    preview,
                )
            emit("price_history_repair_previewed", preview)
        except ValueError as exc:
            emit("price_history_maintenance_error", {"message": str(exc)})
        except (OSError, sqlite3.Error):
            logging.exception("历史数据修复预检失败")
            emit("price_history_maintenance_error", {
                "message": "历史数据修复预检失败，请稍后重试。",
            })


    @socketio.on("execute_price_history_repair")
    def on_execute_price_history_repair(data=None):
        action = data.get("action") if isinstance(data, dict) else ""
        confirmed = bool(data.get("confirmed")) if isinstance(data, dict) else False
        preview_token = (
            str(data.get("preview_token") or "").strip()
            if isinstance(data, dict)
            else ""
        )
        preview_record = (
            consume_price_history_repair_preview(preview_token, action)
            if confirmed and preview_token
            else None
        )
        if not preview_record:
            emit("price_history_maintenance_error", {
                "message": "修复预览已失效，请重新查看影响范围后确认。",
            })
            return
        try:
            result = execute_price_history_repair(
                action,
                preview_record["effects"],
                preview_record["revision"],
            )
        except ValueError as exc:
            emit("price_history_maintenance_error", {"message": str(exc)})
            return
        except (OSError, sqlite3.Error):
            logging.exception("历史数据修复失败")
            emit("price_history_maintenance_error", {
                "message": "历史数据修复失败，事务已回滚。",
            })
            return
        background_task_recheck = recheck_price_history_background_task()
        result["background_task_recheck"] = background_task_recheck
        if background_task_recheck.get("ran"):
            result["message"] = (
                str(result.get("message") or "历史数据修复完成。")
                + "后台历史数据状态已自动复检。"
            )
        emit("price_history_repair_completed", result)
        socketio.emit(
            "price_history_maintenance_updated",
            result.get("diagnosis") or diagnose_price_history_maintenance(),
        )


    @socketio.on("preview_import_config")
    def on_preview_import_config(data=None):
        try:
            payload = data.get("payload") if isinstance(data, dict) else data
            if isinstance(payload, str):
                payload = json.loads(payload)
            emit("config_import_previewed", preview_config_backup(payload))
        except json.JSONDecodeError as exc:
            emit("config_import_previewed", {
                "ok": False,
                "importable": False,
                "message": str(exc),
            })

    @socketio.on("import_config")
    def on_import_config(data=None):
        try:
            payload = data.get("payload") if isinstance(data, dict) else data
            if isinstance(payload, str):
                payload = json.loads(payload)
            result = restore_config_backup(payload)
            emit("config_import_result", {**result, "message": "配置导入完成。"})
            if "settings" in result.get("imported", []):
                socketio.emit("source_health_updated", get_source_health_state())
                thread_factory(target=fetch_price_once, daemon=True).start()
        except (ValueError, json.JSONDecodeError) as exc:
            emit("config_import_result", {"ok": False, "message": str(exc)})
        except OSError:
            emit("config_import_result", {"ok": False, "message": "配置导入失败，请检查配置目录权限。"})


    @socketio.on("reset_settings")
    def on_reset_settings():
        try:
            result = reset_to_default_settings()
            emit("settings_reset_result", {**result, "message": "已恢复默认设置。"})
            socketio.emit("source_health_updated", get_source_health_state())
            thread_factory(target=fetch_price_once, daemon=True).start()
        except OSError:
            emit("settings_reset_result", {"ok": False, "message": "恢复默认设置失败，请检查配置目录权限。"})


    @socketio.on("get_diagnostics")
    def on_get_diagnostics():
        filename = f"GoldMonitor-diagnostics-{now_factory().strftime('%Y%m%d-%H%M%S')}.json"
        try:
            content = build_diagnostics_report()
            saved_path = save_export_file(filename, content)
            emit("diagnostics_ready", {
                "ok": True,
                "filename": filename,
                "content": content,
                "saved_path": saved_path,
            })
        except OSError:
            emit("diagnostics_ready", build_export_error_payload("诊断报告导出失败，请检查导出目录权限。"))


    @socketio.on("copy_diagnostics")
    def on_copy_diagnostics():
        try:
            emit("diagnostics_copy_ready", {
                "ok": True,
                "content": build_diagnostics_clipboard_text(),
            })
        except Exception:
            logging.exception("failed to build diagnostics clipboard text")
            emit("diagnostics_copy_ready", {"ok": False, "message": "诊断摘要生成失败，请稍后重试。"})


    @socketio.on("open_exports_folder")
    def on_open_exports_folder():
        export_dir = resolve_export_dir()
        try:
            open_exports_folder()
            emit("exports_folder_opened", {"ok": True, "export_dir": export_dir, "message": f"已打开导出目录：{export_dir}"})
        except Exception as exc:
            emit("exports_folder_opened", build_open_exports_folder_error_payload(export_dir, exc))


    @socketio.on("test_alert")
    def on_test_alert(data=None):
        alert_type = "warning"
        if isinstance(data, dict) and data.get("type") in {"warning", "critical", "volatility"}:
            alert_type = data.get("type")
        now_str = now_factory().strftime("%H:%M:%S")
        entry = {
            "time": now_str,
            "type": alert_type,
            "mode": "rmb",
            "message": "这是一条手动测试提醒，用于验证弹窗、声音和邮件通知配置。",
            "force_notify": True,
        }
        emit_alert(entry, "金价监控测试提醒")
        emit("test_alert_result", {"ok": True, "message": "测试提醒已触发。"})


    @socketio.on("check_update")
    def on_check_update():
        try:
            emit_update_status(get_update_status())
        except ValueError as exc:
            emit_update_status({
                "state": "error",
                "current_version": current_version(),
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": str(exc),
            })
        except Exception:
            emit_update_status({
                "state": "error",
                "current_version": current_version(),
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": "检查更新失败，请确认网络连接后重试。",
            })


    @socketio.on("install_update")
    def on_install_update(data=None):
        try:
            status = get_update_status(expose_download=True)
            if status.get("state") != "available":
                emit_update_status(status)
                return
            update_info = {
                "version": status["latest_version"],
                "url": status["url"],
                "notes": status.get("notes", ""),
                "sha256": status["sha256"],
            }
            emit_update_status({
                "state": "downloading",
                "current_version": current_version(),
                "latest_version": update_info["version"],
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": "正在下载更新安装包...",
                "progress_percent": 0,
            })

            def emit_progress(received_bytes, total_bytes):
                percent = int(received_bytes / total_bytes * 100) if total_bytes else None
                status = record_update_status({
                    "state": "downloading",
                    "current_version": current_version(),
                    "latest_version": update_info["version"],
                    "checked_at": now_factory().isoformat(timespec="seconds"),
                    "message": "正在下载更新安装包...",
                    "downloaded_bytes": received_bytes,
                    "total_bytes": total_bytes,
                    "progress_percent": percent,
                })
                socketio.emit("update_status", status, room=request.sid)

            try:
                installer_path = download_update_installer(update_info, progress_callback=emit_progress)
            except TypeError:
                installer_path = download_update_installer(update_info)
            emit_update_status({
                "state": "installing",
                "current_version": current_version(),
                "latest_version": update_info["version"],
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": "安装包已下载，正在启动更新程序。",
                "progress_percent": 100,
            })
            launch_update_installer(installer_path)
            emit_update_status({
                "state": "installer_opened",
                "current_version": current_version(),
                "latest_version": update_info["version"],
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": "安装程序已打开，请按提示完成更新。安装过程中当前程序可能会被关闭。",
                "progress_percent": 100,
            })
        except ValueError as exc:
            emit_update_status({
                "state": "error",
                "current_version": current_version(),
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": str(exc),
            })
        except Exception:
            emit_update_status({
                "state": "error",
                "current_version": current_version(),
                "checked_at": now_factory().isoformat(timespec="seconds"),
                "message": "更新失败，请稍后重试或手动下载安装包。",
            })
