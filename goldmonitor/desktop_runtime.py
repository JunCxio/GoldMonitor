import logging
import os
import threading
import time


SW_HIDE = 0
SW_MAXIMIZE = 3
SW_RESTORE = 9
WM_SETICON = 0x0080


def start_thread_once(
    *,
    is_started,
    mark_started,
    target,
    thread_factory=threading.Thread,
):
    if is_started():
        return False
    mark_started(True)
    thread_factory(target=target, daemon=True).start()
    return True


def run_periodic_task(
    task,
    *,
    interval,
    sleep=time.sleep,
    logger=logging,
    error_message="后台任务执行失败",
):
    while True:
        try:
            task()
        except Exception:
            logger.exception(error_message)
        sleep(interval)


def hide_main_window(
    *,
    get_window,
    os_name,
    get_window_hwnd,
    set_window_hwnd,
    find_window_hwnd,
    ctypes_loader,
):
    window = get_window()
    if window:
        try:
            window.hide()
        except Exception:
            pass

    if os_name != "nt":
        return

    try:
        ctypes = ctypes_loader()
        hwnd = get_window_hwnd() or find_window_hwnd()
        if hwnd:
            set_window_hwnd(hwnd)
            ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def show_main_window(
    *,
    get_window,
    os_name,
    sys_platform,
    process_id,
    run_macos_script,
    get_window_hwnd,
    set_window_hwnd,
    find_window_hwnd,
    ctypes_loader,
):
    window = get_window()
    if window:
        try:
            window.show()
            window.restore()
        except Exception:
            pass

    if sys_platform == "darwin":
        script = f'''\
tell application "System Events"
    set targetProcesses to every process whose unix id is {process_id}
    if (count of targetProcesses) > 0 then set frontmost of item 1 of targetProcesses to true
end tell
'''
        run_macos_script(script, wait=False)

    if os_name != "nt":
        return

    try:
        ctypes = ctypes_loader()
        hwnd = get_window_hwnd() or find_window_hwnd()
        if hwnd:
            set_window_hwnd(hwnd)
            ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def exit_application(*, get_tray_icon, process_exit):
    icon = get_tray_icon()
    if icon:
        try:
            icon.stop()
        except Exception:
            pass
    process_exit(0)


def _load_pillow():
    from PIL import Image, ImageDraw

    return Image, ImageDraw


def _load_pystray():
    import pystray

    return pystray


def update_tray_tooltip(icon, *, format_title, sleep=time.sleep, interval=5):
    while True:
        try:
            icon.title = format_title()
        except Exception:
            pass
        sleep(interval)


def create_tray_icon(
    *,
    base_dir,
    path_exists=os.path.exists,
    image_loader=_load_pillow,
    pystray_loader=_load_pystray,
    set_tray_icon,
    show_window,
    refresh_price,
    open_risk_analysis,
    toggle_floating_price,
    exit_application,
    format_title,
    thread_factory=threading.Thread,
    sleep=time.sleep,
):
    try:
        image_module, image_draw_module = image_loader()
        pystray = pystray_loader()

        icon_path = os.path.join(base_dir, "static", "icon-64.png")
        if path_exists(icon_path):
            icon_image = image_module.open(icon_path)
        else:
            icon_image = image_module.new("RGBA", (64, 64), (0, 0, 0, 0))
            image_draw_module.Draw(icon_image).ellipse([4, 4, 60, 60], fill="#e8b830")

        menu = (
            pystray.MenuItem("显示窗口", lambda icon, item: show_window(), default=True),
            pystray.MenuItem("刷新行情", lambda icon, item: refresh_price()),
            pystray.MenuItem("风险分析", lambda icon, item: open_risk_analysis()),
            pystray.MenuItem("切换悬浮条", lambda icon, item: toggle_floating_price()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon, item: exit_application()),
        )

        icon = pystray.Icon("gold_monitor", icon_image, "金价监控", menu)
        set_tray_icon(icon)
        thread_factory(
            target=lambda: update_tray_tooltip(
                icon,
                format_title=format_title,
                sleep=sleep,
            ),
            daemon=True,
        ).start()
        icon.run()
        return icon
    except Exception:
        return None


def handle_window_closing(
    runtime_platform,
    *,
    get_settings_snapshot,
    close_behavior_decision,
    hide_window,
    exit_application,
    emit,
):
    if runtime_platform not in ("macos", "windows"):
        exit_application()
        return False

    snapshot = get_settings_snapshot()
    decision = close_behavior_decision(snapshot, runtime_platform)
    if decision == "exit":
        exit_application()
        return False
    if decision == "minimize_to_tray":
        hide_window()
        return False

    emit("show_close_dialog", {
        "close_behavior": snapshot.get("close_behavior", "ask"),
        "close_remembered": bool(snapshot.get("close_remembered")),
    })
    return False


def handle_window_shown(
    *,
    os_name,
    app_name,
    base_dir,
    start_hidden,
    get_window,
    set_window_hwnd,
    hide_window,
    path_exists=os.path.exists,
    ctypes_loader,
):
    if os_name != "nt":
        return

    try:
        ctypes = ctypes_loader()
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, app_name)
        if not hwnd:
            return
        set_window_hwnd(hwnd)
        icon_path = os.path.join(base_dir, "static", "icon.ico")
        if path_exists(icon_path):
            icon = user32.LoadImageW(None, icon_path, 1, 64, 64, 0x10)
            if icon:
                user32.SendMessageW(hwnd, WM_SETICON, 0, icon)
                user32.SendMessageW(hwnd, WM_SETICON, 1, icon)
        if start_hidden and get_window():
            hide_window()
        else:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
    except Exception:
        pass


class DesktopBridge:
    def __init__(self, choose_export_dir):
        self._choose_export_dir = choose_export_dir

    def choose_export_dir(self):
        return self._choose_export_dir()


def _load_webview():
    import webview

    return webview


def start_desktop_window(
    *,
    app_name,
    url,
    base_dir,
    start_hidden,
    os_name,
    sys_platform,
    bridge,
    get_window,
    set_window,
    set_window_hwnd,
    create_macos_status_item,
    get_settings_snapshot,
    close_behavior_decision,
    hide_window,
    exit_application,
    emit,
    path_exists=os.path.exists,
    ctypes_loader,
    webview_loader=_load_webview,
):
    try:
        webview = webview_loader()
        if sys_platform == "darwin":
            create_macos_status_item()

        def on_shown():
            handle_window_shown(
                os_name=os_name,
                app_name=app_name,
                base_dir=base_dir,
                start_hidden=start_hidden,
                get_window=get_window,
                set_window_hwnd=set_window_hwnd,
                hide_window=hide_window,
                path_exists=path_exists,
                ctypes_loader=ctypes_loader,
            )

        def on_closing():
            if sys_platform == "darwin":
                runtime_platform = "macos"
            elif os_name == "nt":
                runtime_platform = "windows"
            else:
                runtime_platform = "other"
            return handle_window_closing(
                runtime_platform,
                get_settings_snapshot=get_settings_snapshot,
                close_behavior_decision=close_behavior_decision,
                hide_window=hide_window,
                exit_application=exit_application,
                emit=emit,
            )

        window = webview.create_window(
            title=app_name,
            url=url,
            width=1200,
            height=780,
            min_size=(860, 500),
            hidden=start_hidden,
            resizable=True,
            easy_drag=False,
            on_top=False,
            maximized=not start_hidden,
            js_api=bridge,
        )
        set_window(window)
        window.events.shown += on_shown
        window.events.closing += on_closing

        if os_name == "nt":
            webview.start(gui="edgechromium")
        else:
            webview.start()
        return window
    except Exception:
        return None
