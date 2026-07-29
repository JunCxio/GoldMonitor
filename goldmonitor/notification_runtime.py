import logging
import os
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime

from goldmonitor import daily_digest as daily_digest_core
from goldmonitor import notifications as notifications_core
from goldmonitor import scheduler as scheduler_core


def send_desktop_notification(
    title,
    body,
    *,
    sys_platform,
    base_dir,
    app_id,
    applescript_string,
    run_applescript,
    path_exists=os.path.exists,
    notify_loader=None,
):
    if sys_platform == "darwin":
        script = (
            "display notification "
            + applescript_string(body)
            + " with title "
            + applescript_string(title)
        )
        run_applescript(script, wait=False)
        return
    try:
        if notify_loader is None:
            from win11toast import notify
        else:
            notify = notify_loader()
        icon = os.path.join(base_dir, "static", "icon.ico")
        if not path_exists(icon):
            icon = os.path.join(base_dir, "static", "icon-64.png")
        notify(title, body, app_id=app_id, icon=icon)
    except Exception:
        pass


def show_alert_dialog(
    title,
    message,
    *,
    enabled,
    active_lock,
    get_active,
    set_active,
    sys_platform,
    os_name,
    applescript_string,
    run_applescript,
    thread_factory=threading.Thread,
    logger=logging,
):
    if not enabled:
        return False
    with active_lock:
        if get_active():
            logger.info("告警弹窗已存在，跳过新的系统消息框。")
            return False
        set_active(True)

    def show():
        try:
            if sys_platform == "darwin":
                script = (
                    "display alert "
                    + applescript_string(title)
                    + " message "
                    + applescript_string(message)
                    + ' as warning buttons {"知道了"} default button "知道了"'
                )
                run_applescript(script, wait=True, timeout=3600)
            elif os_name == "nt":
                import ctypes
                flags = 0x00000000 | 0x00000030 | 0x00040000 | 0x00010000
                ctypes.windll.user32.MessageBoxW(None, message, title, flags)
        except Exception:
            pass
        finally:
            with active_lock:
                set_active(False)

    thread_factory(target=show, daemon=True).start()
    return True


def play_system_alert_sound(
    level,
    *,
    enabled,
    sys_platform,
    path_exists=os.path.exists,
    popen=subprocess.Popen,
    run_applescript=None,
    winsound_loader=None,
):
    if not enabled:
        return False
    if sys_platform == "darwin":
        try:
            sound = "Basso" if level == "critical" else "Glass"
            path = f"/System/Library/Sounds/{sound}.aiff"
            if path_exists(path):
                popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
            elif run_applescript:
                run_applescript("beep", wait=False)
        except Exception:
            pass
        return True
    try:
        if winsound_loader is None:
            import winsound
        else:
            winsound = winsound_loader()
        sound = "SystemHand" if level == "critical" else "SystemExclamation"
        winsound.PlaySound(sound, winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        pass
    return True


def send_email_alert(
    alert_type,
    title,
    message,
    *,
    get_settings,
    build_values,
    smtp_module,
    default_subject_template,
    default_body_template,
    timeout=10,
    blocking=False,
    thread_factory=threading.Thread,
    logger=logging,
):
    return notifications_core.send_email_notification(
        get_settings(),
        alert_type,
        title,
        message,
        build_values(alert_type, title, message),
        smtp_module=smtp_module,
        default_subject_template=default_subject_template,
        default_body_template=default_body_template,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def send_webhook_alert(
    alert_type,
    title,
    message,
    *,
    get_settings,
    build_values,
    post,
    require_https_url,
    app_name,
    app_version,
    user_agent,
    proxies,
    timeout=8,
    blocking=False,
    thread_factory=threading.Thread,
    logger=logging,
):
    return notifications_core.send_webhook_notification(
        get_settings(),
        alert_type,
        title,
        message,
        build_values(alert_type, title, message),
        post=post,
        require_https_url=require_https_url,
        app_name=app_name,
        app_version=app_version,
        user_agent=user_agent,
        proxies=proxies,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def send_daily_digest_email(
    digest,
    *,
    get_settings,
    smtp_module,
    timeout=10,
    blocking=False,
    thread_factory=threading.Thread,
    logger=logging,
):
    return notifications_core.send_email_message(
        get_settings(),
        digest.get("subject", "GoldMonitor 每日摘要"),
        digest.get("message", ""),
        smtp_module=smtp_module,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def send_daily_digest_webhook(
    digest,
    *,
    get_settings,
    post,
    require_https_url,
    user_agent,
    proxies,
    timeout=8,
    blocking=False,
    thread_factory=threading.Thread,
    logger=logging,
):
    payload = digest.get("payload") if isinstance(digest.get("payload"), dict) else {}
    return notifications_core.send_webhook_payload(
        get_settings(),
        payload,
        post=post,
        require_https_url=require_https_url,
        user_agent=user_agent,
        proxies=proxies,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def persist_alert_notification_update(
    alert_id,
    notifications,
    *,
    update_entry,
    emit,
):
    def updater(entry):
        updated = dict(entry)
        updated["notifications"] = [dict(item) for item in notifications]
        updated["notification_summary"] = notifications_core.summarize_notifications(
            updated["notifications"]
        )
        return updated

    ok, updated = update_entry(alert_id, updater)
    if ok and updated:
        emit("alert_log_status_updated", {"ok": True, "entry": updated})
    return ok, updated


def start_alert_notification_delivery(
    entry,
    title,
    *,
    get_settings,
    deliver,
    thread_factory=threading.Thread,
):
    notifications = entry.get("notifications") if isinstance(entry.get("notifications"), list) else []
    if not any(item.get("status") == "pending" for item in notifications if isinstance(item, dict)):
        return False
    alert_id = str(entry.get("id") or "").strip()
    if not alert_id:
        return False
    settings_snapshot = dict(get_settings())
    entry_snapshot = dict(entry)
    notification_snapshot = [dict(item) for item in notifications if isinstance(item, dict)]
    thread_factory(
        target=lambda: deliver(
            alert_id,
            entry_snapshot,
            title,
            settings_snapshot,
            notification_snapshot,
        ),
        daemon=True,
    ).start()
    return True


def selected_daily_digest_channels(settings):
    channels = []
    if settings.get("daily_digest_email_enabled", True):
        channels.append("email")
    if settings.get("daily_digest_webhook_enabled", False):
        channels.append("webhook")
    return channels


def build_daily_digest_snapshot(
    *,
    now,
    build_timeline,
    build_portfolio,
    get_source_health,
    timeline_max_limit,
    timeline_types,
):
    timeline_state = build_timeline(
        minutes=1440,
        limit=timeline_max_limit,
        types=timeline_types,
    )
    source_health_state = get_source_health()
    market_quality = (
        source_health_state.get("quality")
        if isinstance(source_health_state.get("quality"), dict)
        else {}
    )
    return daily_digest_core.build_daily_digest(
        timeline_state,
        portfolio_state=build_portfolio(),
        market_quality=market_quality,
        now=now,
    )


def daily_digest_status_payload(
    *,
    now,
    settings,
    state,
):
    decision = scheduler_core.daily_task_due(
        settings.get("daily_digest_time", "20:00"),
        state.get("last_completed_at", ""),
        now=now,
    )
    return {
        "enabled": bool(settings.get("daily_digest_enabled")),
        "time": settings.get("daily_digest_time", "20:00"),
        "channels": selected_daily_digest_channels(settings),
        "state": state,
        "schedule": decision,
    }


def dispatch_daily_digest(
    digest,
    settings,
    *,
    email_sender,
    webhook_sender,
    logger=logging,
):
    notifications = []
    channels = selected_daily_digest_channels(settings)
    if "email" in channels:
        notifications.append(notifications_core.deliver_notification(
            notifications_core.notification_status(
                "email", "邮件", "pending", "等待发送",
                attempts=0, started_at="", completed_at="",
            ),
            email_sender,
            (digest,),
            logger=logger,
        ))
    if "webhook" in channels:
        notifications.append(notifications_core.deliver_notification(
            notifications_core.notification_status(
                "webhook", "Webhook", "pending", "等待发送",
                attempts=0, started_at="", completed_at="",
            ),
            webhook_sender,
            (digest,),
            logger=logger,
        ))
    return notifications


def run_daily_digest_once(
    *,
    now,
    force,
    manual,
    settings,
    lock,
    state_store,
    build_digest,
    email_sender,
    webhook_sender,
    emit_status,
    status_payload,
    logger=logging,
):
    with lock:
        state = state_store.load()
        if not force:
            if not settings.get("daily_digest_enabled", False):
                return {
                    "ok": False,
                    "status": "disabled",
                    "reason": "disabled",
                    "message": "每日摘要未启用",
                    "state": state,
                }
            decision = scheduler_core.daily_task_due(
                settings.get("daily_digest_time", "20:00"),
                state.get("last_completed_at", ""),
                now=now,
            )
            if not decision.get("due"):
                return {
                    "ok": False,
                    "status": "not_due",
                    "reason": decision.get("reason", "not_due"),
                    "message": "当前无需发送每日摘要",
                    "schedule": decision,
                    "state": state,
                }

        digest = build_digest(now)
        channels = selected_daily_digest_channels(settings)
        notifications = dispatch_daily_digest(
            digest,
            settings,
            email_sender=email_sender,
            webhook_sender=webhook_sender,
            logger=logger,
        ) if channels else []
        summary = notifications_core.summarize_notifications(notifications)
        sent = summary.get("sent", 0) > 0
        if not channels:
            summary = {
                **summary,
                "status": "skipped",
                "label": "未选择渠道",
                "message": "请至少选择一个每日摘要通知渠道",
            }
        state = state_store.record_result(
            status=summary.get("status", "none"),
            message=summary.get("message", ""),
            channels=channels,
            sent=sent,
            manual=manual,
        )
        result = {
            "ok": sent,
            "status": summary.get("status", "none"),
            "message": summary.get("message", ""),
            "notifications": notifications,
            "state": state,
            "digest": digest,
        }
    if not manual:
        emit_status("daily_digest_status", status_payload(now))
    return result


def emit_alert(
    entry,
    title,
    *,
    settings,
    market_lock,
    market_price,
    generate_id,
    evaluate_delivery,
    plan_notifications,
    select_news,
    alert_log,
    alert_log_limit,
    save_entry,
    emit,
    start_delivery,
    build_history_state,
    local_delivery_enabled,
    send_desktop_notification,
    play_system_alert_sound,
    show_alert_dialog,
    now_factory=datetime.now,
    logger=logging,
):
    entry["title"] = str(title or "")
    if entry.get("trigger_price") in (None, ""):
        with market_lock:
            entry["trigger_price"] = market_price(entry.get("mode"))
    entry["id"] = str(entry.get("id") or generate_id())
    entry["timestamp"] = str(
        entry.get("timestamp") or now_factory().isoformat(timespec="seconds")
    )
    delivery = evaluate_delivery(entry, settings)
    if not delivery.get("deliver"):
        reason = delivery.get("reason", "")
        entry["notification_muted"] = True
        entry["notification_reason"] = reason
        messages = {
            "quiet_time": "当前处于静默时段，仅记录提醒。",
            "cooldown": "提醒冷却中，仅记录本次触发。",
            "no_channels": "该规则未选择通知渠道，仅记录本次触发。",
        }
        if reason in messages:
            entry["notification_message"] = messages[reason]
        entry["notifications"] = [notifications_core.notification_status(
            "all",
            "通知",
            "muted",
            entry.get("notification_message", "仅记录提醒"),
        )]
    else:
        entry["notifications"] = plan_notifications(entry, settings)
    entry["notification_summary"] = notifications_core.summarize_notifications(
        entry.get("notifications")
    )
    entry["related_news"] = select_news(title)
    alert_log.append(entry)
    while len(alert_log) > alert_log_limit:
        alert_log.pop(0)
    try:
        save_entry(entry)
    except (OSError, sqlite3.Error) as exc:
        logger.warning("告警记录保存失败: %s", exc)
    emit("alert", entry)
    if delivery.get("deliver"):
        start_delivery(entry, title, settings=settings)
    history_state = build_history_state(limit=240)
    history_state["scope"] = "live"
    emit("price_history_updated", history_state)
    if delivery.get("deliver") and local_delivery_enabled(entry):
        send_desktop_notification(title, entry["message"])
        play_system_alert_sound(entry.get("type", "warning"))
        show_alert_dialog(title, f"{entry['message']}\n\n时间: {entry['time']}")


def resend_alert_notification(
    alert_id,
    *,
    settings,
    blocking,
    start_delivery,
    update_entry,
    plan_notifications,
    summarize_notifications,
    deliver_notifications,
    persist_update,
    start_notification_delivery,
    title_builder,
    now_factory=datetime.now,
):
    def updater(entry):
        updated = dict(entry)
        updated["notifications"] = plan_notifications(updated, settings)
        updated["notification_summary"] = summarize_notifications(
            updated.get("notifications")
        )
        updated["notification_muted"] = False
        updated["notification_reason"] = ""
        updated["notification_message"] = ""
        updated["last_notification_resend_at"] = now_factory().isoformat(
            timespec="seconds"
        )
        return updated

    ok, updated = update_entry(alert_id, updater)
    if not (ok and updated and start_delivery):
        return ok, updated
    title = title_builder(updated)
    if blocking:
        notifications = deliver_notifications(
            updated["id"],
            updated,
            title,
            settings,
            updated.get("notifications", []),
        )
        return persist_update(updated["id"], notifications)
    start_notification_delivery(updated, title, settings=settings)
    return ok, updated
