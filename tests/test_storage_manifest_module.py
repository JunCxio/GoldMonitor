import tempfile
from pathlib import Path


def test_storage_manifest_covers_current_persistent_paths():
    from goldmonitor.storage_manifest import build_storage_manifest

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        paths = {
            "appdata": str(tmp),
            "settings": str(tmp / "settings.json"),
            "thresholds": str(tmp / "thresholds.json"),
            "watch_targets": str(tmp / "watch_targets.json"),
            "portfolio_positions": str(tmp / "portfolio_positions.json"),
            "portfolio_transactions": str(tmp / "portfolio_transactions.json"),
            "portfolio_import_backup": str(tmp / "portfolio_import_backup.json"),
            "portfolio_alerts": str(tmp / "portfolio_alerts.json"),
            "market_cache": str(tmp / "market_cache.json"),
            "source_metrics": str(tmp / "source_metrics.json"),
            "update_dir": str(tmp / "updates"),
            "exports": str(tmp / "exports"),
            "news": str(tmp / "news.json"),
            "risk_analysis_history": str(tmp / "risk_analysis_history.json"),
            "review_notes": str(tmp / "review_notes.json"),
            "price_history": str(tmp / "price_history.json"),
            "daily_digest_state": str(tmp / "daily_digest_state.json"),
            "price_history_db": str(tmp / "price_history.sqlite3"),
            "alert_log_db": str(tmp / "alert_log.sqlite3"),
            "log": str(tmp / "GoldMonitor.log"),
        }

        manifest = build_storage_manifest(paths)

    assert set(manifest) == set(paths)
    assert manifest["appdata"]["kind"] == "directory"
    assert manifest["settings"]["kind"] == "json"
    assert manifest["watch_targets"]["schema"] == "item_payload"
    assert manifest["watch_targets"]["expected_schema_version"] == 1
    assert manifest["portfolio_transactions"]["schema"] == "item_payload"
    assert manifest["review_notes"]["schema"] == "item_payload"
    assert manifest["review_notes"]["expected_schema_version"] == 1
    assert manifest["daily_digest_state"]["schema"] == "versioned_object"
    assert manifest["daily_digest_state"]["expected_schema_version"] == 1
    assert manifest["daily_digest_state"]["format"] == "missing"
    assert manifest["source_metrics"]["schema"] == "versioned_object"
    assert manifest["source_metrics"]["expected_schema_version"] == 1
    assert manifest["price_history_db"]["kind"] == "sqlite"
    assert manifest["alert_log_db"]["kind"] == "sqlite"
    assert manifest["exports"]["kind"] == "directory"


def test_storage_manifest_marks_json_payload_metadata_and_missing_sqlite():
    from goldmonitor.data_contracts import wrap_item_payload
    from goldmonitor.storage_manifest import build_storage_manifest

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        watch_targets_path = tmp / "watch_targets.json"
        watch_targets_path.write_text(
            '{"schema_version":1,"items":[{"id":"target-1"}]}',
            encoding="utf-8",
        )
        risk_history_path = tmp / "risk_analysis_history.json"
        risk_history_path.write_text(
            __import__("json").dumps(wrap_item_payload([{"id": "risk-1"}]), ensure_ascii=False),
            encoding="utf-8",
        )

        manifest = build_storage_manifest(
            {
                "watch_targets": str(watch_targets_path),
                "risk_analysis_history": str(risk_history_path),
                "price_history_db": str(tmp / "price_history.sqlite3"),
            }
        )

    assert manifest["watch_targets"]["exists"] is True
    assert manifest["watch_targets"]["format"] == "versioned_dict"
    assert manifest["watch_targets"]["needs_migration"] is False
    assert manifest["risk_analysis_history"]["schema_version"] == 1
    assert manifest["price_history_db"]["exists"] is False
    assert manifest["price_history_db"]["format"] == "sqlite"


def test_storage_manifest_reports_versioned_object_metadata():
    from goldmonitor.storage_manifest import build_storage_manifest

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        state_path = tmp / "daily_digest_state.json"
        state_path.write_text(
            '{"schema_version":1,"last_status":"sent"}',
            encoding="utf-8",
        )

        manifest = build_storage_manifest({"daily_digest_state": str(state_path)})

        assert manifest["daily_digest_state"] == {
            "key": "daily_digest_state",
            "label": "每日摘要状态",
            "path": str(state_path),
            "kind": "json",
            "schema": "versioned_object",
            "exists": True,
            "schema_version": 1,
            "expected_schema_version": 1,
            "format": "versioned_dict",
            "needs_migration": False,
        }

        state_path.write_text("[]", encoding="utf-8")
        invalid = build_storage_manifest({"daily_digest_state": str(state_path)})

    assert invalid["daily_digest_state"]["exists"] is True
    assert invalid["daily_digest_state"]["format"] == "invalid"
    assert invalid["daily_digest_state"]["needs_migration"] is True


def test_diagnostics_summary_uses_storage_manifest_when_provided():
    from goldmonitor.diagnostics import build_health_summary

    summary = build_health_summary(
        fetch_status={"ok": True},
        source_health={"summary": {"failed": 0, "cached": 0}},
        price_history={"total": 1},
        watch_targets={"total": 0},
        risk_history_count=0,
        recent_alerts=[],
        paths={"settings": "/tmp/settings.json"},
        storage_manifest={
            "settings": {
                "path": "/tmp/settings.json",
                "kind": "json",
                "schema": "plain_json",
                "exists": False,
            }
        },
    )

    assert summary["storage"]["settings"] == {
        "path": "/tmp/settings.json",
        "kind": "json",
        "schema": "plain_json",
        "exists": False,
    }


def test_app_diagnostics_report_includes_complete_storage_manifest(monkeypatch, tmp_path):
    import json
    import app

    path_keys = {
        "APPDATA_DIR": tmp_path,
        "SETTINGS_PATH": tmp_path / "settings.json",
        "THRESHOLDS_PATH": tmp_path / "thresholds.json",
        "WATCH_TARGETS_PATH": tmp_path / "watch_targets.json",
        "PORTFOLIO_POSITIONS_PATH": tmp_path / "portfolio_positions.json",
        "PORTFOLIO_TRANSACTIONS_PATH": tmp_path / "portfolio_transactions.json",
        "PORTFOLIO_IMPORT_BACKUP_PATH": tmp_path / "portfolio_import_backup.json",
        "PORTFOLIO_ALERTS_PATH": tmp_path / "portfolio_alerts.json",
        "MARKET_CACHE_PATH": tmp_path / "market_cache.json",
        "SOURCE_METRICS_PATH": tmp_path / "source_metrics.json",
        "UPDATE_DIR": tmp_path / "updates",
        "EXPORT_DIR": tmp_path / "exports",
        "NEWS_CACHE_PATH": tmp_path / "news.json",
        "RISK_ANALYSIS_HISTORY_PATH": tmp_path / "risk_analysis_history.json",
        "REVIEW_NOTES_PATH": tmp_path / "review_notes.json",
        "PRICE_HISTORY_PATH": tmp_path / "price_history.json",
        "DAILY_DIGEST_STATE_PATH": tmp_path / "daily_digest_state.json",
        "APP_LOG_PATH": tmp_path / "GoldMonitor.log",
    }
    for name, value in path_keys.items():
        monkeypatch.setattr(app, name, str(value))

    report = json.loads(app.build_diagnostics_report())

    for key in {
        "settings",
        "thresholds",
        "watch_targets",
        "portfolio_positions",
        "portfolio_transactions",
        "portfolio_alerts",
        "source_metrics",
        "news",
        "risk_analysis_history",
        "review_notes",
        "price_history",
        "daily_digest_state",
        "price_history_db",
        "alert_log_db",
    }:
        assert key in report["paths"]
        assert key in report["storage_manifest"]
        assert key in report["health_summary"]["storage"]

    assert report["storage_manifest"]["portfolio_transactions"]["schema"] == "item_payload"
    assert report["storage_manifest"]["review_notes"]["schema"] == "item_payload"
    assert report["storage_manifest"]["daily_digest_state"]["schema"] == "versioned_object"
    assert report["storage_manifest"]["daily_digest_state"]["expected_schema_version"] == 1
    assert report["storage_manifest"]["source_metrics"]["schema"] == "versioned_object"
    assert report["storage_manifest"]["price_history_db"]["kind"] == "sqlite"
    assert report["data_schemas"]["portfolio_transactions"]["expected_schema_version"] == 1
    assert report["data_schemas"]["portfolio_alerts"]["expected_schema_version"] == 1
    assert report["data_schemas"]["review_notes"]["expected_schema_version"] == 1
    assert report["data_schemas"]["daily_digest_state"]["expected_schema_version"] == 1
    assert report["data_schemas"]["source_metrics"]["expected_schema_version"] == 1
