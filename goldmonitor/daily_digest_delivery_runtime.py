import logging

from goldmonitor import daily_digest as daily_digest_core
from goldmonitor import notification_delivery as notification_delivery_core
from goldmonitor import scheduler as scheduler_core


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
        notifications.append(
            notification_delivery_core.deliver_notification(
                notification_delivery_core.notification_status(
                    "email",
                    "邮件",
                    "pending",
                    "等待发送",
                    attempts=0,
                    started_at="",
                    completed_at="",
                ),
                email_sender,
                (digest,),
                logger=logger,
            )
        )
    if "webhook" in channels:
        notifications.append(
            notification_delivery_core.deliver_notification(
                notification_delivery_core.notification_status(
                    "webhook",
                    "Webhook",
                    "pending",
                    "等待发送",
                    attempts=0,
                    started_at="",
                    completed_at="",
                ),
                webhook_sender,
                (digest,),
                logger=logger,
            )
        )
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
        notifications = (
            dispatch_daily_digest(
                digest,
                settings,
                email_sender=email_sender,
                webhook_sender=webhook_sender,
                logger=logger,
            )
            if channels
            else []
        )
        summary = notification_delivery_core.summarize_notifications(notifications)
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
