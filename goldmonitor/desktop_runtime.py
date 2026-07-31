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


def _load_pillow_font():
    from PIL import ImageFont

    return ImageFont


def _load_pystray():
    import pystray

    return pystray


def load_windows_tray_font(
    pixel_height,
    *,
    bold=False,
    font_loader=_load_pillow_font,
    windows_dir=None,
):
    font_module = font_loader()
    pixel_height = max(8, int(pixel_height))
    windows_dir = windows_dir or os.environ.get("WINDIR", r"C:\Windows")
    font_names = (
        ("segoeuib.ttf", "seguisb.ttf", "segoeui.ttf")
        if bold
        else ("segoeui.ttf", "arial.ttf")
    )
    for font_name in font_names:
        try:
            return font_module.truetype(
                os.path.join(windows_dir, "Fonts", font_name),
                pixel_height,
            )
        except (OSError, TypeError):
            continue
    try:
        return font_module.load_default(size=pixel_height)
    except TypeError:
        return font_module.load_default()


def render_windows_tray_price_icon(
    base_icon,
    state,
    *,
    size=64,
    image_loader=_load_pillow,
    font_provider=load_windows_tray_font,
):
    state = dict(state or {})
    if not state.get("enabled"):
        return base_icon.copy() if hasattr(base_icon, "copy") else base_icon

    image_module, image_draw_module = image_loader()
    image = image_module.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = image_draw_module.Draw(image)
    text = str(state.get("text") or "--")
    currency_symbol = str(state.get("currency_symbol") or "")
    trend_state = str(state.get("trend_state") or "neutral")
    colors = {
        "up": (220, 52, 68, 255),
        "down": (25, 154, 97, 255),
        "neutral": (214, 163, 48, 255),
    }
    color = colors.get(trend_state, colors["neutral"])
    outline = (24, 28, 34, 230)
    font_size = 34 if len(text) <= 3 else 28 if len(text) == 4 else 23
    value_font = font_provider(font_size, bold=True)
    symbol_font = font_provider(15, bold=True)

    bounds = draw.textbbox((0, 0), text, font=value_font, stroke_width=1)
    text_width = bounds[2] - bounds[0]
    text_height = bounds[3] - bounds[1]
    x = (size - text_width) // 2 - bounds[0]
    y = ((size - text_height) // 2) - bounds[1] + 2
    draw.text(
        (x, y),
        text,
        font=value_font,
        fill=color,
        stroke_width=1,
        stroke_fill=outline,
    )
    if currency_symbol:
        draw.text(
            (2, 0),
            currency_symbol,
            font=symbol_font,
            fill=color,
            stroke_width=1,
            stroke_fill=outline,
        )
    line_y = size - 5
    draw.line((8, line_y, size - 8, line_y), fill=color, width=3)
    return image


def refresh_windows_tray_icon(
    icon,
    *,
    base_icon,
    format_title,
    format_icon_state,
    render_icon=render_windows_tray_price_icon,
):
    if not icon:
        return False
    title = format_title()
    state = dict(format_icon_state() or {})
    icon.title = title
    state_key = (
        bool(state.get("enabled")),
        str(state.get("text") or ""),
        str(state.get("currency_symbol") or ""),
        str(state.get("trend_state") or "neutral"),
    )
    if getattr(icon, "_goldmonitor_price_state", None) != state_key:
        icon.icon = render_icon(base_icon, state)
        icon._goldmonitor_price_state = state_key
    return True


def update_tray_tooltip(
    icon,
    *,
    base_icon,
    format_title,
    format_icon_state,
    render_icon=render_windows_tray_price_icon,
    sleep=time.sleep,
    interval=5,
):
    while True:
        try:
            refresh_windows_tray_icon(
                icon,
                base_icon=base_icon,
                format_title=format_title,
                format_icon_state=format_icon_state,
                render_icon=render_icon,
            )
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
    format_icon_state,
    render_icon=render_windows_tray_price_icon,
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

        initial_icon = render_icon(icon_image, format_icon_state())
        menu = (
            pystray.MenuItem("显示窗口", lambda icon, item: show_window(), default=True),
            pystray.MenuItem("刷新行情", lambda icon, item: refresh_price()),
            pystray.MenuItem("风险分析", lambda icon, item: open_risk_analysis()),
            pystray.MenuItem("切换价格显示", lambda icon, item: toggle_floating_price()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("退出", lambda icon, item: exit_application()),
        )

        icon = pystray.Icon("gold_monitor", initial_icon, format_title(), menu)
        set_tray_icon(icon)
        thread_factory(
            target=lambda: update_tray_tooltip(
                icon,
                base_icon=icon_image,
                format_title=format_title,
                format_icon_state=format_icon_state,
                render_icon=render_icon,
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
