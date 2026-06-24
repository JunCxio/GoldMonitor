import logging
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
    return ":".join([
        str(entry.get("type") or "warning"),
        str(entry.get("mode") or "all"),
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
    settings = settings or {}
    logger = logger or logging.getLogger(__name__)
    server = settings.get("smtp_server", "").strip()
    port_str = settings.get("smtp_port", "465").strip()
    encryption = settings.get("smtp_encryption", "ssl")
    sender = settings.get("smtp_sender", "").strip()
    password = settings.get("smtp_password", "")
    recipient = settings.get("smtp_recipient", "").strip()
    if not (server and port_str and sender and password and recipient):
        return "SMTP 配置不完整，跳过邮件发送"
    try:
        port = int(port_str)
    except ValueError:
        return f"SMTP 端口格式无效: {port_str}"
    try:
        msg = build_email_message(settings, values, default_subject_template, default_body_template)
    except Exception as exc:
        return f"构建邮件失败: {exc}"

    def _send():
        try:
            if encryption == "ssl":
                server_obj = smtp_module.SMTP_SSL(server, port, timeout=timeout)
            else:
                server_obj = smtp_module.SMTP(server, port, timeout=timeout)
                server_obj.starttls()
            server_obj.login(sender, password)
            server_obj.sendmail(sender, [recipient], msg.as_string())
            server_obj.quit()
            return None
        except Exception as exc:
            return str(exc)

    if blocking:
        return _send()

    def _send_async():
        error = _send()
        if error:
            logger.warning("邮件通知发送失败: %s", error)

    if thread_factory:
        thread_factory(target=_send_async, daemon=True).start()
    else:
        _send_async()
    return None


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
    payload = build_webhook_payload(alert_type, title, message, values, app_name, app_version)

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
            logger.warning("Webhook 通知发送失败: %s", error)

    if thread_factory:
        thread_factory(target=_send_async, daemon=True).start()
    else:
        _send_async()
    return None


def notification_status(channel, label, status, message):
    return {
        "channel": channel,
        "label": label,
        "status": status,
        "message": message,
    }


def dispatch_alert(entry, title, settings, email_sender, webhook_sender, logger=None):
    settings = settings or {}
    logger = logger or logging.getLogger(__name__)
    alert_type = entry.get("type", "warning")
    message = entry.get("message", "")
    notifications = []

    email_key = ALERT_CHANNEL_KEYS["email"].get(alert_type, "email_warning_enabled")
    if settings.get(email_key, True):
        error = email_sender(alert_type, title, message)
        if error:
            logger.warning("邮件通知跳过: %s", error)
            notifications.append(notification_status("email", "邮件", "skipped", error))
        else:
            notifications.append(notification_status("email", "邮件", "queued", "已提交发送"))
    else:
        notifications.append(notification_status("email", "邮件", "disabled", "未启用"))

    webhook_key = ALERT_CHANNEL_KEYS["webhook"].get(alert_type, "webhook_warning_enabled")
    if settings.get("webhook_enabled", False) and settings.get(webhook_key, True):
        error = webhook_sender(alert_type, title, message)
        if error:
            logger.warning("Webhook 通知跳过: %s", error)
            notifications.append(notification_status("webhook", "Webhook", "skipped", error))
        else:
            notifications.append(notification_status("webhook", "Webhook", "queued", "已提交发送"))
    else:
        notifications.append(notification_status("webhook", "Webhook", "disabled", "未启用"))
    return notifications
