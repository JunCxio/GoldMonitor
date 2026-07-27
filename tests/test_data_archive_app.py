import io


def test_data_archive_paths_cover_all_restorable_state():
    import app

    paths = app._data_archive_paths()

    assert set(paths) == {
        "settings",
        "thresholds",
        "alert_profiles",
        "watch_targets",
        "portfolio_positions",
        "portfolio_transactions",
        "portfolio_import_backup",
        "portfolio_alerts",
        "market_cache",
        "source_metrics",
        "news",
        "risk_analysis_history",
        "review_notes",
        "price_history",
        "daily_digest_state",
        "price_history_db",
        "alert_log_db",
    }
    assert paths["settings"]["sensitive"] is True
    assert paths["price_history_db"]["kind"] == "sqlite"
    assert paths["alert_log_db"]["kind"] == "sqlite"


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
