import csv
import io
import json
import logging
import math
import os
import sqlite3
import time
from datetime import datetime, timedelta

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


def parse_iso_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


class PriceHistoryStore:
    def __init__(self, json_path, archive_limit=20000, export_limit=5000, save_interval_seconds=60, logger=None):
        self.json_path = json_path
        self.archive_limit = int(archive_limit)
        self.export_limit = int(export_limit)
        self.save_interval_seconds = int(save_interval_seconds)
        self.logger = logger or logging.getLogger(__name__)

    def db_path(self):
        base, _ext = os.path.splitext(self.json_path)
        return base + ".sqlite3"

    def normalize(self, items):
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
        return normalized[-self.archive_limit:]

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
        return conn

    def upsert_points(self, items):
        normalized = self.normalize(items)
        if not normalized:
            return []
        with self.connect_db() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO price_history(timestamp, time, usd, rmb, rate)
                VALUES(:timestamp, :time, :usd, :rmb, :rate)
                """,
                normalized,
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
        return normalized

    def load_from_db(self):
        if not os.path.exists(self.db_path()):
            return []
        with self.connect_db() as conn:
            rows = conn.execute(
                """
                SELECT usd, rmb, rate, time, timestamp
                FROM price_history
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (self.archive_limit,),
            ).fetchall()
        return self.normalize([
            {"usd": row[0], "rmb": row[1], "rate": row[2], "time": row[3], "timestamp": row[4]}
            for row in rows
        ])

    def filter_from_db(self, minutes=None, limit=600):
        if not os.path.exists(self.db_path()):
            return []
        params = []
        where = ""
        if minutes:
            latest_items = self.load_from_db()
            latest_time = parse_iso_datetime(latest_items[-1].get("timestamp")) if latest_items else datetime.now()
            cutoff = (latest_time or datetime.now()) - timedelta(minutes=int(minutes))
            where = "WHERE timestamp >= ?"
            params.append(cutoff.isoformat(timespec="seconds"))
        params.append(int(limit or self.export_limit))
        with self.connect_db() as conn:
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
        rows.reverse()
        return self.normalize([
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
        if len(items) < int(limit or 0):
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
