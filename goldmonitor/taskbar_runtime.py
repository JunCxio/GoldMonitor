import logging

from goldmonitor import floating_runtime as floating_runtime_core


WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_DISPLAYCHANGE = 0x007E
WM_SETTINGCHANGE = 0x001A
WM_THEMECHANGED = 0x031A
WM_TIMER = 0x0113
WM_DESTROY = 0x0002

MF_STRING = 0x0000
MF_CHECKED = 0x0008
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
TASKBAR_MENU_OPEN = 2001
TASKBAR_MENU_REFRESH = 2002
TASKBAR_MENU_RISK = 2003
TASKBAR_MENU_MODE_FLOATING = 2004
TASKBAR_MENU_MODE_TASKBAR = 2005
TASKBAR_MENU_MODE_BOTH = 2006
TASKBAR_MENU_HIDE = 2007

TASKBAR_LAYOUT_TIMER_ID = 2
TASKBAR_LAYOUT_TIMER_MS = 750
TASKBAR_DESIRED_WIDTH = 224
TASKBAR_MINIMUM_WIDTH = 154
TASKBAR_MARGIN = 3
TASKBAR_CONTENT_PADDING = 6
TASKBAR_CONTENT_GAP = 5
TASKBAR_ARROW_WIDTH = 9
TASKBAR_MINIMUM_PRICE_WIDTH = 42

ABM_GETSTATE = 0x00000004
ABS_AUTOHIDE = 0x00000001
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
HWND_TOPMOST = -1
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
LWA_COLORKEY = 0x00000001
DT_LEFT = 0x0000
DT_VCENTER = 0x0004
DT_SINGLELINE = 0x0020
DT_END_ELLIPSIS = 0x8000
TRANSPARENT = 1
PS_SOLID = 0
DEFAULT_CHARSET = 1
OUT_DEFAULT_PRECIS = 0
CLIP_DEFAULT_PRECIS = 0
ANTIALIASED_QUALITY = 4
DEFAULT_PITCH = 0
FF_DONTCARE = 0
CS_DBLCLKS = 0x0008

TASKBAR_TRANSPARENT_COLOR = (0, 0, 0)
TASKBAR_THEME_REGISTRY_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
)

TASK_LIST_CLASSES = {"MSTaskListWClass", "MSTaskSwWClass"}


def _load_win32_types():
    import ctypes
    from ctypes import wintypes

    return ctypes, wintypes


def _load_windows_registry():
    import winreg

    return winreg


def taskbar_uses_light_theme(registry_loader=_load_windows_registry):
    key = None
    try:
        registry = registry_loader()
        key = registry.OpenKey(
            registry.HKEY_CURRENT_USER,
            TASKBAR_THEME_REGISTRY_PATH,
        )
        for value_name in ("SystemUsesLightTheme", "AppsUseLightTheme"):
            try:
                value, _value_type = registry.QueryValueEx(key, value_name)
                return bool(int(value))
            except OSError:
                continue
        return False
    except (AttributeError, OSError, TypeError, ValueError):
        return False
    finally:
        if key is not None:
            try:
                registry.CloseKey(key)
            except (AttributeError, OSError):
                pass


def taskbar_draw_palette(*, light_theme, source_state, trend_state):
    if light_theme:
        palette = {
            "price": (32, 38, 45),
            "brand_live": (154, 106, 10),
            "brand_cached": (145, 111, 43),
            "brand_waiting": (92, 102, 115),
            "brand_error": (201, 52, 63),
            "trend_up": (201, 52, 63),
            "trend_down": (19, 122, 77),
            "trend_neutral": (92, 102, 115),
        }
    else:
        palette = {
            "price": (241, 244, 247),
            "brand_live": (224, 180, 76),
            "brand_cached": (197, 165, 91),
            "brand_waiting": (174, 181, 191),
            "brand_error": (255, 107, 118),
            "trend_up": (255, 107, 118),
            "trend_down": (76, 197, 138),
            "trend_neutral": (174, 181, 191),
        }
    brand_key = f"brand_{source_state}"
    trend_key = f"trend_{trend_state}"
    return {
        "price": palette["price"],
        "brand": palette.get(brand_key, palette["brand_waiting"]),
        "trend": palette.get(trend_key, palette["trend_neutral"]),
        "transparent": TASKBAR_TRANSPARENT_COLOR,
    }


def taskbar_window_ex_style():
    return WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE


def enable_taskbar_transparency(hwnd, *, user32):
    if not hwnd:
        return False
    return bool(
        user32.SetLayeredWindowAttributes(
            hwnd,
            floating_runtime_core.rgb(*TASKBAR_TRANSPARENT_COLOR),
            0,
            LWA_COLORKEY,
        )
    )


def layout_taskbar_content(
    client_width,
    *,
    brand_width,
    price_width,
    change_width=0,
    padding=TASKBAR_CONTENT_PADDING,
):
    client_width = max(0, int(client_width))
    brand_width = max(0, int(brand_width))
    price_width = max(0, int(price_width))
    change_width = max(0, int(change_width))
    padding = max(0, int(padding))
    has_change = change_width > 0
    available = max(0, client_width - (2 * padding))
    fixed_width = brand_width + TASKBAR_CONTENT_GAP
    if has_change:
        fixed_width += (
            TASKBAR_CONTENT_GAP
            + TASKBAR_ARROW_WIDTH
            + 3
            + change_width
        )
    maximum_price_width = max(
        TASKBAR_MINIMUM_PRICE_WIDTH,
        available - fixed_width,
    )
    drawn_price_width = min(price_width, maximum_price_width)
    total_width = fixed_width + drawn_price_width
    start_x = max(padding, (client_width - total_width) // 2)

    brand = (start_x, brand_width)
    price_x = start_x + brand_width + TASKBAR_CONTENT_GAP
    price = (price_x, drawn_price_width)
    arrow = None
    change = None
    if has_change:
        arrow_x = price_x + drawn_price_width + TASKBAR_CONTENT_GAP
        arrow = (arrow_x, TASKBAR_ARROW_WIDTH)
        change = (arrow_x + TASKBAR_ARROW_WIDTH + 3, change_width)
    return {
        "brand": brand,
        "price": price,
        "arrow": arrow,
        "change": change,
        "total_width": total_width,
        "price_clipped": drawn_price_width < price_width,
    }


def normalize_rect(rect):
    if rect is None:
        return None
    if isinstance(rect, (tuple, list)) and len(rect) == 4:
        values = rect
    else:
        values = (rect.left, rect.top, rect.right, rect.bottom)
    left, top, right, bottom = (int(value) for value in values)
    if right <= left or bottom <= top:
        return None
    return left, top, right, bottom


def _clip_interval(rect, taskbar_rect):
    rect = normalize_rect(rect)
    if not rect:
        return None
    left, _top, right, _bottom = rect
    taskbar_left, _taskbar_top, taskbar_right, _taskbar_bottom = taskbar_rect
    left = max(taskbar_left, left)
    right = min(taskbar_right, right)
    return (left, right) if right > left else None


def _merge_intervals(intervals):
    merged = []
    for left, right in sorted(intervals):
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))
    return merged


def choose_taskbar_layout(
    taskbar_rect,
    *,
    tray_rect,
    task_list_rect,
    start_rect=None,
    desired_width=TASKBAR_DESIRED_WIDTH,
    minimum_width=TASKBAR_MINIMUM_WIDTH,
    margin=TASKBAR_MARGIN,
):
    taskbar_rect = normalize_rect(taskbar_rect)
    tray_rect = normalize_rect(tray_rect)
    task_list_rect = normalize_rect(task_list_rect)
    if not taskbar_rect or not tray_rect or not task_list_rect:
        return None

    left, top, right, bottom = taskbar_rect
    taskbar_width = right - left
    taskbar_height = bottom - top
    if taskbar_width <= taskbar_height or taskbar_height < 28:
        return None

    occupied = []
    for rect in (tray_rect, task_list_rect, start_rect):
        interval = _clip_interval(rect, taskbar_rect)
        if interval:
            occupied.append(interval)
    if not occupied:
        return None

    cursor = left
    free_intervals = []
    for occupied_left, occupied_right in _merge_intervals(occupied):
        if occupied_left - cursor >= minimum_width + (2 * margin):
            free_intervals.append((cursor, occupied_left))
        cursor = max(cursor, occupied_right)
    if right - cursor >= minimum_width + (2 * margin):
        free_intervals.append((cursor, right))
    if not free_intervals:
        return None

    tray_left = tray_rect[0]
    free_left, free_right = min(
        free_intervals,
        key=lambda interval: (
            0 if interval[1] <= tray_left else 1,
            abs(tray_left - interval[1]),
            -(interval[1] - interval[0]),
        ),
    )
    usable_width = free_right - free_left - (2 * margin)
    width = min(int(desired_width), usable_width)
    if width < int(minimum_width):
        return None
    height = min(34, taskbar_height - (2 * margin))
    if height < 24:
        return None
    x = free_right - margin - width
    y = top + max(margin, (taskbar_height - height) // 2)
    return {
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
        "orientation": "horizontal",
        "taskbar_rect": taskbar_rect,
    }


def get_window_rect(user32, hwnd, *, ctypes_loader=_load_win32_types):
    if not hwnd:
        return None
    try:
        ctypes, wintypes = ctypes_loader()
        rect = wintypes.RECT()
        if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return normalize_rect(rect)
    except Exception:
        pass
    return None


def find_descendant_window(
    user32,
    parent,
    class_names,
    *,
    ctypes_loader=_load_win32_types,
    limit=256,
):
    if not parent:
        return None
    ctypes, _wintypes = ctypes_loader()
    wanted = set(class_names)
    queue = [parent]
    visited = 0
    while queue and visited < limit:
        current = queue.pop(0)
        child = None
        while visited < limit:
            child = user32.FindWindowExW(current, child, None, None)
            if not child:
                break
            visited += 1
            class_name = ctypes.create_unicode_buffer(128)
            if user32.GetClassNameW(child, class_name, len(class_name)):
                if class_name.value in wanted:
                    return child
            queue.append(child)
    return None


def taskbar_is_auto_hidden(
    taskbar_hwnd,
    *,
    shell32,
    ctypes_loader=_load_win32_types,
):
    if not taskbar_hwnd:
        return False
    try:
        ctypes, wintypes = ctypes_loader()

        class AppBarData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uCallbackMessage", wintypes.UINT),
                ("uEdge", wintypes.UINT),
                ("rc", wintypes.RECT),
                ("lParam", wintypes.LPARAM),
            ]

        data = AppBarData()
        data.cbSize = ctypes.sizeof(data)
        data.hWnd = taskbar_hwnd
        return bool(shell32.SHAppBarMessage(ABM_GETSTATE, ctypes.byref(data)) & ABS_AUTOHIDE)
    except Exception:
        return False


def resolve_taskbar_layout(
    *,
    user32,
    shell32,
    ctypes_loader=_load_win32_types,
):
    try:
        taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if not taskbar_hwnd:
            return None, {"visible": False, "reason": "taskbar_not_found"}
        if taskbar_is_auto_hidden(
            taskbar_hwnd,
            shell32=shell32,
            ctypes_loader=ctypes_loader,
        ):
            return None, {"visible": False, "reason": "taskbar_auto_hidden"}

        tray_hwnd = find_descendant_window(
            user32,
            taskbar_hwnd,
            {"TrayNotifyWnd"},
            ctypes_loader=ctypes_loader,
        )
        task_list_hwnd = find_descendant_window(
            user32,
            taskbar_hwnd,
            {"MSTaskListWClass"},
            ctypes_loader=ctypes_loader,
        )
        if not task_list_hwnd:
            task_list_hwnd = find_descendant_window(
                user32,
                taskbar_hwnd,
                {"MSTaskSwWClass"},
                ctypes_loader=ctypes_loader,
            )
        start_hwnd = find_descendant_window(
            user32,
            taskbar_hwnd,
            {"Start"},
            ctypes_loader=ctypes_loader,
        )
        if not tray_hwnd or not task_list_hwnd:
            return None, {"visible": False, "reason": "taskbar_regions_unavailable"}

        taskbar_rect = get_window_rect(
            user32,
            taskbar_hwnd,
            ctypes_loader=ctypes_loader,
        )
        tray_rect = get_window_rect(user32, tray_hwnd, ctypes_loader=ctypes_loader)
        task_list_rect = get_window_rect(
            user32,
            task_list_hwnd,
            ctypes_loader=ctypes_loader,
        )
        start_rect = get_window_rect(user32, start_hwnd, ctypes_loader=ctypes_loader)
        layout = choose_taskbar_layout(
            taskbar_rect,
            tray_rect=tray_rect,
            task_list_rect=task_list_rect,
            start_rect=start_rect,
        )
        if not layout:
            return None, {
                "visible": False,
                "reason": "insufficient_taskbar_space",
                "taskbar_rect": taskbar_rect,
            }
        return layout, {
            "visible": False,
            "reason": "ready",
            "taskbar_rect": taskbar_rect,
            "bounds": (
                layout["x"],
                layout["y"],
                layout["width"],
                layout["height"],
            ),
        }
    except Exception:
        return None, {"visible": False, "reason": "layout_error"}


def invalidate_window(hwnd, *, os_name, ctypes_loader=_load_win32_types):
    if not hwnd or os_name != "nt":
        return None
    try:
        ctypes, _wintypes = ctypes_loader()
        ctypes.windll.user32.InvalidateRect(hwnd, None, False)
    except Exception:
        pass
    return None


def set_taskbar_window_visible(
    visible,
    *,
    hwnd,
    os_name,
    layout_provider,
    should_suppress,
    set_layout_state,
    invalidate,
    ctypes_loader=_load_win32_types,
):
    if not hwnd or os_name != "nt":
        return None
    try:
        ctypes, _wintypes = ctypes_loader()
        user32 = ctypes.windll.user32
        if not visible:
            user32.ShowWindow(hwnd, 0)
            set_layout_state({"visible": False, "reason": "disabled"})
            return False

        layout, state = layout_provider()
        if not layout:
            user32.ShowWindow(hwnd, 0)
            set_layout_state(state)
            return False
        if should_suppress(hwnd, user32):
            user32.ShowWindow(hwnd, 0)
            set_layout_state({**state, "visible": False, "reason": "fullscreen"})
            return False

        pointer_bits = ctypes.sizeof(ctypes.c_void_p) * 8
        topmost = ctypes.c_void_p(HWND_TOPMOST & ((1 << pointer_bits) - 1))
        positioned = user32.SetWindowPos(
            hwnd,
            topmost,
            layout["x"],
            layout["y"],
            layout["width"],
            layout["height"],
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        if not positioned:
            user32.ShowWindow(hwnd, 0)
            set_layout_state({**state, "visible": False, "reason": "position_error"})
            return False
        user32.ShowWindow(hwnd, 4)
        set_layout_state({**state, "visible": True, "reason": "visible"})
        invalidate()
        return True
    except Exception:
        set_layout_state({"visible": False, "reason": "visibility_error"})
        return None


def _draw_taskbar_trend_arrow(hdc, bounds, trend_state, color, *, gdi32):
    if not bounds:
        return None
    left, top, right, bottom = bounds
    center_x = (left + right) // 2
    center_y = (top + bottom) // 2
    pen = gdi32.CreatePen(PS_SOLID, 2, color)
    old_pen = gdi32.SelectObject(hdc, pen)
    try:
        if trend_state == "up":
            arrow_tip_y = center_y - 5
            arrow_end_y = center_y + 5
            gdi32.MoveToEx(hdc, center_x, arrow_end_y, None)
            gdi32.LineTo(hdc, center_x, arrow_tip_y)
            gdi32.MoveToEx(hdc, center_x, arrow_tip_y, None)
            gdi32.LineTo(hdc, center_x - 4, arrow_tip_y + 4)
            gdi32.MoveToEx(hdc, center_x, arrow_tip_y, None)
            gdi32.LineTo(hdc, center_x + 4, arrow_tip_y + 4)
        elif trend_state == "down":
            arrow_tip_y = center_y + 5
            arrow_end_y = center_y - 5
            gdi32.MoveToEx(hdc, center_x, arrow_end_y, None)
            gdi32.LineTo(hdc, center_x, arrow_tip_y)
            gdi32.MoveToEx(hdc, center_x, arrow_tip_y, None)
            gdi32.LineTo(hdc, center_x - 4, arrow_tip_y - 4)
            gdi32.MoveToEx(hdc, center_x, arrow_tip_y, None)
            gdi32.LineTo(hdc, center_x + 4, arrow_tip_y - 4)
        else:
            gdi32.MoveToEx(hdc, center_x - 4, center_y, None)
            gdi32.LineTo(hdc, center_x + 4, center_y)
    finally:
        gdi32.SelectObject(hdc, old_pen)
        gdi32.DeleteObject(pen)
    return None


def draw_taskbar_window(
    hwnd,
    *,
    ctypes_module,
    wintypes,
    user32,
    gdi32,
    paint_struct_type,
    get_text_state,
    light_theme_provider=taskbar_uses_light_theme,
):
    paint = paint_struct_type()
    hdc = user32.BeginPaint(hwnd, ctypes_module.byref(paint))
    if not hdc:
        return None
    brand_font = None
    value_font = None
    try:
        client = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes_module.byref(client))
        transparent_color = floating_runtime_core.rgb(*TASKBAR_TRANSPARENT_COLOR)
        background = gdi32.CreateSolidBrush(transparent_color)
        user32.FillRect(hdc, ctypes_module.byref(client), background)
        gdi32.DeleteObject(background)

        state = get_text_state()
        source_state = state.get("source_state", "waiting")
        trend_state = state.get("trend_state", "neutral")
        palette = taskbar_draw_palette(
            light_theme=bool(light_theme_provider()),
            source_state=source_state,
            trend_state=trend_state,
        )
        brand_text = "Au"
        price_text = str(state.get("price") or "--")
        change_text = str(state.get("change") or "")

        brand_font = gdi32.CreateFontW(
            -14,
            0,
            0,
            0,
            700,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE,
            "Microsoft YaHei UI",
        )
        value_font = gdi32.CreateFontW(
            -13,
            0,
            0,
            0,
            600,
            0,
            0,
            0,
            DEFAULT_CHARSET,
            OUT_DEFAULT_PRECIS,
            CLIP_DEFAULT_PRECIS,
            ANTIALIASED_QUALITY,
            DEFAULT_PITCH | FF_DONTCARE,
            "Microsoft YaHei UI",
        )
        gdi32.SetBkMode(hdc, TRANSPARENT)

        def measure_text(text, font):
            size = wintypes.SIZE()
            old_font = gdi32.SelectObject(hdc, font)
            try:
                if gdi32.GetTextExtentPoint32W(hdc, text, len(text), ctypes_module.byref(size)):
                    return int(size.cx)
            finally:
                gdi32.SelectObject(hdc, old_font)
            return max(1, len(text) * 7)

        brand_width = measure_text(brand_text, brand_font)
        price_width = measure_text(price_text, value_font)
        change_width = measure_text(change_text, value_font) if change_text else 0
        layout = layout_taskbar_content(
            client.right,
            brand_width=brand_width,
            price_width=price_width,
            change_width=change_width,
        )

        def draw_text(text, segment, font, color):
            if not segment or not text:
                return
            left, width = segment
            text_rect = wintypes.RECT(left, 0, left + width, client.bottom)
            old_font = gdi32.SelectObject(hdc, font)
            try:
                gdi32.SetTextColor(hdc, floating_runtime_core.rgb(*color))
                user32.DrawTextW(
                    hdc,
                    text,
                    -1,
                    ctypes_module.byref(text_rect),
                    DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS,
                )
            finally:
                gdi32.SelectObject(hdc, old_font)

        draw_text(brand_text, layout["brand"], brand_font, palette["brand"])
        draw_text(price_text, layout["price"], value_font, palette["price"])
        if layout["arrow"]:
            arrow_left, arrow_width = layout["arrow"]
            _draw_taskbar_trend_arrow(
                hdc,
                (arrow_left, 0, arrow_left + arrow_width, client.bottom),
                trend_state,
                floating_runtime_core.rgb(*palette["trend"]),
                gdi32=gdi32,
            )
        draw_text(change_text, layout["change"], value_font, palette["trend"])
    finally:
        if brand_font:
            gdi32.DeleteObject(brand_font)
        if value_font:
            gdi32.DeleteObject(value_font)
        user32.EndPaint(hwnd, ctypes_module.byref(paint))
    return None


def show_taskbar_context_menu(
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
    set_windows_mode,
):
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes_module.byref(point)):
        return None
    menu = user32.CreatePopupMenu()
    if not menu:
        return None
    try:
        mode = get_settings().get("floating_price_windows_mode", "floating")
        user32.AppendMenuW(menu, MF_STRING, TASKBAR_MENU_OPEN, "打开主界面")
        user32.AppendMenuW(menu, MF_STRING, TASKBAR_MENU_RISK, "风险分析")
        user32.AppendMenuW(menu, MF_STRING, TASKBAR_MENU_REFRESH, "刷新行情")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if mode == "floating" else 0),
            TASKBAR_MENU_MODE_FLOATING,
            "仅显示悬浮条",
        )
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if mode == "taskbar" else 0),
            TASKBAR_MENU_MODE_TASKBAR,
            "仅显示任务栏价格",
        )
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_CHECKED if mode == "both" else 0),
            TASKBAR_MENU_MODE_BOTH,
            "两处同时显示",
        )
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, TASKBAR_MENU_HIDE, "关闭桌面价格")
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

    if command == TASKBAR_MENU_OPEN:
        show_main_window()
    elif command == TASKBAR_MENU_REFRESH:
        refresh_price()
    elif command == TASKBAR_MENU_RISK:
        open_risk_analysis()
    elif command == TASKBAR_MENU_MODE_FLOATING:
        set_windows_mode("floating")
    elif command == TASKBAR_MENU_MODE_TASKBAR:
        set_windows_mode("taskbar")
    elif command == TASKBAR_MENU_MODE_BOTH:
        set_windows_mode("both")
    elif command == TASKBAR_MENU_HIDE:
        set_enabled(False)
    return command


def handle_taskbar_window_message(
    hwnd,
    msg,
    wparam,
    lparam,
    *,
    user32,
    draw_window,
    show_context_menu,
    show_main_window,
    sync_visibility,
):
    if msg == WM_PAINT:
        draw_window(hwnd)
        return 0
    if msg == WM_ERASEBKGND:
        return 1
    if msg in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
        show_main_window()
        return 0
    if msg in (WM_RBUTTONUP, WM_CONTEXTMENU):
        show_context_menu(hwnd)
        return 0
    if msg in (WM_DISPLAYCHANGE, WM_SETTINGCHANGE, WM_THEMECHANGED):
        sync_visibility()
        return 0
    if msg == WM_TIMER and int(wparam) == TASKBAR_LAYOUT_TIMER_ID:
        sync_visibility()
        return 0
    if msg == WM_DESTROY:
        try:
            user32.KillTimer(hwnd, TASKBAR_LAYOUT_TIMER_ID)
        except Exception:
            pass
        return 0
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def run_taskbar_price_window(
    *,
    set_window_handle,
    set_ready,
    get_text_state,
    window_enabled,
    sync_visibility,
    show_main_window,
    set_enabled,
    refresh_price,
    open_risk_analysis,
    get_settings,
    set_windows_mode,
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
        user32.FindWindowW.restype = wintypes.HWND
        user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
        user32.FindWindowExW.restype = wintypes.HWND
        user32.FindWindowExW.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
        ]
        user32.GetClassNameW.argtypes = [
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        ]
        user32.GetClassNameW.restype = ctypes.c_int
        user32.GetWindowRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetWindowRect.restype = wintypes.BOOL
        user32.GetClientRect.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.RECT),
        ]
        user32.GetClientRect.restype = wintypes.BOOL
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.IsWindowVisible.restype = wintypes.BOOL
        user32.IsIconic.argtypes = [wintypes.HWND]
        user32.IsIconic.restype = wintypes.BOOL
        user32.GetWindowThreadProcessId.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        ]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.ShowWindow.restype = wintypes.BOOL
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.DestroyWindow.restype = wintypes.BOOL
        user32.SetLayeredWindowAttributes.argtypes = [
            wintypes.HWND,
            wintypes.COLORREF,
            wintypes.BYTE,
            wintypes.DWORD,
        ]
        user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
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
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        ctypes.windll.shell32.SHAppBarMessage.restype = ctypes.c_size_t
        ctypes.windll.shell32.SHAppBarMessage.argtypes = [
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        gdi32.SetTextColor.argtypes = [wintypes.HDC, wintypes.COLORREF]
        gdi32.SetBkMode.argtypes = [wintypes.HDC, ctypes.c_int]
        gdi32.CreateSolidBrush.restype = wintypes.HANDLE
        gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
        gdi32.CreatePen.restype = wintypes.HANDLE
        gdi32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wintypes.COLORREF]
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
        gdi32.MoveToEx.argtypes = [
            wintypes.HDC,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        gdi32.MoveToEx.restype = wintypes.BOOL
        gdi32.LineTo.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.LineTo.restype = wintypes.BOOL
        gdi32.GetTextExtentPoint32W.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.SIZE),
        ]
        gdi32.GetTextExtentPoint32W.restype = wintypes.BOOL
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
        user32.FillRect.argtypes = [
            wintypes.HDC,
            ctypes.POINTER(wintypes.RECT),
            wintypes.HANDLE,
        ]
        user32.DrawTextW.argtypes = [
            wintypes.HDC,
            wintypes.LPCWSTR,
            ctypes.c_int,
            ctypes.POINTER(wintypes.RECT),
            wintypes.UINT,
        ]

        def draw_window(hwnd):
            return draw_taskbar_window(
                hwnd,
                ctypes_module=ctypes,
                wintypes=wintypes,
                user32=user32,
                gdi32=gdi32,
                paint_struct_type=PaintStruct,
                get_text_state=get_text_state,
            )

        def show_context_menu(hwnd):
            return show_taskbar_context_menu(
                hwnd,
                ctypes_module=ctypes,
                wintypes=wintypes,
                user32=user32,
                show_main_window=show_main_window,
                set_enabled=set_enabled,
                refresh_price=refresh_price,
                open_risk_analysis=open_risk_analysis,
                get_settings=get_settings,
                set_windows_mode=set_windows_mode,
            )

        @window_proc_type
        def window_proc(hwnd, msg, wparam, lparam):
            return handle_taskbar_window_message(
                hwnd,
                msg,
                wparam,
                lparam,
                user32=user32,
                draw_window=draw_window,
                show_context_menu=show_context_menu,
                show_main_window=show_main_window,
                sync_visibility=sync_visibility,
            )

        instance = kernel32.GetModuleHandleW(None)
        class_name = "GoldMonitorTaskbarPriceWindow"
        window_class = WindowClass()
        window_class.style = CS_DBLCLKS
        window_class.lpfnWndProc = window_proc
        window_class.hInstance = instance
        window_class.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32649))
        window_class.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(window_class))

        hwnd = user32.CreateWindowExW(
            taskbar_window_ex_style(),
            class_name,
            "任务栏金价",
            WS_POPUP,
            0,
            0,
            TASKBAR_MINIMUM_WIDTH,
            32,
            None,
            None,
            instance,
            None,
        )
        if not hwnd:
            set_ready()
            return None

        if not enable_taskbar_transparency(hwnd, user32=user32):
            logger.warning("任务栏金价窗口透明效果初始化失败")
            user32.DestroyWindow(hwnd)
            set_ready()
            return None
        set_window_handle(hwnd)
        user32.SetTimer(hwnd, TASKBAR_LAYOUT_TIMER_ID, TASKBAR_LAYOUT_TIMER_MS, None)
        set_ready()
        if window_enabled():
            sync_visibility()

        message = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        return hwnd
    except Exception:
        logger.warning("任务栏金价窗口启动失败", exc_info=True)
        set_ready()
        return None
