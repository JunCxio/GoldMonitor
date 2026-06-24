from datetime import datetime


CURRENT_SCHEMA_VERSION = 1
SCHEMA_VERSION_KEY = "schema_version"
ITEMS_KEY = "items"
UPDATED_AT_KEY = "updated_at"


def _now_iso():
    return datetime.now().isoformat(timespec="seconds")


def wrap_item_payload(items, updated_at=None, schema_version=CURRENT_SCHEMA_VERSION, **extra):
    payload = {
        SCHEMA_VERSION_KEY: int(schema_version),
        UPDATED_AT_KEY: updated_at or _now_iso(),
        ITEMS_KEY: list(items) if isinstance(items, list) else [],
    }
    payload.update(extra)
    return payload


def unwrap_item_payload(payload):
    if isinstance(payload, dict):
        items = payload.get(ITEMS_KEY, [])
        return list(items) if isinstance(items, list) else []
    if isinstance(payload, list):
        return list(payload)
    return []


def item_payload_metadata(payload, expected_version=CURRENT_SCHEMA_VERSION):
    if isinstance(payload, dict):
        raw_version = payload.get(SCHEMA_VERSION_KEY, 0)
        try:
            version = int(raw_version)
        except (TypeError, ValueError):
            version = 0
        if version > 0:
            payload_format = "versioned_dict"
        else:
            payload_format = "legacy_dict"
        return {
            "schema_version": version,
            "expected_schema_version": int(expected_version),
            "format": payload_format,
            "needs_migration": version != int(expected_version),
        }
    if isinstance(payload, list):
        return {
            "schema_version": 0,
            "expected_schema_version": int(expected_version),
            "format": "legacy_list",
            "needs_migration": True,
        }
    return {
        "schema_version": 0,
        "expected_schema_version": int(expected_version),
        "format": "invalid",
        "needs_migration": True,
    }

