import json
import os
import secrets
from datetime import datetime

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


REVIEW_NOTE_SCHEMA_VERSION = 1
REVIEW_NOTE_LIMIT = 500
REVIEW_NOTE_TITLE_LIMIT = 80
REVIEW_NOTE_CONTENT_LIMIT = 2000
REVIEW_NOTE_RELATED_EVENT_ID_LIMIT = 160
REVIEW_NOTE_RELATED_EVENT_TYPE_LIMIT = 40
REVIEW_NOTE_RELATED_EVENT_TITLE_LIMIT = 120
REVIEW_NOTE_ID_PREFIX = "note-"


def generate_review_note_id():
    return REVIEW_NOTE_ID_PREFIX + secrets.token_hex(10)


def _now_iso(now_factory):
    return now_factory().isoformat(timespec="seconds")


def _normalize_text(value, limit):
    text = str(value or "").strip()
    return text[:limit]


def _valid_note_id(value):
    return (
        isinstance(value, str)
        and value.startswith(REVIEW_NOTE_ID_PREFIX)
        and len(value) > len(REVIEW_NOTE_ID_PREFIX)
        and all(
            character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in value
        )
    )


def _new_note_id(id_factory):
    note_id = str(id_factory() or "").strip() if callable(id_factory) else ""
    if not _valid_note_id(note_id):
        raise ValueError("复盘笔记 ID 生成失败")
    return note_id


def _normalize_iso_datetime(value, field_label, fallback):
    text = str(value or fallback or "").strip()
    if not text:
        raise ValueError(f"{field_label}不能为空")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise ValueError(f"{field_label}格式无效") from None
    return parsed.isoformat(timespec="seconds")


def _title_from_content(content):
    for line in str(content or "").splitlines():
        title = line.strip()
        if title:
            return title[:REVIEW_NOTE_TITLE_LIMIT]
    return ""


def normalize_review_note(item, existing=None, now_factory=None, id_factory=None):
    if not isinstance(item, dict):
        raise ValueError("复盘笔记格式无效")

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_review_note_id
    now = _now_iso(now_factory)

    raw_id = item.get("id") if "id" in item else existing.get("id")
    note_id = str(raw_id or "").strip()
    if note_id and not _valid_note_id(note_id):
        raise ValueError("复盘笔记 ID 格式无效")
    if not note_id:
        note_id = _new_note_id(id_factory)

    raw_content = item.get("content") if "content" in item else existing.get("content")
    content = _normalize_text(raw_content, REVIEW_NOTE_CONTENT_LIMIT)
    if not content:
        raise ValueError("复盘内容不能为空")

    raw_title = item.get("title") if "title" in item else existing.get("title")
    title = _normalize_text(raw_title, REVIEW_NOTE_TITLE_LIMIT) or _title_from_content(content)

    timestamp_value = item.get("timestamp") if "timestamp" in item else existing.get("timestamp")
    timestamp = _normalize_iso_datetime(timestamp_value, "复盘时间", now)

    created_value = existing.get("created_at") or item.get("created_at")
    created_at = _normalize_iso_datetime(created_value, "创建时间", now)
    if existing:
        updated_at = now
    else:
        updated_at = _normalize_iso_datetime(item.get("updated_at"), "更新时间", now)

    return {
        "id": note_id,
        "timestamp": timestamp,
        "title": title,
        "content": content,
        "related_event_id": _normalize_text(
            item.get("related_event_id", existing.get("related_event_id", "")),
            REVIEW_NOTE_RELATED_EVENT_ID_LIMIT,
        ),
        "related_event_type": _normalize_text(
            item.get("related_event_type", existing.get("related_event_type", "")),
            REVIEW_NOTE_RELATED_EVENT_TYPE_LIMIT,
        ),
        "related_event_title": _normalize_text(
            item.get("related_event_title", existing.get("related_event_title", "")),
            REVIEW_NOTE_RELATED_EVENT_TITLE_LIMIT,
        ),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def normalize_review_notes(items, now_factory=None, id_factory=None, limit=REVIEW_NOTE_LIMIT):
    if not isinstance(items, list):
        return []

    try:
        item_limit = max(0, int(limit))
    except (TypeError, ValueError):
        item_limit = REVIEW_NOTE_LIMIT
    if item_limit == 0:
        return []

    normalized = []
    seen = set()
    for item in items:
        try:
            note = normalize_review_note(
                item,
                now_factory=now_factory,
                id_factory=id_factory,
            )
        except ValueError:
            continue
        if note["id"] in seen:
            continue
        seen.add(note["id"])
        normalized.append(note)
        if len(normalized) >= item_limit:
            break
    return normalized


def review_notes_state(items, limit=REVIEW_NOTE_LIMIT):
    notes = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    try:
        item_limit = max(0, int(limit))
    except (TypeError, ValueError):
        item_limit = REVIEW_NOTE_LIMIT
    return {
        "items": notes,
        "total": len(notes),
        "limit": item_limit,
        "remaining": max(0, item_limit - len(notes)),
    }


def upsert_review_note(
    items,
    data,
    now_factory=None,
    id_factory=None,
    limit=REVIEW_NOTE_LIMIT,
):
    if not isinstance(data, dict):
        raise ValueError("复盘笔记格式无效")

    try:
        item_limit = max(0, int(limit))
    except (TypeError, ValueError):
        item_limit = REVIEW_NOTE_LIMIT
    normalized = normalize_review_notes(
        items,
        now_factory=now_factory,
        id_factory=id_factory,
        limit=item_limit,
    )

    raw_id = str(data.get("id") or "").strip()
    if raw_id and not _valid_note_id(raw_id):
        raise ValueError("复盘笔记 ID 格式无效")

    existing_index = -1
    for index, note in enumerate(normalized):
        if raw_id and note.get("id") == raw_id:
            existing_index = index
            break

    if existing_index < 0 and len(normalized) >= item_limit:
        raise ValueError("复盘笔记数量已达到上限")

    existing = normalized[existing_index] if existing_index >= 0 else None
    note = normalize_review_note(
        data,
        existing=existing,
        now_factory=now_factory,
        id_factory=id_factory,
    )
    if existing_index >= 0:
        normalized[existing_index] = note
    else:
        normalized.insert(0, note)
    return normalized, note


def delete_review_note(items, note_id):
    note_id = str(note_id or "").strip()
    if not note_id:
        raise ValueError("复盘笔记 ID 不能为空")

    normalized = [dict(item) for item in list(items or []) if isinstance(item, dict)]
    next_items = [item for item in normalized if item.get("id") != note_id]
    return next_items, len(next_items) != len(normalized)


class ReviewNoteStore:
    def __init__(self, json_path, limit=REVIEW_NOTE_LIMIT, now_factory=None, id_factory=None):
        self.json_path = json_path
        self.limit = max(0, int(limit))
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_review_note_id

    def normalize(self, items):
        return normalize_review_notes(
            items,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
            limit=self.limit,
        )

    def load(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, items):
        normalized = self.normalize(items)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        payload = wrap_item_payload(
            normalized,
            schema_version=REVIEW_NOTE_SCHEMA_VERSION,
        )
        temporary_path = self.json_path + ".tmp"
        with open(temporary_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
        os.replace(temporary_path, self.json_path)
        return normalized

    def upsert(self, item):
        items = self.load()
        next_items, note = upsert_review_note(
            items,
            item,
            now_factory=self.now_factory,
            id_factory=self.id_factory,
            limit=self.limit,
        )
        self.save(next_items)
        return note

    def delete(self, note_id):
        note_id = str(note_id or "").strip()
        if not note_id:
            raise ValueError("复盘笔记 ID 不能为空")

        items = self.load()
        deleted = next((note for note in items if note.get("id") == note_id), None)
        next_items, deleted_ok = delete_review_note(items, note_id)
        if not deleted_ok:
            raise ValueError("未找到复盘笔记")
        self.save(next_items)
        return deleted

    def state(self):
        return review_notes_state(self.load(), limit=self.limit)
