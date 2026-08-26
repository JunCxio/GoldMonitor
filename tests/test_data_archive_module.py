import json
import sqlite3
import zipfile
from datetime import datetime

import pytest


def _build_paths(tmp_path):
    return {
        "settings": {
            "path": str(tmp_path / "settings.json"),
            "kind": "json",
            "label": "通用设置",
            "sensitive": True,
        },
        "watch_targets": {
            "path": str(tmp_path / "watch_targets.json"),
            "kind": "json",
            "label": "目标价观察清单",
        },
        "price_history_db": {
            "path": str(tmp_path / "price_history.sqlite3"),
            "kind": "sqlite",
            "label": "价格历史数据库",
        },
    }


def _create_sqlite(path, value):
    connection = sqlite3.connect(path)
    with connection:
        connection.execute("CREATE TABLE IF NOT EXISTS samples(value TEXT)")
        connection.execute("DELETE FROM samples")
        connection.execute("INSERT INTO samples(value) VALUES(?)", (value,))
    connection.close()


def _sqlite_value(path):
    connection = sqlite3.connect(path)
    try:
        return connection.execute("SELECT value FROM samples").fetchone()[0]
    finally:
        connection.close()


def test_full_archive_roundtrip_preserves_json_sqlite_and_sensitive_override(tmp_path):
    from goldmonitor.data_archive import DataArchiveManager

    paths = _build_paths(tmp_path)
    (tmp_path / "settings.json").write_text('{"smtp_password":"file-value"}', encoding="utf-8")
    (tmp_path / "watch_targets.json").write_text('{"schema_version":1,"items":[{"id":"old"}]}', encoding="utf-8")
    _create_sqlite(tmp_path / "price_history.sqlite3", "old-db")
    archive_path = tmp_path / "backup.zip"
    manager = DataArchiveManager(
        paths,
        app_version="1.0.6",
        now_factory=lambda: datetime(2026, 7, 27, 12, 0),
    )

    created = manager.create(
        archive_path,
        content_overrides={"settings": json.dumps({"smtp_password": "secret-value"}).encode("utf-8")},
    )
    preview = manager.preview(archive_path)

    assert created["files"] == 3
    assert created["contains_sensitive_data"] is True
    assert preview["restorable"] is True
    assert preview["source_app_version"] == "1.0.6"
    assert preview["files"] == 3

    (tmp_path / "settings.json").write_text('{"smtp_password":"changed"}', encoding="utf-8")
    (tmp_path / "watch_targets.json").write_text('{"schema_version":1,"items":[]}', encoding="utf-8")
    _create_sqlite(tmp_path / "price_history.sqlite3", "changed-db")

    restored = manager.restore(archive_path)

    assert restored["restored"] == 3
    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["smtp_password"] == "secret-value"
    assert json.loads((tmp_path / "watch_targets.json").read_text(encoding="utf-8"))["items"][0]["id"] == "old"
    assert _sqlite_value(tmp_path / "price_history.sqlite3") == "old-db"


def test_restore_reproduces_missing_files_and_rolls_back_when_apply_fails(tmp_path):
    from goldmonitor.data_archive import DataArchiveManager

    paths = _build_paths(tmp_path)
    (tmp_path / "settings.json").write_text('{"name":"archived"}', encoding="utf-8")
    _create_sqlite(tmp_path / "price_history.sqlite3", "archived-db")
    archive_path = tmp_path / "backup.zip"
    manager = DataArchiveManager(paths, app_version="1.0.6")
    manager.create(archive_path)

    (tmp_path / "settings.json").write_text('{"name":"current"}', encoding="utf-8")
    (tmp_path / "watch_targets.json").write_text('{"items":[{"id":"current"}]}', encoding="utf-8")
    _create_sqlite(tmp_path / "price_history.sqlite3", "current-db")
    rollback_called = []

    with pytest.raises(RuntimeError, match="reload failed"):
        manager.restore(
            archive_path,
            apply_callback=lambda manifest, preview: (_ for _ in ()).throw(RuntimeError("reload failed")),
            rollback_callback=lambda: rollback_called.append(True),
        )

    assert json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))["name"] == "current"
    assert json.loads((tmp_path / "watch_targets.json").read_text(encoding="utf-8"))["items"][0]["id"] == "current"
    assert _sqlite_value(tmp_path / "price_history.sqlite3") == "current-db"
    assert rollback_called == [True]

    manager.restore(archive_path)
    assert not (tmp_path / "watch_targets.json").exists()


def test_archive_preview_rejects_modified_payload_and_future_version(tmp_path):
    from goldmonitor.data_archive import DataArchiveError, DataArchiveManager

    paths = _build_paths(tmp_path)
    (tmp_path / "settings.json").write_text('{"name":"archived"}', encoding="utf-8")
    archive_path = tmp_path / "backup.zip"
    manager = DataArchiveManager(paths, app_version="1.0.6")
    manager.create(archive_path)

    modified_path = tmp_path / "modified.zip"
    with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(modified_path, "w") as destination:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename.startswith("data/settings/"):
                content = b'{"name":"modified"}'
            destination.writestr(item.filename, content)

    with pytest.raises(DataArchiveError, match="校验失败"):
        manager.preview(modified_path)

    future_path = tmp_path / "future.zip"
    with zipfile.ZipFile(archive_path, "r") as source, zipfile.ZipFile(future_path, "w") as destination:
        for item in source.infolist():
            content = source.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(content.decode("utf-8"))
                manifest["schema_version"] = 99
                content = json.dumps(manifest).encode("utf-8")
            destination.writestr(item.filename, content)

    with pytest.raises(DataArchiveError, match="高于当前支持版本"):
        manager.preview(future_path)


def test_archive_accepts_older_manifest_without_optional_quality_state(tmp_path):
    from goldmonitor.data_archive import DataArchiveManager

    settings_path = tmp_path / "settings.json"
    quality_path = tmp_path / "market_quality_history.json"
    quality_alert_path = tmp_path / "market_quality_alert_state.json"
    settings_path.write_text('{"theme":"dark"}', encoding="utf-8")
    legacy_manager = DataArchiveManager(
        {
            "settings": {
                "path": settings_path,
                "kind": "json",
                "label": "通用设置",
            },
        },
        app_version="1.0.22",
    )
    archive_path = tmp_path / "legacy.zip"
    legacy_manager.create(archive_path)
    quality_path.write_text(
        '{"schema_version":1,"items":[{"id":"current"}]}',
        encoding="utf-8",
    )
    quality_alert_path.write_text(
        '{"schema_version":1,"state":{"incident_active":true}}',
        encoding="utf-8",
    )
    manager = DataArchiveManager(
        {
            "settings": {
                "path": settings_path,
                "kind": "json",
                "label": "通用设置",
            },
            "market_quality_history": {
                "path": quality_path,
                "kind": "json",
                "label": "行情质量历史",
                "required": False,
            },
            "market_quality_alert_state": {
                "path": quality_alert_path,
                "kind": "json",
                "label": "行情质量通知状态",
                "required": False,
            },
        },
        app_version="1.0.23",
    )

    preview = manager.preview(archive_path)
    manager.restore(archive_path)

    assert preview["files"] == 1
    assert not quality_path.exists()
    assert not quality_alert_path.exists()
