import sys
from types import SimpleNamespace


EXPECTED_COMPILE_TARGETS = (
    "app.py",
    "goldmonitor/application.py",
    "goldmonitor/application_bootstrap.py",
    "goldmonitor/application_state_bootstrap.py",
    "goldmonitor/app_state.py",
    "goldmonitor/runtime_state.py",
    "setup_gui.py",
    "goldmonitor/alert_rules.py",
    "goldmonitor/alert_log_runtime.py",
    "goldmonitor/alert_notification_runtime.py",
    "goldmonitor/alert_delivery_runtime.py",
    "goldmonitor/daily_digest.py",
    "goldmonitor/daily_digest_delivery_runtime.py",
    "goldmonitor/daily_digest_runtime.py",
    "goldmonitor/config_runtime.py",
    "goldmonitor/settings_runtime.py",
    "goldmonitor/history_runtime.py",
    "goldmonitor/desktop_runtime.py",
    "goldmonitor/desktop_status.py",
    "goldmonitor/diagnostics_runtime.py",
    "goldmonitor/export_runtime.py",
    "goldmonitor/floating_controller.py",
    "goldmonitor/floating_runtime.py",
    "goldmonitor/taskbar_controller.py",
    "goldmonitor/taskbar_automation.py",
    "goldmonitor/taskbar_runtime.py",
    "goldmonitor/today_overview.py",
    "goldmonitor/today_overview_runtime.py",
    "goldmonitor/instance_runtime.py",
    "goldmonitor/http_routes.py",
    "goldmonitor/platform_runtime.py",
    "goldmonitor/platform_integration_runtime.py",
    "goldmonitor/market_adapters.py",
    "goldmonitor/market_clients.py",
    "goldmonitor/market_data.py",
    "goldmonitor/market_observation.py",
    "goldmonitor/market_runtime.py",
    "goldmonitor/news.py",
    "goldmonitor/desktop_notification_runtime.py",
    "goldmonitor/notification_adapters.py",
    "goldmonitor/notification_channel_runtime.py",
    "goldmonitor/notification_delivery.py",
    "goldmonitor/notification_policy.py",
    "goldmonitor/notification_retry.py",
    "goldmonitor/notification_retry_runtime.py",
    "goldmonitor/notification_runtime.py",
    "goldmonitor/notification_transport.py",
    "goldmonitor/operations_runtime.py",
    "goldmonitor/data_archive.py",
    "goldmonitor/data_archive_runtime.py",
    "goldmonitor/alert_runtime.py",
    "goldmonitor/portfolio_runtime.py",
    "goldmonitor/portfolio_investment.py",
    "goldmonitor/portfolio_investment_runtime.py",
    "goldmonitor/portfolio_analytics.py",
    "goldmonitor/price_history.py",
    "goldmonitor/price_history_maintenance.py",
    "goldmonitor/risk_analysis.py",
    "goldmonitor/risk_analysis_runtime.py",
    "goldmonitor/review_notes.py",
    "goldmonitor/scheduler.py",
    "goldmonitor/task_scheduler.py",
    "goldmonitor/time_utils.py",
    "goldmonitor/socket_alert_rules.py",
    "goldmonitor/socket_bootstrap.py",
    "goldmonitor/socket_alert_configuration.py",
    "goldmonitor/socket_alert_log.py",
    "goldmonitor/socket_history_review.py",
    "goldmonitor/socket_operations.py",
    "goldmonitor/socket_portfolio.py",
    "goldmonitor/socket_risk_analysis.py",
    "goldmonitor/socket_settings.py",
    "goldmonitor/socket_today_overview.py",
    "goldmonitor/socket_runtime.py",
    "goldmonitor/update_runtime.py",
    "tests/risk_contract_check.py",
    "tests/watch_targets_check.py",
    "tests/update_logic_check.py",
    "tests/startup_contract_check.py",
    "tests/frontend_asset_check.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/test_alert_rules_module.py",
    "tests/test_alert_log_runtime_module.py",
    "tests/test_alert_notification_runtime_module.py",
    "tests/test_notification_retry_module.py",
    "tests/test_alert_batch_actions_app.py",
    "tests/test_architecture_boundaries.py",
    "tests/test_alert_rules_app.py",
    "tests/test_http_assets_app.py",
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_portfolio_module.py",
    "tests/test_portfolio_investment_module.py",
    "tests/test_portfolio_investment_runtime_module.py",
    "tests/test_portfolio_investment_app.py",
    "tests/test_portfolio_investment_frontend.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_risk_analysis_runtime_module.py",
    "tests/test_market_data_module.py",
    "tests/test_market_adapters_module.py",
    "tests/test_market_runtime_module.py",
    "tests/test_time_utils_module.py",
    "tests/test_runtime_state_module.py",
    "tests/test_data_archive_runtime_module.py",
    "tests/test_news_runtime_module.py",
    "tests/test_domain_runtime_modules.py",
    "tests/test_application_bootstrap_module.py",
    "tests/test_application_state_bootstrap_module.py",
    "tests/test_app_state_module.py",
    "tests/test_market_adapters_app.py",
    "tests/test_market_source_management.py",
    "tests/test_data_archive_module.py",
    "tests/test_data_archive_app.py",
    "tests/test_onboarding_app.py",
    "tests/test_portfolio_analytics_module.py",
    "tests/test_portfolio_analytics_app.py",
    "tests/test_settings_store_module.py",
    "tests/test_settings_runtime_module.py",
    "tests/test_history_runtime_module.py",
    "tests/test_price_history_maintenance_module.py",
    "tests/test_price_history_maintenance_app.py",
    "tests/test_price_history_maintenance_frontend.py",
    "tests/test_notifications_module.py",
    "tests/test_notification_adapters_module.py",
    "tests/test_scheduler_module.py",
    "tests/test_task_scheduler_module.py",
    "tests/test_daily_digest_module.py",
    "tests/test_daily_digest_runtime_module.py",
    "tests/test_daily_digest_app.py",
    "tests/test_review_notes_module.py",
    "tests/test_review_notes_app.py",
    "tests/test_event_timeline_module.py",
    "tests/test_instance_runtime_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_update_runtime_module.py",
    "tests/test_export_runtime_module.py",
    "tests/test_platform_module.py",
    "tests/test_platform_runtime_module.py",
    "tests/test_platform_integration_runtime_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/test_desktop_runtime_module.py",
    "tests/test_desktop_status_module.py",
    "tests/test_floating_runtime_module.py",
    "tests/test_floating_controller_module.py",
    "tests/test_taskbar_runtime_module.py",
    "tests/test_taskbar_automation_module.py",
    "tests/test_taskbar_controller_module.py",
    "tests/test_verify_release_assets_script.py",
    "tests/test_open_source_foundation.py",
    "tests/test_run_checks_script.py",
    "tests/test_storage_manifest_module.py",
    "tests/test_today_overview_module.py",
    "tests/test_today_overview_runtime_module.py",
    "tests/test_operations_auto_refresh.py",
    "scripts/verify_release_assets.py",
    "scripts/run_checks.py",
)

EXPECTED_PYTHON_CHECKS = (
    "tests/risk_contract_check.py",
    "tests/watch_targets_check.py",
    "tests/gold_cache_check.py",
    "tests/price_fetch_with_cache_check.py",
    "tests/fetch_status_check.py",
    "tests/threshold_persistence_check.py",
    "tests/socket_connect_check.py",
    "tests/news_logic_check.py",
    "tests/forex_cache_check.py",
    "tests/startup_contract_check.py",
    "tests/update_logic_check.py",
    "tests/port_selection_check.py",
    "tests/event_timeline_review_check.py",
    "tests/engineering_foundation_check.py",
    "tests/test_storage_modules.py",
    "tests/test_alert_log_runtime_module.py",
    "tests/test_alert_notification_runtime_module.py",
    "tests/test_notification_retry_module.py",
    "tests/test_portfolio_module.py",
    "tests/test_portfolio_investment_module.py",
    "tests/test_portfolio_investment_runtime_module.py",
    "tests/test_portfolio_investment_app.py",
    "tests/test_portfolio_investment_frontend.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_risk_analysis_runtime_module.py",
    "tests/test_market_data_module.py",
    "tests/test_market_adapters_module.py",
    "tests/test_market_runtime_module.py",
    "tests/test_settings_store_module.py",
    "tests/test_settings_runtime_module.py",
    "tests/test_history_runtime_module.py",
    "tests/test_price_history_maintenance_module.py",
    "tests/test_notifications_module.py",
    "tests/test_notification_adapters_module.py",
    "tests/test_scheduler_module.py",
    "tests/test_task_scheduler_module.py",
    "tests/test_daily_digest_module.py",
    "tests/test_daily_digest_runtime_module.py",
    "tests/test_review_notes_module.py",
    "tests/test_event_timeline_module.py",
    "tests/test_instance_runtime_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_update_runtime_module.py",
    "tests/test_export_runtime_module.py",
    "tests/test_platform_module.py",
    "tests/test_platform_integration_runtime_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/frontend_asset_check.py",
)

EXPECTED_RELEASE_PYTEST_TARGETS = (
    "tests/test_http_assets_app.py",
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_verify_release_assets_script.py",
)


def expected_darwin_commands():
    return [
        [sys.executable, "-m", "py_compile", *EXPECTED_COMPILE_TARGETS],
        *[[sys.executable, path] for path in EXPECTED_PYTHON_CHECKS],
        [sys.executable, "-m", "pytest", *EXPECTED_RELEASE_PYTEST_TARGETS],
        [sys.executable, "-m", "pytest", "-q"],
    ]


def test_build_check_commands_preserves_existing_release_checks():
    from scripts.run_checks import build_check_commands

    commands = build_check_commands("darwin")

    assert commands == expected_darwin_commands()


def test_windows_commands_include_existing_powershell_contract():
    from scripts.run_checks import build_check_commands

    windows_commands = build_check_commands("win32")
    powershell_command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "tests/contract_checks.ps1",
    ]
    darwin_commands = expected_darwin_commands()
    expected_windows_commands = [
        darwin_commands[0],
        powershell_command,
        *darwin_commands[1:],
    ]

    assert windows_commands == expected_windows_commands


def test_run_checks_stops_at_first_failure_and_reports_command(capsys):
    from scripts.run_checks import ROOT, run_checks

    commands = [
        ["python", "first.py"],
        ["python", "second.py"],
        ["python", "third.py"],
    ]
    calls = []

    def fake_runner(command, cwd, check):
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=9 if command[-1] == "second.py" else 0)

    exit_code = run_checks(commands=commands, runner=fake_runner)
    captured = capsys.readouterr()

    assert exit_code == 9
    assert [item[0] for item in calls] == commands[:2]
    assert [item[1] for item in calls] == [ROOT, ROOT]
    assert all(item[2] is False for item in calls)
    assert "检查失败 (9)" in captured.err
    assert "python second.py" in captured.err


def test_run_checks_reports_os_error_without_traceback(capsys):
    from scripts.run_checks import run_checks

    def fake_runner(command, cwd, check):
        raise FileNotFoundError("tool missing")

    exit_code = run_checks(
        commands=[["missing-tool", "--check"]],
        runner=fake_runner,
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "检查失败 (1)" in captured.err
    assert "missing-tool --check" in captured.err
    assert "tool missing" in captured.err
    assert "Traceback" not in captured.err


def test_run_checks_returns_zero_after_all_commands_pass():
    from scripts.run_checks import run_checks

    calls = []

    def fake_runner(command, cwd, check):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    exit_code = run_checks(
        commands=[["python", "first.py"], ["python", "second.py"]],
        runner=fake_runner,
    )

    assert exit_code == 0
    assert len(calls) == 2
