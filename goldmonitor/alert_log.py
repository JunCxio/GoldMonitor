import csv
import io
import json
import logging
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime

from goldmonitor.time_utils import to_local_naive


HANDLING_NOTE_LIMIT = 200


class AlertLogStore:
    def __init__(self, appdata_dir, memory_limit=50, db_limit=5000, export_limit=1000, id_factory=None, logger=None):
        self.appdata_dir = appdata_dir
        self.memory_limit = int(memory_limit)
        self.db_limit = int(db_limit)
        self.export_limit = int(export_limit)
        self.id_factory = id_factory or self.generate_id
        self.logger = logger or logging.getLogger(__name__)

    def db_path(self):
        return os.path.join(self.appdata_dir, "alert_log.sqlite3")

    @staticmethod
    def generate_id():
        return "alert-" + secrets.token_hex(10)

    @staticmethod
    def coerce_bool(value, default=False):
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off", ""}:
            return False
        return default

    @staticmethod
    def parse_datetime(value):
        return to_local_naive(value)

    def normalize_entry(self, entry, default_read=False):
        if not isinstance(entry, dict):
            return None
        normalized = dict(entry)
        normalized["id"] = str(normalized.get("id") or normalized.get("alert_id") or self.id_factory())
        timestamp = str(normalized.get("timestamp") or datetime.now().isoformat(timespec="seconds"))
        parsed = self.parse_datetime(timestamp)
        if parsed:
            timestamp = parsed.isoformat(timespec="seconds")
        normalized["timestamp"] = timestamp
        normalized["time"] = str(normalized.get("time") or (parsed.strftime("%H:%M:%S") if parsed else ""))
        normalized["type"] = str(normalized.get("type") or "warning")
        normalized["mode"] = str(normalized.get("mode") or "")
        normalized["message"] = str(normalized.get("message") or "")
        normalized["read"] = self.coerce_bool(normalized.get("read"), default_read)
        normalized["acknowledged"] = self.coerce_bool(normalized.get("acknowledged"), False)
        if normalized["acknowledged"]:
            normalized["read"] = True
        normalized["read_at"] = str(normalized.get("read_at") or "")
        normalized["acknowledged_at"] = str(normalized.get("acknowledged_at") or "")
        normalized["handled"] = self.coerce_bool(normalized.get("handled"), False)
        if normalized["handled"]:
            normalized["read"] = True
        normalized["handled_at"] = str(normalized.get("handled_at") or "")
        normalized["handling_note"] = str(normalized.get("handling_note") or "").strip()[:HANDLING_NOTE_LIMIT]
        try:
            retry_count = int(normalized.get("notification_auto_retry_count") or 0)
        except (TypeError, ValueError):
            retry_count = 0
        normalized["notification_auto_retry_count"] = max(0, min(3, retry_count))
        normalized["notification_retry_next_at"] = str(
            normalized.get("notification_retry_next_at") or ""
        )
        normalized["last_notification_auto_retry_at"] = str(
            normalized.get("last_notification_auto_retry_at") or ""
        )
        return normalized

    def connect_db(self):
        os.makedirs(self.appdata_dir, exist_ok=True)
        conn = sqlite3.connect(self.db_path(), timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                time TEXT,
                alert_type TEXT,
                mode TEXT,
                message TEXT,
                payload TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_log_timestamp ON alert_log(timestamp)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_log_type ON alert_log(alert_type)")
        return conn

    def save_entry(self, entry):
        normalized = self.normalize_entry(entry)
        if not normalized:
            return None
        entry.update(normalized)
        payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), default=str)
        with closing(self.connect_db()) as conn, conn:
            conn.execute(
                """
                INSERT INTO alert_log(timestamp, time, alert_type, mode, message, payload)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.get("timestamp", ""),
                    normalized.get("time", ""),
                    normalized.get("type", ""),
                    normalized.get("mode", ""),
                    normalized.get("message", ""),
                    payload,
                ),
            )
            conn.execute(
                """
                DELETE FROM alert_log
                WHERE id NOT IN (
                    SELECT id FROM alert_log ORDER BY id DESC LIMIT ?
                )
                """,
                (self.db_limit,),
            )
        return normalized

    def load_archive(self, limit=None):
        limit = self.memory_limit if limit is None else limit
        try:
            with closing(self.connect_db()) as conn:
                rows = conn.execute(
                    "SELECT id, payload FROM alert_log ORDER BY id DESC LIMIT ?",
                    (max(1, int(limit)),),
                ).fetchall()
            items = []
            for row_id, payload in reversed(rows):
                try:
                    parsed = json.loads(payload)
                except (TypeError, json.JSONDecodeError):
                    continue
                if isinstance(parsed, dict) and not (parsed.get("id") or parsed.get("alert_id")):
                    parsed["id"] = f"db-{row_id}"
                normalized = self.normalize_entry(parsed, default_read=True)
                if normalized:
                    items.append(normalized)
            return items
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.logger.warning("读取告警记录数据库失败: %s", exc)
            return []

    def clear_archive(self):
        try:
            with closing(self.connect_db()) as conn, conn:
                conn.execute("DELETE FROM alert_log")
            return True
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("清空告警记录数据库失败: %s", exc)
            return False

    def apply_status(self, entry, read=None, acknowledged=None):
        now = datetime.now().isoformat(timespec="seconds")
        if read is not None:
            is_read = self.coerce_bool(read, entry.get("read", False))
            entry["read"] = is_read
            entry["read_at"] = now if is_read else ""
        if acknowledged is not None:
            is_acknowledged = self.coerce_bool(acknowledged, entry.get("acknowledged", False))
            entry["acknowledged"] = is_acknowledged
            entry["acknowledged_at"] = now if is_acknowledged else ""
            if is_acknowledged:
                entry["read"] = True
                entry["read_at"] = entry.get("read_at") or now
        return entry

    def apply_handling(self, entry, handled=None, note=None):
        now = datetime.now().isoformat(timespec="seconds")
        if handled is not None:
            is_handled = self.coerce_bool(handled, entry.get("handled", False))
            entry["handled"] = is_handled
            entry["handled_at"] = now if is_handled else ""
            if is_handled:
                entry["read"] = True
                entry["read_at"] = entry.get("read_at") or now
            elif note is None:
                entry["handling_note"] = ""
        if note is not None:
            entry["handling_note"] = str(note or "").strip()[:HANDLING_NOTE_LIMIT]
        return entry

    @staticmethod
    def replace_memory_entry(memory_entries, updated):
        target_id = updated.get("id")
        if not target_id:
            return
        for index, entry in enumerate(memory_entries or []):
            if isinstance(entry, dict) and entry.get("id") == target_id:
                memory_entries[index] = updated
                return

    def update_entry_payload(self, alert_id, updater, memory_entries=None):
        target_id = str(alert_id or "").strip()
        if not target_id:
            return False, None

        try:
            with closing(self.connect_db()) as conn, conn:
                rows = conn.execute(
                    "SELECT id, payload FROM alert_log ORDER BY id DESC LIMIT ?",
                    (self.db_limit,),
                ).fetchall()
                for row_id, payload in rows:
                    try:
                        parsed = json.loads(payload)
                    except (TypeError, json.JSONDecodeError):
                        continue
                    if isinstance(parsed, dict) and not (parsed.get("id") or parsed.get("alert_id")):
                        parsed["id"] = f"db-{row_id}"
                    normalized = self.normalize_entry(parsed, default_read=True)
                    if not normalized or normalized.get("id") != target_id:
                        continue
                    updated = updater(normalized)
                    normalized_updated = self.normalize_entry(updated, default_read=True)
                    if not normalized_updated:
                        return False, None
                    conn.execute(
                        """
                        UPDATE alert_log
                        SET timestamp = ?, time = ?, alert_type = ?, mode = ?, message = ?, payload = ?
                        WHERE id = ?
                        """,
                        (
                            normalized_updated.get("timestamp", ""),
                            normalized_updated.get("time", ""),
                            normalized_updated.get("type", ""),
                            normalized_updated.get("mode", ""),
                            normalized_updated.get("message", ""),
                            json.dumps(normalized_updated, ensure_ascii=False, separators=(",", ":"), default=str),
                            row_id,
                        ),
                    )
                    self.replace_memory_entry(memory_entries, normalized_updated)
                    return True, normalized_updated
        except (OSError, sqlite3.Error) as exc:
            self.logger.warning("更新告警记录状态失败: %s", exc)

        for entry in memory_entries or []:
            if isinstance(entry, dict) and entry.get("id") == target_id:
                normalized = self.normalize_entry(entry) or entry
                updated = self.normalize_entry(updater(normalized))
                if not updated:
                    return False, None
                entry.update(updated)
                try:
                    self.save_entry(entry)
                except (OSError, sqlite3.Error) as exc:
                    self.logger.warning("保存告警记录状态失败: %s", exc)
                return True, updated

        return False, None

    def export_entries(self, memory_entries, limit=None):
        limit = self.export_limit if limit is None else limit
        persisted = self.load_archive(limit=limit)
        if persisted:
            return persisted
        return list(memory_entries[-int(limit):]) if isinstance(memory_entries, list) else []

    @staticmethod
    def format_notifications(entry):
        items = entry.get("notifications")
        if not isinstance(items, list):
            return ""
        parts = []
        for item in items:
            if not isinstance(item, dict):
                continue
            label = item.get("label") or item.get("channel") or "通知"
            status = item.get("status") or ""
            message = item.get("message") or ""
            parts.append(f"{label}:{status}:{message}".strip(":"))
        return "；".join(parts)

    @staticmethod
    def format_notification_summary(entry):
        summary = entry.get("notification_summary")
        if not isinstance(summary, dict):
            return ""
        status = summary.get("status") or ""
        label = summary.get("label") or ""
        message = summary.get("message") or ""
        return f"{status}:{label}:{message}".strip(":")

    def build_csv(self, memory_entries, limit=None):
        items = self.export_entries(memory_entries, limit=limit)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "timestamp",
            "time",
            "type",
            "mode",
            "rule_id",
            "rule_kind",
            "rule_name",
            "rule_condition",
            "message",
            "read",
            "acknowledged",
            "handled",
            "handled_at",
            "handling_note",
            "notification_summary",
            "notifications",
            "related_news",
            "market_observation",
        ])
        for entry in items:
            related = entry.get("related_news")
            if isinstance(related, list):
                news_text = "；".join(str(item.get("title") or "") for item in related if isinstance(item, dict))
            else:
                news_text = ""
            writer.writerow([
                entry.get("timestamp", ""),
                entry.get("time", ""),
                entry.get("type", ""),
                entry.get("mode", ""),
                entry.get("rule_id", ""),
                entry.get("rule_kind", ""),
                entry.get("rule_name", ""),
                json.dumps(entry.get("rule_condition") or {}, ensure_ascii=False, separators=(",", ":")),
                entry.get("message", ""),
                "yes" if entry.get("read") else "no",
                "yes" if entry.get("acknowledged") else "no",
                "yes" if entry.get("handled") else "no",
                entry.get("handled_at", ""),
                entry.get("handling_note", ""),
                self.format_notification_summary(entry),
                self.format_notifications(entry),
                news_text,
                json.dumps(
                    entry.get("market_observation") or {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            ])
        return output.getvalue(), len(items)
