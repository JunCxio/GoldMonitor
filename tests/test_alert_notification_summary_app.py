from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def _isolate_alert_emit(monkeypatch):
    monkeypatch.setattr(app, "alert_log", [])
    monkeypatch.setattr(app, "select_related_news", lambda title: [])
    monkeypatch.setattr(app, "save_alert_log_entry", lambda entry: entry)
    monkeypatch.setattr(app, "build_price_history_state", lambda limit=240: {})
    monkeypatch.setattr(app.socketio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "send_desktop_notification", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "play_system_alert_sound", lambda *args, **kwargs: None)
    monkeypatch.setattr(app, "show_alert_dialog", lambda *args, **kwargs: None)


def test_emit_alert_persists_muted_notification_summary(monkeypatch):
    _isolate_alert_emit(monkeypatch)
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {})
    monkeypatch.setattr(app, "evaluate_alert_delivery", lambda entry, settings: {"deliver": False, "reason": "quiet_time"})

    app.emit_alert({"type": "warning", "mode": "rmb", "time": "12:00:00", "message": "测试静默提醒"}, "静默测试")

    entry = app.alert_log[-1]
    assert entry["notification_muted"] is True
    assert entry["notification_reason"] == "quiet_time"
    assert entry["notification_summary"]["status"] == "muted"
    assert entry["notification_summary"]["label"] == "已静默"


def test_emit_alert_persists_pending_status_before_starting_delivery(monkeypatch):
    _isolate_alert_emit(monkeypatch)
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {})
    monkeypatch.setattr(app, "evaluate_alert_delivery", lambda entry, settings: {"deliver": True, "reason": ""})
    monkeypatch.setattr(app, "_plan_alert_notifications", lambda entry, settings: [
        app._notification_status("email", "邮件", "pending", "等待发送", attempts=0),
        app._notification_status("webhook", "Webhook", "disabled", "未启用"),
    ])
    started = []
    monkeypatch.setattr(
        app,
        "_start_alert_notification_delivery",
        lambda entry, title, settings=None: started.append((entry["id"], title)),
    )

    app.emit_alert({"type": "warning", "mode": "rmb", "time": "12:00:00", "message": "测试通知提醒"}, "通知测试")

    entry = app.alert_log[-1]
    assert entry["id"].startswith("alert-")
    assert entry["notification_summary"]["status"] == "pending"
    assert entry["notification_summary"]["pending"] == 1
    assert started == [(entry["id"], "通知测试")]


def test_persist_alert_notification_update_replaces_summary_and_broadcasts(monkeypatch):
    entries = {
        "alert-1": {
            "id": "alert-1",
            "notifications": [app._notification_status("email", "邮件", "pending", "等待发送")],
        },
    }
    emitted = []

    def update_payload(alert_id, updater):
        updated = updater(entries[alert_id])
        entries[alert_id] = updated
        return True, updated

    monkeypatch.setattr(app, "_update_alert_log_entry_payload", update_payload)
    monkeypatch.setattr(app.socketio, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))

    ok, entry = app._persist_alert_notification_update("alert-1", [
        app._notification_status("email", "邮件", "sent", "发送成功", attempts=1),
        app._notification_status("webhook", "Webhook", "failed", "Webhook 地址未配置", attempts=1),
    ])

    assert ok is True
    assert entry["notification_summary"]["status"] == "partial"
    assert entry["notification_summary"]["sent"] == 1
    assert entry["notification_summary"]["failed"] == 1
    assert entry["notification_summary"]["message"] == "Webhook 地址未配置"
    assert emitted[-1][0][0] == "alert_log_status_updated"
