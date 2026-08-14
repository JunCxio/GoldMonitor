import logging
from datetime import datetime

from goldmonitor import event_timeline as event_timeline_core


class HistoryReviewRuntime:
    def __init__(
        self,
        state,
        *,
        risk_history_store_factory,
        price_history_store_factory,
        alert_log_reader,
        get_fetch_status,
        get_source_health_state,
        get_source_comparison_state,
        news_key,
        save_export_file,
        event_types,
        allowed_minutes,
        default_minutes,
        default_limit,
        max_limit,
        risk_history_limit,
        news_limit,
        alert_log_export_limit,
        price_history_export_limit,
        review_report_prefix,
        format_number,
        now_factory=datetime.now,
        logger=logging,
    ):
        self.state = state
        self.risk_history_store_factory = risk_history_store_factory
        self.price_history_store_factory = price_history_store_factory
        self.alert_log_reader = alert_log_reader
        self.get_fetch_status = get_fetch_status
        self.get_source_health_state = get_source_health_state
        self.get_source_comparison_state = get_source_comparison_state
        self.news_key = news_key
        self.save_export_file = save_export_file
        self.event_types = tuple(event_types)
        self.allowed_minutes = tuple(allowed_minutes)
        self.default_minutes = default_minutes
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.risk_history_limit = risk_history_limit
        self.news_limit = news_limit
        self.alert_log_export_limit = alert_log_export_limit
        self.price_history_export_limit = price_history_export_limit
        self.review_report_prefix = review_report_prefix
        self.format_number = format_number
        self.now_factory = now_factory
        self.logger = logger

    def risk_store(self):
        return self.risk_history_store_factory()

    def price_store(self):
        return self.price_history_store_factory()

    def normalize_risk_history(self, items):
        return self.risk_store().normalize(items)

    def load_risk_history(self):
        return self.risk_store().load()

    def save_risk_history(self, items=None):
        items = self.state.risk_analysis_history if items is None else items
        return self.risk_store().save(items)

    def risk_history_state(self):
        with self.state.risk_history_lock:
            return self.risk_store().build_state(self.state.risk_analysis_history)

    def add_risk_history_entry(self, result, snapshot):
        with self.state.risk_history_lock:
            store = self.risk_store()
            self.state.risk_analysis_history, entry = store.add_entry(
                self.state.risk_analysis_history,
                result,
                snapshot,
            )
            try:
                store.save(self.state.risk_analysis_history)
            except OSError as exc:
                self.logger.warning("failed to save risk analysis history: %s", exc)
            return entry

    def clear_risk_history(self):
        with self.state.risk_history_lock:
            self.state.risk_analysis_history = []
            try:
                self.risk_store().clear()
            except OSError as exc:
                self.logger.warning("failed to clear risk analysis history: %s", exc)
            return self.risk_store().build_state(self.state.risk_analysis_history)

    def normalize_price_history(self, items):
        return self.price_store().normalize(items)

    def price_history_db_path(self):
        return self.price_store().db_path()

    def connect_price_history_db(self):
        return self.price_store().connect_db()

    def upsert_price_history_points(self, items):
        with self.state.price_history_maintenance_lock:
            return self.price_store().upsert_points(items)

    def load_price_history_from_db(self):
        return self.price_store().load_from_db()

    def filter_price_history_from_db(self, minutes=None, limit=600):
        return self.price_store().filter_from_db(minutes=minutes, limit=limit)

    def load_price_history_json_archive(self):
        return self.price_store().load_json_archive()

    def load_price_history_archive(self):
        return self.price_store().load_archive()

    def write_price_history_json_archive(self, items):
        with self.state.price_history_maintenance_lock:
            return self.price_store().write_json_archive(items)

    def save_price_history_archive(self, items=None):
        if items is None:
            with self.state.lock:
                items = list(self.state.price_archive)
        with self.state.price_history_maintenance_lock:
            return self.price_store().save_archive(items)

    def diagnose_price_history_maintenance(self):
        with self.state.price_history_maintenance_lock:
            return self.price_store().diagnose_maintenance()

    def preview_price_history_repair(self, action):
        with self.state.price_history_maintenance_lock:
            return self.price_store().preview_maintenance_repair(action)

    def execute_price_history_repair(self, action):
        with self.state.price_history_maintenance_lock:
            store = self.price_store()
            result = store.execute_maintenance_repair(action)
        with self.state.lock:
            self.state.price_archive = store.load_from_db()
        return result

    def add_price_history_entry(self, entry, force_save=False):
        with self.state.price_history_maintenance_lock:
            (
                self.state.price_archive,
                self.state.last_price_history_save_at,
                point,
            ) = self.price_store().add_entry(
                self.state.price_archive,
                self.state.last_price_history_save_at,
                entry,
                force_save=force_save,
            )
        return point

    def filter_price_archive(self, minutes=None, limit=600):
        with self.state.lock:
            items = list(self.state.price_archive)
        return self.price_store().filter_archive(
            items,
            minutes=minutes,
            limit=limit,
        )

    def event_time_from_alert(self, entry):
        return event_timeline_core.event_time_from_alert(
            entry,
            today_date=self.state.today_date,
        )

    def normalize_timeline_request(self, data=None):
        return event_timeline_core.normalize_event_timeline_request(
            data,
            event_types=self.event_types,
            allowed_minutes=self.allowed_minutes,
            default_minutes=self.default_minutes,
            default_limit=self.default_limit,
            max_limit=self.max_limit,
        )

    def timeline_range(self, minutes):
        return event_timeline_core.event_timeline_range(
            minutes,
            now_factory=self.now_factory,
        )

    @staticmethod
    def make_timeline_event(
        event_type,
        timestamp,
        title,
        summary,
        source,
        payload=None,
        event_id=None,
    ):
        return event_timeline_core.make_timeline_event(
            event_type,
            timestamp,
            title,
            summary,
            source,
            payload,
            event_id,
        )

    @staticmethod
    def build_event_price_summary(points):
        return event_timeline_core.build_event_price_summary(points)

    @staticmethod
    def build_price_summary_timeline_event(points, start_time, end_time):
        return event_timeline_core.build_price_summary_timeline_event(
            points,
            start_time,
            end_time,
        )

    def event_sources(self):
        with self.state.risk_history_lock:
            risk_items = list(
                self.state.risk_analysis_history[: self.risk_history_limit]
            )
        with self.state.lock:
            news_items = list(self.state.news_items[: self.news_limit])
        with self.state.review_notes_lock:
            review_notes = list(self.state.review_notes)
        return {
            "alert_entries": self.alert_log_reader(
                limit=self.alert_log_export_limit
            ),
            "risk_items": risk_items,
            "news_items": news_items,
            "review_notes": review_notes,
            "fetch_status": self.get_fetch_status(),
            "source_health_state": self.get_source_health_state(),
            "source_comparison_state": self.get_source_comparison_state(),
            "today_date": self.state.today_date,
            "news_key": self.news_key,
            "now_factory": self.now_factory,
        }

    def build_alert_timeline_events(self, start_time, end_time):
        return event_timeline_core.build_alert_timeline_events(
            start_time,
            end_time,
            alert_entries=self.alert_log_reader(
                limit=self.alert_log_export_limit
            ),
            today_date=self.state.today_date,
        )

    def build_risk_timeline_events(self, start_time, end_time):
        with self.state.risk_history_lock:
            risk_items = list(
                self.state.risk_analysis_history[: self.risk_history_limit]
            )
        return event_timeline_core.build_risk_timeline_events(
            start_time,
            end_time,
            risk_items=risk_items,
        )

    def build_news_timeline_events(self, start_time, end_time):
        with self.state.lock:
            news_items = list(self.state.news_items[: self.news_limit])
        return event_timeline_core.build_news_timeline_events(
            start_time,
            end_time,
            news_items=news_items,
            news_key=self.news_key,
        )

    def build_data_status_timeline_events(self, start_time, end_time):
        return event_timeline_core.build_data_status_timeline_events(
            start_time,
            end_time,
            fetch_status=self.get_fetch_status(),
            source_health_state=self.get_source_health_state(),
            source_comparison_state=self.get_source_comparison_state(),
            now_factory=self.now_factory,
        )

    def build_event_timeline_events(self, start_time, end_time, types=None):
        return event_timeline_core.build_event_timeline_events(
            start_time,
            end_time,
            types,
            **self.event_sources(),
        )

    def build_event_timeline_state(self, minutes=None, limit=None, types=None):
        if limit is None:
            limit = self.default_limit
        points = self.filter_price_archive(
            minutes=minutes,
            limit=self.price_history_export_limit,
        )
        return event_timeline_core.build_event_timeline_state(
            minutes=minutes,
            limit=limit,
            types=types,
            price_points=points,
            **self.event_sources(),
        )

    def build_price_event_state(self, items):
        return event_timeline_core.build_price_chart_events(
            items,
            self.build_event_timeline_events,
        )

    @staticmethod
    def alert_level_label(alert_type):
        return event_timeline_core.alert_level_label(alert_type)

    def build_price_history_state(self, minutes=None, limit=600):
        with self.state.lock:
            items = list(self.state.price_archive)
        return self.price_store().build_state(
            items,
            minutes=minutes,
            limit=limit,
            build_events=self.build_price_event_state,
            format_number=self.format_number,
        )

    def build_price_history_csv(self, minutes=None):
        with self.state.lock:
            items = list(self.state.price_archive)
        return self.price_store().build_csv(items, minutes=minutes)

    @staticmethod
    def build_review_report(timeline_state):
        return event_timeline_core.build_review_report(timeline_state)

    def save_review_report(self, content, filename=None):
        if not filename:
            filename = event_timeline_core.review_report_filename(
                prefix=self.review_report_prefix
            )
        return self.save_export_file(filename, content)
