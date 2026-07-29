import plistlib
from types import SimpleNamespace
from unittest.mock import Mock


def test_credential_store_override_handles_read_write_and_delete():
    from goldmonitor.platform_runtime import read_credential_secret, write_credential_secret

    store = {"token": "secret"}
    assert read_credential_secret(
        "token",
        store_override=lambda: store,
        os_name="posix",
        sys_platform="linux",
        read_windows=lambda key: "windows",
        read_macos=lambda key: "macos",
    ) == "secret"

    common = {
        "store_override": lambda: store,
        "os_name": "posix",
        "sys_platform": "linux",
        "write_windows": lambda key, value: False,
        "delete_windows": lambda key: False,
        "write_macos": lambda key, value: False,
        "delete_macos": lambda key: False,
    }
    assert write_credential_secret("token", "updated", **common) is True
    assert store["token"] == "updated"
    assert write_credential_secret("token", "", **common) is True
    assert "token" not in store


def test_macos_security_and_credential_commands_use_expected_contract():
    from goldmonitor.platform_runtime import (
        read_macos_credential,
        run_macos_security,
        write_macos_credential,
    )

    runner_calls = []

    def runner(args, **kwargs):
        runner_calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="secret\n", stderr="")

    assert run_macos_security(["find"], runner=runner) == (0, "secret\n", "")
    assert runner_calls[0][0] == ["security", "find"]
    assert runner_calls[0][1]["timeout"] == 5

    commands = []
    assert read_macos_credential(
        "api_key",
        sys_platform="darwin",
        service_name="GoldMonitor",
        run_security=lambda args: commands.append(args) or (0, "value\n", ""),
    ) == "value"
    assert commands[0] == [
        "find-generic-password",
        "-s", "GoldMonitor",
        "-a", "api_key",
        "-w",
    ]

    assert write_macos_credential(
        "api_key",
        "value",
        sys_platform="darwin",
        service_name="GoldMonitor",
        run_security=lambda args: commands.append(args) or (0, "", ""),
    ) is True
    assert commands[1][-2:] == ["value", "-U"]


def test_credential_failures_do_not_log_sensitive_context():
    from goldmonitor.platform_runtime import (
        read_windows_credential,
        write_macos_credential,
        write_windows_credential,
    )

    windows_logger = Mock()

    def fail_windows_types():
        raise RuntimeError("sensitive failure detail")

    assert read_windows_credential(
        "api_key",
        os_name="nt",
        target_name=lambda key: f"GoldMonitor:{key}",
        ctypes_loader=fail_windows_types,
        logger=windows_logger,
    ) == ""
    windows_logger.warning.assert_called_once_with(
        "读取系统凭据失败",
        exc_info=True,
    )

    windows_logger.reset_mock()
    assert write_windows_credential(
        "api_key",
        "secret",
        os_name="nt",
        target_name=lambda key: f"GoldMonitor:{key}",
        ctypes_loader=fail_windows_types,
        logger=windows_logger,
    ) is False
    windows_logger.warning.assert_called_once_with(
        "写入系统凭据失败",
        exc_info=True,
    )

    macos_logger = Mock()
    assert write_macos_credential(
        "api_key",
        "secret",
        sys_platform="darwin",
        service_name="GoldMonitor",
        run_security=lambda args: (1, "", "sensitive failure detail"),
        logger=macos_logger,
    ) is False
    macos_logger.warning.assert_called_once_with("写入 macOS Keychain 失败")


def test_windows_startup_runtime_writes_and_deletes_run_value():
    from goldmonitor.platform_runtime import set_windows_startup_enabled

    calls = []

    class Key:
        def __enter__(self):
            return "key"

        def __exit__(self, exc_type, exc, traceback):
            return False

    winreg = SimpleNamespace(
        HKEY_CURRENT_USER="hkcu",
        KEY_SET_VALUE="set",
        REG_SZ="string",
        CreateKeyEx=lambda root, path, reserved, access: calls.append(
            ("create", root, path, reserved, access)
        ) or Key(),
        SetValueEx=lambda key, name, reserved, value_type, value: calls.append(
            ("set", key, name, reserved, value_type, value)
        ),
        DeleteValue=lambda key, name: calls.append(("delete", key, name)),
    )

    assert set_windows_startup_enabled(
        True,
        run_key_path="Software\\Vendor\\Run",
        run_key_name="GoldMonitor",
        startup_command='"app.exe" --startup',
        winreg_loader=lambda: winreg,
    ) == (True, None)
    assert calls[-1] == (
        "set", "key", "GoldMonitor", 0, "string", '"app.exe" --startup',
    )

    assert set_windows_startup_enabled(
        False,
        run_key_path="Software\\Vendor\\Run",
        run_key_name="GoldMonitor",
        startup_command='"app.exe" --startup',
        winreg_loader=lambda: winreg,
    ) == (True, None)
    assert calls[-1] == ("delete", "key", "GoldMonitor")


def test_macos_launch_agent_runtime_writes_loads_and_removes_plist(tmp_path):
    from goldmonitor.platform_runtime import set_macos_startup_enabled

    launch_agent = tmp_path / "Library" / "LaunchAgents" / "app.plist"
    commands = []
    payload = {
        "Label": "com.example.app",
        "ProgramArguments": ["/Applications/App", "--startup"],
    }

    result = set_macos_startup_enabled(
        True,
        path=str(launch_agent),
        launch_agent_id="com.example.app",
        startup_arguments=payload["ProgramArguments"],
        current_executable="/Applications/App",
        home_dir=str(tmp_path),
        build_payload=lambda *args: dict(payload),
        runner=lambda args, **kwargs: commands.append(args) or SimpleNamespace(returncode=0),
    )

    assert result == (True, None)
    with launch_agent.open("rb") as file_handle:
        assert plistlib.load(file_handle) == payload
    assert commands == [
        ["launchctl", "unload", str(launch_agent)],
        ["launchctl", "load", "-w", str(launch_agent)],
    ]

    assert set_macos_startup_enabled(
        False,
        path=str(launch_agent),
        launch_agent_id="com.example.app",
        startup_arguments=payload["ProgramArguments"],
        current_executable="/Applications/App",
        home_dir=str(tmp_path),
        build_payload=lambda *args: dict(payload),
        runner=lambda args, **kwargs: commands.append(args) or SimpleNamespace(returncode=0),
    ) == (True, None)
    assert not launch_agent.exists()
