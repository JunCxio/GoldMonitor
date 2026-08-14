import json
from pathlib import Path


def find_event(events, name):
    return next(event["args"][0] for event in events if event["name"] == name)


def build_point(timestamp, usd=2300, rmb=540):
    return {
        "timestamp": timestamp,
        "time": timestamp[11:19],
        "usd": usd,
        "rmb": rmb,
        "rate": 7.2,
    }


def test_price_history_maintenance_socket_requires_preview_confirmation(monkeypatch, tmp_path):
    import app

    json_path = tmp_path / "price_history.json"
    monkeypatch.setattr(app, "PRICE_HISTORY_PATH", str(json_path))
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [
            build_point("2026-08-11T12:00:00"),
            build_point("2026-08-11T12:10:00", usd=2310, rmb=542),
        ],
    }), encoding="utf-8")
    monkeypatch.setattr(app.runtime, "price_archive", [])

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()

    client.emit("get_price_history_maintenance")
    diagnosis = find_event(
        client.get_received(),
        "price_history_maintenance_updated",
    )
    assert diagnosis["status"] == "attention"
    assert diagnosis["database"]["exists"] is False
    assert diagnosis["operations"]["sync_json_and_rebuild"]["available"] is False

    app._connect_price_history_db().close()
    client.emit("get_price_history_maintenance")
    diagnosis = find_event(
        client.get_received(),
        "price_history_maintenance_updated",
    )
    assert diagnosis["database"]["exists"] is True
    assert diagnosis["operations"]["sync_json_and_rebuild"]["available"] is True

    client.emit("preview_price_history_repair", {
        "action": "sync_json_and_rebuild",
    })
    preview = find_event(
        client.get_received(),
        "price_history_repair_previewed",
    )
    assert preview["executable"] is True
    assert preview["effects"]["json_points_to_add"] == 2
    assert preview["preview_token"]

    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": "invalid-preview-token",
    })
    rejected = find_event(
        client.get_received(),
        "price_history_maintenance_error",
    )
    assert "确认" in rejected["message"]
    assert app._load_price_history_from_db() == []

    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": preview["preview_token"],
    })
    events = client.get_received()
    completed = find_event(events, "price_history_repair_completed")
    updated = find_event(events, "price_history_maintenance_updated")

    assert completed["ok"] is True
    assert completed["inserted_points"] == 2
    assert updated["database"]["raw"]["valid"] == 2
    assert len(app.runtime.price_archive) == 2
    assert Path(app._price_history_db_path()).exists()
    client.disconnect()
