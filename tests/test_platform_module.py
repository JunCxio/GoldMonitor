from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_startup_commands_preserve_packaged_and_script_modes():
    from goldmonitor.platform import (
        build_macos_startup_arguments,
        build_startup_command,
        current_executable,
        macos_launch_agent_path,
    )

    assert current_executable(True, "/Applications/GoldMonitor.app/Contents/MacOS/GoldMonitor", "app.py") == (
        "/Applications/GoldMonitor.app/Contents/MacOS/GoldMonitor"
    )
    assert current_executable(False, "/usr/bin/python3", "app.py") == str(Path("app.py").resolve())
    assert build_startup_command("/tmp/GoldMonitor.exe") == '"/tmp/GoldMonitor.exe" --startup'
    assert build_macos_startup_arguments(True, "/tmp/GoldMonitor", "/tmp/app.py") == ["/tmp/GoldMonitor", "--startup"]
    assert build_macos_startup_arguments(False, "/usr/bin/python3", "/tmp/app.py") == [
        "/usr/bin/python3",
        "/tmp/app.py",
        "--startup",
    ]
    assert macos_launch_agent_path("/Users/dev", "com.example.gold") == (
        "/Users/dev/Library/LaunchAgents/com.example.gold.plist"
    )


def test_macos_launch_agent_payload_is_deterministic():
    from goldmonitor.platform import build_macos_launch_agent_payload

    payload = build_macos_launch_agent_payload(
        "com.example.gold",
        ["/Applications/GoldMonitor.app/Contents/MacOS/GoldMonitor", "--startup"],
        "/Applications/GoldMonitor.app/Contents/MacOS/GoldMonitor",
        "/Users/dev",
    )

    assert payload == {
        "Label": "com.example.gold",
        "ProgramArguments": ["/Applications/GoldMonitor.app/Contents/MacOS/GoldMonitor", "--startup"],
        "RunAtLoad": True,
        "KeepAlive": False,
        "WorkingDirectory": "/Applications/GoldMonitor.app/Contents/MacOS",
    }

    fallback = build_macos_launch_agent_payload("com.example.gold", ["/tmp/app", "--startup"], "", "/Users/dev")
    assert fallback["WorkingDirectory"] == "/Users/dev"


def test_startup_support_policy_matches_platform_contract():
    from goldmonitor.platform import startup_support_result

    assert startup_support_result(True, "darwin", "posix") == (None, None)
    assert startup_support_result(True, "win32", "nt") == (None, None)
    assert startup_support_result(False, "linux", "posix") == (True, None)
    assert startup_support_result(True, "linux", "posix") == (False, "当前平台不支持开机自启动")


def test_close_behavior_decision_uses_remembered_and_explicit_choices():
    from goldmonitor.platform import close_behavior_decision

    assert close_behavior_decision({"close_behavior": "exit", "close_remembered": True}, "windows") == "exit"
    assert close_behavior_decision({"close_behavior": "minimize_to_tray"}, "macos") == "minimize_to_tray"
    assert close_behavior_decision({"close_behavior": "ask"}, "windows") == "ask"
    assert close_behavior_decision({"close_behavior": "ask"}, "other") == "exit"


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("platform module checks passed.")
