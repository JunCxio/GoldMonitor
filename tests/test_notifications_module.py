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
        app_version="1.4.2",
    )
    assert payload["app"] == "GoldMonitor"
    assert payload["version"] == "1.4.2"
    assert payload["type"] == "critical"
    assert payload["title"] == "突破上限"
    assert payload["price_rmb"] == "543.21"


def test_dispatch_alert_reports_enabled_disabled_and_skipped_channels():
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
    assert notifications[0]["status"] == "queued"
    assert notifications[1]["status"] == "skipped"
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


def test_summarize_notifications_prioritizes_muted_and_partial_failures():
    from goldmonitor.notifications import notification_status, summarize_notifications

    muted = summarize_notifications([
        notification_status("all", "通知", "muted", "当前处于静默时段，仅记录提醒。"),
    ])
    assert muted == {
        "status": "muted",
        "label": "已静默",
        "message": "当前处于静默时段，仅记录提醒。",
        "queued": 0,
        "skipped": 0,
        "disabled": 0,
        "muted": 1,
    }

    partial = summarize_notifications([
        notification_status("email", "邮件", "queued", "已提交发送"),
        notification_status("webhook", "Webhook", "skipped", "Webhook 地址未配置"),
    ])
    assert partial["status"] == "partial"
    assert partial["label"] == "部分提交"
    assert partial["queued"] == 1
    assert partial["skipped"] == 1
    assert partial["message"] == "Webhook 地址未配置"

    disabled = summarize_notifications([
        notification_status("email", "邮件", "disabled", "未启用"),
        notification_status("webhook", "Webhook", "disabled", "未启用"),
    ])
    assert disabled["status"] == "disabled"
    assert disabled["label"] == "未启用"
    assert disabled["disabled"] == 2


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
