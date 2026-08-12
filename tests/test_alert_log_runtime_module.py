from datetime import datetime
from types import SimpleNamespace


class StubAlertLogStore:
    def __init__(self):
        self.entries = {}
        self.memory_entries = None
        self.saved = []
        self.clear_result = True

    @staticmethod
    def db_path():
        return "/tmp/alert-log.sqlite3"

    @staticmethod
    def generate_id():
        return "alert-fixed"

    @staticmethod
    def coerce_bool(value, default=False):
        if value is None:
            return default
        return bool(value)

    @staticmethod
    def normalize_entry(entry, default_read=False):
        normalized = dict(entry)
        normalized.setdefault("read", default_read)
        return normalized

    @staticmethod
    def connect_db():
        return "connection"

    def save_entry(self, entry):
        saved = dict(entry)
        self.saved.append(saved)
        return saved

    def load_archive(self, limit=None):
        return [{"id": "loaded", "limit": limit}]

    def clear_archive(self):
        return self.clear_result

    @staticmethod
    def apply_status(entry, read=None, acknowledged=None):
        updated = dict(entry)
        if read is not None:
            updated["read"] = read
        if acknowledged is not None:
            updated["acknowledged"] = acknowledged
        return updated

    @staticmethod
    def apply_handling(entry, handled=None, note=None):
        updated = dict(entry)
        if handled is not None:
            updated["handled"] = handled
        if note is not None:
            updated["handling_note"] = note
        return updated

    @staticmethod
    def replace_memory_entry(memory_entries, updated):
        for index, entry in enumerate(memory_entries):
            if entry.get("id") == updated.get("id"):
                memory_entries[index] = updated
                return

    def update_entry_payload(self, alert_id, updater, memory_entries=None):
        self.memory_entries = memory_entries
        current = next(
            (entry for entry in memory_entries if entry.get("id") == alert_id),
            None,
        )
        if current is None:
            return False, None
        updated = updater(dict(current))
        self.replace_memory_entry(memory_entries, updated)
        return True, updated

    @staticmethod
    def export_entries(memory_entries, limit=None):
        return list(memory_entries[-limit:])

    @staticmethod
    def format_notifications(entry):
        return ";".join(entry.get("notifications", []))

    @staticmethod
    def build_csv(memory_entries):
        return "csv-body", len(memory_entries)


def _runtime(notification_resender=None):
    from goldmonitor.alert_log_runtime import AlertLogRuntime

    store = StubAlertLogStore()
    state = SimpleNamespace(
        alert_log=[
            {
                "id": "alert-1",
                "type": "warning",
                "read": False,
                "handled": False,
            }
        ]
    )
    runtime = AlertLogRuntime(
        state,
        store_factory=lambda: store,
        alert_level_label=lambda alert_type: {
            "warning": "关注",
            "critical": "重要",
        }.get(alert_type, "提醒"),
        notification_resender=notification_resender,
        now_factory=lambda: datetime(2026, 8, 11, 12, 0, 0),
    )
    return runtime, state, store


def test_alert_log_runtime_delegates_store_operations_and_memory_state():
    runtime, state, store = _runtime()

    assert runtime.db_path() == "/tmp/alert-log.sqlite3"
    assert runtime.generate_id() == "alert-fixed"
    assert runtime.coerce_bool(None, True) is True
    assert runtime.normalize_entry({"id": "alert-2"}, default_read=True)["read"] is True
    assert runtime.connect_db() == "connection"
    assert runtime.save_entry({"id": "alert-2"}) == {"id": "alert-2"}
    assert runtime.load_archive(5) == [{"id": "loaded", "limit": 5}]
    assert runtime.clear_archive() is True

    ok, status_entry = runtime.update_status(
        "alert-1",
        read=True,
        acknowledged=True,
    )
    assert ok is True
    assert status_entry["read"] is True
    assert status_entry["acknowledged"] is True
    assert store.memory_entries is state.alert_log

    ok, handled_entry = runtime.update_handling(
        "alert-1",
        handled=True,
        note="已处理",
    )
    assert ok is True
    assert handled_entry["handled"] is True
    assert handled_entry["handling_note"] == "已处理"
    assert state.alert_log[0] == handled_entry

    runtime.replace_memory_entry({**handled_entry, "read": False})
    assert state.alert_log[0]["read"] is False
    assert runtime.export_entries(1) == [state.alert_log[0]]
    assert runtime.format_notifications({"notifications": ["邮件", "Webhook"]}) == "邮件;Webhook"
    assert runtime.build_csv() == ("csv-body", 1)


def test_alert_log_runtime_builds_resend_title_and_forwards_notification_contract():
    captured = {}

    def notification_resender(alert_id, **kwargs):
        captured["alert_id"] = alert_id
        captured.update(kwargs)
        return True, {"id": alert_id}

    runtime, _state, _store = _runtime(
        notification_resender=notification_resender
    )
    callbacks = {
        "update_entry": lambda *args: args,
        "plan_notifications": lambda *args: args,
        "summarize_notifications": lambda *args: args,
        "deliver_notifications": lambda *args: args,
        "persist_update": lambda *args: args,
        "start_notification_delivery": lambda *args: args,
        "title_builder": lambda entry: entry.get("title", ""),
    }

    result = runtime.resend_notification(
        "alert-1",
        settings={"email_warning_enabled": True},
        blocking=True,
        start_delivery=False,
        **callbacks,
    )

    assert result == (True, {"id": "alert-1"})
    assert captured["alert_id"] == "alert-1"
    assert captured["settings"] == {"email_warning_enabled": True}
    assert captured["blocking"] is True
    assert captured["start_delivery"] is False
    assert captured["now_factory"]() == datetime(2026, 8, 11, 12, 0, 0)
    for name, callback in callbacks.items():
        assert captured[name] is callback

    assert runtime.resend_title({"type": "warning"}) == "金价预警 - 关注"
    assert runtime.resend_title({"type": "critical", "title": "自定义标题"}) == "自定义标题"
