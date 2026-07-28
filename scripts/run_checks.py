import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMPILE_TARGETS = (
    "app.py",
    "setup_gui.py",
    "goldmonitor/alert_rules.py",
    "goldmonitor/daily_digest.py",
    "goldmonitor/instance_runtime.py",
    "goldmonitor/market_adapters.py",
    "goldmonitor/market_data.py",
    "goldmonitor/market_runtime.py",
    "goldmonitor/data_archive.py",
    "goldmonitor/portfolio_analytics.py",
    "goldmonitor/review_notes.py",
    "goldmonitor/scheduler.py",
    "goldmonitor/socket_alert_rules.py",
    "goldmonitor/socket_alert_configuration.py",
    "goldmonitor/socket_alert_log.py",
    "goldmonitor/socket_history_review.py",
    "goldmonitor/socket_operations.py",
    "goldmonitor/socket_portfolio.py",
    "goldmonitor/socket_risk_analysis.py",
    "goldmonitor/socket_settings.py",
    "goldmonitor/update_runtime.py",
    "tests/risk_contract_check.py",
    "tests/watch_targets_check.py",
    "tests/update_logic_check.py",
    "tests/startup_contract_check.py",
    "tests/frontend_asset_check.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/test_alert_rules_module.py",
    "tests/test_alert_rules_app.py",
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_portfolio_module.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_market_data_module.py",
    "tests/test_market_adapters_module.py",
    "tests/test_market_runtime_module.py",
    "tests/test_market_adapters_app.py",
    "tests/test_market_source_management.py",
    "tests/test_data_archive_module.py",
    "tests/test_data_archive_app.py",
    "tests/test_onboarding_app.py",
    "tests/test_portfolio_analytics_module.py",
    "tests/test_portfolio_analytics_app.py",
    "tests/test_settings_store_module.py",
    "tests/test_notifications_module.py",
    "tests/test_scheduler_module.py",
    "tests/test_daily_digest_module.py",
    "tests/test_daily_digest_app.py",
    "tests/test_review_notes_module.py",
    "tests/test_review_notes_app.py",
    "tests/test_event_timeline_module.py",
    "tests/test_instance_runtime_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_update_runtime_module.py",
    "tests/test_platform_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/test_verify_release_assets_script.py",
    "tests/test_open_source_foundation.py",
    "tests/test_run_checks_script.py",
    "tests/test_storage_manifest_module.py",
    "scripts/verify_release_assets.py",
    "scripts/run_checks.py",
)

PYTHON_CHECKS = (
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
    "tests/test_portfolio_module.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_market_data_module.py",
    "tests/test_market_adapters_module.py",
    "tests/test_market_runtime_module.py",
    "tests/test_settings_store_module.py",
    "tests/test_notifications_module.py",
    "tests/test_scheduler_module.py",
    "tests/test_daily_digest_module.py",
    "tests/test_review_notes_module.py",
    "tests/test_event_timeline_module.py",
    "tests/test_instance_runtime_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_update_runtime_module.py",
    "tests/test_platform_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/frontend_asset_check.py",
)

RELEASE_PYTEST_TARGETS = (
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_verify_release_assets_script.py",
)

WINDOWS_CONTRACT_COMMAND = (
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "tests/contract_checks.ps1",
)


def build_check_commands(platform_name=None):
    platform_name = platform_name or sys.platform
    commands = [
        [sys.executable, "-m", "py_compile", *COMPILE_TARGETS],
    ]
    if str(platform_name).lower().startswith("win"):
        commands.append(list(WINDOWS_CONTRACT_COMMAND))
    commands.extend([sys.executable, path] for path in PYTHON_CHECKS)
    commands.append([
        sys.executable,
        "-m",
        "pytest",
        *RELEASE_PYTEST_TARGETS,
    ])
    commands.append([sys.executable, "-m", "pytest", "-q"])
    return commands


def command_text(command):
    return subprocess.list2cmdline([str(part) for part in command])


def run_checks(commands=None, runner=None):
    commands = build_check_commands() if commands is None else commands
    runner = runner or subprocess.run
    for command in commands:
        display = command_text(command)
        print(f"$ {display}", flush=True)
        try:
            result = runner(command, cwd=ROOT, check=False)
        except OSError as error:
            print(
                f"检查失败 (1): {display}: {error}",
                file=sys.stderr,
                flush=True,
            )
            return 1
        if result.returncode:
            print(
                f"检查失败 ({result.returncode}): {display}",
                file=sys.stderr,
                flush=True,
            )
            return result.returncode or 1
    print("GoldMonitor checks passed.", flush=True)
    return 0


def main():
    return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
