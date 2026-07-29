import logging
import os

from goldmonitor import desktop_ui as desktop_ui_core


WM_PAINT = 0x000F
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_CAPTURECHANGED = 0x0215
WM_DISPLAYCHANGE = 0x007E
WM_TIMER = 0x0113
WM_DESTROY = 0x0002

MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
FLOATING_MENU_OPEN = 1001
FLOATING_MENU_HIDE = 1002
FLOATING_MENU_REFRESH = 1003
FLOATING_MENU_RISK = 1004
FLOATING_MENU_LOCK_POSITION = 1005
FLOATING_MENU_HIDE_FULLSCREEN = 1006
FLOATING_MENU_ALWAYS_ON_TOP = 1007
FLOATING_MENU_RESET_POSITION = 1008
FLOATING_VISIBILITY_TIMER_ID = 1
FLOATING_VISIBILITY_TIMER_MS = 500

MK_LBUTTON = 0x0001
DT_SINGLELINE = 0x0020
DT_VCENTER = 0x0004
DT_END_ELLIPSIS = 0x8000
TRANSPARENT = 1
PS_SOLID = 0
DEFAULT_CHARSET = 1
OUT_DEFAULT_PRECIS = 0
CLIP_DEFAULT_PRECIS = 0
CLEARTYPE_QUALITY = 5
DEFAULT_PITCH = 0
FF_DONTCARE = 0
CS_DBLCLKS = 0x0008

WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
MONITOR_DEFAULTTONEAREST = 2
FULLSCREEN_EDGE_TOLERANCE = 2
SHELL_WINDOW_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd"}


def get_lparam_point(lparam):
    value = int(lparam)
    x = value & 0xFFFF
    y = (value >> 16) & 0xFFFF
    if x >= 0x8000:
        x -= 0x10000
    if y >= 0x8000:
        y -= 0x10000
    return x, y


def rgb(red, green, blue):
    return red | (green << 8) | (blue << 16)


def window_rect_covers_monitor(
    window_rect,
    monitor_rect,
    tolerance=FULLSCREEN_EDGE_TOLERANCE,
):
    return (
        window_rect.left <= monitor_rect.left + tolerance
        and window_rect.top <= monitor_rect.top + tolerance
        and window_rect.right >= monitor_rect.right - tolerance
        and window_rect.bottom >= monitor_rect.bottom - tolerance
    )


def is_foreground_window_fullscreen(
    floating_hwnd,
    *,
    user32,
    current_process_id=None,
    monitor_info_type=None,
    ctypes_loader=None,
):
    try:
        ctypes_loader = ctypes_loader or _load_win32_types
        ctypes, wintypes = ctypes_loader()
        foreground = user32.GetForegroundWindow()
        if not foreground or foreground == floating_hwnd:
            return False
        if hasattr(user32, "IsWindowVisible") and not user32.IsWindowVisible(foreground):
            return False
        if hasattr(user32, "IsIconic") and user32.IsIconic(foreground):
            return False

        class_name = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(foreground, class_name, len(class_name)):
            if class_name.value in SHELL_WINDOW_CLASSES:
                return False

        process_id = wintypes.DWORD()
        if not user32.GetWindowThreadProcessId(
            foreground,
            ctypes.byref(process_id),
        ):
            return False
        own_process_id = os.getpid() if current_process_id is None else current_process_id
        if int(process_id.value) == int(own_process_id):
            return False

        window_rect = wintypes.RECT()
        if not user32.GetWindowRect(foreground, ctypes.byref(window_rect)):
            return False

        monitor = user32.MonitorFromWindow(foreground, MONITOR_DEFAULTTONEAREST)
        if not monitor:
            return False
        if monitor_info_type is None:
            class MonitorInfo(ctypes.Structure):
                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD),
                ]

            monitor_info_type = MonitorInfo
        monitor_info = monitor_info_type()
        monitor_info.cbSize = ctypes.sizeof(monitor_info)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(monitor_info)):
            return False
        return window_rect_covers_monitor(window_rect, monitor_info.rcMonitor)
    except Exception:
        return False


def should_hide_for_fullscreen(
    floating_hwnd,
    *,
    user32,
    get_settings,
    current_process_id=None,
    ctypes_loader=None,
):
    settings = get_settings()
    if not settings.get("floating_price_hide_on_fullscreen", True):
        return False
    return is_foreground_window_fullscreen(
        floating_hwnd,
        user32=user32,
        current_process_id=current_process_id,
        ctypes_loader=ctypes_loader,
    )


def _load_win32_types():
    import ctypes
    from ctypes import wintypes

    return ctypes, wintypes


def apply_window_corner_preference(
    hwnd,
    *,
    os_name,
    ctypes_loader=_load_win32_types,
):
    if not hwnd or os_name != "nt":
        return
    try:
        ctypes, _wintypes = ctypes_loader()
        value = ctypes.c_int(3)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(33),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass


def get_work_area(user32, *, ctypes_loader=_load_win32_types):
    try:
        ctypes, wintypes = ctypes_loader()
        rect = wintypes.RECT()
        if user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0):
            return rect.left, rect.top, rect.right, rect.bottom
    except Exception:
        pass
    return 0, 0, 1280, 720


def clamp_window_position(
    x,
    y,
    *,
    window_size,
    work_area,
):
    try:
        return desktop_ui_core.clamp_floating_position(x, y, window_size(), work_area())
    except Exception:
        return int(x), int(y)


def snap_window_position(
    x,
    y,
    *,
    settings,
    window_size,
    work_area,
):
    if not settings().get("floating_price_snap_edge", True):
        return x, y
    try:
        return desktop_ui_core.snap_floating_position(
            x,
            y,
            window_size(),
            work_area(),
            enabled=True,
        )
    except Exception:
        return x, y


def resolve_window_position(*, settings, width, height, work_area):
    return desktop_ui_core.resolve_floating_position(
        settings(),
        (width, height),
        work_area(),
    )


def save_window_position(
    x,
    y,
    *,
    clamp_position,
    snap_position,
    get_settings,
    save_settings,
    emit_settings_updated,
    logger=logging,
):
    try:
        x, y = clamp_position(x, y)
        x, y = snap_position(x, y)
        snapshot = get_settings()
        if (
            snapshot.get("floating_price_position_saved")
            and snapshot.get("floating_price_x") == x
            and snapshot.get("floating_price_y") == y
        ):
            return x, y
        snapshot["floating_price_position_saved"] = True
        snapshot["floating_price_x"] = x
        snapshot["floating_price_y"] = y
        save_settings(snapshot)
        emit_settings_updated()
        return x, y
    except Exception:
        logger.warning("桌面金价悬浮条位置保存失败", exc_info=True)
        return x, y


def position_window(
    hwnd,
    *,
    user32,
    x=None,
    y=None,
    window_size,
    resolve_position,
    clamp_position,
    get_settings,
    set_positioned,
    ctypes_loader=_load_win32_types,
    logger=logging,
):
    if not hwnd:
        return
    try:
        ctypes, _wintypes = ctypes_loader()
        user32.SetWindowPos.restype = ctypes.c_bool
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        width, height = window_size()
        if x is None or y is None:
            x, y = resolve_position(user32, width, height)
        else:
            x, y = clamp_position(x, y, user32)
        pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
        topmost = ctypes.c_void_p(HWND_TOPMOST & ((1 << pointer_bits) - 1))
        not_topmost = ctypes.c_void_p(HWND_NOTOPMOST & ((1 << pointer_bits) - 1))
        insert_after = (
            topmost
            if desktop_ui_core.floating_window_z_order(get_settings()) == "topmost"
            else not_topmost
        )
        ok = user32.SetWindowPos(
            hwnd,
            insert_after,
            int(x),
            int(y),
            int(width),
            int(height),
            0x0010 | 0x0200,
        )
        set_positioned(bool(ok))
        if not ok:
            raise OSError(ctypes.get_last_error(), "SetWindowPos failed")
    except Exception:
        logger.warning("桌面金价悬浮条定位失败", exc_info=True)


def invalidate_window(
    hwnd,
    *,
    os_name,
    ctypes_loader=_load_win32_types,
):
    if not hwnd or os_name != "nt":
        return
    try:
        ctypes, _wintypes = ctypes_loader()
        user32 = ctypes.windll.user32
        user32.InvalidateRect.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_bool,
        ]
        user32.InvalidateRect(hwnd, None, True)
    except Exception:
        pass


def set_window_visible(
    visible,
    *,
    hwnd,
    os_name,
    get_positioned,
    position_window,
    apply_opacity,
    invalidate_window,
    should_suppress=None,
    ctypes_loader=_load_win32_types,
):
    if not hwnd or os_name != "nt":
        return
    try:
        ctypes, _wintypes = ctypes_loader()
        user32 = ctypes.windll.user32
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        suppressed = bool(
            visible
            and should_suppress
            and should_suppress(hwnd, user32)
        )
        should_show = bool(visible and not suppressed)
        currently_visible = None
        if hasattr(user32, "IsWindowVisible"):
            currently_visible = bool(user32.IsWindowVisible(hwnd))
        if should_show:
            if currently_visible is True:
                return True
            if not get_positioned():
                position_window(hwnd, user32)
            apply_opacity(hwnd, user32)
            user32.ShowWindow(hwnd, 4)
            invalidate_window()
            return True
        else:
            if currently_visible is not False:
                user32.ShowWindow(hwnd, 0)
            return False
    except Exception:
        return None


def set_enabled(
    enabled,
    *,
    get_settings,
    save_settings,
    set_window_visible,
    apply_settings,
    public_settings_snapshot,
    emit,
    logger=logging,
):
    try:
        enabled = bool(enabled)
        snapshot = get_settings()
        if snapshot.get("floating_price_enabled", True) == enabled:
            set_window_visible(enabled)
            return
        snapshot["floating_price_enabled"] = enabled
        save_settings(snapshot)
        apply_settings(snapshot)
        emit("settings_updated", public_settings_snapshot(snapshot))
    except Exception:
        logger.warning("桌面金价悬浮条显示状态更新失败", exc_info=True)


def apply_window_opacity(
    hwnd,
    *,
    os_name,
    get_settings,
    user32=None,
    ctypes_loader=_load_win32_types,
):
    if not hwnd or os_name != "nt":
        return
    try:
        ctypes, _wintypes = ctypes_loader()
        user32 = user32 or ctypes.windll.user32
        opacity = get_settings().get("floating_price_opacity", 94)
        alpha = max(1, min(255, int(int(opacity) / 100 * 255)))
        user32.SetLayeredWindowAttributes(hwnd, 0, alpha, 0x00000002)
    except Exception:
        pass


def draw_floating_window(
    hwnd,
    *,
    ctypes_module,
    wintypes,
    user32,
    gdi32,
    paint_struct_type,
    window_size,
    window_metrics,
    floating_rect,
    get_text_state,
):
    width, height = window_size()
    metrics = window_metrics()
    radius = metrics["radius"]
    paint = paint_struct_type()
    hdc = user32.BeginPaint(hwnd, ctypes_module.byref(paint))
    if not hdc:
        return
    try:
        background = gdi32.CreateSolidBrush(rgb(21, 21, 38))
        border_pen = gdi32.CreatePen(PS_SOLID, 1, rgb(62, 58, 78))
        old_brush = gdi32.SelectObject(hdc, background)
        old_pen = gdi32.SelectObject(hdc, border_pen)
        gdi32.RoundRect(hdc, 0, 0, width, height, radius, radius)
        gdi32.SelectObject(hdc, old_brush)
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(background)
        gdi32.DeleteObject(border_pen)

        text_state = get_text_state()
        primary = text_state["primary"]
        secondary = text_state["secondary"]
        status = text_state["status"]
        trend_state = text_state["trend_state"]
        source_state = text_state["source_state"]

        gdi32.SetBkMode(hdc, TRANSPARENT)
        title_font = gdi32.CreateFontW(
            metrics["title_font"], 0, 0, 0, 700, 0, 0, 0, DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
        )
        meta_font = gdi32.CreateFontW(
            metrics["meta_font"], 0, 0, 0, 500, 0, 0, 0, DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
        )
        status_font = gdi32.CreateFontW(
            metrics["status_font"], 0, 0, 0, 500, 0, 0, 0, DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE, "Microsoft YaHei UI",
        )

        title_rect_values = floating_rect(metrics["title_rect"], width, height)
        meta_rect_values = floating_rect(metrics["meta_rect"], width, height)
        status_rect_values = floating_rect(metrics.get("status_rect"), width, height)
        title_rect = wintypes.RECT(*title_rect_values)
        meta_rect = wintypes.RECT(*meta_rect_values)
        status_rect = wintypes.RECT(*status_rect_values) if status_rect_values else None

        trend_color = rgb(232, 184, 48)
        if trend_state == "up":
            trend_color = rgb(224, 85, 106)
        elif trend_state == "down":
            trend_color = rgb(76, 175, 132)

        status_color = rgb(160, 158, 174)
        if source_state == "live":
            status_color = rgb(130, 204, 166)
        elif source_state == "cached":
            status_color = rgb(232, 184, 48)
        elif source_state == "error":
            status_color = rgb(224, 85, 106)

        old_font = gdi32.SelectObject(hdc, title_font)
        gdi32.SetTextColor(hdc, trend_color)
        user32.DrawTextW(
            hdc,
            primary,
            -1,
            ctypes_module.byref(title_rect),
            DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
        )
        gdi32.SelectObject(hdc, meta_font)
        gdi32.SetTextColor(hdc, rgb(205, 202, 214))
        user32.DrawTextW(
            hdc,
            secondary,
            -1,
            ctypes_module.byref(meta_rect),
            DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
        )
        if status_rect is not None:
            gdi32.SelectObject(hdc, status_font)
            gdi32.SetTextColor(hdc, status_color)
            user32.DrawTextW(
                hdc,
                status,
                -1,
                ctypes_module.byref(status_rect),
                DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS,
            )
        gdi32.SelectObject(hdc, old_font)
        gdi32.DeleteObject(title_font)
        gdi32.DeleteObject(meta_font)
        gdi32.DeleteObject(status_font)
    finally:
        user32.EndPaint(hwnd, ctypes_module.byref(paint))


def show_floating_context_menu(
    hwnd,
    *,
    ctypes_module,
    wintypes,
    user32,
    show_main_window,
    set_enabled,
    refresh_price,
    open_risk_analysis,
    get_settings,
    toggle_setting,
    reset_position,
):
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes_module.byref(point)):
        return None
    menu = user32.CreatePopupMenu()
    if not menu:
        return None
    try:
        settings = get_settings()
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_OPEN, "打开主界面")
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_RISK, "风险分析")
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_REFRESH, "刷新行情")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if settings.get("floating_price_lock_position", False) else 0),
            FLOATING_MENU_LOCK_POSITION,
            "锁定位置",
        )
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if settings.get("floating_price_hide_on_fullscreen", True) else 0),
            FLOATING_MENU_HIDE_FULLSCREEN,
            "全屏时自动隐藏",
        )
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if settings.get("floating_price_always_on_top", False) else 0),
            FLOATING_MENU_ALWAYS_ON_TOP,
            "始终置顶",
        )
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_RESET_POSITION, "重置位置")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_HIDE, "隐藏悬浮条")
        user32.SetForegroundWindow(hwnd)
        command = user32.TrackPopupMenu(
            menu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD,
            point.x,
            point.y,
            0,
            hwnd,
            None,
        )
    finally:
        user32.DestroyMenu(menu)

    if command == FLOATING_MENU_OPEN:
        show_main_window()
    elif command == FLOATING_MENU_HIDE:
        set_enabled(False)
    elif command == FLOATING_MENU_REFRESH:
        refresh_price()
    elif command == FLOATING_MENU_RISK:
        open_risk_analysis()
    elif command == FLOATING_MENU_LOCK_POSITION:
        toggle_setting("floating_price_lock_position")
    elif command == FLOATING_MENU_HIDE_FULLSCREEN:
        toggle_setting("floating_price_hide_on_fullscreen")
    elif command == FLOATING_MENU_ALWAYS_ON_TOP:
        toggle_setting("floating_price_always_on_top")
    elif command == FLOATING_MENU_RESET_POSITION:
        reset_position()
    return command


def handle_floating_window_message(
    hwnd,
    msg,
    wparam,
    lparam,
    *,
    ctypes_module,
    wintypes,
    user32,
    get_drag_state,
    set_drag_state,
    clamp_position,
    position_window,
    save_position,
    show_main_window,
    draw_window,
    show_context_menu,
    is_position_locked,
    sync_visibility,
):
    if msg == WM_PAINT:
        draw_window(hwnd)
        return 0
    if msg == WM_LBUTTONDOWN:
        if is_position_locked():
            set_drag_state(None)
            return 0
        try:
            point_x, point_y = get_lparam_point(lparam)
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes_module.byref(rect))
            set_drag_state({
                "offset_x": point_x,
                "offset_y": point_y,
                "start_x": rect.left,
                "start_y": rect.top,
                "moved": False,
            })
            user32.SetCapture(hwnd)
        except Exception:
            set_drag_state(None)
        return 0

    drag_state = get_drag_state()
    if msg == WM_MOUSEMOVE and drag_state and (int(wparam) & MK_LBUTTON):
        try:
            cursor = wintypes.POINT()
            if user32.GetCursorPos(ctypes_module.byref(cursor)):
                new_x = cursor.x - drag_state["offset_x"]
                new_y = cursor.y - drag_state["offset_y"]
                x, y = clamp_position(new_x, new_y, user32)
                if (
                    abs(x - drag_state["start_x"]) > 3
                    or abs(y - drag_state["start_y"]) > 3
                ):
                    drag_state["moved"] = True
                position_window(hwnd, user32, x, y)
        except Exception:
            pass
        return 0
    if msg == WM_LBUTTONUP:
        try:
            user32.ReleaseCapture()
        except Exception:
            pass
        drag_state = get_drag_state()
        set_drag_state(None)
        if drag_state and drag_state.get("moved"):
            try:
                rect = wintypes.RECT()
                if user32.GetWindowRect(hwnd, ctypes_module.byref(rect)):
                    saved_x, saved_y = save_position(rect.left, rect.top)
                    position_window(hwnd, user32, saved_x, saved_y)
            except Exception:
                pass
        return 0
    if msg == WM_LBUTTONDBLCLK:
        set_drag_state(None)
        try:
            user32.ReleaseCapture()
        except Exception:
            pass
        show_main_window()
        return 0
    if msg in (WM_RBUTTONUP, WM_CONTEXTMENU):
        show_context_menu(hwnd)
        return 0
    if msg == WM_CAPTURECHANGED:
        set_drag_state(None)
        return 0
    if msg == WM_DISPLAYCHANGE:
        position_window(hwnd, user32)
        sync_visibility()
        return 0
    if msg == WM_TIMER and int(wparam) == FLOATING_VISIBILITY_TIMER_ID:
        sync_visibility()
        return 0
    if msg == WM_DESTROY:
        try:
            user32.KillTimer(hwnd, FLOATING_VISIBILITY_TIMER_ID)
        except Exception:
            pass
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def run_floating_price_window(
    *,
    window_size,
    window_metrics,
    floating_rect,
    get_text_state,
    clamp_position,
    position_window,
    save_position,
    resolve_position,
    set_window_handle,
    apply_corner_preference,
    apply_opacity,
    set_window_visible,
    window_enabled,
    set_ready,
    show_main_window,
    set_enabled,
    refresh_price,
    open_risk_analysis,
    get_drag_state,
    set_drag_state,
    is_topmost,
    get_settings,
    toggle_setting,
    reset_position,
    is_position_locked,
    sync_visibility,
    ctypes_loader=_load_win32_types,
    logger=logging,
):
    try:
        ctypes, wintypes = ctypes_loader()
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        kernel32 = ctypes.windll.kernel32

        result_type = ctypes.c_ssize_t
        window_proc_type = ctypes.WINFUNCTYPE(
            result_type,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        user32.DefWindowProcW.restype = result_type
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

        class WindowClass(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", window_proc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class PaintStruct(ctypes.Structure):
            _fields_ = [
                ("hdc", wintypes.HDC),
                ("fErase", wintypes.BOOL),
                ("rcPaint", wintypes.RECT),
                ("fRestore", wintypes.BOOL),
                ("fIncUpdate", wintypes.BOOL),
                ("rgbReserved", wintypes.BYTE * 32),
            ]

        user32.BeginPaint.restype = wintypes.HDC
        user32.BeginPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintStruct)]
        user32.EndPaint.argtypes = [wintypes.HWND, ctypes.POINTER(PaintStruct)]
        user32.DrawTextW.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.RECT),
            wintypes.UINT,
        ]
        user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.SetTimer.argtypes = [
            wintypes.HWND,
            ctypes.c_size_t,
            wintypes.UINT,
            ctypes.c_void_p,
        ]
        user32.SetTimer.restype = ctypes.c_size_t
        user32.KillTimer.argtypes = [wintypes.HWND, ctypes.c_size_t]
        user32.KillTimer.restype = wintypes.BOOL
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SetCapture.argtypes = [wintypes.HWND]
        user32.SetCapture.restype = wintypes.HWND
        user32.ReleaseCapture.argtypes = []
        user32.ReleaseCapture.restype = wintypes.BOOL
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_size_t,
            wintypes.LPCWSTR,
        ]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            ctypes.c_void_p,
        ]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi32.CreateSolidBrush.restype = wintypes.HANDLE
        gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        gdi32.CreatePen.restype = wintypes.HANDLE
        gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.CreateFontW.restype = wintypes.HANDLE
        gdi32.CreateFontW.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPCWSTR,
        ]
        gdi32.RoundRect.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
        ]

        def draw_window(hwnd):
            return draw_floating_window(
                hwnd,
                ctypes_module=ctypes,
                wintypes=wintypes,
                user32=user32,
                gdi32=gdi32,
                paint_struct_type=PaintStruct,
                window_size=window_size,
                window_metrics=window_metrics,
                floating_rect=floating_rect,
                get_text_state=get_text_state,
            )

        def show_context_menu(hwnd):
            return show_floating_context_menu(
                hwnd,
                ctypes_module=ctypes,
                wintypes=wintypes,
                user32=user32,
                show_main_window=show_main_window,
                set_enabled=set_enabled,
                refresh_price=refresh_price,
                open_risk_analysis=open_risk_analysis,
                get_settings=get_settings,
                toggle_setting=toggle_setting,
                reset_position=reset_position,
            )

        @window_proc_type
        def window_proc(hwnd, msg, wparam, lparam):
            return handle_floating_window_message(
                hwnd,
                msg,
                wparam,
                lparam,
                ctypes_module=ctypes,
                wintypes=wintypes,
                user32=user32,
                get_drag_state=get_drag_state,
                set_drag_state=set_drag_state,
                clamp_position=clamp_position,
                position_window=position_window,
                save_position=save_position,
                show_main_window=show_main_window,
                draw_window=draw_window,
                show_context_menu=show_context_menu,
                is_position_locked=is_position_locked,
                sync_visibility=sync_visibility,
            )

        instance = kernel32.GetModuleHandleW(None)
        class_name = "GoldMonitorFloatingPriceWindow"
        window_class = WindowClass()
        window_class.style = CS_DBLCLKS
        window_class.lpfnWndProc = window_proc
        window_class.hInstance = instance
        window_class.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32649))
        window_class.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(window_class))

        width, height = window_size()
        x, y = resolve_position(user32, width, height)
        extended_style = WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
        if is_topmost():
            extended_style |= WS_EX_TOPMOST

        hwnd = user32.CreateWindowExW(
            extended_style,
            class_name,
            "金价悬浮条",
            WS_POPUP,
            int(x),
            int(y),
            int(width),
            int(height),
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            set_ready()
            return None

        set_window_handle(hwnd)
        apply_corner_preference(hwnd)
        apply_opacity(hwnd, user32)
        user32.SetTimer(hwnd, FLOATING_VISIBILITY_TIMER_ID, FLOATING_VISIBILITY_TIMER_MS, None)
        if window_enabled():
            set_window_visible(True)
        set_ready()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        return hwnd
    except Exception:
        logger.warning("桌面金价悬浮条启动失败", exc_info=True)
        set_ready()
        return None
