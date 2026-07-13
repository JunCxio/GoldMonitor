import json
from datetime import datetime


def configure_review_notes_app(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "REVIEW_NOTES_PATH", str(tmp_path / "review_notes.json"))
    monkeypatch.setattr(app, "review_notes", [])
    return app


def test_app_persists_updates_and_deletes_review_notes(monkeypatch, tmp_path):
    app = configure_review_notes_app(monkeypatch, tmp_path)
    ids = iter(["note-app-1"])
    monkeypatch.setattr(app, "_generate_review_note_id", lambda: next(ids))

    state, note = app.upsert_review_note({
        "timestamp": "2026-07-13T10:00:00",
        "title": "观察预警结果",
        "content": "记录预警触发后的价格变化。",
        "related_event_id": "alert-1",
        "related_event_type": "alert",
        "related_event_title": "价格预警",
    })

    assert state["total"] == 1
    assert note["id"] == "note-app-1"
    persisted = json.loads((tmp_path / "review_notes.json").read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert persisted["items"][0]["related_event_id"] == "alert-1"

    updated_state, updated = app.upsert_review_note({
        "id": note["id"],
        "content": "预警触发后价格继续上涨。",
    })
    assert updated_state["total"] == 1
    assert updated["title"] == "观察预警结果"
    assert updated["content"] == "预警触发后价格继续上涨。"

    deleted, final_state = app.delete_review_note_by_id(note["id"])
    assert deleted is True
    assert final_state["total"] == 0
    assert json.loads((tmp_path / "review_notes.json").read_text(encoding="utf-8"))["items"] == []


def test_app_timeline_includes_review_notes(monkeypatch, tmp_path):
    app = configure_review_notes_app(monkeypatch, tmp_path)
    now = datetime.now().replace(microsecond=0)
    monkeypatch.setattr(app, "review_notes", [{
        "id": "note-app-timeline",
        "timestamp": now.isoformat(timespec="seconds"),
        "title": "时间轴笔记",
        "content": "核对当前行情与风险分析。",
        "related_event_id": "",
        "related_event_type": "",
        "related_event_title": "",
        "created_at": now.isoformat(timespec="seconds"),
        "updated_at": now.isoformat(timespec="seconds"),
    }])

    state = app.build_event_timeline_state(
        minutes=60,
        limit=20,
        types=["review_note"],
    )

    assert state["summary"]["by_type"]["review_note"] == 1
    assert state["events"][0]["payload"]["id"] == "note-app-timeline"


def test_app_keeps_memory_state_unchanged_when_review_note_save_fails(monkeypatch, tmp_path):
    app = configure_review_notes_app(monkeypatch, tmp_path)
    original = [{
        "id": "note-existing",
        "timestamp": "2026-07-13T09:00:00",
        "title": "已有笔记",
        "content": "原始内容",
        "related_event_id": "",
        "related_event_type": "",
        "related_event_title": "",
        "created_at": "2026-07-13T09:00:00",
        "updated_at": "2026-07-13T09:00:00",
    }]
    monkeypatch.setattr(app, "review_notes", [dict(original[0])])
    monkeypatch.setattr(app, "save_review_notes", lambda items=None: (_ for _ in ()).throw(OSError("只读")))

    try:
        app.upsert_review_note({
            "id": "note-existing",
            "content": "不应留在内存中的内容",
        })
    except OSError:
        pass
    else:
        raise AssertionError("保存失败时应抛出 OSError")

    assert app.review_notes == original


def test_review_note_socket_contract_saves_and_deletes(monkeypatch, tmp_path):
    app = configure_review_notes_app(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "_generate_review_note_id", lambda: "note-socket-1")
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("save_review_note", {
        "timestamp": "2026-07-13T11:00:00",
        "content": "通过 Socket.IO 保存复盘笔记。",
    })
    received = client.get_received()
    saved = next(item["args"][0] for item in received if item["name"] == "review_note_saved")
    updated = next(item["args"][0] for item in received if item["name"] == "review_notes_updated")
    assert saved["ok"] is True
    assert saved["note"]["id"] == "note-socket-1"
    assert updated["total"] == 1

    client.emit("delete_review_note", {"id": "note-socket-1"})
    received = client.get_received()
    deleted = next(item["args"][0] for item in received if item["name"] == "review_note_deleted")
    updated = next(item["args"][0] for item in received if item["name"] == "review_notes_updated")
    assert deleted == {
        "ok": True,
        "id": "note-socket-1",
        "state": updated,
    }
    assert updated["total"] == 0
