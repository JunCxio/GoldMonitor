import logging
import sqlite3
import threading
from datetime import datetime

from goldmonitor import notification_delivery as notification_delivery_core


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
        updated["notification_summary"] = notification_delivery_core.summarize_notifications(
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
    notifications = (
        entry.get("notifications")
        if isinstance(entry.get("notifications"), list)
        else []
    )
    if not any(
        item.get("status") == "pending"
        for item in notifications
        if isinstance(item, dict)
    ):
        return False
    alert_id = str(entry.get("id") or "").strip()
    if not alert_id:
        return False
    settings_snapshot = dict(get_settings())
    entry_snapshot = dict(entry)
    notification_snapshot = [
        dict(item) for item in notifications if isinstance(item, dict)
    ]
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
        entry["notifications"] = [
            notification_delivery_core.notification_status(
                "all",
                "通知",
                "muted",
                entry.get("notification_message", "仅记录提醒"),
            )
        ]
    else:
        entry["notifications"] = plan_notifications(entry, settings)
    entry["notification_summary"] = notification_delivery_core.summarize_notifications(
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
