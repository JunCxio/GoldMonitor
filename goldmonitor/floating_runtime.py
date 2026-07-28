import logging


WM_PAINT = 0x000F
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_MOUSEMOVE = 0x0200
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_CAPTURECHANGED = 0x0215
WM_DISPLAYCHANGE = 0x007E
WM_DESTROY = 0x0002

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
TPM_RIGHTBUTTON = 0x0002
TPM_RETURNCMD = 0x0100
FLOATING_MENU_OPEN = 1001
FLOATING_MENU_HIDE = 1002
FLOATING_MENU_REFRESH = 1003
FLOATING_MENU_RISK = 1004

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


def _load_win32_types():
    import ctypes
    from ctypes import wintypes

    return ctypes, wintypes


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
):
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes_module.byref(point)):
        return None
    menu = user32.CreatePopupMenu()
    if not menu:
        return None
    try:
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_OPEN, "打开主界面")
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_RISK, "风险分析")
        user32.AppendMenuW(menu, MF_STRING, FLOATING_MENU_REFRESH, "刷新行情")
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
):
    if msg == WM_PAINT:
        draw_window(hwnd)
        return 0
    if msg == WM_LBUTTONDOWN:
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
        return 0
    if msg == WM_DESTROY:
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
