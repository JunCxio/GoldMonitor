from datetime import datetime, timedelta
import time


def _socket_payloads(client, name, timeout=1.5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        received = [
            item["args"][0]
            for item in client.get_received()
            if item["name"] == name
        ]
        if received:
            return received
        time.sleep(0.01)
    return []


def test_retry_plan_preserves_sent_channel_and_only_requeues_failed_channel():
    from goldmonitor.notification_retry import build_retry_notifications

    entry = {
        "notifications": [
            {
                "channel": "email",
                "label": "邮件",
                "status": "sent",
                "message": "发送成功",
                "attempts": 1,
            },
            {
                "channel": "webhook",
                "label": "Webhook",
                "status": "failed",
                "message": "连接超时",
                "attempts": 3,
                "retryable": True,
            },
        ],
    }
    planned = [
        {"channel": "email", "label": "邮件", "status": "pending", "message": "等待发送"},
        {"channel": "webhook", "label": "Webhook", "status": "pending", "message": "等待发送"},
    ]

    result = build_retry_notifications(entry, planned)

    assert result["channels"] == ["webhook"]
    assert result["notifications"][0]["status"] == "sent"
    assert result["notifications"][1]["status"] == "pending"
    assert result["notifications"][1]["previous_attempts"] == 3


def test_automatic_retry_plan_rejects_non_retryable_failure():
    from goldmonitor.notification_retry import build_retry_notifications

    entry = {
        "notifications": [{
            "channel": "email",
            "label": "邮件",
            "status": "failed",
            "message": "SMTP 配置不完整",
            "attempts": 1,
            "retryable": False,
        }],
    }
    planned = [{
        "channel": "email",
        "label": "邮件",
        "status": "pending",
        "message": "等待发送",
    }]

    result = build_retry_notifications(entry, planned, retryable_only=True)

    assert result["channels"] == []
    assert result["notifications"] == entry["notifications"]


def test_retry_status_filters_expired_exhausted_and_not_due_entries():
    from goldmonitor.notification_retry import build_notification_retry_status

    now = datetime(2026, 8, 12, 12, 0)
    entries = [
        {
            "id": "eligible",
            "timestamp": "2026-08-12T10:00:00",
            "notifications": [{
                "channel": "webhook",
                "status": "failed",
                "message": "连接超时",
                "retryable": True,
                "completed_at": "2026-08-12T11:50:00",
            }],
        },
        {
            "id": "not-due",
            "timestamp": "2026-08-12T10:00:00",
            "notification_retry_next_at": "2026-08-12T12:10:00",
            "notifications": [{
                "channel": "email",
                "status": "failed",
                "message": "连接超时",
                "retryable": True,
            }],
        },
        {
            "id": "exhausted",
            "timestamp": "2026-08-12T10:00:00",
            "notification_auto_retry_count": 3,
            "notifications": [{
                "channel": "email",
                "status": "failed",
                "message": "连接超时",
                "retryable": True,
            }],
        },
        {
            "id": "expired",
            "timestamp": "2026-08-10T10:00:00",
            "notifications": [{
                "channel": "email",
                "status": "failed",
                "message": "连接超时",
                "retryable": True,
            }],
        },
    ]

    status = build_notification_retry_status(
        entries,
        enabled=True,
        now=now,
    )

    assert status["pending_count"] == 2
    assert status["eligible_count"] == 1
    assert status["exhausted_count"] == 1
    assert status["expired_count"] == 1
    assert [item["id"] for item in status["candidates"]] == ["eligible"]
    assert status["next_retry_at"] == "2026-08-12T12:10:00"


def test_retry_runtime_restores_candidates_from_persisted_entries():
    from goldmonitor.notification_retry_runtime import NotificationRetryRuntime

    entries = [{
        "id": "restart-failure",
        "timestamp": "2026-08-12T10:00:00",
        "notifications": [{
            "channel": "webhook",
            "status": "failed",
            "message": "连接超时",
            "retryable": True,
            "completed_at": "2026-08-12T11:40:00",
        }],
    }]
    resent = []
    emitted = []

    runtime = NotificationRetryRuntime(
        get_settings=lambda: {"notification_auto_retry_enabled": True},
        get_entries=lambda: entries,
        resend=lambda alert_id, **kwargs: resent.append((alert_id, kwargs)) or (
            True,
            {
                **entries[0],
                "notifications": [{
                    "channel": "webhook",
                    "status": "sent",
                    "message": "发送成功",
                }],
            },
        ),
        emit=lambda event, payload: emitted.append((event, payload)),
        now_factory=lambda: datetime(2026, 8, 12, 12, 0),
    )

    result = runtime.run_once()

    assert result["attempted_count"] == 1
    assert result["success_count"] == 1
    assert resent == [("restart-failure", {"blocking": True, "automatic": True})]
    assert emitted[-1][0] == "notification_retry_status"


def test_manual_retry_reports_channel_delivery_failure_without_broadcasting():
    from goldmonitor.notification_retry_runtime import NotificationRetryRuntime

    entry = {
        "id": "manual-failure",
        "timestamp": "2026-08-12T10:00:00",
        "notifications": [{
            "channel": "email",
            "status": "failed",
            "message": "连接超时",
            "retryable": True,
            "completed_at": "2026-08-12T11:40:00",
        }],
    }
    emitted = []
    runtime = NotificationRetryRuntime(
        get_settings=lambda: {"notification_auto_retry_enabled": False},
        get_entries=lambda: [entry],
        resend=lambda alert_id, **kwargs: (True, entry),
        emit=lambda event, payload: emitted.append((event, payload)),
        now_factory=lambda: datetime(2026, 8, 12, 12, 0),
    )

    result = runtime.run_once(manual=True)

    assert result["attempted_count"] == 1
    assert result["success_count"] == 0
    assert result["failure_count"] == 1
    assert result["attempts"][0]["persisted"] is True
    assert result["attempts"][0]["channels"][0]["status"] == "failed"
    assert emitted == []


def test_notification_retry_status_socket_reads_persisted_queue(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "APPDATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        app,
        "get_settings_snapshot",
        lambda: {"notification_auto_retry_enabled": True},
    )
    app.runtime.notification_retry_runtime_instance = None
    app.alert_log = []
    now = datetime.now()
    saved = app.save_alert_log_entry({
        "type": "warning",
        "message": "跨重启通知失败",
        "timestamp": (now - timedelta(minutes=30)).isoformat(timespec="seconds"),
        "notifications": [{
            "channel": "webhook",
            "status": "failed",
            "message": "连接超时",
            "retryable": True,
            "completed_at": (now - timedelta(minutes=20)).isoformat(timespec="seconds"),
        }],
    })
    assert saved

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("get_notification_retry_status")

    payload = _socket_payloads(client, "notification_retry_status")[0]
    assert payload["pending_count"] == 1
    assert payload["eligible_count"] == 1
    assert payload["expired_count"] == 0


def test_manual_retry_socket_only_replies_to_requesting_client(monkeypatch):
    import app

    calls = []
    result = {
        "ok": True,
        "status": "completed",
        "attempted_count": 1,
        "success_count": 1,
        "failure_count": 0,
    }
    monkeypatch.setattr(
        app,
        "run_notification_retry_once",
        lambda **kwargs: calls.append(kwargs) or result,
    )
    monkeypatch.setattr(
        app,
        "notification_retry_status",
        lambda: {"enabled": False, "pending_count": 0, "eligible_count": 0},
    )

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    other = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    other.get_received()
    client.emit("retry_failed_notifications")

    assert _socket_payloads(client, "notification_retry_result") == [result]
    assert calls == [{"manual": True}]
    assert not _socket_payloads(other, "notification_retry_result", timeout=0.1)


def test_manual_retry_only_sends_failed_channel_and_persists_result(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "APPDATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        app,
        "get_settings_snapshot",
        lambda: {
            "notification_auto_retry_enabled": False,
            "email_warning_enabled": True,
            "webhook_enabled": True,
            "webhook_warning_enabled": True,
        },
    )
    app.runtime.notification_retry_runtime_instance = None
    app.runtime.alert_notification_runtime_instance = None
    app.alert_log = []
    sent = []
    monkeypatch.setattr(
        app.EmailNotifier,
        "send",
        lambda *args, **kwargs: sent.append("email"),
    )
    monkeypatch.setattr(
        app.WebhookNotifier,
        "send",
        lambda *args, **kwargs: sent.append("webhook"),
    )
    saved = app.save_alert_log_entry({
        "type": "warning",
        "message": "部分送达",
        "title": "部分送达测试",
        "timestamp": "2026-08-12T10:00:00",
        "notifications": [
            {
                "channel": "email",
                "label": "邮件",
                "status": "sent",
                "message": "发送成功",
                "attempts": 1,
            },
            {
                "channel": "webhook",
                "label": "Webhook",
                "status": "failed",
                "message": "连接超时",
                "attempts": 3,
                "retryable": True,
                "completed_at": "2026-08-12T10:05:00",
            },
        ],
    })
    assert saved

    result = app.run_notification_retry_once(manual=True)

    assert result["success_count"] == 1
    assert sent == ["webhook"]
    persisted = app.load_alert_log_archive(limit=5)[-1]
    states = {item["channel"]: item["status"] for item in persisted["notifications"]}
    assert states == {"email": "sent", "webhook": "sent"}


def test_automatic_retry_increments_and_persists_retry_count(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "APPDATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        app,
        "get_settings_snapshot",
        lambda: {
            "notification_auto_retry_enabled": True,
            "email_warning_enabled": True,
            "webhook_enabled": False,
        },
    )
    app.runtime.notification_retry_runtime_instance = None
    app.runtime.alert_notification_runtime_instance = None
    app.alert_log = []
    monkeypatch.setattr(app.EmailNotifier, "send", lambda *args, **kwargs: None)
    saved = app.save_alert_log_entry({
        "type": "warning",
        "message": "自动重试计数",
        "timestamp": "2026-08-12T10:00:00",
        "notifications": [{
            "channel": "email",
            "label": "邮件",
            "status": "failed",
            "message": "连接超时",
            "retryable": True,
            "completed_at": "2026-08-12T10:05:00",
        }],
    })
    assert saved

    ok, updated = app.resend_alert_notification(
        saved["id"],
        blocking=True,
        automatic=True,
        retryable_only=True,
    )

    assert ok is True
    assert updated["notification_auto_retry_count"] == 1
    assert updated["last_notification_auto_retry_at"]
    persisted = app.load_alert_log_archive(limit=5)[-1]
    assert persisted["notification_auto_retry_count"] == 1


def test_automatic_retry_ignores_non_retryable_failure():
    from goldmonitor.notification_retry_runtime import NotificationRetryRuntime

    entries = [{
        "id": "invalid-config",
        "timestamp": "2026-08-12T10:00:00",
        "notifications": [{
            "channel": "email",
            "status": "failed",
            "message": "SMTP 配置不完整",
            "retryable": False,
        }],
    }]
    resent = []
    runtime = NotificationRetryRuntime(
        get_settings=lambda: {"notification_auto_retry_enabled": True},
        get_entries=lambda: entries,
        resend=lambda *args, **kwargs: resent.append((args, kwargs)),
        emit=lambda *args, **kwargs: None,
        now_factory=lambda: datetime(2026, 8, 12, 12, 0),
    )

    result = runtime.run_once()

    assert result["attempted_count"] == 0
    assert result["non_retryable_count"] == 1
    assert resent == []
