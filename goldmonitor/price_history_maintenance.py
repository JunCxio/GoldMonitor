import json
import math
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from goldmonitor.data_contracts import unwrap_item_payload


ROLLUP_RESOLUTIONS = (
    ("1m", 60, 30 * 24 * 60),
    ("5m", 5 * 60, 90 * 24 * 60),
    ("1h", 60 * 60, 2 * 365 * 24 * 60),
    ("1d", 24 * 60 * 60, None),
)
MAINTENANCE_ACTIONS = (
    "clean_invalid_records",
    "rebuild_rollups",
    "sync_json_and_rebuild",
)


def _parse_timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError:
        return None


class PriceHistoryMaintenanceMixin:
    @staticmethod
    def _collapse_rollup_rows(rows):
        collapsed = {}
        for row in rows:
            key = (row["resolution"], row["bucket_timestamp"])
            current = collapsed.get(key)
            if current is None:
                collapsed[key] = dict(row)
                continue
            if row["last_timestamp"] < current["last_timestamp"]:
                continue
            for field in ("time", "usd", "rmb", "rate"):
                if row.get(field) is not None:
                    current[field] = row[field]
            current["last_timestamp"] = row["last_timestamp"]
        return collapsed

    @staticmethod
    def _values_match(left, right):
        if left is None or right is None:
            return left is None and right is None
        try:
            return math.isclose(
                float(left),
                float(right),
                rel_tol=1e-9,
                abs_tol=1e-9,
            )
        except (TypeError, ValueError):
            return left == right

    def _maintenance_item(self, item):
        normalized = self._normalize_items([item])
        if not normalized:
            return None
        point = normalized[0]
        if point.get("usd") is None and point.get("rmb") is None:
            return None
        return point

    def _json_maintenance_snapshot(self):
        snapshot = {
            "exists": os.path.exists(self.json_path),
            "readable": True,
            "total": 0,
            "valid": 0,
            "unique_valid": 0,
            "invalid_timestamp": 0,
            "missing_price": 0,
            "duplicate_timestamp": 0,
            "first_timestamp": None,
            "last_timestamp": None,
            "items": [],
            "message": "",
        }
        if not snapshot["exists"]:
            snapshot["message"] = "未找到 JSON 历史归档。"
            return snapshot
        try:
            with open(self.json_path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except (OSError, json.JSONDecodeError):
            snapshot.update({
                "readable": False,
                "message": "JSON 历史归档无法读取或格式无效。",
            })
            return snapshot

        raw_items = unwrap_item_payload(payload)
        snapshot["total"] = len(raw_items)
        merged = {}
        for item in raw_items:
            if not isinstance(item, dict) or not _parse_timestamp(item.get("timestamp")):
                snapshot["invalid_timestamp"] += 1
                continue
            point = self._maintenance_item(item)
            if point is None:
                snapshot["missing_price"] += 1
                continue
            snapshot["valid"] += 1
            timestamp = point["timestamp"]
            if timestamp in merged:
                snapshot["duplicate_timestamp"] += 1
                current = merged[timestamp]
                for field in ("usd", "rmb", "rate"):
                    if point.get(field) is not None:
                        current[field] = point[field]
                if point.get("time"):
                    current["time"] = point["time"]
            else:
                merged[timestamp] = point
        items = sorted(merged.values(), key=lambda item: item["timestamp"])
        snapshot["items"] = items
        snapshot["unique_valid"] = len(items)
        if items:
            snapshot["first_timestamp"] = items[0]["timestamp"]
            snapshot["last_timestamp"] = items[-1]["timestamp"]
            snapshot["message"] = "JSON 历史归档可用于补充数据库。"
        else:
            snapshot["message"] = "JSON 历史归档中没有可同步的有效价格。"
        return snapshot

    def _database_maintenance_snapshot(self):
        path = self.db_path()
        snapshot = {
            "exists": os.path.exists(path),
            "readable": True,
            "integrity_ok": True,
            "integrity_message": "数据库尚未创建。",
            "schema_ok": False,
            "raw": {
                "total": 0,
                "valid": 0,
                "invalid_timestamp": 0,
                "missing_price": 0,
                "duplicate_timestamp": 0,
                "first_timestamp": None,
                "last_timestamp": None,
            },
            "rollups": [],
            "unknown_resolution": 0,
            "items": [],
            "rollup_actual": {},
            "message": "",
        }
        if not snapshot["exists"]:
            snapshot["message"] = "尚未创建 SQLite 历史数据库。"
            return snapshot

        required_tables = {
            "price_history",
            "price_history_rollups",
            "price_history_metadata",
        }
        try:
            with closing(sqlite3.connect(path, timeout=5)) as conn:
                integrity_messages = [
                    str(row[0])
                    for row in conn.execute("PRAGMA integrity_check").fetchall()
                ]
                snapshot["integrity_ok"] = integrity_messages == ["ok"]
                snapshot["integrity_message"] = (
                    "完整性检查通过。"
                    if snapshot["integrity_ok"]
                    else "；".join(integrity_messages[:3])
                )
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'"
                    ).fetchall()
                }
                snapshot["schema_ok"] = required_tables.issubset(tables)
                if not snapshot["integrity_ok"] or not snapshot["schema_ok"]:
                    snapshot["message"] = (
                        "历史数据库结构不完整。"
                        if snapshot["integrity_ok"]
                        else "历史数据库完整性检查未通过。"
                    )
                    return snapshot

                valid_items = self._read_valid_database_items(conn, snapshot["raw"])
                snapshot["items"] = valid_items
                expected = self._collapse_rollup_rows(self._rollup_rows(valid_items))
                self._inspect_rollups(conn, expected, snapshot)
                snapshot["message"] = "SQLite 历史数据库可读取。"
        except sqlite3.Error as exc:
            snapshot.update({
                "readable": False,
                "integrity_ok": False,
                "integrity_message": "完整性检查无法完成。",
                "message": f"历史数据库无法读取：{exc}",
            })
        return snapshot

    def _read_valid_database_items(self, conn, raw):
        rows = conn.execute(
            """
            SELECT timestamp, time, usd, rmb, rate
            FROM price_history
            ORDER BY timestamp ASC
            """
        ).fetchall()
        raw["total"] = len(rows)
        valid_items = []
        seen_timestamps = set()
        for timestamp, point_time, usd, rmb, rate in rows:
            if not _parse_timestamp(timestamp):
                raw["invalid_timestamp"] += 1
                continue
            item = self._maintenance_item({
                "timestamp": timestamp,
                "time": point_time,
                "usd": usd,
                "rmb": rmb,
                "rate": rate,
            })
            if item is None:
                raw["missing_price"] += 1
                continue
            if item["timestamp"] in seen_timestamps:
                raw["duplicate_timestamp"] += 1
            seen_timestamps.add(item["timestamp"])
            valid_items.append(item)
        raw["valid"] = len(valid_items)
        if valid_items:
            raw["first_timestamp"] = valid_items[0]["timestamp"]
            raw["last_timestamp"] = valid_items[-1]["timestamp"]
        return valid_items

    def _inspect_rollups(self, conn, expected, snapshot):
        rows = conn.execute(
            """
            SELECT resolution, bucket_timestamp, time, usd, rmb, rate,
                   last_timestamp
            FROM price_history_rollups
            ORDER BY resolution, bucket_timestamp
            """
        ).fetchall()
        known_resolutions = {item[0] for item in ROLLUP_RESOLUTIONS}
        actual = {}
        for row in rows:
            resolution = str(row[0] or "")
            if resolution not in known_resolutions:
                snapshot["unknown_resolution"] += 1
                continue
            actual[(resolution, row[1])] = {
                "resolution": resolution,
                "bucket_timestamp": row[1],
                "time": row[2],
                "usd": row[3],
                "rmb": row[4],
                "rate": row[5],
                "last_timestamp": row[6],
            }
        snapshot["rollup_actual"] = actual

        for resolution, interval_seconds, retention_minutes in ROLLUP_RESOLUTIONS:
            resolution_rows = [
                row for key, row in actual.items() if key[0] == resolution
            ]
            expected_rows = {
                key: row for key, row in expected.items() if key[0] == resolution
            }
            missing, mismatched = self._compare_rollup_rows(actual, expected_rows)
            expected_timestamps = sorted(key[1] for key in expected_rows)
            unexpected = 0
            if expected_timestamps:
                unexpected = sum(
                    1
                    for row in resolution_rows
                    if (
                        expected_timestamps[0]
                        <= row["bucket_timestamp"]
                        <= expected_timestamps[-1]
                        and (resolution, row["bucket_timestamp"]) not in expected_rows
                    )
                )
            snapshot["rollups"].append({
                "resolution": resolution,
                "interval_seconds": interval_seconds,
                "retention_minutes": retention_minutes,
                "total": len(resolution_rows),
                "first_timestamp": (
                    resolution_rows[0]["bucket_timestamp"]
                    if resolution_rows else None
                ),
                "last_timestamp": (
                    resolution_rows[-1]["bucket_timestamp"]
                    if resolution_rows else None
                ),
                "repairable_expected": len(expected_rows),
                "repairable_present": len(expected_rows) - missing,
                "missing": missing,
                "mismatched": mismatched,
                "unexpected": unexpected,
            })

    def _compare_rollup_rows(self, actual, expected_rows):
        missing = 0
        mismatched = 0
        for key, expected_row in expected_rows.items():
            actual_row = actual.get(key)
            if actual_row is None:
                missing += 1
                continue
            fields_match = all(
                self._values_match(actual_row.get(field), expected_row.get(field))
                for field in ("usd", "rmb", "rate")
            )
            if (
                not fields_match
                or actual_row.get("time") != expected_row.get("time")
                or actual_row.get("last_timestamp")
                != expected_row.get("last_timestamp")
            ):
                mismatched += 1
        return missing, mismatched

    @staticmethod
    def _public_maintenance_snapshot(snapshot):
        private_keys = {"items", "rollup_actual"}
        return {key: value for key, value in snapshot.items() if key not in private_keys}

    @staticmethod
    def _count_unexpected_rollups(actual, expected):
        unexpected = 0
        for resolution, _interval_seconds, _retention_minutes in ROLLUP_RESOLUTIONS:
            expected_keys = {key for key in expected if key[0] == resolution}
            timestamps = sorted(key[1] for key in expected_keys)
            if not timestamps:
                continue
            unexpected += sum(
                1
                for key in actual
                if (
                    key[0] == resolution
                    and timestamps[0] <= key[1] <= timestamps[-1]
                    and key not in expected_keys
                )
            )
        return unexpected

    def _json_sync_candidates(self, database, json_archive):
        items = list(json_archive.get("items", []))
        if not items or self.raw_retention_minutes <= 0:
            return items
        latest_times = [
            parsed
            for parsed in (
                _parse_timestamp(database.get("raw", {}).get("last_timestamp")),
                _parse_timestamp(json_archive.get("last_timestamp")),
            )
            if parsed is not None
        ]
        if not latest_times:
            return items
        cutoff = max(latest_times) - timedelta(minutes=self.raw_retention_minutes)
        return [
            item
            for item in items
            if (_parse_timestamp(item.get("timestamp")) or cutoff) >= cutoff
        ]

    def diagnose_maintenance(self):
        database = self._database_maintenance_snapshot()
        json_archive = self._json_maintenance_snapshot()
        db_items = {
            item["timestamp"]: item for item in database.get("items", [])
        }
        json_candidates = self._json_sync_candidates(database, json_archive)
        comparison = self._compare_json_items(db_items, json_candidates)
        projected_items = self._project_synced_items(db_items, json_candidates)
        projected_rollups = self._collapse_rollup_rows(
            self._rollup_rows(projected_items)
        )
        comparison["json_sync_candidates"] = len(json_candidates)
        comparison["repairable_rollups"] = sum(
            item["repairable_expected"] for item in database["rollups"]
        )
        comparison["projected_repairable_rollups"] = len(projected_rollups)
        comparison["projected_rollup_unexpected"] = (
            self._count_unexpected_rollups(
                database.get("rollup_actual", {}),
                projected_rollups,
            )
        )
        comparison["rollup_missing"] = sum(
            item["missing"] for item in database["rollups"]
        )
        comparison["rollup_mismatched"] = sum(
            item["mismatched"] for item in database["rollups"]
        )
        comparison["rollup_unexpected"] = sum(
            item["unexpected"] for item in database["rollups"]
        )
        issues = self._maintenance_issues(database, json_archive, comparison)
        database_healthy = bool(
            database["exists"]
            and database["readable"]
            and database["integrity_ok"]
            and database["schema_ok"]
        )
        rebuild_available = bool(database_healthy and database["raw"]["valid"])
        sync_available = bool(
            database_healthy and json_archive["readable"] and json_candidates
        )
        clean_invalid_available = bool(
            database_healthy
            and (
                database["raw"]["invalid_timestamp"]
                or database["raw"]["missing_price"]
            )
        )
        if database["exists"] and not database_healthy:
            status = "unavailable"
        elif issues:
            status = "attention"
        elif not database["exists"] and not json_archive["exists"]:
            status = "empty"
        else:
            status = "healthy"
        return {
            "ok": not database["exists"] or database_healthy,
            "status": status,
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "database": self._public_maintenance_snapshot(database),
            "json_archive": self._public_maintenance_snapshot(json_archive),
            "comparison": comparison,
            "issues": issues,
            "operations": {
                "clean_invalid_records": {
                    "available": clean_invalid_available,
                    "reason": (
                        "可移除无法参与行情计算的无效数据库明细。"
                        if clean_invalid_available
                        else "没有可安全清理的无效数据库明细。"
                    ),
                },
                "rebuild_rollups": {
                    "available": rebuild_available,
                    "reason": (
                        "可从现有明细重新生成汇总。"
                        if rebuild_available
                        else "没有可用于重建的有效数据库明细。"
                    ),
                },
                "sync_json_and_rebuild": {
                    "available": sync_available,
                    "reason": (
                        "可补充有效 JSON 记录并重新生成可还原汇总。"
                        if sync_available
                        else "没有可同步的有效 JSON 历史归档。"
                    ),
                },
            },
        }

    def _compare_json_items(self, db_items, json_items):
        comparison = {
            "missing_in_database": 0,
            "supplementable_fields": 0,
            "conflicts_preserved": 0,
        }
        for item in json_items:
            current = db_items.get(item["timestamp"])
            if current is None:
                comparison["missing_in_database"] += 1
                continue
            for field in ("usd", "rmb", "rate"):
                json_value = item.get(field)
                db_value = current.get(field)
                if db_value is None and json_value is not None:
                    comparison["supplementable_fields"] += 1
                elif (
                    db_value is not None
                    and json_value is not None
                    and not self._values_match(db_value, json_value)
                ):
                    comparison["conflicts_preserved"] += 1
        return comparison

    def _project_synced_items(self, db_items, json_items):
        projected = {timestamp: dict(item) for timestamp, item in db_items.items()}
        for item in json_items:
            current = projected.get(item["timestamp"])
            if current is None:
                projected[item["timestamp"]] = dict(item)
                continue
            for field in ("usd", "rmb", "rate"):
                if current.get(field) is None and item.get(field) is not None:
                    current[field] = item[field]
        return sorted(projected.values(), key=lambda item: item["timestamp"])

    @staticmethod
    def _maintenance_issues(database, json_archive, comparison):
        raw = database["raw"]
        issues = []
        if database["exists"] and not database["integrity_ok"]:
            issues.append("数据库完整性检查未通过，当前维护操作已停用。")
        elif database["exists"] and not database["schema_ok"]:
            issues.append("数据库表结构不完整，当前维护操作已停用。")
        if raw["invalid_timestamp"]:
            issues.append(f"数据库中有 {raw['invalid_timestamp']} 条无效时间记录。")
        if raw["missing_price"]:
            issues.append(f"数据库中有 {raw['missing_price']} 条缺少价格的记录。")
        if any(comparison[key] for key in (
            "rollup_missing",
            "rollup_mismatched",
            "rollup_unexpected",
        )):
            issues.append(
                "可还原范围内有 "
                f"{comparison['rollup_missing']} 个汇总缺失、"
                f"{comparison['rollup_mismatched']} 个汇总不一致、"
                f"{comparison['rollup_unexpected']} 个多余汇总。"
            )
        if database["unknown_resolution"]:
            issues.append(
                f"发现 {database['unknown_resolution']} 条未知粒度汇总记录，"
                "为避免误删较新版本数据，当前不会自动清理。"
            )
        if not json_archive["readable"]:
            issues.append("JSON 历史归档无法读取。")
        if json_archive["invalid_timestamp"] or json_archive["missing_price"]:
            issues.append(
                "JSON 历史归档含有 "
                f"{json_archive['invalid_timestamp']} 条无效时间记录、"
                f"{json_archive['missing_price']} 条缺少价格的记录。"
            )
        if comparison["missing_in_database"] or comparison["supplementable_fields"]:
            issues.append(
                f"JSON 可补充 {comparison['missing_in_database']} 个数据库时间点和 "
                f"{comparison['supplementable_fields']} 个空缺字段。"
            )
        return issues

    def preview_maintenance_repair(self, action):
        action = str(action or "").strip()
        if action not in MAINTENANCE_ACTIONS:
            raise ValueError("不支持的历史数据维护操作")
        diagnosis = self.diagnose_maintenance()
        operation = diagnosis["operations"][action]
        comparison = diagnosis["comparison"]
        database = diagnosis["database"]
        json_archive = diagnosis["json_archive"]
        if action == "clean_invalid_records":
            effects = {
                "invalid_timestamp_rows_to_remove": (
                    database["raw"]["invalid_timestamp"]
                ),
                "missing_price_rows_to_remove": database["raw"]["missing_price"],
                "raw_rows_to_remove": (
                    database["raw"]["invalid_timestamp"]
                    + database["raw"]["missing_price"]
                ),
                "raw_rows_preserved": database["raw"]["valid"],
                "unknown_rollups_preserved": database["unknown_resolution"],
                "rollup_buckets_to_remove": comparison["rollup_unexpected"],
                "rollup_buckets_to_rebuild": comparison["repairable_rollups"],
            }
            summary = (
                f"将移除 {database['raw']['invalid_timestamp']} 条无效时间记录和 "
                f"{database['raw']['missing_price']} 条缺少价格的记录，保留 "
                f"{database['raw']['valid']} 条有效明细；清理 "
                f"{comparison['rollup_unexpected']} 个多余汇总并重建 "
                f"{comparison['repairable_rollups']} 个可还原汇总桶；"
                f"{database['unknown_resolution']} 条未知粒度汇总不会被删除。"
            )
        elif action == "rebuild_rollups":
            effects = {
                "raw_rows_unchanged": database["raw"]["total"],
                "rollup_buckets_to_rebuild": comparison["repairable_rollups"],
                "rollup_buckets_to_remove": comparison["rollup_unexpected"],
                "json_points_to_add": 0,
                "json_fields_to_supplement": 0,
                "invalid_json_ignored": 0,
                "conflicts_preserved": 0,
                "first_timestamp": database["raw"]["first_timestamp"],
                "last_timestamp": database["raw"]["last_timestamp"],
            }
            summary = (
                f"将保留 {database['raw']['total']} 条数据库明细，"
                f"清理 {comparison['rollup_unexpected']} 个可还原范围内的多余汇总，"
                f"重建 {comparison['repairable_rollups']} 个可还原汇总桶。"
            )
        else:
            effects = {
                "raw_rows_unchanged": database["raw"]["total"],
                "rollup_buckets_to_rebuild": comparison["projected_repairable_rollups"],
                "rollup_buckets_to_remove": comparison["projected_rollup_unexpected"],
                "json_points_to_add": comparison["missing_in_database"],
                "json_points_eligible": comparison["json_sync_candidates"],
                "json_fields_to_supplement": comparison["supplementable_fields"],
                "invalid_json_ignored": (
                    json_archive["invalid_timestamp"] + json_archive["missing_price"]
                ),
                "conflicts_preserved": comparison["conflicts_preserved"],
                "first_timestamp": json_archive["first_timestamp"],
                "last_timestamp": json_archive["last_timestamp"],
            }
            summary = (
                f"将从 JSON 补充 {comparison['missing_in_database']} 个时间点和 "
                f"{comparison['supplementable_fields']} 个空缺字段，清理 "
                f"{comparison['projected_rollup_unexpected']} 个可还原范围内的多余汇总，"
                "再重建 "
                f"{comparison['projected_repairable_rollups']} 个可还原汇总桶。"
            )
        return {
            "ok": bool(operation["available"]),
            "action": action,
            "executable": bool(operation["available"]),
            "requires_confirmation": True,
            "summary": summary,
            "message": operation["reason"],
            "effects": effects,
            "diagnosis": diagnosis,
        }

    def _rebuild_repairable_rollups(self, conn):
        raw = {
            "total": 0,
            "valid": 0,
            "invalid_timestamp": 0,
            "missing_price": 0,
            "duplicate_timestamp": 0,
            "first_timestamp": None,
            "last_timestamp": None,
        }
        items = self._read_valid_database_items(conn, raw)
        expected = self._collapse_rollup_rows(self._rollup_rows(items))
        replaced = 0
        removed = 0
        for resolution, _interval_seconds, _retention_minutes in ROLLUP_RESOLUTIONS:
            timestamps = sorted(key[1] for key in expected if key[0] == resolution)
            if not timestamps:
                continue
            existing_timestamps = [
                row[0]
                for row in conn.execute(
                    """
                    SELECT bucket_timestamp FROM price_history_rollups
                    WHERE resolution = ? AND bucket_timestamp BETWEEN ? AND ?
                    """,
                    [resolution, timestamps[0], timestamps[-1]],
                ).fetchall()
            ]
            expected_timestamps = set(timestamps)
            replaced += sum(
                1 for timestamp in existing_timestamps
                if timestamp in expected_timestamps
            )
            removed += sum(
                1 for timestamp in existing_timestamps
                if timestamp not in expected_timestamps
            )
            conn.execute(
                """
                DELETE FROM price_history_rollups
                WHERE resolution = ? AND bucket_timestamp BETWEEN ? AND ?
                """,
                [resolution, timestamps[0], timestamps[-1]],
            )
        self._upsert_rollups(conn, list(expected.values()))
        return {
            "raw_points": len(items),
            "replaced_rollups": replaced,
            "removed_rollups": removed,
            "rebuilt_rollups": len(expected),
            "first_timestamp": items[0]["timestamp"] if items else None,
            "last_timestamp": items[-1]["timestamp"] if items else None,
        }

    @staticmethod
    def _database_integrity_ok(conn):
        rows = conn.execute("PRAGMA integrity_check").fetchall()
        return [str(row[0]) for row in rows] == ["ok"]

    @staticmethod
    def _remove_invalid_raw_rows(conn):
        invalid_timestamp_rowids = []
        missing_price_rowids = []
        rows = conn.execute(
            "SELECT rowid, timestamp, usd, rmb FROM price_history"
        ).fetchall()
        for rowid, timestamp, usd, rmb in rows:
            if not _parse_timestamp(timestamp):
                invalid_timestamp_rowids.append(rowid)
            elif usd is None and rmb is None:
                missing_price_rowids.append(rowid)
        rowids = invalid_timestamp_rowids + missing_price_rowids
        for offset in range(0, len(rowids), 500):
            batch = rowids[offset:offset + 500]
            placeholders = ",".join("?" for _item in batch)
            conn.execute(
                f"DELETE FROM price_history WHERE rowid IN ({placeholders})",
                batch,
            )
        return len(invalid_timestamp_rowids), len(missing_price_rowids)

    def execute_maintenance_repair(self, action):
        action = str(action or "").strip()
        preview = self.preview_maintenance_repair(action)
        if not preview["executable"]:
            raise ValueError(preview["message"])
        json_snapshot = (
            self._json_maintenance_snapshot()
            if action == "sync_json_and_rebuild"
            else None
        )
        with closing(self.connect_db()) as conn:
            if not self._database_integrity_ok(conn):
                raise sqlite3.DatabaseError("历史数据库完整性检查未通过")
            inserted = 0
            supplemented = 0
            removed_invalid_timestamps = 0
            removed_missing_prices = 0
            if json_snapshot is not None:
                database_snapshot = self._database_maintenance_snapshot()
                json_items = self._json_sync_candidates(database_snapshot, json_snapshot)
                with conn:
                    inserted, supplemented = self._sync_json_items(conn, json_items)
                    rebuild = self._rebuild_repairable_rollups(conn)
                    latest_row = conn.execute(
                        "SELECT MAX(timestamp) FROM price_history"
                    ).fetchone()
                    if latest_row and latest_row[0]:
                        self._cleanup_retention(conn, latest_row[0])
            elif action == "clean_invalid_records":
                with conn:
                    (
                        removed_invalid_timestamps,
                        removed_missing_prices,
                    ) = self._remove_invalid_raw_rows(conn)
                    rebuild = self._rebuild_repairable_rollups(conn)
            else:
                with conn:
                    rebuild = self._rebuild_repairable_rollups(conn)
        diagnosis = self.diagnose_maintenance()
        if action == "sync_json_and_rebuild":
            message = (
                "JSON 历史已同步，"
                f"清理 {rebuild['removed_rollups']} 个多余汇总并重建 "
                f"{rebuild['rebuilt_rollups']} 个可还原汇总桶。"
            )
        elif action == "clean_invalid_records":
            message = (
                f"已移除 {removed_invalid_timestamps} 条无效时间记录和 "
                f"{removed_missing_prices} 条缺少价格的记录，清理 "
                f"{rebuild['removed_rollups']} 个多余汇总并重建 "
                f"{rebuild['rebuilt_rollups']} 个可还原汇总桶。"
            )
        else:
            message = (
                f"清理 {rebuild['removed_rollups']} 个多余汇总并重建 "
                f"{rebuild['rebuilt_rollups']} 个可还原汇总桶，"
                "原始明细保持不变。"
            )
        return {
            "ok": True,
            "action": action,
            "inserted_points": inserted,
            "supplemented_fields": supplemented,
            "removed_invalid_timestamps": removed_invalid_timestamps,
            "removed_missing_prices": removed_missing_prices,
            **rebuild,
            "diagnosis": diagnosis,
            "message": message,
        }

    def _sync_json_items(self, conn, json_items):
        timestamps = [item["timestamp"] for item in json_items]
        existing = {}
        for offset in range(0, len(timestamps), 500):
            batch = timestamps[offset:offset + 500]
            placeholders = ",".join("?" for _item in batch)
            rows = conn.execute(
                f"""
                SELECT timestamp, usd, rmb, rate FROM price_history
                WHERE timestamp IN ({placeholders})
                """,
                batch,
            ).fetchall()
            existing.update({
                row[0]: {"usd": row[1], "rmb": row[2], "rate": row[3]}
                for row in rows
            })
        inserted = sum(1 for item in json_items if item["timestamp"] not in existing)
        supplemented = sum(
            1
            for item in json_items
            for field in ("usd", "rmb", "rate")
            if (
                item["timestamp"] in existing
                and existing[item["timestamp"]].get(field) is None
                and item.get(field) is not None
            )
        )
        conn.executemany(
            """
            INSERT INTO price_history(timestamp, time, usd, rmb, rate)
            VALUES(:timestamp, :time, :usd, :rmb, :rate)
            ON CONFLICT(timestamp) DO UPDATE SET
                time = CASE
                    WHEN price_history.time = '' THEN excluded.time
                    ELSE price_history.time
                END,
                usd = COALESCE(price_history.usd, excluded.usd),
                rmb = COALESCE(price_history.rmb, excluded.rmb),
                rate = COALESCE(price_history.rate, excluded.rate)
            """,
            json_items,
        )
        return inserted, supplemented
