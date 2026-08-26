import threading
from types import SimpleNamespace


def _runtime_state():
    return SimpleNamespace(
        data_archive_lock=threading.Lock(),
        price_refresh_lock=threading.RLock(),
        price_history_maintenance_lock=threading.Lock(),
        risk_analysis_lock=threading.RLock(),
        daily_digest_lock=threading.RLock(),
        today_overview_lock=threading.RLock(),
        lock=threading.RLock(),
        settings_lock=threading.RLock(),
        risk_history_lock=threading.RLock(),
        review_notes_lock=threading.RLock(),
        investment_plan_lock=threading.RLock(),
        app_settings={},
        portfolio_positions=[],
        portfolio_transactions=[],
        portfolio_investment_plans=[],
        portfolio_import_backup={},
        alert_rules=[],
        alert_profiles=[],
        review_notes=[],
        news_items=[],
        news_last_updated="old",
        news_last_error="old",
        risk_analysis_history=[],
        source_health={},
        alert_log=[],
        price_archive=[],
        price_usd=None,
        price_rmb=None,
        previous_usd=None,
        previous_rmb=None,
        usdcny_rate=None,
        usdcny_rate_source="old",
        usdcny_rate_time="old",
        usdcny_rate_cached=True,
        usdcny_rate_error="old",
        gold_price_source="old",
        gold_price_time="old",
        gold_price_cached=True,
        gold_price_error="old",
        market_quality_history=[{"quality_level": "stale"}],
        market_quality_last_saved_monotonic=42.0,
        market_quality_alert_state={"incident_active": True},
        market_quality_alert_last_saved_monotonic=84.0,
        today_date="old",
        today_open_usd=1,
        today_high_usd=1,
        today_low_usd=1,
        today_open_rmb=1,
        today_high_rmb=1,
        today_low_rmb=1,
        alert_cooldown_state={"rule": "old"},
        alerted_flags={"rule": True},
    )


def test_data_archive_runtime_reloads_all_persisted_state_and_market_snapshot():
    from goldmonitor.data_archive_runtime import DataArchiveRuntime

    state = _runtime_state()
    calls = []
    service = DataArchiveRuntime(
        state,
        loaders={
            "settings": lambda: {"theme": "dark"},
            "portfolio_positions": lambda: [{"id": "position-1"}],
            "portfolio_transactions": lambda: [{"id": "transaction-1"}],
            "portfolio_investment_plans": lambda: [{"id": "plan-1"}],
            "portfolio_import_backup": lambda: {"available": True},
            "alert_rules": lambda: [{"id": "rule-1"}],
            "sync_legacy_alert_rule_views": lambda: calls.append("sync-rules"),
            "alert_profiles": lambda: [{"id": "profile-1"}],
            "review_notes": lambda: [{"id": "note-1"}],
            "news": lambda: [{"title": "news"}],
            "risk_analysis_history": lambda: [{"id": "risk-1"}],
            "alert_log": lambda: [{"id": "alert-1"}],
            "market_quality_history": lambda: [
                {
                    "quality_level": "normal",
                    "first_seen_at": "2026-08-26T10:00:00Z",
                }
            ],
            "market_quality_alert_state": lambda: {
                "incident_active": False,
            },
            "price_history": lambda: [{"usd": 2350, "rmb": 545, "rate": 7.2}],
        },
        source_health_loader=lambda: {"source": {"ok": True}},
        restore_price_history_state=lambda archive: calls.append(
            ("restore-history", list(archive))
        ),
        initialize_market_cache=lambda: calls.append("market-cache"),
        get_settings=lambda: dict(state.app_settings),
        save_settings=lambda settings: settings,
        archive_manager=lambda: None,
        apply_floating_price_settings=lambda settings: None,
        clear_price_history_repair_backup=lambda: True,
    )

    service.reload_from_disk()

    assert state.app_settings == {"theme": "dark"}
    assert state.price_usd == 2350
    assert state.price_rmb == 545
    assert state.previous_usd == 2350
    assert state.usdcny_rate == 7.2
    assert state.news_last_updated is None
    assert state.alert_cooldown_state == {}
    assert state.market_quality_history[0]["quality_level"] == "normal"
    assert state.market_quality_alert_state == {"incident_active": False}
    assert state.market_quality_last_saved_monotonic == 0.0
    assert state.market_quality_alert_last_saved_monotonic == 0.0
    assert calls[0] == "sync-rules"
    assert calls[-1] == "market-cache"


def test_data_archive_runtime_restore_applies_reload_and_floating_settings():
    from goldmonitor.data_archive_runtime import DataArchiveRuntime

    state = _runtime_state()
    calls = []

    class TrackingLock:
        def __init__(self):
            self.held = False

        def __enter__(self):
            assert self.held is False
            self.held = True
            return self

        def __exit__(self, exc_type, exc, traceback):
            self.held = False

    state.data_archive_lock = TrackingLock()
    state.price_history_maintenance_lock = TrackingLock()

    class Manager:
        def restore(self, path, apply_callback, rollback_callback):
            assert state.data_archive_lock.held is True
            assert state.price_history_maintenance_lock.held is True
            calls.append(("restore", path))
            apply_callback({}, {})
            return {"ok": True, "restored": 1}

    empty_loaders = {
        "settings": lambda: {"floating_price_enabled": False},
        "portfolio_positions": list,
        "portfolio_transactions": list,
        "portfolio_investment_plans": list,
        "portfolio_import_backup": dict,
        "alert_rules": list,
        "sync_legacy_alert_rule_views": lambda: None,
        "alert_profiles": list,
        "review_notes": list,
        "news": list,
        "risk_analysis_history": list,
        "alert_log": list,
        "market_quality_history": list,
        "market_quality_alert_state": dict,
        "price_history": list,
    }
    service = DataArchiveRuntime(
        state,
        loaders=empty_loaders,
        source_health_loader=dict,
        restore_price_history_state=lambda archive: None,
        initialize_market_cache=lambda: None,
        get_settings=lambda: dict(state.app_settings),
        save_settings=lambda settings: calls.append(("save", settings)),
        archive_manager=Manager,
        apply_floating_price_settings=(
            lambda settings: calls.append(("floating", settings))
        ),
        clear_price_history_repair_backup=lambda: (
            calls.append("clear-repair-backup") or True
        ),
    )

    result = service.restore("backup.zip")

    assert result == {
        "ok": True,
        "restored": 1,
        "repair_backup_cleared": True,
    }
    assert state.data_archive_lock.held is False
    assert state.price_history_maintenance_lock.held is False
    assert calls[0] == ("restore", "backup.zip")
    assert calls[-2] == "clear-repair-backup"
    assert calls[-1] == ("floating", {"floating_price_enabled": False})
