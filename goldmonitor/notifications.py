import logging
import inspect
import time
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formatdate


ALERT_CHANNEL_KEYS = {
    "email": {
        "warning": "email_warning_enabled",
        "critical": "email_critical_enabled",
        "volatility": "email_volatility_enabled",
    },
    "webhook": {
        "warning": "webhook_warning_enabled",
        "critical": "webhook_critical_enabled",
        "volatility": "webhook_volatility_enabled",
    },
}


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def format_template(template, values, fallback):
    text = str(template or fallback)
    try:
        return text.format_map(SafeFormatDict(values))
    except Exception:
        return str(fallback).format_map(SafeFormatDict(values))


def time_to_minutes(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


def is_alert_quiet_time(settings, now=None):
    settings = settings or {}
    start = time_to_minutes(settings.get("alert_quiet_start"))
    end = time_to_minutes(settings.get("alert_quiet_end"))
    if start is None or end is None or start == end:
        return False
    now = now or datetime.now()
    current = now.hour * 60 + now.minute
    if start < end:
        return start <= current < end
    return current >= start or current < end


def alert_cooldown_key(entry):
    source = str(entry.get("source") or "alert")
    identifier = (
        entry.get("threshold_key")
        or entry.get("watch_target_id")
        or entry.get("portfolio_alert_id")
        or entry.get("portfolio_position_id")
        or source
    )
    if entry.get("portfolio_alert_condition"):
        identifier = f"{identifier}:{entry.get('portfolio_alert_condition')}"
    return ":".join([
        str(entry.get("type") or "warning"),
        str(entry.get("mode") or "all"),
        source,
        str(identifier),
    ])


def evaluate_alert_delivery(entry, settings, cooldown_state, now=None):
    if entry.get("force_notify"):
        return {"deliver": True, "reason": ""}
    settings = settings or {}
    cooldown_state = cooldown_state if isinstance(cooldown_state, dict) else {}
    now = now or datetime.now()
    if is_alert_quiet_time(settings, now):
        return {"deliver": False, "reason": "quiet_time"}
    try:
        cooldown_minutes = int(settings.get("alert_cooldown_minutes", 0) or 0)
    except (TypeError, ValueError):
        cooldown_minutes = 0
    if cooldown_minutes <= 0:
        return {"deliver": True, "reason": ""}
    key = alert_cooldown_key(entry)
    last_time = cooldown_state.get(key)
    if last_time and (now - last_time).total_seconds() < cooldown_minutes * 60:
        remaining = int(cooldown_minutes * 60 - (now - last_time).total_seconds())
        return {"deliver": False, "reason": "cooldown", "remaining_seconds": max(1, remaining)}
    cooldown_state[key] = now
    return {"deliver": True, "reason": ""}


def build_alert_template_values(alert_type, title, message, market=None, level_map=None, now=None):
    market = market or {}
    level_map = level_map or {}
    now = now or datetime.now()
    price_usd = market.get("price_usd")
    price_rmb = market.get("price_rmb")
    usdcny_rate = market.get("usdcny_rate")
    return {
        "title": title,
        "message": message,
        "level": level_map.get(alert_type, alert_type),
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "price_usd": f"{price_usd:,.2f}" if price_usd is not None else "--",
        "price_rmb": f"{price_rmb:,.2f}" if price_rmb is not None else "--",
        "rate": f"{usdcny_rate:.4f}" if usdcny_rate is not None else "--",
        "gold_source": market.get("gold_price_source") or "--",
        "rate_source": market.get("usdcny_rate_source") or "--",
    }


def build_email_message(settings, values, default_subject_template, default_body_template):
    settings = settings or {}
    sender = settings.get("smtp_sender", "").strip()
    recipient = settings.get("smtp_recipient", "").strip()
    subject = format_template(
        settings.get("email_subject_template"),
        values,
        default_subject_template,
    )
    body = format_template(
        settings.get("email_body_template"),
        values,
        default_body_template,
    )
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    return msg


def build_plain_email_message(settings, subject, body):
    settings = settings or {}
    sender = settings.get("smtp_sender", "").strip()
    recipient = settings.get("smtp_recipient", "").strip()
    msg = MIMEText(str(body or ""), "plain", "utf-8")
    msg["Subject"] = str(subject or "")
    msg["From"] = sender
    msg["To"] = recipient
    msg["Date"] = formatdate(localtime=True)
    return msg


def _smtp_delivery_config(settings):
    settings = settings or {}
    server = settings.get("smtp_server", "").strip()
    port_str = settings.get("smtp_port", "465").strip()
    encryption = settings.get("smtp_encryption", "ssl")
    sender = settings.get("smtp_sender", "").strip()
    password = settings.get("smtp_password", "")
    recipient = settings.get("smtp_recipient", "").strip()
    if not (server and port_str and sender and password and recipient):
        return None, "SMTP 配置不完整，跳过邮件发送"
    try:
        port = int(port_str)
    except ValueError:
        return None, f"SMTP 端口格式无效: {port_str}"
    return {
        "server": server,
        "port": port,
        "encryption": encryption,
        "sender": sender,
        "password": password,
        "recipient": recipient,
    }, ""


def _send_email_mime_message(
    settings,
    msg,
    smtp_module,
    timeout=10,
    blocking=False,
    thread_factory=None,
    logger=None,
):
    logger = logger or logging.getLogger(__name__)
    config, error = _smtp_delivery_config(settings)
    if error:
        return error

    def _send():
        try:
            if config["encryption"] == "ssl":
                server_obj = smtp_module.SMTP_SSL(config["server"], config["port"], timeout=timeout)
            else:
                server_obj = smtp_module.SMTP(config["server"], config["port"], timeout=timeout)
                server_obj.starttls()
            server_obj.login(config["sender"], config["password"])
            server_obj.sendmail(config["sender"], [config["recipient"]], msg.as_string())
            server_obj.quit()
            return None
        except Exception as exc:
            return str(exc)

    if blocking:
        return _send()

    def _send_async():
        send_error = _send()
        if send_error:
            logger.warning("邮件通知发送失败")

    if thread_factory:
        thread_factory(target=_send_async, daemon=True).start()
    else:
        _send_async()
    return None


def send_email_message(
    settings,
    subject,
    body,
    smtp_module,
    timeout=10,
    blocking=False,
    thread_factory=None,
    logger=None,
):
    try:
        msg = build_plain_email_message(settings, subject, body)
    except Exception as exc:
        return f"构建邮件失败: {exc}"
    return _send_email_mime_message(
        settings,
        msg,
        smtp_module,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def send_email_notification(
    settings,
    alert_type,
    title,
    message,
    values,
    smtp_module,
    default_subject_template,
    default_body_template,
    timeout=10,
    blocking=False,
    thread_factory=None,
    logger=None,
):
    try:
        msg = build_email_message(settings, values, default_subject_template, default_body_template)
    except Exception as exc:
        return f"构建邮件失败: {exc}"
    return _send_email_mime_message(
        settings,
        msg,
        smtp_module,
        timeout=timeout,
        blocking=blocking,
        thread_factory=thread_factory,
        logger=logger,
    )


def build_webhook_payload(alert_type, title, message, values, app_name, app_version):
    return {
        "app": app_name,
        "version": app_version,
        "type": alert_type,
        "level": values["level"],
        "title": title,
        "message": message,
        "time": values["time"],
        "price_usd": values["price_usd"],
        "price_rmb": values["price_rmb"],
        "rate": values["rate"],
        "gold_source": values["gold_source"],
        "rate_source": values["rate_source"],
    }


def send_webhook_notification(
    settings,
    alert_type,
    title,
    message,
    values,
    post,
    require_https_url,
    app_name,
    app_version,
    user_agent,
    proxies=None,
    timeout=8,
    blocking=False,
    thread_factory=None,
    logger=None,
):
    payload = build_webhook_payload(alert_type, title, message, values, app_name, app_version)
    return send_webhook_payload(
        settings,
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


def send_webhook_payload(
    settings,
    payload,
    post,
    require_https_url,
    user_agent,
    proxies=None,
    timeout=8,
    blocking=False,
    thread_factory=None,
    logger=None,
):
    settings = settings or {}
    logger = logger or logging.getLogger(__name__)
    if not settings.get("webhook_enabled", False):
        return "Webhook 通知未启用"
    url = settings.get("webhook_url", "").strip()
    if not url:
        return "Webhook 地址未配置，跳过发送"
    try:
        require_https_url(url, "Webhook 地址")
    except ValueError as exc:
        return str(exc)

    def _send():
        try:
            response = post(
                url,
                json=payload,
                headers={"User-Agent": user_agent, "Content-Type": "application/json"},
                timeout=timeout,
                proxies=proxies,
            )
            response.raise_for_status()
            return None
        except Exception as exc:
            return str(exc)

    if blocking:
        return _send()

    def _send_async():
        error = _send()
        if error:
            logger.warning("Webhook 通知发送失败")

    if thread_factory:
        thread_factory(target=_send_async, daemon=True).start()
    else:
        _send_async()
    return None


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
        parameter.kind == inspect.Parameter.VAR_KEYWORD or parameter.name == "blocking"
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
            error = str(_invoke_blocking_sender(sender, tuple(sender_args or ())) or "")
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

    email_key = ALERT_CHANNEL_KEYS["email"].get(alert_type, "email_warning_enabled")
    if settings.get(email_key, True):
        notifications.append(notification_status(
            "email",
            "邮件",
            "pending",
            "等待发送",
            attempts=0,
            started_at="",
            completed_at="",
        ))
    else:
        notifications.append(notification_status("email", "邮件", "disabled", "未启用"))

    webhook_key = ALERT_CHANNEL_KEYS["webhook"].get(alert_type, "webhook_warning_enabled")
    if settings.get("webhook_enabled", False) and settings.get(webhook_key, True):
        notifications.append(notification_status(
            "webhook",
            "Webhook",
            "pending",
            "等待发送",
            attempts=0,
            started_at="",
            completed_at="",
        ))
    else:
        notifications.append(notification_status("webhook", "Webhook", "disabled", "未启用"))
    return notifications


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
    items = [dict(item) for item in (notifications or plan_alert_notifications(entry, settings))]
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
    items = [dict(item) for item in list(notifications or []) if isinstance(item, dict)]
    counts = {
        "pending": sum(1 for item in items if item.get("status") == "pending"),
        "sent": sum(1 for item in items if item.get("status") == "sent"),
        "failed": sum(1 for item in items if item.get("status") == "failed"),
        "queued": sum(1 for item in items if item.get("status") == "queued"),
        "skipped": sum(1 for item in items if item.get("status") == "skipped"),
        "disabled": sum(1 for item in items if item.get("status") == "disabled"),
        "muted": sum(1 for item in items if item.get("status") == "muted"),
    }
    message = next(
        (
            str(item.get("message") or "")
            for item in items
            if item.get("status") in {"muted", "failed", "skipped"} and item.get("message")
        ),
        "",
    )
    total = len(items)
    if counts["muted"]:
        status, label = "muted", "已静默"
    elif counts["pending"]:
        status, label = "pending", "投递中"
    elif (counts["failed"] or counts["skipped"]) and (counts["sent"] or counts["queued"]):
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
