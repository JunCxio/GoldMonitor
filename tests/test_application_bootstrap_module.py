from types import SimpleNamespace


def test_resolve_launch_mode_covers_web_desktop_and_packaged_macos():
    from goldmonitor.application_bootstrap import resolve_launch_mode

    assert resolve_launch_mode([], os_name="posix", sys_platform="darwin") == {
        "desktop": False,
        "startup": False,
    }
    assert resolve_launch_mode(
        [],
        os_name="posix",
        sys_platform="darwin",
        frozen=True,
    )["desktop"] is True
    assert resolve_launch_mode(
        ["--web"],
        os_name="nt",
        sys_platform="win32",
    )["desktop"] is False
    assert resolve_launch_mode(
        ["--desktop", "--startup"],
        os_name="posix",
        sys_platform="linux",
    ) == {"desktop": True, "startup": True}


def test_run_application_web_mode_starts_services_before_server():
    from goldmonitor.application_bootstrap import run_application

    runtime = SimpleNamespace(server_port=5000, desktop_runtime_active=False)
    calls = []
    result = run_application(
        argv=["--web"],
        os_name="posix",
        sys_platform="darwin",
        frozen=False,
        default_host="127.0.0.1",
        default_port=5000,
        runtime=runtime,
        find_existing_instance=lambda host, port: None,
        local_app_url=lambda host, port: f"http://{host}:{port}",
        open_existing_instance=lambda *args, **kwargs: calls.append("existing"),
        find_available_port=lambda port: 5001,
        create_tray_icon=lambda: calls.append("tray"),
        run_server=lambda host, port: calls.append(("server", host, port)),
        wait_for_server_ready=lambda: calls.append("wait"),
        update_floating_price=lambda: calls.append("floating"),
        start_background_fetching=lambda: calls.append("market"),
        start_task_scheduler=lambda: calls.append("tasks"),
        start_lan_dashboard=lambda: calls.append("lan"),
        get_settings=lambda: {},
        start_desktop_window=lambda **kwargs: calls.append("window"),
        thread_factory=lambda **kwargs: None,
        browser_open=lambda url: calls.append(("browser", url)),
        output=lambda message: calls.append(("output", message)),
    )

    assert result == "web"
    assert runtime.server_port == 5001
    assert runtime.desktop_runtime_active is False
    assert calls[-1] == ("server", "127.0.0.1", 5001)
    assert calls.index("market") < len(calls) - 1
    assert calls.index("tasks") < len(calls) - 1
    assert calls.index("lan") < len(calls) - 1


def test_run_application_reuses_existing_instance_without_starting_services():
    from goldmonitor.application_bootstrap import run_application

    runtime = SimpleNamespace(server_port=5000, desktop_runtime_active=False)
    calls = []
    result = run_application(
        argv=["--desktop"],
        os_name="posix",
        sys_platform="darwin",
        frozen=False,
        default_host="127.0.0.1",
        default_port=5000,
        runtime=runtime,
        find_existing_instance=lambda host, port: 5003,
        local_app_url=lambda host, port: f"http://{host}:{port}",
        open_existing_instance=lambda *args, **kwargs: calls.append(
            ("existing", args, kwargs)
        ),
        find_available_port=lambda port: 5001,
        create_tray_icon=lambda: calls.append("tray"),
        run_server=lambda host, port: calls.append("server"),
        wait_for_server_ready=lambda: calls.append("wait"),
        update_floating_price=lambda: calls.append("floating"),
        start_background_fetching=lambda: calls.append("market"),
        start_task_scheduler=lambda: calls.append("tasks"),
        start_lan_dashboard=lambda: calls.append("lan"),
        get_settings=lambda: {},
        start_desktop_window=lambda **kwargs: calls.append("window"),
        thread_factory=lambda **kwargs: None,
        browser_open=lambda url: calls.append("browser"),
        exit_process=lambda code: calls.append(("exit", code)),
        output=lambda message: calls.append(("output", message)),
    )

    assert result == "existing"
    assert calls[1][0] == "existing"
    assert calls[-1] == ("exit", 0)
    assert "market" not in calls
    assert "lan" not in calls
