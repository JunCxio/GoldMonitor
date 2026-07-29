from datetime import datetime
import threading


def test_alert_delivery_start_snapshots_mutable_inputs():
    from goldmonitor.notification_runtime import start_alert_notification_delivery

    calls = []

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    entry = {
        "id": "alert-1",
        "notifications": [{"channel": "email", "status": "pending"}],
    }
    assert start_alert_notification_delivery(
        entry,
        "测试提醒",
        get_settings=lambda: {"email_enabled": True},
        deliver=lambda *args: calls.append(args),
        thread_factory=ImmediateThread,
    ) is True
    assert calls[0][0] == "alert-1"
    assert calls[0][1] is not entry
    assert calls[0][4] is not entry["notifications"]


def test_daily_digest_runtime_records_scheduled_result_and_emits_status():
    from goldmonitor.notification_runtime import run_daily_digest_once

    state = {"last_completed_at": ""}
    emitted = []

    class Store:
        def load(self):
            return dict(state)

        def record_result(self, **values):
            state.update({"last_completed_at": "2026-07-28T20:05:00", **values})
            return dict(state)

    result = run_daily_digest_once(
        now=datetime(2026, 7, 28, 20, 5),
        force=False,
        manual=False,
        settings={
            "daily_digest_enabled": True,
            "daily_digest_time": "20:00",
            "daily_digest_email_enabled": True,
            "daily_digest_webhook_enabled": False,
        },
        lock=threading.RLock(),
        state_store=Store(),
        build_digest=lambda now: {"subject": "摘要", "message": "内容"},
        email_sender=lambda digest, blocking=False: None,
        webhook_sender=lambda digest, blocking=False: None,
        emit_status=lambda event, payload: emitted.append((event, payload)),
        status_payload=lambda now: {"time": now.isoformat()},
    )

    assert result["ok"] is True
    assert result["status"] == "sent"
    assert emitted == [("daily_digest_status", {"time": "2026-07-28T20:05:00"})]


def test_emit_alert_builds_muted_record_without_local_delivery():
    from goldmonitor.notification_runtime import emit_alert

    alerts = []
    emitted = []
    local = []
    lock = threading.RLock()
    entry = {"type": "warning", "mode": "rmb", "time": "12:00", "message": "测试"}

    emit_alert(
        entry,
        "静默提醒",
        settings={},
        market_lock=lock,
        market_price=lambda mode: 528.1,
        generate_id=lambda: "alert-1",
        evaluate_delivery=lambda item, settings: {"deliver": False, "reason": "quiet_time"},
        plan_notifications=lambda item, settings: [],
        select_news=lambda title: [],
        alert_log=alerts,
        alert_log_limit=10,
        save_entry=lambda item: None,
        emit=lambda event, payload: emitted.append((event, payload)),
        start_delivery=lambda *args, **kwargs: None,
        build_history_state=lambda limit: {},
        local_delivery_enabled=lambda item: True,
        send_desktop_notification=lambda *args: local.append("desktop"),
        play_system_alert_sound=lambda *args: local.append("sound"),
        show_alert_dialog=lambda *args: local.append("dialog"),
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
    )

    assert alerts[0]["trigger_price"] == 528.1
    assert alerts[0]["notification_summary"]["status"] == "muted"
    assert [event for event, _payload in emitted] == ["alert", "price_history_updated"]
    assert local == []


def test_desktop_notification_uses_macos_applescript_contract():
    from goldmonitor.notification_runtime import send_desktop_notification

    scripts = []
    send_desktop_notification(
        "标题",
        "内容",
        sys_platform="darwin",
        base_dir="/app",
        app_id="GoldMonitor.App",
        applescript_string=lambda value: f'"{value}"',
        run_applescript=lambda script, **kwargs: scripts.append((script, kwargs)),
    )

    assert scripts == [('display notification "内容" with title "标题"', {"wait": False})]
