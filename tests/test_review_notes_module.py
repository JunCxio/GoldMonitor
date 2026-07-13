import json
from datetime import datetime
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 7, 13, 21, 30, 0)


def test_normalize_review_note_generates_title_and_limits_fields():
    from goldmonitor.review_notes import (
        REVIEW_NOTE_CONTENT_LIMIT,
        REVIEW_NOTE_RELATED_EVENT_ID_LIMIT,
        REVIEW_NOTE_RELATED_EVENT_TITLE_LIMIT,
        REVIEW_NOTE_RELATED_EVENT_TYPE_LIMIT,
        REVIEW_NOTE_TITLE_LIMIT,
        normalize_review_note,
    )

    note = normalize_review_note(
        {
            "content": "  今日复盘第一行\n" + "内容" * 1200,
            "related_event_id": "e" * 300,
            "related_event_type": "alert" * 20,
            "related_event_title": "金价预警" * 40,
        },
        now_factory=fixed_now,
        id_factory=lambda: "note-fixed",
    )

    assert note["id"] == "note-fixed"
    assert note["timestamp"] == "2026-07-13T21:30:00"
    assert note["title"] == "今日复盘第一行"
    assert len(note["title"]) <= REVIEW_NOTE_TITLE_LIMIT
    assert len(note["content"]) == REVIEW_NOTE_CONTENT_LIMIT
    assert len(note["related_event_id"]) == REVIEW_NOTE_RELATED_EVENT_ID_LIMIT
    assert len(note["related_event_type"]) == REVIEW_NOTE_RELATED_EVENT_TYPE_LIMIT
    assert len(note["related_event_title"]) == REVIEW_NOTE_RELATED_EVENT_TITLE_LIMIT
    assert note["created_at"] == "2026-07-13T21:30:00"
    assert note["updated_at"] == "2026-07-13T21:30:00"


def test_normalize_review_note_updates_existing_and_rejects_invalid_input():
    from goldmonitor.review_notes import normalize_review_note

    original = normalize_review_note(
        {
            "timestamp": "2026-07-12T20:00:00",
            "title": "原始标题",
            "content": "原始内容",
            "related_event_id": "alert-1",
        },
        now_factory=lambda: datetime(2026, 7, 12, 20, 5),
        id_factory=lambda: "note-fixed",
    )
    updated = normalize_review_note(
        {"id": "note-fixed", "content": "更新后的内容"},
        existing=original,
        now_factory=fixed_now,
    )

    assert updated["timestamp"] == "2026-07-12T20:00:00"
    assert updated["title"] == "原始标题"
    assert updated["related_event_id"] == "alert-1"
    assert updated["created_at"] == "2026-07-12T20:05:00"
    assert updated["updated_at"] == "2026-07-13T21:30:00"

    with pytest.raises(ValueError, match="复盘内容不能为空"):
        normalize_review_note({"content": "  "}, now_factory=fixed_now)
    with pytest.raises(ValueError, match="复盘时间格式无效"):
        normalize_review_note({"content": "有效内容", "timestamp": "bad"}, now_factory=fixed_now)
    with pytest.raises(ValueError, match="复盘笔记 ID 格式无效"):
        normalize_review_note({"id": "unsafe/id", "content": "有效内容"}, now_factory=fixed_now)


def test_normalize_review_notes_skips_invalid_duplicates_and_applies_limit():
    from goldmonitor.review_notes import (
        delete_review_note,
        normalize_review_notes,
        review_notes_state,
        upsert_review_note,
    )

    items = [
        {"id": "note-one", "content": "第一条"},
        {"id": "note-one", "content": "重复条目"},
        {"id": "bad/id", "content": "非法 ID"},
        {"id": "note-empty", "content": ""},
        {"id": "note-two", "content": "第二条"},
        {"id": "note-three", "content": "第三条"},
    ]
    normalized = normalize_review_notes(items, now_factory=fixed_now, limit=2)

    assert [item["id"] for item in normalized] == ["note-one", "note-two"]
    assert review_notes_state(normalized, limit=2) == {
        "items": normalized,
        "total": 2,
        "limit": 2,
        "remaining": 0,
    }
    assert normalize_review_notes(items, now_factory=fixed_now, limit=0) == []

    updated_items, updated = upsert_review_note(
        normalized,
        {"id": "note-one", "content": "更新第一条"},
        now_factory=lambda: datetime(2026, 7, 13, 22, 0),
        limit=2,
    )
    assert updated["content"] == "更新第一条"
    assert updated_items[0] == updated
    remaining, deleted = delete_review_note(updated_items, "note-two")
    assert deleted is True
    assert [item["id"] for item in remaining] == ["note-one"]
    unchanged, deleted = delete_review_note(remaining, "note-missing")
    assert deleted is False
    assert unchanged == remaining


def test_review_note_store_writes_versioned_payload_and_supports_crud(tmp_path):
    from goldmonitor.review_notes import ReviewNoteStore

    path = tmp_path / "review_notes.json"
    current = {"value": datetime(2026, 7, 13, 20, 0)}
    identifiers = iter(["note-one", "note-two"])
    store = ReviewNoteStore(
        str(path),
        limit=2,
        now_factory=lambda: current["value"],
        id_factory=lambda: next(identifiers),
    )

    assert store.load() == []
    first = store.upsert({"content": "第一条复盘"})
    current["value"] = datetime(2026, 7, 13, 20, 10)
    second = store.upsert(
        {
            "content": "第二条复盘",
            "related_event_id": "alert-2",
            "related_event_type": "alert",
            "related_event_title": "关键预警",
        }
    )
    current["value"] = datetime(2026, 7, 13, 20, 20)
    edited = store.upsert({"id": first["id"], "title": "更新标题", "content": "更新内容"})

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert [item["id"] for item in payload["items"]] == [second["id"], first["id"]]
    assert edited["created_at"] == "2026-07-13T20:00:00"
    assert edited["updated_at"] == "2026-07-13T20:20:00"
    assert store.state()["total"] == 2
    assert store.state()["remaining"] == 0
    assert not Path(str(path) + ".tmp").exists()

    with pytest.raises(ValueError, match="数量已达到上限"):
        store.upsert({"content": "第三条复盘"})

    deleted = store.delete(second["id"])
    assert deleted["id"] == second["id"]
    assert [item["id"] for item in store.load()] == [first["id"]]
    with pytest.raises(ValueError, match="未找到复盘笔记"):
        store.delete("note-missing")
    with pytest.raises(ValueError, match="ID 不能为空"):
        store.delete("")


def test_review_note_store_loads_legacy_items_and_ignores_invalid_files(tmp_path):
    from goldmonitor.review_notes import ReviewNoteStore

    path = tmp_path / "review_notes.json"
    store = ReviewNoteStore(str(path), now_factory=fixed_now)
    path.write_text(
        json.dumps(
            [
                {"id": "note-legacy", "content": "旧格式笔记"},
                {"id": "note-invalid", "content": ""},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0]["id"] == "note-legacy"

    path.write_text("{invalid", encoding="utf-8")
    assert store.load() == []


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            if "tmp_path" in value.__code__.co_varnames:
                continue
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("review notes module checks passed.")
