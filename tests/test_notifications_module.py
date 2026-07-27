import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_alert_delivery_respects_quiet_time_force_and_cooldown():
    from goldmonitor.notifications import evaluate_alert_delivery, is_alert_quiet_time

    settings = {
        "alert_quiet_start": "22:00",
        "alert_quiet_end": "07:30",
        "alert_cooldown_minutes": 30,
    }
    assert is_alert_quiet_time(settings, datetime(2026, 6, 8, 23, 0)) is True
    assert is_alert_quiet_time(settings, datetime(2026, 6, 8, 8, 0)) is False

    cooldown_state = {}
    quiet = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 23, 0),
    )
    assert quiet == {"deliver": False, "reason": "quiet_time"}
    assert cooldown_state == {}

    forced = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb", "force_notify": True},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 23, 0),
    )
    assert forced == {"deliver": True, "reason": ""}

    first = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 0),
    )
    second = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 10),
    )
    assert first == {"deliver": True, "reason": ""}
    assert second["deliver"] is False
    assert second["reason"] == "cooldown"
    assert second["remaining_seconds"] == 1200


def test_alert_cooldown_is_scoped_to_the_specific_alert_rule():
    from goldmonitor.notifications import evaluate_alert_delivery

    settings = {"alert_cooldown_minutes": 30}
    cooldown_state = {}

    threshold = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb", "source": "threshold", "threshold_key": "upper_warning_rmb"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 0),
    )
    watch_target = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb", "source": "watch_target", "watch_target_id": "target-1"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 5),
    )
    same_watch_target = evaluate_alert_delivery(
        {"type": "warning", "mode": "rmb", "source": "watch_target", "watch_target_id": "target-1"},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 10),
    )

    assert threshold == {"deliver": True, "reason": ""}
    assert watch_target == {"deliver": True, "reason": ""}
    assert same_watch_target["deliver"] is False
    assert same_watch_target["reason"] == "cooldown"


def test_rule_delivery_overrides_channels_and_cooldown():
    from goldmonitor.notifications import (
        alert_local_delivery_enabled,
        evaluate_alert_delivery,
        plan_alert_notifications,
    )

    settings = {
        "alert_cooldown_minutes": 30,
        "email_warning_enabled": True,
        "webhook_enabled": True,
        "webhook_warning_enabled": True,
    }
    cooldown_state = {}
    entry = {
        "rule_id": "rule-budget",
        "type": "warning",
        "mode": "rmb",
        "source": "watch_target",
        "delivery_channels": ["email"],
        "cooldown_minutes": 5,
    }

    first = evaluate_alert_delivery(entry, settings, cooldown_state, now=datetime(2026, 6, 8, 12, 0))
    repeated = evaluate_alert_delivery(entry, settings, cooldown_state, now=datetime(2026, 6, 8, 12, 3))
    notifications = plan_alert_notifications(entry, settings)

    assert first == {"deliver": True, "reason": ""}
    assert repeated["reason"] == "cooldown"
    assert repeated["remaining_seconds"] == 120
    assert notifications[0]["channel"] == "email" and notifications[0]["status"] == "pending"
    assert notifications[1]["channel"] == "webhook" and notifications[1]["status"] == "disabled"
    assert alert_local_delivery_enabled(entry) is False

    record_only = evaluate_alert_delivery(
        {**entry, "rule_id": "rule-record", "delivery_channels": []},
        settings,
        cooldown_state,
        now=datetime(2026, 6, 8, 12, 0),
    )
    assert record_only == {"deliver": False, "reason": "no_channels"}


def test_templates_and_webhook_payload_use_market_context_without_leaking_format_errors():
    from goldmonitor.notifications import build_alert_template_values, build_webhook_payload, format_template

    values = build_alert_template_values(
        "critical",
        "突破上限",
        "价格触发",
        market={
            "price_usd": 2350.12,
            "price_rmb": 543.21,
            "usdcny_rate": 7.19,
            "gold_price_source": "Stooq",
            "usdcny_rate_source": "Frankfurter",
        },
        level_map={"critical": "警告"},
        now=datetime(2026, 6, 8, 12, 0, 0),
    )
    assert values["level"] == "警告"
    assert values["price_usd"] == "2,350.12"
    assert values["price_rmb"] == "543.21"
    assert values["rate"] == "7.1900"

    rendered = format_template("{missing", values, "[{level}] {title}")
    assert rendered == "[警告] 突破上限"

    payload = build_webhook_payload(
        "critical",
        "突破上限",
        "价格触发",
        values,
        app_name="GoldMonitor",
        app_version="1.0.0",
    )
    assert payload["app"] == "GoldMonitor"
    assert payload["version"] == "1.0.0"
    assert payload["type"] == "critical"
    assert payload["title"] == "突破上限"
    assert payload["price_rmb"] == "543.21"


def test_dispatch_alert_reports_final_delivery_statuses():
    from goldmonitor.notifications import dispatch_alert

    class QuietLogger:
        def warning(self, *args, **kwargs):
            return None

    sent = []

    def email_send(alert_type, title, message, **kwargs):
        sent.append(("email", alert_type, title, message))
        return None

    def webhook_send(alert_type, title, message, **kwargs):
        sent.append(("webhook", alert_type, title, message))
        return "Webhook 地址未配置，跳过发送"

    settings = {
        "email_warning_enabled": True,
        "webhook_enabled": True,
        "webhook_warning_enabled": True,
    }
    notifications = dispatch_alert(
        {"type": "warning", "message": "测试提醒"},
        "通知测试",
        settings,
        email_sender=email_send,
        webhook_sender=webhook_send,
        logger=QuietLogger(),
    )
    assert [item["channel"] for item in notifications] == ["email", "webhook"]
    assert notifications[0]["status"] == "sent"
    assert notifications[0]["attempts"] == 1
    assert notifications[1]["status"] == "failed"
    assert notifications[1]["attempts"] == 1
    assert sent == [
        ("email", "warning", "通知测试", "测试提醒"),
        ("webhook", "warning", "通知测试", "测试提醒"),
    ]

    disabled = dispatch_alert(
        {"type": "critical", "message": "测试提醒"},
        "通知测试",
        {"email_critical_enabled": False, "webhook_enabled": False},
        email_sender=email_send,
        webhook_sender=webhook_send,
        logger=QuietLogger(),
    )
    assert [item["status"] for item in disabled] == ["disabled", "disabled"]


def test_delivery_failure_log_does_not_include_raw_error_details():
    from goldmonitor.notifications import deliver_notification, notification_status

    warnings = []

    class CapturedLogger:
        def warning(self, *args, **kwargs):
            warnings.append((args, kwargs))

    secret_error = "Webhook 请求失败: https://example.com/hooks/private-token"
    result = deliver_notification(
        notification_status("webhook", "Webhook", "pending", "等待发送"),
        lambda *args, **kwargs: secret_error,
        (),
        max_attempts=1,
        logger=CapturedLogger(),
    )

    assert result["status"] == "failed"
    assert result["message"] == secret_error
    assert len(warnings) == 1
    assert "private-token" not in repr(warnings)


def test_dispatch_alert_async_returns_pending_then_reports_retried_result():
    from goldmonitor.notifications import dispatch_alert

    attempts = []
    updates = []
    threads = []

    def email_send(alert_type, title, message, blocking=False):
        attempts.append(blocking)
        return "临时网络错误" if len(attempts) < 3 else None

    class CapturedThread:
        def __init__(self, target, daemon=False):
            threads.append((target, daemon))

        def start(self):
            return None

    notifications = dispatch_alert(
        {"type": "warning", "message": "测试提醒"},
        "通知测试",
        {"email_warning_enabled": True, "webhook_enabled": False},
        email_sender=email_send,
        webhook_sender=lambda *args, **kwargs: None,
        blocking=False,
        thread_factory=CapturedThread,
        retry_wait=lambda attempt: None,
        on_update=lambda items, item: updates.append((items, item)),
    )

    assert notifications[0]["status"] == "pending"
    assert notifications[0]["attempts"] == 0
    assert len(threads) == 1
    assert threads[0][1] is True

    threads[0][0]()

    assert attempts == [True, True, True]
    assert updates[-1][1]["status"] == "sent"
    assert updates[-1][1]["attempts"] == 3


def test_summarize_notifications_prioritizes_muted_and_partial_failures():
    from goldmonitor.notifications import notification_status, summarize_notifications

    muted = summarize_notifications([
        notification_status("all", "通知", "muted", "当前处于静默时段，仅记录提醒。"),
    ])
    assert muted == {
        "status": "muted",
        "label": "已静默",
        "message": "当前处于静默时段，仅记录提醒。",
        "pending": 0,
        "sent": 0,
        "failed": 0,
        "queued": 0,
        "skipped": 0,
        "disabled": 0,
        "muted": 1,
    }

    partial = summarize_notifications([
        notification_status("email", "邮件", "sent", "发送成功"),
        notification_status("webhook", "Webhook", "failed", "Webhook 地址未配置"),
    ])
    assert partial["status"] == "partial"
    assert partial["label"] == "部分送达"
    assert partial["sent"] == 1
    assert partial["failed"] == 1
    assert partial["message"] == "Webhook 地址未配置"

    disabled = summarize_notifications([
        notification_status("email", "邮件", "disabled", "未启用"),
        notification_status("webhook", "Webhook", "disabled", "未启用"),
    ])
    assert disabled["status"] == "disabled"
    assert disabled["label"] == "未启用"
    assert disabled["disabled"] == 2


def test_generic_email_and_webhook_senders_preserve_digest_content():
    from goldmonitor.notifications import send_email_message, send_webhook_payload

    sent_mail = {}

    class FakeServer:
        def login(self, sender, password):
            sent_mail["login"] = (sender, password)

        def sendmail(self, sender, recipients, message):
            sent_mail["message"] = (sender, recipients, message)

        def quit(self):
            sent_mail["quit"] = True

    class FakeSmtp:
        @staticmethod
        def SMTP_SSL(server, port, timeout):
            sent_mail["connect"] = (server, port, timeout)
            return FakeServer()

    settings = {
        "smtp_server": "smtp.example.com",
        "smtp_port": "465",
        "smtp_encryption": "ssl",
        "smtp_sender": "sender@example.com",
        "smtp_password": "secret",
        "smtp_recipient": "receiver@example.com",
        "webhook_enabled": True,
        "webhook_url": "https://example.com/hook",
    }
    error = send_email_message(
        settings,
        "[GoldMonitor] 每日摘要 2026-07-13",
        "摘要正文",
        smtp_module=FakeSmtp,
        blocking=True,
    )
    assert error is None
    assert sent_mail["connect"] == ("smtp.example.com", 465, 10)
    from email import message_from_string
    from email.header import decode_header

    parsed_message = message_from_string(sent_mail["message"][2])
    subject_bytes, subject_encoding = decode_header(parsed_message["Subject"])[0]
    decoded_subject = (
        subject_bytes.decode(subject_encoding or "utf-8")
        if isinstance(subject_bytes, bytes)
        else subject_bytes
    )
    assert "每日摘要 2026-07-13" in decoded_subject
    assert parsed_message.get_payload(decode=True).decode("utf-8") == "摘要正文"

    posted = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

    def fake_post(url, **kwargs):
        posted["url"] = url
        posted.update(kwargs)
        return FakeResponse()

    error = send_webhook_payload(
        settings,
        {"kind": "daily_summary", "message": "摘要正文"},
        post=fake_post,
        require_https_url=lambda value, label: None,
        user_agent="GoldMonitor/1.0.5",
        blocking=True,
    )
    assert error is None
    assert posted["url"] == "https://example.com/hook"
    assert posted["json"]["kind"] == "daily_summary"
    assert posted["headers"]["User-Agent"] == "GoldMonitor/1.0.5"


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("notification module checks passed.")
