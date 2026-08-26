import webbrowser


def resolve_launch_mode(argv, *, os_name, sys_platform, frozen=False):
    arguments = set(argv or [])
    macos_packaged_app = sys_platform == "darwin" and bool(frozen)
    desktop_mode = (
        "--desktop" in arguments
        or (os_name == "nt" and "--web" not in arguments)
        or (macos_packaged_app and "--web" not in arguments)
    )
    return {
        "desktop": desktop_mode,
        "startup": "--startup" in arguments,
    }


def run_application(
    *,
    argv,
    os_name,
    sys_platform,
    frozen,
    default_host,
    default_port,
    runtime,
    find_existing_instance,
    local_app_url,
    open_existing_instance,
    find_available_port,
    create_tray_icon,
    run_server,
    wait_for_server_ready,
    update_floating_price,
    start_background_fetching,
    start_task_scheduler,
    start_lan_dashboard,
    get_settings,
    start_desktop_window,
    thread_factory,
    browser_open=webbrowser.open,
    exit_process=None,
    output=print,
):
    mode = resolve_launch_mode(
        argv,
        os_name=os_name,
        sys_platform=sys_platform,
        frozen=frozen,
    )
    desktop_mode = mode["desktop"]
    startup_mode = mode["startup"]
    existing_port = find_existing_instance(default_host, default_port)
    if existing_port is not None:
        existing_url = local_app_url(default_host, existing_port)
        output(f"金价监控已在运行，正在打开已有实例 -> {existing_url}")
        if not startup_mode:
            open_existing_instance(
                default_host,
                existing_port,
                desktop_mode=desktop_mode,
            )
        if exit_process is not None:
            exit_process(0)
        return "existing"

    runtime.server_port = find_available_port(default_port)
    runtime.desktop_runtime_active = desktop_mode

    if os_name == "nt":
        thread_factory(target=create_tray_icon, daemon=True).start()

    if desktop_mode:
        output("金价监控 - 桌面模式")
        thread_factory(
            target=lambda: run_server(default_host, runtime.server_port),
            daemon=True,
        ).start()
        wait_for_server_ready()
        update_floating_price()
        start_background_fetching()
        start_task_scheduler()
        if start_lan_dashboard is not None:
            start_lan_dashboard()
        start_hidden = (
            os_name == "nt" or sys_platform == "darwin"
        ) and startup_mode and get_settings().get("startup_to_tray", True)
        start_desktop_window(start_hidden=start_hidden)
        return "desktop"

    start_background_fetching()
    start_task_scheduler()
    if start_lan_dashboard is not None:
        start_lan_dashboard()
    web_url = local_app_url(default_host, runtime.server_port)
    output(f"金价监控服务已启动 -> {web_url}")
    try:
        browser_open(web_url)
    except Exception:
        pass
    run_server(default_host, runtime.server_port)
    return "web"
