import io
from datetime import datetime


def test_data_archive_paths_cover_all_restorable_state():
    import app

    paths = app._data_archive_paths()

    assert set(paths) == {
        "settings",
        "thresholds",
        "alert_rules",
        "alert_profiles",
        "watch_targets",
        "portfolio_positions",
        "portfolio_transactions",
        "portfolio_investment_plans",
        "portfolio_import_backup",
        "portfolio_alerts",
        "market_cache",
        "source_metrics",
        "news",
        "risk_analysis_history",
        "review_notes",
        "price_history",
        "daily_digest_state",
        "today_overview_state",
        "price_history_db",
        "alert_log_db",
    }
    assert paths["settings"]["sensitive"] is True
    assert paths["alert_rules"]["kind"] == "json"
    assert paths["price_history_db"]["kind"] == "sqlite"
    assert paths["alert_log_db"]["kind"] == "sqlite"


def test_data_archive_creation_coordinates_with_price_history_maintenance(
    monkeypatch,
    tmp_path,
):
    import app

    captured = {}

    def create_archive(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(app, "resolve_export_dir", lambda: str(tmp_path))
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {})
    monkeypatch.setattr(app, "_data_archive_manager", lambda now_factory=None: object())
    monkeypatch.setattr(
        app.operations_runtime_core,
        "create_data_archive",
        create_archive,
    )

    result = app.create_data_archive(datetime(2026, 8, 14, 12, 0))

    assert result == {"ok": True}
    assert captured["archive_lock"] is app.runtime.data_archive_lock
    assert captured["state_locks"] == (
        app.runtime.price_history_maintenance_lock,
    )


def test_data_archive_http_preview_and_restore_require_auth_and_one_time_token(monkeypatch, tmp_path):
    import app

    class FakeManager:
        def preview(self, path):
            assert path.endswith(".zip")
            return {
                "ok": True,
                "restorable": True,
                "files": 2,
                "bytes": 12,
                "items": [],
                "message": "归档校验通过",
            }

    restored = []
    emitted = []
    monkeypatch.setattr(app, "_data_archive_manager", lambda now_factory=None: FakeManager())
    monkeypatch.setattr(app, "restore_data_archive", lambda path: restored.append(path) or {
        "ok": True,
        "restored": 2,
        "message": "已恢复 2 项本地数据",
    })
    monkeypatch.setattr(app.socketio, "emit", lambda *args, **kwargs: emitted.append((args, kwargs)))
    monkeypatch.setattr(app, "data_archive_uploads", {})

    client = app.app.test_client()
    unauthorized = client.post(
        "/api/data-archive/preview",
        data={"archive": (io.BytesIO(b"archive"), "backup.zip")},
        content_type="multipart/form-data",
    )
    assert unauthorized.status_code == 403

    preview = client.post(
        "/api/data-archive/preview",
        data={"archive": (io.BytesIO(b"archive"), "backup.zip")},
        headers={"X-GoldMonitor-Token": app.SOCKET_ACCESS_TOKEN},
        content_type="multipart/form-data",
    )
    assert preview.status_code == 200
    preview_payload = preview.get_json()
    assert preview_payload["restore_token"]

    restore = client.post(
        "/api/data-archive/restore",
        json={"restore_token": preview_payload["restore_token"]},
        headers={"X-GoldMonitor-Token": app.SOCKET_ACCESS_TOKEN},
    )
    assert restore.status_code == 200
    assert restore.get_json()["restored"] == 2
    assert len(restored) == 1
    assert emitted[-1][0][0] == "data_archive_restored"

    repeated = client.post(
        "/api/data-archive/restore",
        json={"restore_token": preview_payload["restore_token"]},
        headers={"X-GoldMonitor-Token": app.SOCKET_ACCESS_TOKEN},
    )
    assert repeated.status_code == 400


def test_data_archive_http_errors_do_not_expose_exception_details(monkeypatch):
    import app

    secret_detail = "/private/user/path/archive.zip contains secret-token"

    class PreviewFailureManager:
        def preview(self, path):
            raise app.data_archive_core.DataArchiveError(secret_detail)

    monkeypatch.setattr(app, "_data_archive_manager", lambda now_factory=None: PreviewFailureManager())
    monkeypatch.setattr(app, "data_archive_uploads", {})
    client = app.app.test_client()
    headers = {"X-GoldMonitor-Token": app.SOCKET_ACCESS_TOKEN}

    failed_preview = client.post(
        "/api/data-archive/preview",
        data={"archive": (io.BytesIO(b"archive"), "backup.zip")},
        headers=headers,
        content_type="multipart/form-data",
    )

    assert failed_preview.status_code == 400
    preview_payload = failed_preview.get_json()
    assert preview_payload["message"] == "数据归档校验失败，请确认文件来自 GoldMonitor 且未损坏"
    assert secret_detail not in preview_payload["message"]

    class RestorableManager:
        def preview(self, path):
            return {
                "ok": True,
                "restorable": True,
                "files": 1,
                "bytes": 7,
                "items": [],
                "message": "归档校验通过",
            }

    monkeypatch.setattr(app, "_data_archive_manager", lambda now_factory=None: RestorableManager())

    def fail_restore(path):
        raise app.data_archive_core.DataArchiveError(secret_detail)

    monkeypatch.setattr(app, "restore_data_archive", fail_restore)
    preview = client.post(
        "/api/data-archive/preview",
        data={"archive": (io.BytesIO(b"archive"), "backup.zip")},
        headers=headers,
        content_type="multipart/form-data",
    )
    restore = client.post(
        "/api/data-archive/restore",
        json={"restore_token": preview.get_json()["restore_token"]},
        headers=headers,
    )

    assert restore.status_code == 400
    restore_payload = restore.get_json()
    assert restore_payload["message"] == "数据恢复失败，原数据已回滚。请检查归档文件后重试。"
    assert secret_detail not in restore_payload["message"]
