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

    rechecked_tasks = []
    background_status = {
        "summary": {"total": 1, "error": 0, "attention": 0},
        "tasks": [{
            "name": "price_history_health",
            "state": "ok",
            "attention_required": False,
        }],
    }
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
    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda name: (
            rechecked_tasks.append(name)
            or {"ran": True, "task": background_status["tasks"][0]}
        ),
    )
    monkeypatch.setattr(
        app,
        "get_background_task_status",
        lambda: background_status,
    )

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
    assert rechecked_tasks == []

    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": preview["preview_token"],
    })
    events = client.get_received()
    completed = find_event(events, "price_history_repair_completed")
    updated = find_event(events, "price_history_maintenance_updated")
    task_status = find_event(events, "background_task_status")

    assert completed["ok"] is True
    assert completed["inserted_points"] == 2
    assert completed["background_task_recheck"]["ran"] is True
    assert "自动复检" in completed["message"]
    assert updated["database"]["raw"]["valid"] == 2
    assert task_status == background_status
    assert rechecked_tasks == ["price_history_health"]
    assert len(app.runtime.price_archive) == 2
    assert Path(app._price_history_db_path()).exists()
    client.disconnect()


def test_price_history_repair_completion_survives_background_recheck_failure(
    monkeypatch,
    tmp_path,
):
    import app

    json_path = tmp_path / "price_history.json"
    monkeypatch.setattr(app, "PRICE_HISTORY_PATH", str(json_path))
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [build_point("2026-08-11T12:00:00")],
    }), encoding="utf-8")
    monkeypatch.setattr(app.runtime, "price_archive", [])
    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda _name: (_ for _ in ()).throw(RuntimeError("recheck failed")),
    )
    monkeypatch.setattr(
        app,
        "get_background_task_status",
        lambda: {"summary": {}, "tasks": []},
    )
    app._connect_price_history_db().close()

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("preview_price_history_repair", {
        "action": "sync_json_and_rebuild",
    })
    preview = find_event(
        client.get_received(),
        "price_history_repair_previewed",
    )

    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": preview["preview_token"],
    })
    events = client.get_received()
    completed = find_event(events, "price_history_repair_completed")

    assert completed["ok"] is True
    assert completed["background_task_recheck"] == {
        "ran": False,
        "reason": "error",
        "message": "历史数据后台状态复检失败",
    }
    assert not any(
        event["name"] == "price_history_maintenance_error"
        for event in events
    )
    client.disconnect()


def test_price_history_repair_rejects_stale_effects_and_accepts_new_preview(
    monkeypatch,
    tmp_path,
):
    import app

    json_path = tmp_path / "price_history.json"
    monkeypatch.setattr(app, "PRICE_HISTORY_PATH", str(json_path))
    monkeypatch.setattr(app.runtime, "price_archive", [])
    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda _name: {"ran": False, "reason": "not_due"},
    )
    monkeypatch.setattr(
        app,
        "get_background_task_status",
        lambda: {"summary": {}, "tasks": []},
    )
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [build_point("2026-08-11T12:00:00")],
    }), encoding="utf-8")
    app._connect_price_history_db().close()

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("preview_price_history_repair", {
        "action": "sync_json_and_rebuild",
    })
    stale_preview = find_event(
        client.get_received(),
        "price_history_repair_previewed",
    )

    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [
            build_point("2026-08-11T12:00:00"),
            build_point("2026-08-11T12:10:00", usd=2310, rmb=542),
        ],
    }), encoding="utf-8")
    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": stale_preview["preview_token"],
    })
    rejected = find_event(
        client.get_received(),
        "price_history_maintenance_error",
    )

    assert "影响范围已变化" in rejected["message"]
    assert app._load_price_history_from_db() == []
    assert app.runtime.price_archive == []

    client.emit("preview_price_history_repair", {
        "action": "sync_json_and_rebuild",
    })
    current_preview = find_event(
        client.get_received(),
        "price_history_repair_previewed",
    )
    assert current_preview["effects"]["json_points_to_add"] == 2

    client.emit("execute_price_history_repair", {
        "action": "sync_json_and_rebuild",
        "confirmed": True,
        "preview_token": current_preview["preview_token"],
    })
    completed = find_event(
        client.get_received(),
        "price_history_repair_completed",
    )

    assert completed["ok"] is True
    assert completed["inserted_points"] == 2
    assert len(app.runtime.price_archive) == 2
    client.disconnect()
