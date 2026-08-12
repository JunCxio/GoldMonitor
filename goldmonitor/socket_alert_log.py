from flask_socketio import emit


ALERT_LOG_BATCH_LIMIT = 50


def _batch_alert_ids(data):
    if not isinstance(data, dict) or not isinstance(data.get("ids"), list):
        return []
    result = []
    seen = set()
    for value in data["ids"]:
        alert_id = str(value or "").strip()
        if not alert_id or alert_id in seen:
            continue
        seen.add(alert_id)
        result.append(alert_id)
        if len(result) >= ALERT_LOG_BATCH_LIMIT:
            break
    return result


def _batch_result(alert_ids, operation, failure_message):
    entries = []
    failures = []
    for alert_id in alert_ids:
        ok, entry = operation(alert_id)
        if ok and entry:
            entries.append(entry)
        else:
            failures.append({"id": alert_id, "message": failure_message})
    return {
        "ok": bool(entries) and not failures,
        "partial": bool(entries) and bool(failures),
        "requested_count": len(alert_ids),
        "success_count": len(entries),
        "failure_count": len(failures),
        "entries": entries,
        "failures": failures,
    }


def register_alert_log_handlers(
    socketio,
    *,
    now_factory,
    build_alert_log_csv,
    save_export_file,
    build_export_error_payload,
    clear_alert_log_archive,
    clear_alert_log_memory,
    update_alert_log_status,
    update_alert_log_handling,
    resend_alert_notification,
    start_alert_notification_delivery,
    alert_resend_title,
):
    @socketio.on("export_alert_log")
    def on_export_alert_log():
        filename = f"GoldMonitor-alert-log-{now_factory().strftime('%Y%m%d-%H%M%S')}.csv"
        try:
            content, count = build_alert_log_csv()
            saved_path = save_export_file(filename, content)
            emit("alert_log_exported", {
                "ok": True,
                "filename": filename,
                "saved_path": saved_path,
                "count": count,
            })
        except OSError as exc:
            emit("alert_log_export_error", build_export_error_payload(f"告警记录导出失败: {exc}"))


    @socketio.on("clear_alert_log")
    def on_clear_alert_log():
        ok = clear_alert_log_archive()
        if ok:
            clear_alert_log_memory()
        socketio.emit("alert_log_cleared", {"ok": ok})


    @socketio.on("update_alert_log_status")
    def on_update_alert_log_status(data=None):
        if not isinstance(data, dict):
            emit("alert_log_status_error", {"message": "告警记录状态参数无效"})
            return
        ok, entry = update_alert_log_status(
            data.get("id"),
            read=data.get("read") if "read" in data else None,
            acknowledged=data.get("acknowledged") if "acknowledged" in data else None,
        )
        if not ok:
            emit("alert_log_status_error", {"message": "未找到对应告警记录"})
            return
        socketio.emit("alert_log_status_updated", {"ok": True, "entry": entry})


    @socketio.on("update_alert_log_handling")
    def on_update_alert_log_handling(data=None):
        if not isinstance(data, dict):
            emit("alert_log_handling_error", {"message": "告警处理参数无效"})
            return
        ok, entry = update_alert_log_handling(
            data.get("id"),
            handled=data.get("handled") if "handled" in data else None,
            note=data.get("note") if "note" in data else None,
        )
        if not ok:
            emit("alert_log_handling_error", {"message": "未找到对应告警记录"})
            return
        socketio.emit("alert_log_handling_updated", {"ok": True, "entry": entry})


    @socketio.on("batch_update_alert_log_handling")
    def on_batch_update_alert_log_handling(data=None):
        alert_ids = _batch_alert_ids(data)
        if not alert_ids:
            emit("alert_log_handling_batch_error", {"message": "请选择需要处理的警报"})
            return
        result = _batch_result(
            alert_ids,
            lambda alert_id: update_alert_log_handling(
                alert_id,
                handled=True,
                note="",
            ),
            "未找到对应警报记录",
        )
        socketio.emit("alert_log_handling_batch_updated", result)


    @socketio.on("resend_alert_notification")
    def on_resend_alert_notification(data=None):
        if not isinstance(data, dict):
            emit("alert_notification_resend_error", {"message": "告警通知重发参数无效"})
            return
        ok, entry = resend_alert_notification(data.get("id"), start_delivery=False)
        if not ok:
            emit("alert_notification_resend_error", {"message": "未找到对应告警记录"})
            return
        socketio.emit("alert_notification_resent", {"ok": True, "entry": entry})
        start_alert_notification_delivery(entry, alert_resend_title(entry))


    @socketio.on("batch_resend_alert_notifications")
    def on_batch_resend_alert_notifications(data=None):
        alert_ids = _batch_alert_ids(data)
        if not alert_ids:
            emit("alert_notification_batch_resend_error", {"message": "请选择需要重发通知的警报"})
            return
        result = _batch_result(
            alert_ids,
            lambda alert_id: resend_alert_notification(
                alert_id,
                start_delivery=False,
            ),
            "未找到对应警报记录",
        )
        socketio.emit("alert_notification_batch_resent", result)
        for entry in result["entries"]:
            start_alert_notification_delivery(entry, alert_resend_title(entry))
