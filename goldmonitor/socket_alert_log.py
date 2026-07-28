from flask_socketio import emit


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
