import logging
import threading

from goldmonitor import notifications as notifications_core


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
