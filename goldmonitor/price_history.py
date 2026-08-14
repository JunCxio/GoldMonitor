import csv
import io
import json
import logging
import math
import os
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload
from goldmonitor.price_history_maintenance import (
    ROLLUP_RESOLUTIONS,
    PriceHistoryMaintenanceMixin,
)


PRICE_HISTORY_DB_SCHEMA_VERSION = 2
def history_number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def history_timestamp(value):
    parsed = parse_iso_datetime(value)
    return parsed.replace(tzinfo=None) if parsed and parsed.tzinfo else parsed


def kline_bucket_start(timestamp, minutes=5):
    return timestamp.replace(
        minute=(timestamp.minute // minutes) * minutes,
        second=0,
        microsecond=0,
    )


def ohlc(values):
    if not values:
        return {"open": None, "high": None, "low": None, "close": None}
    return {
        "open": values[0],
        "high": max(values),
        "low": min(values),
        "close": values[-1],
    }


def build_5min_klines(history_items, limit=96):
    points = []
    for item in history_items or []:
        if not isinstance(item, dict):
            continue
        timestamp = history_timestamp(item.get("timestamp"))
        if not timestamp:
            continue
        usd = history_number(item.get("usd"))
        rmb = history_number(item.get("rmb"))
        if usd is not None or rmb is not None:
            points.append((timestamp, usd, rmb))
    if len(points) < 2:
        return []

    buckets = []
    bucket_by_timestamp = {}
    for timestamp, usd, rmb in sorted(points, key=lambda point: point[0]):
        bucket_start = kline_bucket_start(timestamp)
        bucket_key = bucket_start.isoformat(timespec="seconds")
        if bucket_key not in bucket_by_timestamp:
            bucket_by_timestamp[bucket_key] = {
                "time": bucket_start.strftime("%H:%M"),
                "timestamp": bucket_key,
                "usd": [],
                "rmb": [],
            }
            buckets.append(bucket_by_timestamp[bucket_key])
        if usd is not None:
            bucket_by_timestamp[bucket_key]["usd"].append(usd)
        if rmb is not None:
            bucket_by_timestamp[bucket_key]["rmb"].append(rmb)

    candles = []
    for bucket in buckets:
        usd = ohlc(bucket["usd"])
        rmb = ohlc(bucket["rmb"])
        candles.append({
            **usd,
            "open_rmb": rmb["open"],
            "high_rmb": rmb["high"],
            "low_rmb": rmb["low"],
            "close_rmb": rmb["close"],
            "time": bucket["time"],
            "timestamp": bucket["timestamp"],
        })
    return candles[-int(limit or 96):]


def parse_iso_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


class PriceHistoryStore(PriceHistoryMaintenanceMixin):
    def __init__(
        self,
        json_path,
        archive_limit=20000,
        export_limit=5000,
        save_interval_seconds=60,
        raw_retention_minutes=24 * 60,
        raw_interval_seconds=10,
        logger=None,
    ):
        self.json_path = json_path
        self.archive_limit = int(archive_limit)
        self.export_limit = int(export_limit)
        self.save_interval_seconds = int(save_interval_seconds)
        self.raw_retention_minutes = int(raw_retention_minutes)
        self.raw_interval_seconds = max(1, int(raw_interval_seconds))
        self.logger = logger or logging.getLogger(__name__)

    def db_path(self):
        base, _ext = os.path.splitext(self.json_path)
        return base + ".sqlite3"

    def _normalize_items(self, items, max_items=None):
        if not isinstance(items, list):
            return []
        normalized = []
        for item in items:
            if not isinstance(item, dict):
                continue
            timestamp = str(item.get("timestamp") or "").strip()
            if not timestamp:
                continue
            parsed = parse_iso_datetime(timestamp)
            if not parsed:
                continue

            def optional_float(key):
                value = item.get(key)
                if value in (None, ""):
                    return None
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    return None
                return number if math.isfinite(number) else None

            normalized.append({
                "usd": optional_float("usd"),
                "rmb": optional_float("rmb"),
                "rate": optional_float("rate"),
                "time": str(item.get("time") or parsed.strftime("%H:%M:%S")),
                "timestamp": parsed.isoformat(timespec="seconds"),
            })
        normalized.sort(key=lambda item: item.get("timestamp", ""))
        if max_items:
            normalized = normalized[-int(max_items):]
        return normalized

    def normalize(self, items):
        return self._normalize_items(items, max_items=self.archive_limit)

    @staticmethod
    def _bucket_timestamp(timestamp, interval_seconds):
        parsed = parse_iso_datetime(timestamp)
        if not parsed:
            return ""
        seconds_from_day_start = parsed.hour * 3600 + parsed.minute * 60 + parsed.second
        bucket_seconds = seconds_from_day_start - (seconds_from_day_start % int(interval_seconds))
        bucket = parsed.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(seconds=bucket_seconds)
        return bucket.isoformat(timespec="seconds")

    def _rollup_rows(self, items):
        rows = []
        for item in items:
            for resolution, interval_seconds, _retention_minutes in ROLLUP_RESOLUTIONS:
                bucket_timestamp = self._bucket_timestamp(item.get("timestamp"), interval_seconds)
                if not bucket_timestamp:
                    continue
                rows.append({
                    "resolution": resolution,
                    "bucket_timestamp": bucket_timestamp,
                    "time": bucket_timestamp[11:19],
                    "usd": item.get("usd"),
                    "rmb": item.get("rmb"),
                    "rate": item.get("rate"),
                    "last_timestamp": item.get("timestamp"),
                })
        return rows

    @staticmethod
    def _upsert_rollups(conn, rows):
        if not rows:
            return
        conn.executemany(
            """
            INSERT INTO price_history_rollups(
                resolution, bucket_timestamp, time, usd, rmb, rate, last_timestamp
            ) VALUES(
                :resolution, :bucket_timestamp, :time, :usd, :rmb, :rate, :last_timestamp
            )
            ON CONFLICT(resolution, bucket_timestamp) DO UPDATE SET
                time = CASE
                    WHEN excluded.last_timestamp >= price_history_rollups.last_timestamp
                    THEN excluded.time ELSE price_history_rollups.time END,
                usd = CASE
                    WHEN excluded.last_timestamp >= price_history_rollups.last_timestamp
                    THEN COALESCE(excluded.usd, price_history_rollups.usd)
                    ELSE price_history_rollups.usd END,
                rmb = CASE
                    WHEN excluded.last_timestamp >= price_history_rollups.last_timestamp
                    THEN COALESCE(excluded.rmb, price_history_rollups.rmb)
                    ELSE price_history_rollups.rmb END,
                rate = CASE
                    WHEN excluded.last_timestamp >= price_history_rollups.last_timestamp
                    THEN COALESCE(excluded.rate, price_history_rollups.rate)
                    ELSE price_history_rollups.rate END,
                last_timestamp = MAX(price_history_rollups.last_timestamp, excluded.last_timestamp)
            """,
            rows,
        )

    def _backfill_rollups(self, conn):
        rows = conn.execute(
            """
            SELECT usd, rmb, rate, time, timestamp
            FROM price_history
            ORDER BY timestamp ASC
            """
        ).fetchall()
        items = [
            {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
            for row in rows
        ]
        self._upsert_rollups(conn, self._rollup_rows(items))

    def _migrate_database(self, conn):
        row = conn.execute(
            "SELECT value FROM price_history_metadata WHERE key = 'schema_version'"
        ).fetchone()
        try:
            schema_version = int(row[0]) if row else 1
        except (TypeError, ValueError):
            schema_version = 1
        if schema_version < PRICE_HISTORY_DB_SCHEMA_VERSION:
            self._backfill_rollups(conn)
            conn.execute(
                """
                INSERT INTO price_history_metadata(key, value)
                VALUES('schema_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(PRICE_HISTORY_DB_SCHEMA_VERSION),),
            )

    def _cleanup_retention(self, conn, latest_timestamp):
        latest_time = parse_iso_datetime(latest_timestamp)
        if not latest_time:
            return
        if self.raw_retention_minutes > 0:
            raw_cutoff = latest_time - timedelta(minutes=self.raw_retention_minutes)
            conn.execute(
                "DELETE FROM price_history WHERE timestamp < ?",
                (raw_cutoff.isoformat(timespec="seconds"),),
            )
        conn.execute(
            """
            DELETE FROM price_history
            WHERE timestamp NOT IN (
                SELECT timestamp FROM price_history
                ORDER BY timestamp DESC
                LIMIT ?
            )
            """,
            (self.archive_limit,),
        )
        for resolution, _interval_seconds, retention_minutes in ROLLUP_RESOLUTIONS:
            if retention_minutes is None:
                continue
            cutoff = latest_time - timedelta(minutes=retention_minutes)
            conn.execute(
                """
                DELETE FROM price_history_rollups
                WHERE resolution = ? AND bucket_timestamp < ?
                """,
                (resolution, cutoff.isoformat(timespec="seconds")),
            )

    def connect_db(self):
        path = self.db_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        conn = sqlite3.connect(path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history (
                timestamp TEXT PRIMARY KEY,
                time TEXT NOT NULL,
                usd REAL,
                rmb REAL,
                rate REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history_rollups (
                resolution TEXT NOT NULL,
                bucket_timestamp TEXT NOT NULL,
                time TEXT NOT NULL,
                usd REAL,
                rmb REAL,
                rate REAL,
                last_timestamp TEXT NOT NULL,
                PRIMARY KEY(resolution, bucket_timestamp)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_price_history_rollups_time
            ON price_history_rollups(resolution, bucket_timestamp)
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS price_history_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        self._migrate_database(conn)
        conn.commit()
        return conn

    def upsert_points(self, items):
        normalized = self.normalize(items)
        if not normalized:
            return []
        with closing(self.connect_db()) as conn, conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO price_history(timestamp, time, usd, rmb, rate)
                VALUES(:timestamp, :time, :usd, :rmb, :rate)
                """,
                normalized,
            )
            self._upsert_rollups(conn, self._rollup_rows(normalized))
            self._cleanup_retention(conn, normalized[-1]["timestamp"])
        return normalized

    def load_from_db(self):
        if not os.path.exists(self.db_path()):
            return []
        with closing(self.connect_db()) as conn:
            rows = conn.execute(
                """
                SELECT usd, rmb, rate, time, timestamp
                FROM price_history
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (self.archive_limit,),
            ).fetchall()
        return self._normalize_items([
            {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
            for row in rows
        ], max_items=self.archive_limit)

    def query_resolution(self, minutes=None, limit=600):
        if not minutes:
            return {
                "resolution": "raw",
                "interval_seconds": self.raw_interval_seconds,
                "retention_minutes": self.raw_retention_minutes,
            }
        minutes = max(1, int(minutes))
        limit = max(1, int(limit or self.export_limit))
        candidates = [
            ("raw", self.raw_interval_seconds, self.raw_retention_minutes),
            *ROLLUP_RESOLUTIONS,
        ]
        eligible = []
        for resolution, interval_seconds, retention_minutes in candidates:
            if retention_minutes is not None and minutes > retention_minutes:
                continue
            eligible.append((resolution, interval_seconds, retention_minutes))
            expected_points = math.ceil(minutes * 60 / interval_seconds)
            if expected_points <= limit:
                return {
                    "resolution": resolution,
                    "interval_seconds": interval_seconds,
                    "retention_minutes": retention_minutes,
                }
        resolution, interval_seconds, retention_minutes = eligible[-1] if eligible else ROLLUP_RESOLUTIONS[-1]
        return {
            "resolution": resolution,
            "interval_seconds": interval_seconds,
            "retention_minutes": retention_minutes,
        }

    def filter_from_db(self, minutes=None, limit=600):
        if not os.path.exists(self.db_path()):
            return []
        limit = max(1, int(limit or self.export_limit))
        plan = self.query_resolution(minutes=minutes, limit=limit)
        with closing(self.connect_db()) as conn:
            if plan["resolution"] == "raw":
                latest_row = conn.execute("SELECT MAX(timestamp) FROM price_history").fetchone()
                params = []
                where = ""
                if minutes and latest_row and latest_row[0]:
                    latest_time = parse_iso_datetime(latest_row[0]) or datetime.now()
                    cutoff = latest_time - timedelta(minutes=int(minutes))
                    where = "WHERE timestamp >= ?"
                    params.append(cutoff.isoformat(timespec="seconds"))
                params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT usd, rmb, rate, time, timestamp
                    FROM price_history
                    {where}
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
            else:
                resolution = plan["resolution"]
                latest_row = conn.execute(
                    """
                    SELECT MAX(bucket_timestamp)
                    FROM price_history_rollups
                    WHERE resolution = ?
                    """,
                    (resolution,),
                ).fetchone()
                params = [resolution]
                where = "resolution = ?"
                if minutes and latest_row and latest_row[0]:
                    latest_time = parse_iso_datetime(latest_row[0]) or datetime.now()
                    cutoff = latest_time - timedelta(minutes=int(minutes))
                    where += " AND bucket_timestamp >= ?"
                    params.append(cutoff.isoformat(timespec="seconds"))
                params.append(limit)
                rows = conn.execute(
                    f"""
                    SELECT usd, rmb, rate, time, bucket_timestamp
                    FROM price_history_rollups
                    WHERE {where}
                    ORDER BY bucket_timestamp DESC
                    LIMIT ?
                    """,
                    params,
                ).fetchall()
        rows.reverse()
        return self._normalize_items([
            {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
            for row in rows
        ])

    def load_json_archive(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def load_archive(self):
        try:
            db_items = self.load_from_db()
            if db_items:
                return db_items
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("价格历史数据库读取失败: %s", exc)

        json_items = self.load_json_archive()
        if json_items:
            try:
                self.upsert_points(json_items)
            except (OSError, sqlite3.Error) as exc:
                self.logger.warning("价格历史迁移到 SQLite 失败: %s", exc)
        return json_items

    def write_json_archive(self, items):
        normalized = self.normalize(items)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(wrap_item_payload(normalized), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized

    def save_archive(self, items):
        normalized = self.normalize(items)
        try:
            self.upsert_points(normalized)
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("价格历史写入 SQLite 失败: %s", exc)
        self.write_json_archive(normalized)
        return normalized

    def add_entry(self, archive, last_saved_at, entry, force_save=False):
        normalized = self.normalize([entry])
        if not normalized:
            return list(archive or []), last_saved_at, None
        point = normalized[0]
        next_archive = list(archive or [])
        next_archive.append(point)
        if len(next_archive) > self.archive_limit:
            next_archive = next_archive[-self.archive_limit:]
        try:
            self.upsert_points([point])
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("价格历史增量写入 SQLite 失败: %s", exc)
        now_monotonic = time.monotonic()
        next_saved_at = last_saved_at
        if force_save or now_monotonic - float(last_saved_at or 0) >= self.save_interval_seconds:
            try:
                next_archive = self.write_json_archive(next_archive)
                next_saved_at = now_monotonic
            except OSError as exc:
                self.logger.warning("价格历史保存失败: %s", exc)
        return next_archive, next_saved_at, point

    def filter_archive(self, archive, minutes=None, limit=600):
        items = list(archive or [])
        if minutes or len(items) < int(limit or 0):
            try:
                db_items = self.filter_from_db(minutes=minutes, limit=limit)
                if db_items:
                    return db_items
            except (OSError, sqlite3.Error) as exc:
                self.logger.warning("价格历史数据库查询失败: %s", exc)
        if minutes:
            latest_time = parse_iso_datetime(items[-1].get("timestamp")) if items else datetime.now()
            cutoff = (latest_time or datetime.now()) - timedelta(minutes=int(minutes))
            items = [
                item for item in items
                if (parse_iso_datetime(item.get("timestamp")) or cutoff) >= cutoff
            ]
        if limit:
            items = items[-int(limit):]
        return items

    @staticmethod
    def _format_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return round(number, 4)

    def build_state(self, archive, minutes=None, limit=600, build_events=None, format_number=None):
        items = self.filter_archive(archive, minutes, limit)
        format_number = format_number or self._format_number
        resolution = self.query_resolution(minutes=minutes, limit=limit)

        def series_stats(field):
            values = [item.get(field) for item in items if item.get(field) is not None]
            if not values:
                return {"points": 0, "start": None, "end": None, "high": None, "low": None, "change": None, "change_pct": None}
            start = values[0]
            end = values[-1]
            change = end - start
            return {
                "points": len(values),
                "start": format_number(start),
                "end": format_number(end),
                "high": format_number(max(values)),
                "low": format_number(min(values)),
                "change": format_number(change),
                "change_pct": format_number(change / start * 100 if start else 0),
            }

        return {
            "items": items,
            "stats": {
                "usd": series_stats("usd"),
                "rmb": series_stats("rmb"),
            },
            "total": len(items),
            "minutes": minutes,
            "resolution": resolution["resolution"],
            "resolution_seconds": resolution["interval_seconds"],
            "events": build_events(items) if callable(build_events) else [],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }

    def build_csv(self, archive, minutes=None):
        items = self.filter_archive(archive, minutes, self.export_limit)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["timestamp", "time", "usd_per_oz", "rmb_per_gram", "usdcny_rate"])
        for item in items:
            writer.writerow([
                item.get("timestamp", ""),
                item.get("time", ""),
                item.get("usd", ""),
                item.get("rmb", ""),
                item.get("rate", ""),
            ])
        return output.getvalue(), len(items)
