import sys
from types import SimpleNamespace


def test_build_check_commands_preserves_existing_release_checks():
    from scripts.run_checks import build_check_commands

    commands = build_check_commands("darwin")

    assert commands[0][:3] == [sys.executable, "-m", "py_compile"]
    assert [sys.executable, "tests/risk_contract_check.py"] in commands
    assert [sys.executable, "tests/gold_cache_check.py"] in commands
    assert [sys.executable, "tests/engineering_foundation_check.py"] in commands
    assert [sys.executable, "tests/alert_log_ui_contract_check.py"] in commands
    assert [sys.executable, "tests/frontend_asset_check.py"] in commands
    assert commands[-2] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_single_instance_app.py",
        "tests/test_update_app.py",
        "tests/test_verify_release_assets_script.py",
    ]
    assert commands[-1] == [sys.executable, "-m", "pytest", "-q"]


def test_windows_commands_include_existing_powershell_contract():
    from scripts.run_checks import build_check_commands

    windows_commands = build_check_commands("win32")
    macos_commands = build_check_commands("darwin")
    powershell_command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "tests/contract_checks.ps1",
    ]

    assert powershell_command in windows_commands
    assert powershell_command not in macos_commands


def test_run_checks_stops_at_first_failure_and_reports_command(capsys):
    from scripts.run_checks import run_checks

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
    assert "检查失败 (9)" in captured.err
    assert "python second.py" in captured.err


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
