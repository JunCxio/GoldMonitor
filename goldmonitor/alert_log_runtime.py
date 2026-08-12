from datetime import datetime

from goldmonitor import alert_delivery_runtime as alert_delivery_runtime_core


class AlertLogRuntime:
    def __init__(
        self,
        state,
        *,
        store_factory,
        alert_level_label,
        notification_resender=None,
        now_factory=datetime.now,
    ):
        self.state = state
        self.store_factory = store_factory
        self.alert_level_label = alert_level_label
        self.notification_resender = (
            notification_resender
            or alert_delivery_runtime_core.resend_alert_notification
        )
        self.now_factory = now_factory

    def store(self):
        return self.store_factory()

    def db_path(self):
        return self.store().db_path()

    def generate_id(self):
        return self.store().generate_id()

    def coerce_bool(self, value, default=False):
        return self.store().coerce_bool(value, default)

    def normalize_entry(self, entry, default_read=False):
        return self.store().normalize_entry(
            entry,
            default_read=default_read,
        )

    def connect_db(self):
        return self.store().connect_db()

    def save_entry(self, entry):
        return self.store().save_entry(entry)

    def load_archive(self, limit):
        return self.store().load_archive(limit=limit)

    def clear_archive(self):
        return self.store().clear_archive()

    def apply_status(self, entry, read=None, acknowledged=None):
        return self.store().apply_status(
            entry,
            read=read,
            acknowledged=acknowledged,
        )

    def apply_handling(self, entry, handled=None, note=None):
        return self.store().apply_handling(
            entry,
            handled=handled,
            note=note,
        )

    def replace_memory_entry(self, updated):
        return self.store().replace_memory_entry(
            self.state.alert_log,
            updated,
        )

    def update_entry_payload(self, alert_id, updater):
        return self.store().update_entry_payload(
            alert_id,
            updater,
            memory_entries=self.state.alert_log,
        )

    def update_status(self, alert_id, read=None, acknowledged=None):
        store = self.store()
        return store.update_entry_payload(
            alert_id,
            lambda entry: store.apply_status(
                entry,
                read=read,
                acknowledged=acknowledged,
            ),
            memory_entries=self.state.alert_log,
        )

    def update_handling(self, alert_id, handled=None, note=None):
        store = self.store()
        return store.update_entry_payload(
            alert_id,
            lambda entry: store.apply_handling(
                entry,
                handled=handled,
                note=note,
            ),
            memory_entries=self.state.alert_log,
        )

    def resend_title(self, entry):
        return str(
            entry.get("title")
            or f"金价预警 - {self.alert_level_label(entry.get('type'))}"
        )

    def resend_notification(
        self,
        alert_id,
        *,
        settings,
        blocking,
        start_delivery,
        update_entry,
        plan_notifications,
        summarize_notifications,
        deliver_notifications,
        persist_update,
        start_notification_delivery,
        title_builder,
    ):
        return self.notification_resender(
            alert_id,
            settings=settings,
            blocking=blocking,
            start_delivery=start_delivery,
            update_entry=update_entry,
            plan_notifications=plan_notifications,
            summarize_notifications=summarize_notifications,
            deliver_notifications=deliver_notifications,
            persist_update=persist_update,
            start_notification_delivery=start_notification_delivery,
            title_builder=title_builder,
            now_factory=self.now_factory,
        )

    def export_entries(self, limit):
        return self.store().export_entries(
            self.state.alert_log,
            limit=limit,
        )

    def format_notifications(self, entry):
        return self.store().format_notifications(entry)

    def build_csv(self):
        return self.store().build_csv(self.state.alert_log)
