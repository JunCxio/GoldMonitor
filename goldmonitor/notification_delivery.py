import inspect
import logging
import time
from datetime import datetime

from goldmonitor.notification_policy import ALERT_CHANNEL_KEYS


def notification_status(channel, label, status, message, **details):
    item = {
        "channel": channel,
        "label": label,
        "status": status,
        "message": message,
    }
    item.update(details)
    return item


def _notification_timestamp(now_factory=None):
    now = now_factory() if callable(now_factory) else datetime.now()
    return now.isoformat(timespec="seconds")


def _sender_accepts_blocking(sender):
    try:
        parameters = inspect.signature(sender).parameters.values()
    except (TypeError, ValueError):
        return True
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        or parameter.name == "blocking"
        for parameter in parameters
    )


def _invoke_blocking_sender(sender, args):
    if _sender_accepts_blocking(sender):
        return sender(*args, blocking=True)
    return sender(*args)


def _delivery_error_retryable(error):
    text = str(error or "")
    non_retryable_fragments = (
        "配置不完整",
        "未配置",
        "未启用",
        "格式无效",
        "必须使用 HTTPS",
        "构建邮件失败",
    )
    return not any(fragment in text for fragment in non_retryable_fragments)


def deliver_notification(
    notification,
    sender,
    sender_args,
    max_attempts=3,
    retry_wait=None,
    now_factory=None,
    logger=None,
):
    logger = logger or logging.getLogger(__name__)
    item = dict(notification or {})
    item["status"] = "pending"
    item["message"] = "正在发送"
    item["attempts"] = 0
    item["started_at"] = _notification_timestamp(now_factory)
    item["completed_at"] = ""
    attempts_limit = max(1, int(max_attempts or 1))
    wait = retry_wait or (lambda attempt: time.sleep(min(max(1, attempt), 2)))
    error = ""

    for attempt in range(1, attempts_limit + 1):
        item["attempts"] = attempt
        try:
            error = str(
                _invoke_blocking_sender(sender, tuple(sender_args or ())) or ""
            )
        except Exception as exc:
            error = str(exc) or type(exc).__name__
        if not error:
            item["status"] = "sent"
            item["message"] = "发送成功"
            break
        if attempt >= attempts_limit or not _delivery_error_retryable(error):
            item["status"] = "failed"
            item["message"] = error
            logger.warning(
                "%s通知发送失败（尝试 %s 次）",
                item.get("label") or item.get("channel") or "",
                attempt,
            )
            break
        wait(attempt)

    item["completed_at"] = _notification_timestamp(now_factory)
    return item


def plan_alert_notifications(entry, settings):
    settings = settings or {}
    alert_type = entry.get("type", "warning")
    notifications = []
    delivery_channels = entry.get("delivery_channels")
    explicit_channels = (
        set(delivery_channels) if isinstance(delivery_channels, list) else None
    )

    email_key = ALERT_CHANNEL_KEYS["email"].get(
        alert_type,
        "email_warning_enabled",
    )
    if explicit_channels is not None and "email" not in explicit_channels:
        notifications.append(
            notification_status("email", "邮件", "disabled", "规则未选择")
        )
    elif settings.get(email_key, True):
        notifications.append(
            notification_status(
                "email",
                "邮件",
                "pending",
                "等待发送",
                attempts=0,
                started_at="",
                completed_at="",
            )
        )
    else:
        notifications.append(
            notification_status("email", "邮件", "disabled", "未启用")
        )

    webhook_key = ALERT_CHANNEL_KEYS["webhook"].get(
        alert_type,
        "webhook_warning_enabled",
    )
    if explicit_channels is not None and "webhook" not in explicit_channels:
        notifications.append(
            notification_status(
                "webhook",
                "Webhook",
                "disabled",
                "规则未选择",
            )
        )
    elif settings.get("webhook_enabled", False) and settings.get(
        webhook_key,
        True,
    ):
        notifications.append(
            notification_status(
                "webhook",
                "Webhook",
                "pending",
                "等待发送",
                attempts=0,
                started_at="",
                completed_at="",
            )
        )
    else:
        notifications.append(
            notification_status("webhook", "Webhook", "disabled", "未启用")
        )
    return notifications


def alert_local_delivery_enabled(entry):
    delivery_channels = (
        entry.get("delivery_channels") if isinstance(entry, dict) else None
    )
    return not isinstance(delivery_channels, list) or "local" in delivery_channels


def deliver_alert_notifications(
    entry,
    title,
    settings,
    email_sender,
    webhook_sender,
    notifications=None,
    on_update=None,
    max_attempts=3,
    retry_wait=None,
    now_factory=None,
    logger=None,
):
    logger = logger or logging.getLogger(__name__)
    alert_type = entry.get("type", "warning")
    message = entry.get("message", "")
    items = [
        dict(item)
        for item in (
            notifications or plan_alert_notifications(entry, settings)
        )
    ]
    senders = {
        "email": email_sender,
        "webhook": webhook_sender,
    }
    sender_args = (alert_type, title, message)

    for index, item in enumerate(items):
        if item.get("status") != "pending":
            continue
        sender = senders.get(item.get("channel"))
        if not callable(sender):
            items[index] = notification_status(
                item.get("channel", ""),
                item.get("label", "通知"),
                "failed",
                "通知发送器不可用",
                attempts=0,
                started_at=_notification_timestamp(now_factory),
                completed_at=_notification_timestamp(now_factory),
            )
        else:
            items[index] = deliver_notification(
                item,
                sender,
                sender_args,
                max_attempts=max_attempts,
                retry_wait=retry_wait,
                now_factory=now_factory,
                logger=logger,
            )
        if callable(on_update):
            try:
                on_update([dict(value) for value in items], dict(items[index]))
            except Exception:
                logger.exception("更新通知投递状态失败")
    return items


def summarize_notifications(notifications):
    items = [
        dict(item)
        for item in list(notifications or [])
        if isinstance(item, dict)
    ]
    counts = {
        "pending": sum(1 for item in items if item.get("status") == "pending"),
        "sent": sum(1 for item in items if item.get("status") == "sent"),
        "failed": sum(1 for item in items if item.get("status") == "failed"),
        "queued": sum(1 for item in items if item.get("status") == "queued"),
        "skipped": sum(1 for item in items if item.get("status") == "skipped"),
        "disabled": sum(
            1 for item in items if item.get("status") == "disabled"
        ),
        "muted": sum(1 for item in items if item.get("status") == "muted"),
    }
    message = next(
        (
            str(item.get("message") or "")
            for item in items
            if item.get("status") in {"muted", "failed", "skipped"}
            and item.get("message")
        ),
        "",
    )
    total = len(items)
    if counts["muted"]:
        status, label = "muted", "已静默"
    elif counts["pending"]:
        status, label = "pending", "投递中"
    elif (counts["failed"] or counts["skipped"]) and (
        counts["sent"] or counts["queued"]
    ):
        status, label = "partial", "部分送达"
    elif counts["failed"]:
        status, label = "failed", "发送失败"
    elif counts["skipped"] and counts["queued"]:
        status, label = "partial", "部分提交"
    elif counts["skipped"]:
        status, label = "skipped", "提交失败"
    elif counts["sent"]:
        status, label = "sent", "已送达"
    elif counts["queued"]:
        status, label = "queued", "已提交"
    elif total and counts["disabled"] == total:
        status, label = "disabled", "未启用"
    else:
        status, label = "none", "无通知"
    if not message:
        message = label
    return {
        "status": status,
        "label": label,
        "message": message,
        **counts,
    }


def dispatch_alert(
    entry,
    title,
    settings,
    email_sender,
    webhook_sender,
    logger=None,
    blocking=True,
    thread_factory=None,
    on_update=None,
    max_attempts=3,
    retry_wait=None,
    now_factory=None,
):
    logger = logger or logging.getLogger(__name__)
    notifications = plan_alert_notifications(entry, settings)

    def deliver():
        return deliver_alert_notifications(
            entry,
            title,
            settings,
            email_sender=email_sender,
            webhook_sender=webhook_sender,
            notifications=notifications,
            on_update=on_update,
            max_attempts=max_attempts,
            retry_wait=retry_wait,
            now_factory=now_factory,
            logger=logger,
        )

    if not blocking and thread_factory:
        thread_factory(target=deliver, daemon=True).start()
        return notifications
    return deliver()
