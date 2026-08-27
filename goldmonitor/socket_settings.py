import logging
import threading

from flask import request
from flask_socketio import emit


def register_settings_handlers(
    socketio,
    *,
    public_settings_snapshot,
    start_onboarding,
    complete_onboarding,
    get_settings_snapshot,
    default_setting_keys,
    merge_settings_update,
    build_export_dir_check,
    apply_settings,
    send_test_email,
    send_test_webhook,
    build_daily_digest_snapshot,
    daily_digest_status_payload,
    run_daily_digest_once,
    notification_retry_status,
    run_notification_retry_once,
):
    @socketio.on("get_settings")
    def on_get_settings():
        emit("settings_updated", public_settings_snapshot())


    @socketio.on("start_onboarding")
    def on_start_onboarding():
        try:
            settings_state = start_onboarding()
            emit("onboarding_started", {"ok": True, "settings": settings_state})
        except OSError:
            emit("onboarding_error", {"message": "首次使用状态保存失败，请检查配置目录权限。"})


    @socketio.on("complete_onboarding")
    def on_complete_onboarding(data=None):
        try:
            result = complete_onboarding(data if isinstance(data, dict) else {})
        except OSError:
            emit("onboarding_error", {"message": "首次使用设置保存失败，请检查配置目录权限。"})
            return
        socketio.emit("settings_updated", result["settings"])
        emit("onboarding_completed", result)


    @socketio.on("update_settings")
    def on_update_settings(data):
        if not isinstance(data, dict):
            emit("settings_error", {"message": "设置格式无效"})
            return

        current = get_settings_snapshot()
        secret_clear_flags = {
            "smtp_password": "smtp_password_clear",
            "deepseek_api_key": "deepseek_api_key_clear",
            "openai_compatible_api_key": "openai_compatible_api_key_clear",
            "lan_dashboard_password": "lan_dashboard_password_clear",
        }
        current = merge_settings_update(
            current,
            data,
            allowed_keys=set(default_setting_keys),
            secret_clear_flags=secret_clear_flags,
        )
        if (
            data.get("lan_dashboard_password_clear")
            and not str(data.get("lan_dashboard_password") or "").strip()
        ):
            current["lan_dashboard_enabled"] = False
        if "export_dir" in data:
            export_dir_check = build_export_dir_check(current)
            if not export_dir_check.get("ok"):
                emit("settings_error", {
                    "message": export_dir_check.get("message") or "导出目录不可写，请检查目录权限。",
                    "export_dir_check": export_dir_check,
                })
                emit("settings_updated", public_settings_snapshot())
                return
        try:
            updated, startup_error = apply_settings(current)
        except (OSError, ValueError) as exc:
            emit("settings_error", {
                "message": str(exc) or "设置保存失败，请检查配置目录权限。"
            })
            emit("settings_updated", public_settings_snapshot())
            return
        if startup_error:
            emit("settings_error", {"message": "开机自启动设置失败，请检查系统权限。"})
        socketio.emit("settings_updated", public_settings_snapshot(updated))

    @socketio.on("test_email")
    def on_test_email():
        """发送测试邮件，验证 SMTP 配置是否正确"""
        settings = get_settings_snapshot()
        server = settings.get("smtp_server", "").strip()
        sender = settings.get("smtp_sender", "").strip()
        recipient = settings.get("smtp_recipient", "").strip()

        if not (server and sender and recipient):
            emit("test_email_result", {"ok": False, "message": "SMTP 配置不完整，请先填写服务器、发件邮箱和收件邮箱。"})
            return

        def _test():
            error = send_test_email(
                alert_type="warning",
                title="测试邮件 - 金价监控",
                message="这是一封测试邮件。\n\n如果您收到此邮件，说明 SMTP 配置正确，金价预警通知将正常工作。",
                timeout=10,
                blocking=True,
            )
            if error:
                socketio.emit("test_email_result", {"ok": False, "message": f"发送失败: {error}"})
            else:
                socketio.emit("test_email_result", {"ok": True, "message": "测试邮件发送成功！请检查收件箱（如未收到请查看垃圾邮件文件夹）。"})

        threading.Thread(target=_test, daemon=True).start()


    @socketio.on("get_notification_retry_status")
    def on_get_notification_retry_status():
        emit("notification_retry_status", notification_retry_status())


    @socketio.on("retry_failed_notifications")
    def on_retry_failed_notifications():
        sid = request.sid

        def _retry():
            try:
                result = run_notification_retry_once(manual=True)
            except Exception as exc:
                logging.exception("手动重试失败通知失败")
                result = {
                    "ok": False,
                    "status": "error",
                    "message": f"重试失败通知失败: {exc}",
                }
            socketio.emit(
                "notification_retry_status",
                notification_retry_status(),
                room=sid,
            )
            socketio.emit("notification_retry_result", result, room=sid)

        threading.Thread(target=_retry, daemon=True).start()

    @socketio.on("test_webhook")
    def on_test_webhook():
        """发送测试 Webhook，验证通知地址是否正确"""
        settings = get_settings_snapshot()
        if not settings.get("webhook_enabled", False):
            emit("test_webhook_result", {"ok": False, "message": "Webhook 通知未启用，请先打开开关。"})
            return
        if not settings.get("webhook_url", "").strip():
            emit("test_webhook_result", {"ok": False, "message": "Webhook 地址未配置，请先填写 HTTPS 地址。"})
            return

        def _test():
            error = send_test_webhook(
                alert_type="warning",
                title="测试 Webhook - 金价监控",
                message="这是一条测试 Webhook，用于验证金价预警通知配置。",
                timeout=8,
                blocking=True,
            )
            if error:
                socketio.emit("test_webhook_result", {"ok": False, "message": f"发送失败: {error}"})
            else:
                socketio.emit("test_webhook_result", {"ok": True, "message": "测试 Webhook 发送成功。"})

        threading.Thread(target=_test, daemon=True).start()


    @socketio.on("preview_daily_digest")
    def on_preview_daily_digest():
        try:
            digest = build_daily_digest_snapshot()
            emit("daily_digest_previewed", {"ok": True, **digest})
        except Exception as exc:
            logging.exception("生成每日摘要预览失败")
            emit("daily_digest_previewed", {
                "ok": False,
                "message": f"生成摘要预览失败: {exc}",
            })


    @socketio.on("get_daily_digest_status")
    def on_get_daily_digest_status():
        emit("daily_digest_status", daily_digest_status_payload())


    @socketio.on("test_daily_digest")
    def on_test_daily_digest():
        sid = request.sid

        def _test():
            try:
                result = run_daily_digest_once(
                    force=True,
                    manual=True,
                    blocking=True,
                )
            except Exception as exc:
                logging.exception("发送每日摘要测试失败")
                result = {
                    "ok": False,
                    "status": "error",
                    "message": f"发送摘要测试失败: {exc}",
                }
            socketio.emit("daily_digest_test_result", result, room=sid)
            socketio.emit("daily_digest_status", daily_digest_status_payload(), room=sid)

        threading.Thread(target=_test, daemon=True).start()
