from datetime import datetime
from types import SimpleNamespace
import threading


class StubLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, error):
        self.warnings.append((message, str(error)))


class StubRiskStore:
    def __init__(self):
        self.saved = []
        self.raise_on_save = False
        self.raise_on_clear = False

    def normalize(self, items):
        return list(items or [])

    def load(self):
        return [{"id": "loaded"}]

    def save(self, items):
        if self.raise_on_save:
            raise OSError("save failed")
        self.saved.append(list(items))
        return list(items)

    def clear(self):
        if self.raise_on_clear:
            raise OSError("clear failed")
        return self.save([])

    @staticmethod
    def build_state(items):
        return {"items": list(items)}

    @staticmethod
    def add_entry(history, result, snapshot):
        entry = {
            "id": "risk-new",
            "content": result["content"],
            "snapshot": snapshot,
        }
        return [entry, *list(history)], entry


class StubPriceStore:
    def __init__(self):
        self.saved = []
        self.state_archives = []
        self.csv_archives = []
        self.maintenance_actions = []

    def normalize(self, items):
        return list(items or [])

    @staticmethod
    def db_path():
        return "/tmp/price-history.sqlite3"

    @staticmethod
    def connect_db():
        return "connection"

    @staticmethod
    def upsert_points(items):
        return list(items)

    @staticmethod
    def load_from_db():
        return [{"id": "db"}]

    @staticmethod
    def filter_from_db(minutes=None, limit=600):
        return [{"minutes": minutes, "limit": limit}]

    @staticmethod
    def load_json_archive():
        return [{"id": "json"}]

    @staticmethod
    def load_archive():
        return [{"id": "archive"}]

    @staticmethod
    def write_json_archive(items):
        return list(items)

    def save_archive(self, items):
        snapshot = list(items)
        self.saved.append(snapshot)
        return snapshot

    @staticmethod
    def diagnose_maintenance():
        return {"status": "healthy"}

    @staticmethod
    def preview_maintenance_repair(action):
        return {"action": action, "executable": True}

    def execute_maintenance_repair(self, action, expected_effects=None):
        self.maintenance_actions.append((action, expected_effects))
        return {"ok": True, "action": action}

    @staticmethod
    def add_entry(archive, last_saved_at, entry, force_save=False):
        point = dict(entry)
        return [*list(archive), point], 42.0 if force_save else last_saved_at, point

    @staticmethod
    def filter_archive(archive, minutes=None, limit=600):
        items = list(archive)
        return items[-limit:] if limit else items

    def build_state(
        self,
        archive,
        minutes=None,
        limit=600,
        build_events=None,
        format_number=None,
    ):
        self.state_archives.append(archive)
        return {
            "items": list(archive),
            "minutes": minutes,
            "limit": limit,
            "events": build_events(list(archive)),
            "formatted": format_number(1.23456),
        }

    def build_csv(self, archive, minutes=None):
        self.csv_archives.append(archive)
        return f"minutes={minutes}", len(archive)


def _build_runtime(
    *,
    state=None,
    risk_store=None,
    price_store=None,
    logger=None,
    save_export_file=None,
):
    from goldmonitor.history_runtime import HistoryReviewRuntime

    state = state or SimpleNamespace(
        lock=threading.RLock(),
        risk_history_lock=threading.RLock(),
        review_notes_lock=threading.RLock(),
        price_history_maintenance_lock=threading.Lock(),
        risk_analysis_history=[],
        price_archive=[],
        last_price_history_save_at=0.0,
        news_items=[],
        review_notes=[],
        today_date="2026-08-11",
    )
    risk_store = risk_store or StubRiskStore()
    price_store = price_store or StubPriceStore()
    logger = logger or StubLogger()
    saved_exports = []

    def default_save_export_file(filename, content):
        saved_exports.append((filename, content))
        return {"filename": filename}

    runtime = HistoryReviewRuntime(
        state,
        risk_history_store_factory=lambda: risk_store,
        price_history_store_factory=lambda: price_store,
        alert_log_reader=lambda limit: [{"id": f"alert-{limit}"}],
        get_fetch_status=lambda: {"status": "ok"},
        get_source_health_state=lambda: {"items": [{"name": "gold"}]},
        get_source_comparison_state=lambda: {"status": "normal"},
        news_key=lambda item: item.get("url", ""),
        save_export_file=save_export_file or default_save_export_file,
        event_types=("price_summary", "alert", "risk_analysis", "news"),
        allowed_minutes=(60, 240),
        default_minutes=60,
        default_limit=300,
        max_limit=500,
        risk_history_limit=2,
        news_limit=2,
        alert_log_export_limit=1000,
        price_history_export_limit=5000,
        review_report_prefix="GoldMonitor-review-report",
        format_number=lambda value: round(value, 2),
        now_factory=lambda: datetime(2026, 8, 11, 12, 0, 0),
        logger=logger,
    )
    return runtime, state, risk_store, price_store, logger, saved_exports


def test_history_runtime_adds_risk_entry_and_logs_persistence_failures():
    risk_store = StubRiskStore()
    risk_store.raise_on_save = True
    runtime, state, _risk_store, _price_store, logger, _exports = _build_runtime(
        risk_store=risk_store
    )
    state.risk_analysis_history = [{"id": "risk-old"}]

    entry = runtime.add_risk_history_entry(
        {"content": "风险升高"},
        {"analysis_time": "2026-08-11T11:59:00"},
    )

    assert entry["id"] == "risk-new"
    assert [item["id"] for item in state.risk_analysis_history] == [
        "risk-new",
        "risk-old",
    ]
    assert logger.warnings == [
        ("failed to save risk analysis history: %s", "save failed")
    ]

    risk_store.raise_on_clear = True
    cleared = runtime.clear_risk_history()

    assert cleared == {"items": []}
    assert state.risk_analysis_history == []
    assert logger.warnings[-1] == (
        "failed to clear risk analysis history: %s",
        "clear failed",
    )


def test_history_runtime_uses_price_snapshots_for_save_state_and_csv():
    runtime, state, _risk_store, price_store, _logger, _exports = _build_runtime()
    state.price_archive = [{"timestamp": "2026-08-11T11:59:00", "rmb": 760.1}]

    saved = runtime.save_price_history_archive()
    price_state = runtime.build_price_history_state(minutes=60, limit=20)
    csv_text, count = runtime.build_price_history_csv(minutes=240)

    assert saved == state.price_archive
    assert price_store.saved[0] is not state.price_archive
    assert price_store.state_archives[0] is not state.price_archive
    assert price_store.csv_archives[0] is not state.price_archive
    assert price_state["items"] == state.price_archive
    assert price_state["minutes"] == 60
    assert price_state["limit"] == 20
    assert price_state["formatted"] == 1.23
    assert csv_text == "minutes=240"
    assert count == 1

    point = runtime.add_price_history_entry(
        {"timestamp": "2026-08-11T12:00:00", "rmb": 760.2},
        force_save=True,
    )

    assert point["rmb"] == 760.2
    assert state.price_archive[-1] == point
    assert state.last_price_history_save_at == 42.0


def test_history_runtime_proxies_maintenance_and_refreshes_archive():
    runtime, state, _risk_store, price_store, _logger, _exports = _build_runtime()
    state.price_archive = [{"id": "old"}]

    diagnosis = runtime.diagnose_price_history_maintenance()
    preview = runtime.preview_price_history_repair("rebuild_rollups")
    expected_effects = {"rollup_buckets_to_rebuild": 4}
    result = runtime.execute_price_history_repair(
        "rebuild_rollups",
        expected_effects,
    )

    assert diagnosis == {"status": "healthy"}
    assert preview == {"action": "rebuild_rollups", "executable": True}
    assert result == {"ok": True, "action": "rebuild_rollups"}
    assert price_store.maintenance_actions == [
        ("rebuild_rollups", expected_effects),
    ]
    assert state.price_archive == [{"id": "db"}]


def test_history_runtime_builds_timeline_sources_from_bounded_state_snapshots():
    state = SimpleNamespace(
        lock=threading.RLock(),
        risk_history_lock=threading.RLock(),
        review_notes_lock=threading.RLock(),
        risk_analysis_history=[{"id": "risk-1"}, {"id": "risk-2"}, {"id": "risk-3"}],
        price_archive=[],
        last_price_history_save_at=0.0,
        news_items=[{"url": "news-1"}, {"url": "news-2"}, {"url": "news-3"}],
        review_notes=[{"id": "note-1"}],
        today_date="2026-08-11",
    )
    runtime, _state, _risk_store, _price_store, _logger, _exports = _build_runtime(
        state=state
    )

    sources = runtime.event_sources()

    assert sources["alert_entries"] == [{"id": "alert-1000"}]
    assert [item["id"] for item in sources["risk_items"]] == ["risk-1", "risk-2"]
    assert [item["url"] for item in sources["news_items"]] == ["news-1", "news-2"]
    assert sources["review_notes"] == [{"id": "note-1"}]
    assert sources["fetch_status"] == {"status": "ok"}
    assert sources["source_health_state"] == {"items": [{"name": "gold"}]}
    assert sources["source_comparison_state"] == {"status": "normal"}
    assert sources["today_date"] == "2026-08-11"
    assert sources["news_key"]({"url": "news-1"}) == "news-1"
    assert sources["now_factory"]() == datetime(2026, 8, 11, 12, 0, 0)


def test_history_runtime_uses_default_review_report_filename(monkeypatch):
    from goldmonitor import event_timeline

    saved = []
    runtime, _state, _risk_store, _price_store, _logger, _exports = _build_runtime(
        save_export_file=lambda filename, content: saved.append((filename, content))
        or {"path": filename}
    )
    monkeypatch.setattr(
        event_timeline,
        "review_report_filename",
        lambda prefix: f"{prefix}-fixed.md",
    )

    result = runtime.save_review_report("report body")

    assert result == {"path": "GoldMonitor-review-report-fixed.md"}
    assert saved == [("GoldMonitor-review-report-fixed.md", "report body")]
