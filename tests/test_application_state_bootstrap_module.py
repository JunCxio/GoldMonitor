from datetime import datetime
from types import SimpleNamespace


def test_application_state_bootstrap_loads_all_runtime_state_in_order():
    from goldmonitor.application_state_bootstrap import ApplicationStateBootstrap

    runtime = SimpleNamespace()
    calls = []

    def loader(name, value):
        return lambda: calls.append(name) or value

    def load_alert_log(*, limit):
        calls.append(("alert_log", limit))
        return [{"id": "alert-1"}]

    bootstrap = ApplicationStateBootstrap(
        runtime=runtime,
        loaders={
            "settings": loader("settings", {"theme": "dark"}),
            "alert_rules": loader("alert_rules", [{"id": "rule-1"}]),
            "alert_profiles": loader("alert_profiles", [{"id": "profile-1"}]),
            "review_notes": loader("review_notes", [{"id": "note-1"}]),
            "portfolio_positions": loader("portfolio_positions", [{"id": "position-1"}]),
            "portfolio_transactions": loader("portfolio_transactions", [{"id": "transaction-1"}]),
            "portfolio_import_backup": loader("portfolio_import_backup", {"available": False}),
            "news": loader("news", [{"title": "news-1"}]),
            "risk_analysis_history": loader("risk_analysis_history", [{"id": "risk-1"}]),
            "alert_log": load_alert_log,
            "price_history": loader("price_history", [{"usd": 2300}]),
        },
        save_settings=lambda settings: settings,
        sync_legacy_alert_rule_views=lambda: calls.append("sync_rules"),
        restore_price_history_state=lambda items: calls.append(("restore_price", items)),
        initialize_market_cache=lambda: calls.append("market_cache"),
        settings_file_existed_at_startup=False,
        onboarding_marker_present_at_startup=False,
        alert_log_memory_limit=50,
    )

    assert bootstrap.initialize() is runtime
    assert runtime.app_settings == {"theme": "dark"}
    assert runtime.alert_rules == [{"id": "rule-1"}]
    assert runtime.alert_profiles == [{"id": "profile-1"}]
    assert runtime.review_notes == [{"id": "note-1"}]
    assert runtime.portfolio_positions == [{"id": "position-1"}]
    assert runtime.portfolio_transactions == [{"id": "transaction-1"}]
    assert runtime.portfolio_import_backup == {"available": False}
    assert runtime.news_items == [{"title": "news-1"}]
    assert runtime.risk_analysis_history == [{"id": "risk-1"}]
    assert runtime.alert_log == [{"id": "alert-1"}]
    assert runtime.price_archive == [{"usd": 2300}]
    assert calls.count("sync_rules") == 2
    assert ("alert_log", 50) in calls
    assert ("restore_price", [{"usd": 2300}]) in calls
    assert calls[-1] == "market_cache"


def test_application_state_bootstrap_migrates_existing_settings_marker():
    from goldmonitor.application_state_bootstrap import ApplicationStateBootstrap

    runtime = SimpleNamespace()
    saved = []
    fixed_now = datetime(2026, 7, 28, 9, 30, 0)
    empty_loaders = {
        "settings": lambda: {},
        "alert_rules": lambda: [],
        "alert_profiles": lambda: [],
        "review_notes": lambda: [],
        "portfolio_positions": lambda: [],
        "portfolio_transactions": lambda: [],
        "portfolio_import_backup": lambda: {},
        "news": lambda: [],
        "risk_analysis_history": lambda: [],
        "alert_log": lambda **kwargs: [],
        "price_history": lambda: [],
    }
    bootstrap = ApplicationStateBootstrap(
        runtime=runtime,
        loaders=empty_loaders,
        save_settings=lambda settings: saved.append(dict(settings)) or dict(settings),
        sync_legacy_alert_rule_views=lambda: None,
        restore_price_history_state=lambda items: None,
        initialize_market_cache=lambda: None,
        settings_file_existed_at_startup=True,
        onboarding_marker_present_at_startup=False,
        alert_log_memory_limit=50,
        now_factory=lambda: fixed_now,
    )

    bootstrap.initialize()

    assert saved == [{
        "onboarding_started": True,
        "onboarding_completed": True,
        "onboarding_version": 1,
        "onboarding_completed_at": "2026-07-28T09:30:00",
    }]
    assert runtime.app_settings == saved[0]
