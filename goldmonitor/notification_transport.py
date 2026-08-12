import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formatdate


class SafeFormatDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def format_template(template, values, fallback):
    text = str(template or fallback)
    try:
        return text.format_map(SafeFormatDict(values))
    except Exception:
        return str(fallback).format_map(SafeFormatDict(values))


def build_alert_template_values(
    alert_type,
    title,
    message,
    market=None,
    level_map=None,
    now=None,
):
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


def build_email_message(
    settings,
    values,
    default_subject_template,
    default_body_template,
):
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
                server_obj = smtp_module.SMTP_SSL(
                    config["server"],
                    config["port"],
                    timeout=timeout,
                )
            else:
                server_obj = smtp_module.SMTP(
                    config["server"],
                    config["port"],
                    timeout=timeout,
                )
                server_obj.starttls()
            server_obj.login(config["sender"], config["password"])
            server_obj.sendmail(
                config["sender"],
                [config["recipient"]],
                msg.as_string(),
            )
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
        msg = build_email_message(
            settings,
            values,
            default_subject_template,
            default_body_template,
        )
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


def build_webhook_payload(
    alert_type,
    title,
    message,
    values,
    app_name,
    app_version,
):
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
    payload = build_webhook_payload(
        alert_type,
        title,
        message,
        values,
        app_name,
        app_version,
    )
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
                headers={
                    "User-Agent": user_agent,
                    "Content-Type": "application/json",
                },
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
