import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_price_history_store_persists_versioned_json_and_sqlite():
    from goldmonitor.price_history import PriceHistoryStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = str(Path(tmp_dir) / "price_history.json")
        store = PriceHistoryStore(path, archive_limit=3, export_limit=10, save_interval_seconds=0)

        archive, saved_at, point = store.add_entry(
            [],
            0.0,
            {
                "usd": "2350.12",
                "rmb": "543.21",
                "rate": "7.19",
                "timestamp": "2026-06-08T12:00:00Z",
            },
            force_save=True,
        )

        assert point["time"] == "12:00:00"
        assert point["timestamp"] == "2026-06-08T12:00:00"
        assert archive == [point]
        assert saved_at > 0
        assert Path(path).exists()
        assert Path(store.db_path()).exists()

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["items"] == [point]

        loaded = store.load_archive()
        assert loaded == [point]

        second_archive = store.save_archive([
            {"usd": 2351, "rmb": 544, "rate": 7.2, "time": "12:01:00", "timestamp": "2026-06-08T12:01:00"},
            {"usd": 2352, "rmb": 545, "rate": 7.2, "time": "12:02:00", "timestamp": "2026-06-08T12:02:00"},
            {"usd": 2353, "rmb": 546, "rate": 7.2, "time": "12:03:00", "timestamp": "2026-06-08T12:03:00"},
            {"usd": 2354, "rmb": 547, "rate": 7.2, "time": "12:04:00", "timestamp": "2026-06-08T12:04:00"},
        ])
        assert [item["rmb"] for item in second_archive] == [545.0, 546.0, 547.0]

        state = store.build_state(second_archive, limit=2, build_events=lambda items: [{"type": "alert", "count": len(items)}])
        assert state["total"] == 2
        assert state["stats"]["rmb"]["start"] == 546.0
        assert state["stats"]["rmb"]["end"] == 547.0
        assert state["events"] == [{"type": "alert", "count": 2}]

        csv_text, count = store.build_csv(second_archive)
        assert count == 3
        assert "usd_per_oz" in csv_text
        assert "2354.0" in csv_text


def test_alert_log_store_updates_persisted_and_memory_entries():
    from goldmonitor.alert_log import AlertLogStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = AlertLogStore(tmp_dir, db_limit=10, export_limit=10)
        memory_entries = [{
            "type": "warning",
            "mode": "rmb",
            "message": "测试价格预警",
            "timestamp": "2026-06-08T12:00:00",
            "notifications": [{"channel": "email", "label": "邮件", "status": "queued", "message": "已提交"}],
            "notification_summary": {"status": "queued", "label": "已提交", "message": "已提交"},
            "related_news": [{"title": "Gold holds near highs"}],
        }]

        saved = store.save_entry(memory_entries[0])
        memory_entries[0].update(saved)
        alert_id = saved["id"]

        loaded = store.load_archive(limit=5)
        assert loaded[-1]["id"] == alert_id
        assert loaded[-1]["read"] is False

        ok, updated = store.update_entry_payload(
            alert_id,
            lambda entry: store.apply_status(entry, read=True, acknowledged=True),
            memory_entries=memory_entries,
        )
        assert ok is True
        assert updated["acknowledged"] is True
        assert memory_entries[0]["acknowledged"] is True
        assert store.load_archive(limit=5)[-1]["acknowledged"] is True

        csv_text, count = store.build_csv(memory_entries)
        assert count == 1
        assert "测试价格预警" in csv_text
        assert "notification_summary" in csv_text
        assert "queued:已提交:已提交" in csv_text
        assert "邮件:queued:已提交" in csv_text
        assert "Gold holds near highs" in csv_text


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("storage module checks passed.")
