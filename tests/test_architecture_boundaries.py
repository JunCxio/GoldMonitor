from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(path):
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_app_is_only_a_compatibility_entrypoint():
    source = read_text("app.py")

    assert "from goldmonitor import application" in source
    assert "application.main()" in source
    assert "sys.modules[__name__] = application" in source
    assert "Flask(" not in source
    assert "SocketIO(" not in source


def test_application_composes_routes_sockets_state_and_desktop_services():
    source = read_text("goldmonitor/application.py")

    assert "application_state_bootstrap_core.ApplicationStateBootstrap(" in source
    assert "alert_log_runtime_core.AlertLogRuntime(" in source
    assert "alert_notification_runtime_core.AlertNotificationRuntime(" in source
    assert "daily_digest_runtime_core.DailyDigestRuntime(" in source
    assert "notification_adapters_core.NotificationAdapters(" in source
    assert "platform_integration_runtime_core.PlatformIntegrationRuntime(" in source
    assert "update_runtime_core.UpdateRuntime(" in source
    assert "settings_runtime_core.SettingsRuntime(" in source
    assert "history_runtime_core.HistoryReviewRuntime(" in source
    assert "floating_controller_core.FloatingPriceController(" in source
    assert "taskbar_controller_core.TaskbarPriceController(" in source
    assert "http_routes_core.register_http_routes(" in source
    assert "socket_bootstrap_core.register_socket_handlers(" in source
    assert "application_bootstrap_core.run_application(" in source
    assert "@socketio.on(" not in source
    assert "@app.route(" not in source


def test_notification_runtime_only_reexports_split_responsibilities():
    source = read_text("goldmonitor/notification_runtime.py")

    assert "from goldmonitor.alert_delivery_runtime import" in source
    assert "from goldmonitor.daily_digest_delivery_runtime import" in source
    assert "from goldmonitor.desktop_notification_runtime import" in source
    assert "from goldmonitor.notification_channel_runtime import" in source
    assert "def " not in source
    assert len(source.splitlines()) < 60


def test_notifications_only_reexports_policy_transport_and_delivery():
    source = read_text("goldmonitor/notifications.py")

    assert "from goldmonitor.notification_delivery import" in source
    assert "from goldmonitor.notification_policy import" in source
    assert "from goldmonitor.notification_transport import" in source
    assert "def " not in source
    assert len(source.splitlines()) < 80


def test_runtime_data_initialization_has_one_explicit_entrypoint():
    source = read_text("goldmonitor/application.py")
    stripped_lines = [line.strip() for line in source.splitlines()]
    direct_boot_assignments = (
        "runtime.app_settings = load_settings()",
        "runtime.alert_rules = load_alert_rules()",
        "runtime.news_items = load_news_cache()",
        "runtime.price_archive = load_price_history_archive()",
    )

    assert stripped_lines.count("initialize_application_state()") == 1
    for assignment in direct_boot_assignments:
        assert assignment not in stripped_lines


def test_frontend_center_entries_only_bootstrap_split_modules():
    expected_entries = {
        "static/settings-center.js": "setupSettingsInteractions();",
        "static/alert-rule-center.js": "void 0;",
        "static/operations-center.js": "void 0;",
    }

    for path, expected in expected_entries.items():
        lines = [line.strip() for line in read_text(path).splitlines() if line.strip()]
        assert lines == [expected]


def test_large_frontend_domains_are_split_by_responsibility():
    expected_modules = (
        "static/history-review-notes.js",
        "static/history-review-timeline.js",
        "static/risk-analysis-render.js",
        "static/risk-analysis-comparison.js",
        "static/portfolio-review.js",
    )

    for path in expected_modules:
        assert read_text(path).strip()

    for path in (
        "static/history-review-center.js",
        "static/history-review-notes.js",
        "static/history-review-timeline.js",
        "static/risk-analysis-center.js",
        "static/risk-analysis-render.js",
        "static/risk-analysis-comparison.js",
        "static/portfolio-render.js",
        "static/portfolio-review.js",
    ):
        assert len(read_text(path).splitlines()) < 520
