from types import SimpleNamespace


def _runtime(state=None, **overrides):
    from goldmonitor.platform_integration_runtime import PlatformIntegrationRuntime

    state = state or SimpleNamespace(credential_test_store=None)
    options = {
        "credential_target_prefix": "GoldMonitor:",
        "credential_service_name": "GoldMonitor",
        "macos_launch_agent_id": "com.example.goldmonitor",
        "run_key_path": r"Software\Example\Run",
        "run_key_name": "GoldMonitor",
        "is_frozen": lambda: False,
        "executable": lambda: "/usr/bin/python3",
        "argv0": lambda: "/app/app.py",
        "os_name": lambda: "posix",
        "sys_platform": lambda: "linux",
        "home_dir": lambda: "/Users/test",
        "runner": lambda: lambda *args, **kwargs: None,
    }
    options.update(overrides)
    return PlatformIntegrationRuntime(state, **options)


def test_platform_integration_runtime_manages_override_credentials():
    state = SimpleNamespace(credential_test_store={"token": "secret"})
    runtime = _runtime(state)

    assert runtime.credential_target_name("token") == "GoldMonitor:token"
    assert runtime.read_credential_secret("token") == "secret"
    assert runtime.write_credential_secret("token", "updated") is True
    assert state.credential_test_store["token"] == "updated"
    assert runtime.write_credential_secret("token", "") is True
    assert "token" not in state.credential_test_store
    assert runtime.credentials_required() is False


def test_platform_integration_runtime_selects_macos_startup_callback():
    calls = []
    runtime = _runtime(sys_platform=lambda: "darwin")

    result = runtime.set_startup_enabled(
        True,
        set_macos_startup=lambda enabled: calls.append(enabled) or (True, None),
    )

    assert result == (True, None)
    assert calls == [True]
    assert runtime.credentials_required() is True


def test_platform_integration_runtime_binds_windows_startup_contract(monkeypatch):
    from goldmonitor import platform_runtime

    captured = []

    def set_windows_startup_enabled(enabled, **kwargs):
        captured.append((enabled, kwargs))
        return True, None

    monkeypatch.setattr(
        platform_runtime,
        "set_windows_startup_enabled",
        set_windows_startup_enabled,
    )
    runtime = _runtime(
        os_name=lambda: "nt",
        sys_platform=lambda: "win32",
    )

    result = runtime.set_startup_enabled(
        True,
        startup_command=lambda: '"C:\\GoldMonitor.exe" --startup',
    )

    assert result == (True, None)
    assert captured == [
        (
            True,
            {
                "run_key_path": r"Software\Example\Run",
                "run_key_name": "GoldMonitor",
                "startup_command": '"C:\\GoldMonitor.exe" --startup',
            },
        )
    ]
    assert runtime.credentials_required() is True


def test_platform_integration_runtime_builds_script_startup_paths():
    runtime = _runtime()

    assert runtime.current_executable() == "/app/app.py"
    assert runtime.startup_command() == '"/app/app.py" --startup'
    assert runtime.macos_startup_arguments() == [
        "/usr/bin/python3",
        "/app/app.py",
        "--startup",
    ]
    assert runtime.macos_launch_agent_path() == (
        "/Users/test/Library/LaunchAgents/com.example.goldmonitor.plist"
    )
