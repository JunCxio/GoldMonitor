import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from goldmonitor.socket_alert_log import _batch_alert_ids


def _saved_alert(app, alert_id, message):
    entry = {
        "id": alert_id,
        "type": "warning",
        "mode": "rmb",
        "time": "12:00:00",
        "timestamp": "2026-08-12T12:00:00",
        "message": message,
        "handled": False,
        "notifications": [{"channel": "email", "label": "邮件", "status": "failed"}],
        "notification_summary": {"status": "failed", "label": "邮件"},
    }
    saved = app.save_alert_log_entry(entry)
    app.alert_log.append(saved)
    return saved


def test_alert_log_batch_ids_are_unique_and_limited():
    values = ["alert-1", "alert-1", "", None]
    values.extend(f"alert-{index}" for index in range(2, 60))

    result = _batch_alert_ids({"ids": values})

    assert len(result) == 50
    assert result[:3] == ["alert-1", "alert-2", "alert-3"]
    assert result[-1] == "alert-50"


def test_alert_log_batch_handling_reports_partial_result(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "APPDATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "alert_log", [])
    first = _saved_alert(app, "batch-alert-1", "第一条警报")
    second = _saved_alert(app, "batch-alert-2", "第二条警报")

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("batch_update_alert_log_handling", {
        "ids": [first["id"], second["id"], "missing-alert", first["id"]],
    })
    events = client.get_received()
    result = next(
        event["args"][0]
        for event in events
        if event["name"] == "alert_log_handling_batch_updated"
    )

    assert result["ok"] is False
    assert result["partial"] is True
    assert result["requested_count"] == 3
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert {entry["id"] for entry in result["entries"]} == {
        "batch-alert-1",
        "batch-alert-2",
    }
    assert result["failures"] == [
        {"id": "missing-alert", "message": "未找到对应警报记录"}
    ]
    assert all(entry["handled"] for entry in app.alert_log)
    assert all(entry["handled"] for entry in app.load_alert_log_archive(limit=5))
    client.disconnect()


def test_alert_notification_batch_resend_starts_each_success(monkeypatch):
    import app

    entries = {
        "batch-alert-1": {"id": "batch-alert-1", "title": "第一条警报"},
        "batch-alert-2": {"id": "batch-alert-2", "title": "第二条警报"},
    }
    deliveries = []
    monkeypatch.setattr(
        app,
        "resend_alert_notification",
        lambda alert_id, **kwargs: (
            (True, entries[alert_id])
            if alert_id in entries
            else (False, None)
        ),
    )
    monkeypatch.setattr(
        app,
        "_start_alert_notification_delivery",
        lambda entry, title: deliveries.append((entry["id"], title)),
    )

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("batch_resend_alert_notifications", {
        "ids": ["batch-alert-1", "missing-alert", "batch-alert-2"],
    })
    events = client.get_received()
    result = next(
        event["args"][0]
        for event in events
        if event["name"] == "alert_notification_batch_resent"
    )

    assert result["partial"] is True
    assert result["success_count"] == 2
    assert result["failure_count"] == 1
    assert [entry["id"] for entry in result["entries"]] == [
        "batch-alert-1",
        "batch-alert-2",
    ]
    assert deliveries == [
        ("batch-alert-1", "第一条警报"),
        ("batch-alert-2", "第二条警报"),
    ]
    client.disconnect()
