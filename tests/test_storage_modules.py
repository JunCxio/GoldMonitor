import json
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@contextmanager
def track_sqlite_connections(module):
    real_connect = module.sqlite3.connect
    connections = []

    class TrackingConnection:
        def __init__(self, connection):
            self.connection = connection
            self.closed = False

        def __getattr__(self, name):
            return getattr(self.connection, name)

        def __enter__(self):
            self.connection.__enter__()
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self.connection.__exit__(exc_type, exc_value, traceback)

        def close(self):
            self.closed = True
            self.connection.close()

    def tracking_connect(*args, **kwargs):
        connection = TrackingConnection(real_connect(*args, **kwargs))
        connections.append(connection)
        return connection

    module.sqlite3.connect = tracking_connect
    try:
        yield connections
    finally:
        module.sqlite3.connect = real_connect
        for connection in connections:
            if not connection.closed:
                connection.close()


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

        ok, handled = store.update_entry_payload(
            alert_id,
            lambda entry: store.apply_handling(entry, handled=True, note="已电话确认"),
            memory_entries=memory_entries,
        )
        assert ok is True
        assert handled["handled"] is True
        assert handled["handling_note"] == "已电话确认"
        assert handled["handled_at"]
        assert memory_entries[0]["handled"] is True
        assert store.load_archive(limit=5)[-1]["handling_note"] == "已电话确认"

        csv_text, count = store.build_csv(memory_entries)
        assert count == 1
        assert "测试价格预警" in csv_text
        assert "handling_note" in csv_text
        assert "已电话确认" in csv_text
        assert "notification_summary" in csv_text
        assert "queued:已提交:已提交" in csv_text
        assert "邮件:queued:已提交" in csv_text
        assert "Gold holds near highs" in csv_text


def test_alert_log_store_closes_database_connections():
    import goldmonitor.alert_log as alert_log_module

    with track_sqlite_connections(alert_log_module) as connections:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = alert_log_module.AlertLogStore(tmp_dir, db_limit=10)
            saved = store.save_entry({
                "type": "warning",
                "message": "连接关闭检查",
                "timestamp": "2026-07-10T12:00:00",
            })
            store.load_archive(limit=5)
            store.update_entry_payload(saved["id"], lambda entry: entry)
            store.clear_archive()

            assert len(connections) == 4
            assert all(connection.closed for connection in connections)


def test_price_history_store_closes_database_connections():
    import goldmonitor.price_history as price_history_module

    with track_sqlite_connections(price_history_module) as connections:
        with tempfile.TemporaryDirectory() as tmp_dir:
            store = price_history_module.PriceHistoryStore(
                str(Path(tmp_dir) / "price_history.json"),
                archive_limit=10,
            )
            store.upsert_points([{
                "usd": 2350,
                "rmb": 543,
                "rate": 7.19,
                "timestamp": "2026-07-10T12:00:00",
            }])
            store.load_from_db()
            store.filter_from_db(limit=5)

            assert len(connections) == 3
            assert all(connection.closed for connection in connections)


def test_price_history_store_keeps_long_windows_in_rollups_after_raw_cleanup():
    from goldmonitor.price_history import PriceHistoryStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = PriceHistoryStore(
            str(Path(tmp_dir) / "price_history.json"),
            archive_limit=20000,
            raw_retention_minutes=60,
        )
        start = datetime(2026, 7, 1, 12, 0, 0)
        points = []
        for index in range(8 * 24 * 12 + 1):
            timestamp = start + timedelta(minutes=index * 5)
            points.append({
                "usd": 2300 + index / 10,
                "rmb": 540 + index / 100,
                "rate": 7.2,
                "timestamp": timestamp.isoformat(timespec="seconds"),
            })

        store.upsert_points(points)

        raw_items = store.load_from_db()
        assert len(raw_items) == 13
        assert raw_items[0]["timestamp"] == (start + timedelta(days=8) - timedelta(minutes=60)).isoformat(timespec="seconds")

        state = store.build_state([], minutes=7 * 24 * 60, limit=2100)
        assert state["resolution"] == "5m"
        assert state["resolution_seconds"] == 300
        assert state["total"] == 7 * 24 * 12 + 1
        assert state["items"][0]["timestamp"] == (start + timedelta(days=1)).isoformat(timespec="seconds")
        assert state["items"][-1]["timestamp"] == (start + timedelta(days=8)).isoformat(timespec="seconds")


def test_price_history_store_backfills_rollups_from_legacy_sqlite():
    from goldmonitor.price_history import PRICE_HISTORY_DB_SCHEMA_VERSION, PriceHistoryStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = str(Path(tmp_dir) / "price_history.json")
        store = PriceHistoryStore(path)
        with sqlite3.connect(store.db_path()) as conn:
            conn.execute("""
                CREATE TABLE price_history (
                    timestamp TEXT PRIMARY KEY,
                    time TEXT NOT NULL,
                    usd REAL,
                    rmb REAL,
                    rate REAL
                )
            """)
            conn.executemany(
                """
                INSERT INTO price_history(timestamp, time, usd, rmb, rate)
                VALUES(?, ?, ?, ?, ?)
                """,
                [
                    ("2026-07-01T12:00:00", "12:00:00", 2300, 540, 7.2),
                    ("2026-07-03T12:00:00", "12:00:00", 2320, 545, 7.2),
                ],
            )

        items = store.filter_from_db(minutes=7 * 24 * 60, limit=2100)

        assert [item["usd"] for item in items] == [2300.0, 2320.0]
        with sqlite3.connect(store.db_path()) as conn:
            version = conn.execute(
                "SELECT value FROM price_history_metadata WHERE key = 'schema_version'"
            ).fetchone()
            rollup_count = conn.execute(
                "SELECT COUNT(*) FROM price_history_rollups"
            ).fetchone()[0]
        assert version == (str(PRICE_HISTORY_DB_SCHEMA_VERSION),)
        assert rollup_count == 8


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
