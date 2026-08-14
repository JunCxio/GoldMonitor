import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


def point(timestamp, usd=2300, rmb=540, rate=7.2):
    return {
        "timestamp": timestamp,
        "time": timestamp[11:19],
        "usd": usd,
        "rmb": rmb,
        "rate": rate,
    }


def test_price_history_maintenance_diagnoses_and_repairs_only_recoverable_rollups(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(
        str(tmp_path / "price_history.json"),
        raw_retention_minutes=60,
    )
    store.upsert_points([
        point("2026-08-10T10:00:00", usd=2280, rmb=535),
        point("2026-08-11T11:00:00", usd=2300, rmb=540),
        point("2026-08-11T12:00:00", usd=2310, rmb=542),
    ])

    with closing(sqlite3.connect(store.db_path())) as conn:
        preserved_daily = conn.execute(
            """
            SELECT usd FROM price_history_rollups
            WHERE resolution = '1d' AND bucket_timestamp = '2026-08-10T00:00:00'
            """
        ).fetchone()
        assert preserved_daily == (2280.0,)
        conn.execute(
            """
            DELETE FROM price_history_rollups
            WHERE resolution = '1m' AND bucket_timestamp = '2026-08-11T11:00:00'
            """
        )
        conn.execute(
            """
            UPDATE price_history_rollups
            SET usd = 9999
            WHERE resolution = '1h' AND bucket_timestamp = '2026-08-11T12:00:00'
            """
        )
        conn.execute(
            """
            INSERT INTO price_history_rollups(
                resolution, bucket_timestamp, time, usd, rmb, rate, last_timestamp
            ) VALUES('5m', '2026-08-11T11:30:00', '11:30:00', 1, 1, 1,
                     '2026-08-11T11:30:00')
            """
        )
        conn.execute(
            """
            INSERT INTO price_history_rollups(
                resolution, bucket_timestamp, time, usd, rmb, rate, last_timestamp
            ) VALUES('5m', '2026-08-09T09:00:00', '09:00:00', 2, 2, 2,
                     '2026-08-09T09:00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.commit()

    diagnosis = store.diagnose_maintenance()

    assert diagnosis["status"] == "attention"
    assert diagnosis["database"]["raw"]["invalid_timestamp"] == 1
    assert diagnosis["comparison"]["rollup_missing"] == 1
    assert diagnosis["comparison"]["rollup_mismatched"] == 1
    assert diagnosis["comparison"]["rollup_unexpected"] == 1
    assert diagnosis["operations"]["rebuild_rollups"]["available"] is True

    preview = store.preview_maintenance_repair("rebuild_rollups")

    assert preview["executable"] is True
    assert preview["effects"]["raw_rows_unchanged"] == 3
    assert preview["effects"]["rollup_buckets_to_rebuild"] == 7
    assert preview["effects"]["rollup_buckets_to_remove"] == 1

    result = store.execute_maintenance_repair("rebuild_rollups")

    assert result["ok"] is True
    assert result["rebuilt_rollups"] == 7
    assert result["removed_rollups"] == 1
    assert "清理 1 个多余汇总" in result["message"]
    assert result["diagnosis"]["comparison"]["rollup_missing"] == 0
    assert result["diagnosis"]["comparison"]["rollup_mismatched"] == 0
    assert result["diagnosis"]["comparison"]["rollup_unexpected"] == 0
    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE timestamp = 'invalid-time'"
        ).fetchone() == (1,)
        assert conn.execute(
            """
            SELECT usd FROM price_history_rollups
            WHERE resolution = '1d' AND bucket_timestamp = '2026-08-10T00:00:00'
            """
        ).fetchone() == (2280.0,)
        assert conn.execute(
            """
            SELECT COUNT(*) FROM price_history_rollups
            WHERE resolution = '5m' AND bucket_timestamp = '2026-08-11T11:30:00'
            """
        ).fetchone() == (0,)
        assert conn.execute(
            """
            SELECT COUNT(*) FROM price_history_rollups
            WHERE resolution = '5m' AND bucket_timestamp = '2026-08-09T09:00:00'
            """
        ).fetchone() == (1,)


def test_price_history_json_sync_preserves_database_values_and_retention(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    json_path = tmp_path / "price_history.json"
    store = PriceHistoryStore(str(json_path), raw_retention_minutes=60)
    store.upsert_points([
        point("2026-08-11T12:00:00", usd=2300, rmb=None),
    ])
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [
            point("2026-08-11T10:00:00", usd=2200, rmb=520),
            point("2026-08-11T12:00:00", usd=9999, rmb=540),
            point("2026-08-11T12:10:00", usd=2310, rmb=542),
            {"timestamp": "invalid", "usd": 1, "rmb": 1},
            {"timestamp": "2026-08-11T12:11:00", "usd": None, "rmb": None},
        ],
    }), encoding="utf-8")

    diagnosis = store.diagnose_maintenance()

    assert diagnosis["comparison"]["json_sync_candidates"] == 2
    assert diagnosis["comparison"]["missing_in_database"] == 1
    assert diagnosis["comparison"]["supplementable_fields"] == 1
    assert diagnosis["comparison"]["conflicts_preserved"] == 1
    assert diagnosis["json_archive"]["invalid_timestamp"] == 1
    assert diagnosis["json_archive"]["missing_price"] == 1

    preview = store.preview_maintenance_repair("sync_json_and_rebuild")

    assert preview["effects"]["json_points_eligible"] == 2
    assert preview["effects"]["json_points_to_add"] == 1
    assert preview["effects"]["json_fields_to_supplement"] == 1
    assert preview["effects"]["invalid_json_ignored"] == 2
    assert preview["effects"]["conflicts_preserved"] == 1

    result = store.execute_maintenance_repair("sync_json_and_rebuild")

    assert result["inserted_points"] == 1
    assert result["supplemented_fields"] == 1
    with closing(sqlite3.connect(store.db_path())) as conn:
        rows = conn.execute(
            "SELECT timestamp, usd, rmb FROM price_history ORDER BY timestamp"
        ).fetchall()
    assert rows == [
        ("2026-08-11T12:00:00", 2300.0, 540.0),
        ("2026-08-11T12:10:00", 2310.0, 542.0),
    ]


def test_price_history_maintenance_cleans_only_invalid_database_rows(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(str(tmp_path / "price_history.json"))
    store.upsert_points([point("2026-08-11T12:00:00")])
    with closing(sqlite3.connect(store.db_path())) as conn:
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('2026-08-11T12:05:00', '12:05:00', NULL, NULL, 7.2)
            """
        )
        conn.execute(
            """
            INSERT INTO price_history_rollups(
                resolution, bucket_timestamp, time, usd, rmb, rate, last_timestamp
            ) VALUES('future', '2026-08-11T12:00:00', '12:00:00', 2300, 540,
                     7.2, '2026-08-11T12:00:00')
            """
        )
        conn.commit()

    diagnosis = store.diagnose_maintenance()

    assert diagnosis["database"]["raw"]["invalid_timestamp"] == 1
    assert diagnosis["database"]["raw"]["missing_price"] == 1
    assert diagnosis["database"]["unknown_resolution"] == 1
    assert diagnosis["operations"]["clean_invalid_records"]["available"] is True
    assert "不会自动清理" in diagnosis["issues"][-1]

    preview = store.preview_maintenance_repair("clean_invalid_records")

    assert preview["executable"] is True
    assert preview["effects"] == {
        "invalid_timestamp_rows_to_remove": 1,
        "missing_price_rows_to_remove": 1,
        "raw_rows_to_remove": 2,
        "raw_rows_preserved": 1,
        "unknown_rollups_preserved": 1,
        "rollup_buckets_to_remove": 0,
        "rollup_buckets_to_rebuild": 4,
    }

    result = store.execute_maintenance_repair("clean_invalid_records")

    assert result["removed_invalid_timestamps"] == 1
    assert result["removed_missing_prices"] == 1
    assert "已移除 1 条无效时间记录和 1 条缺少价格的记录" in result["message"]
    assert result["diagnosis"]["database"]["raw"]["invalid_timestamp"] == 0
    assert result["diagnosis"]["database"]["raw"]["missing_price"] == 0
    assert result["diagnosis"]["database"]["unknown_resolution"] == 1
    assert (
        result["diagnosis"]["operations"]["clean_invalid_records"]["available"]
        is False
    )
    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            "SELECT timestamp FROM price_history ORDER BY timestamp"
        ).fetchall() == [("2026-08-11T12:00:00",)]
        assert conn.execute(
            """
            SELECT COUNT(*) FROM price_history_rollups
            WHERE resolution = 'future'
            """
        ).fetchone() == (1,)


def test_price_history_maintenance_restores_latest_repair_checkpoint(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(str(tmp_path / "price_history.json"))
    store.upsert_points([point("2026-08-11T12:00:00")])
    with closing(sqlite3.connect(store.db_path())) as conn:
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.commit()

    cleanup = store.execute_maintenance_repair("clean_invalid_records")

    assert cleanup["diagnosis"]["repair_backup"]["available"] is True
    assert cleanup["diagnosis"]["repair_backup"]["action"] == (
        "clean_invalid_records"
    )
    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE timestamp = 'invalid-time'"
        ).fetchone() == (0,)

    preview = store.preview_maintenance_repair("restore_last_repair")
    assert preview["executable"] is True
    assert preview["effects"]["raw_rows_to_restore"] == 2
    assert preview["effects"]["backup_action"] == "clean_invalid_records"

    restored = store.execute_maintenance_repair(
        "restore_last_repair",
        expected_effects=preview["effects"],
        expected_revision=preview["revision"],
    )

    assert restored["ok"] is True
    assert restored["restored_action"] == "clean_invalid_records"
    assert restored["diagnosis"]["repair_backup"]["available"] is False
    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE timestamp = 'invalid-time'"
        ).fetchone() == (1,)


def test_price_history_maintenance_keeps_restored_empty_database_after_restart(
    tmp_path,
):
    from goldmonitor.price_history import PriceHistoryStore

    json_path = tmp_path / "price_history.json"
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [point("2026-08-11T12:00:00")],
    }), encoding="utf-8")
    store = PriceHistoryStore(str(json_path))
    store.connect_db().close()

    synchronized = store.execute_maintenance_repair("sync_json_and_rebuild")
    assert synchronized["inserted_points"] == 1

    restore_preview = store.preview_maintenance_repair("restore_last_repair")
    restored = store.execute_maintenance_repair(
        "restore_last_repair",
        expected_effects=restore_preview["effects"],
        expected_revision=restore_preview["revision"],
    )

    assert restored["raw_points"] == 0
    assert json.loads(json_path.read_text(encoding="utf-8"))["items"] == [
        point("2026-08-11T12:00:00")
    ]
    restarted_store = PriceHistoryStore(str(json_path))
    assert restarted_store.load_archive() == []
    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone() == (0,)


def test_price_history_maintenance_rejects_changed_content_with_same_effects(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(str(tmp_path / "price_history.json"))
    store.upsert_points([point("2026-08-11T12:00:00")])
    with closing(sqlite3.connect(store.db_path())) as conn:
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.commit()

    preview = store.preview_maintenance_repair("clean_invalid_records")

    with closing(sqlite3.connect(store.db_path())) as conn:
        conn.execute(
            "DELETE FROM price_history WHERE timestamp = 'invalid-time'"
        )
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('different-invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.commit()

    current_preview = store.preview_maintenance_repair("clean_invalid_records")
    assert current_preview["effects"] == preview["effects"]
    assert current_preview["revision"] != preview["revision"]

    with pytest.raises(ValueError, match="影响范围已变化"):
        store.execute_maintenance_repair(
            "clean_invalid_records",
            expected_effects=preview["effects"],
            expected_revision=preview["revision"],
        )

    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            """SELECT COUNT(*) FROM price_history
               WHERE timestamp = 'different-invalid-time'"""
        ).fetchone() == (1,)


def test_price_history_maintenance_disables_repair_for_corrupt_database(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(str(tmp_path / "price_history.json"))
    Path(store.db_path()).write_bytes(b"not-a-sqlite-database")

    diagnosis = store.diagnose_maintenance()

    assert diagnosis["ok"] is False
    assert diagnosis["status"] == "unavailable"
    assert diagnosis["operations"]["clean_invalid_records"]["available"] is False
    assert diagnosis["operations"]["rebuild_rollups"]["available"] is False
    assert diagnosis["operations"]["sync_json_and_rebuild"]["available"] is False


def test_price_history_maintenance_does_not_create_database_during_diagnosis(tmp_path):
    from goldmonitor.price_history import PriceHistoryStore

    json_path = tmp_path / "price_history.json"
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [point("2026-08-11T12:00:00")],
    }), encoding="utf-8")
    store = PriceHistoryStore(str(json_path))

    diagnosis = store.diagnose_maintenance()

    assert diagnosis["database"]["exists"] is False
    assert diagnosis["operations"]["clean_invalid_records"]["available"] is False
    assert diagnosis["operations"]["sync_json_and_rebuild"]["available"] is False
    assert not Path(store.db_path()).exists()


def test_price_history_maintenance_rolls_back_json_sync_on_rebuild_failure(
    monkeypatch,
    tmp_path,
):
    from goldmonitor.price_history import PriceHistoryStore

    json_path = tmp_path / "price_history.json"
    store = PriceHistoryStore(str(json_path))
    store.connect_db().close()
    json_path.write_text(json.dumps({
        "schema_version": 1,
        "items": [point("2026-08-11T12:00:00")],
    }), encoding="utf-8")

    def fail_rollup_write(_conn, _rows):
        raise sqlite3.DatabaseError("rollup failed")

    monkeypatch.setattr(store, "_upsert_rollups", fail_rollup_write)

    try:
        store.execute_maintenance_repair("sync_json_and_rebuild")
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("修复失败时应抛出数据库异常")

    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute("SELECT COUNT(*) FROM price_history").fetchone() == (0,)


def test_price_history_maintenance_rolls_back_invalid_cleanup_on_rebuild_failure(
    monkeypatch,
    tmp_path,
):
    from goldmonitor.price_history import PriceHistoryStore

    store = PriceHistoryStore(str(tmp_path / "price_history.json"))
    store.upsert_points([point("2026-08-11T12:00:00")])
    with closing(sqlite3.connect(store.db_path())) as conn:
        conn.execute(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES('invalid-time', '00:00:00', 1, 1, 1)
            """
        )
        conn.commit()

    def fail_rollup_write(_conn, _rows):
        raise sqlite3.DatabaseError("rollup failed")

    monkeypatch.setattr(store, "_upsert_rollups", fail_rollup_write)

    try:
        store.execute_maintenance_repair("clean_invalid_records")
    except sqlite3.DatabaseError:
        pass
    else:
        raise AssertionError("清理失败时应抛出数据库异常")

    with closing(sqlite3.connect(store.db_path())) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM price_history WHERE timestamp = 'invalid-time'"
        ).fetchone() == (1,)
    assert not Path(store.repair_backup_path() + ".tmp").exists()
