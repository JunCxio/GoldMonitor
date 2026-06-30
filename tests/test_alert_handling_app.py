import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_alert_log_handling_socket_event_updates_memory_and_archive(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "APPDATA_DIR", str(tmp_path))
    monkeypatch.setattr(app, "alert_log", [])
    entry = {
        "type": "warning",
        "mode": "rmb",
        "time": "12:00:00",
        "timestamp": "2026-06-30T12:00:00",
        "message": "测试处理提醒",
    }
    saved = app.save_alert_log_entry(entry)
    app.alert_log.append(saved)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("update_alert_log_handling", {
        "id": saved["id"],
        "handled": True,
        "note": "已完成分批卖出",
    })
    events = client.get_received()
    updated = next(event["args"][0] for event in events if event["name"] == "alert_log_handling_updated")

    assert updated["ok"] is True
    assert updated["entry"]["handled"] is True
    assert updated["entry"]["handling_note"] == "已完成分批卖出"
    assert updated["entry"]["handled_at"]
    assert app.alert_log[0]["handled"] is True
    assert app.load_alert_log_archive(limit=5)[-1]["handling_note"] == "已完成分批卖出"
    client.disconnect()
