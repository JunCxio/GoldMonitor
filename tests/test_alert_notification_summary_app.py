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


def test_emit_alert_persists_partial_notification_summary(monkeypatch):
    _isolate_alert_emit(monkeypatch)
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {})
    monkeypatch.setattr(app, "evaluate_alert_delivery", lambda entry, settings: {"deliver": True, "reason": ""})
    monkeypatch.setattr(app, "dispatch_alert", lambda entry, title: [
        app._notification_status("email", "邮件", "queued", "已提交发送"),
        app._notification_status("webhook", "Webhook", "skipped", "Webhook 地址未配置"),
    ])

    app.emit_alert({"type": "warning", "mode": "rmb", "time": "12:00:00", "message": "测试通知提醒"}, "通知测试")

    entry = app.alert_log[-1]
    assert entry["notification_summary"]["status"] == "partial"
    assert entry["notification_summary"]["queued"] == 1
    assert entry["notification_summary"]["skipped"] == 1
    assert entry["notification_summary"]["message"] == "Webhook 地址未配置"
