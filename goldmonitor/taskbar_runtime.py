import logging
import os


WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_MOUSEACTIVATE = 0x0021
WM_NULL = 0x0000
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_DISPLAYCHANGE = 0x007E
WM_SETTINGCHANGE = 0x001A
WM_DPICHANGED = 0x02E0
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
TASKBAR_MINIMUM_WIDTH = 104
TASKBAR_MARGIN = 3
TASKBAR_CONTENT_PADDING = 6
TASKBAR_CONTENT_GAP = 5
TASKBAR_ARROW_WIDTH = 9
TASKBAR_MINIMUM_PRICE_WIDTH = 42
TASKBAR_HIT_TARGET_ALPHA = 1
TASKBAR_DEFAULT_DPI = 96
TASKBAR_MAXIMUM_DPI = 480

ABM_GETSTATE = 0x00000004
ABS_AUTOHIDE = 0x00000001
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
HWND_TOP = 0
MA_NOACTIVATE = 3
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
BI_RGB = 0
DIB_RGB_COLORS = 0
CS_DBLCLKS = 0x0008

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


def normalize_taskbar_dpi(value):
    try:
        dpi = int(value)
    except (TypeError, ValueError):
        return TASKBAR_DEFAULT_DPI
    if dpi < TASKBAR_DEFAULT_DPI:
        return TASKBAR_DEFAULT_DPI
    return min(dpi, TASKBAR_MAXIMUM_DPI)


def scale_taskbar_metric(value, dpi, *, minimum=1):
    dpi = normalize_taskbar_dpi(dpi)
    scaled = int((int(value) * dpi / TASKBAR_DEFAULT_DPI) + 0.5)
    return max(int(minimum), scaled)


def taskbar_layout_metrics(dpi):
    dpi = normalize_taskbar_dpi(dpi)
    return {
        "dpi": dpi,
        "desired_width": scale_taskbar_metric(TASKBAR_DESIRED_WIDTH, dpi),
        "minimum_width": scale_taskbar_metric(TASKBAR_MINIMUM_WIDTH, dpi),
        "margin": scale_taskbar_metric(TASKBAR_MARGIN, dpi),
        "maximum_height": scale_taskbar_metric(34, dpi),
        "minimum_height": scale_taskbar_metric(24, dpi),
        "minimum_taskbar_height": scale_taskbar_metric(28, dpi),
    }


def taskbar_draw_metrics(dpi):
    dpi = normalize_taskbar_dpi(dpi)
    return {
        "dpi": dpi,
        "padding": scale_taskbar_metric(TASKBAR_CONTENT_PADDING, dpi),
        "gap": scale_taskbar_metric(TASKBAR_CONTENT_GAP, dpi),
        "arrow_width": scale_taskbar_metric(TASKBAR_ARROW_WIDTH, dpi),
        "arrow_gap": scale_taskbar_metric(3, dpi),
        "minimum_price_width": scale_taskbar_metric(
            TASKBAR_MINIMUM_PRICE_WIDTH,
            dpi,
        ),
        "brand_font_height": scale_taskbar_metric(14, dpi),
        "value_font_height": scale_taskbar_metric(13, dpi),
        "arrow_stroke": scale_taskbar_metric(2, dpi),
        "arrow_half_height": scale_taskbar_metric(5, dpi),
        "arrow_head_size": scale_taskbar_metric(4, dpi),
    }


def get_window_dpi(user32, hwnd):
    if not hwnd:
        return TASKBAR_DEFAULT_DPI
    getter = getattr(user32, "GetDpiForWindow", None)
    if not getter:
        return TASKBAR_DEFAULT_DPI
    try:
        return normalize_taskbar_dpi(getter(hwnd))
    except (OSError, TypeError, ValueError):
        return TASKBAR_DEFAULT_DPI


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
    }


def taskbar_window_ex_style():
    return WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE


def find_primary_taskbar(user32):
    return user32.FindWindowW("Shell_TrayWnd", None)


def create_taskbar_price_window(user32, *, class_name, instance):
    taskbar_owner = find_primary_taskbar(user32)
    if not taskbar_owner:
        return None
    return user32.CreateWindowExW(
        taskbar_window_ex_style(),
        class_name,
        "任务栏金价",
        WS_POPUP,
        0,
        0,
        TASKBAR_MINIMUM_WIDTH,
        32,
        taskbar_owner,
        None,
        instance,
        None,
    )


def layout_taskbar_content(
    client_width,
    *,
    brand_width,
    price_width,
    change_width=0,
    padding=None,
    dpi=TASKBAR_DEFAULT_DPI,
):
    metrics = taskbar_draw_metrics(dpi)
    client_width = max(0, int(client_width))
    brand_width = max(0, int(brand_width))
    price_width = max(0, int(price_width))
    change_width = max(0, int(change_width))
    padding = metrics["padding"] if padding is None else max(0, int(padding))
    has_change = change_width > 0
    available = max(0, client_width - (2 * padding))
    fixed_width = brand_width + metrics["gap"]
    if has_change:
        fixed_width += (
            metrics["gap"]
            + metrics["arrow_width"]
            + metrics["arrow_gap"]
            + change_width
        )
    maximum_price_width = max(
        metrics["minimum_price_width"],
        available - fixed_width,
    )
    drawn_price_width = min(price_width, maximum_price_width)
    total_width = fixed_width + drawn_price_width
    start_x = max(padding, (client_width - total_width) // 2)

    brand = (start_x, brand_width)
    price_x = start_x + brand_width + metrics["gap"]
    price = (price_x, drawn_price_width)
    arrow = None
    change = None
    if has_change:
        arrow_x = price_x + drawn_price_width + metrics["gap"]
        arrow = (arrow_x, metrics["arrow_width"])
        change = (
            arrow_x + metrics["arrow_width"] + metrics["arrow_gap"],
            change_width,
        )
    return {
        "brand": brand,
        "price": price,
        "arrow": arrow,
        "change": change,
        "total_width": total_width,
        "price_clipped": drawn_price_width < price_width,
    }


def preferred_taskbar_window_width(
    state,
    *,
    dpi=TASKBAR_DEFAULT_DPI,
    font_loader=None,
    measure_text=None,
):
    font_loader = font_loader or load_taskbar_font
    if measure_text is None:
        from PIL import Image, ImageDraw

        draw = ImageDraw.Draw(Image.new("L", (1, 1)))

        def measure_text(text, font):
            bounds = draw.textbbox((0, 0), text, font=font)
            return max(0, int(bounds[2] - bounds[0]))

    dpi = normalize_taskbar_dpi(dpi)
    layout_metrics = taskbar_layout_metrics(dpi)
    draw_metrics = taskbar_draw_metrics(dpi)
    brand_font = font_loader(draw_metrics["brand_font_height"], bold=True)
    value_font = font_loader(draw_metrics["value_font_height"], bold=False)
    brand_width = measure_text("Au", brand_font)
    price_width = measure_text(str(state.get("price") or "--"), value_font)
    change_text = str(state.get("change") or "")
    change_width = measure_text(change_text, value_font) if change_text else 0
    content_width = brand_width + draw_metrics["gap"] + price_width
    if change_width:
        content_width += (
            draw_metrics["gap"]
            + draw_metrics["arrow_width"]
            + draw_metrics["arrow_gap"]
            + change_width
        )
    preferred_width = content_width + (2 * draw_metrics["padding"])
    return max(
        layout_metrics["minimum_width"],
        min(layout_metrics["desired_width"], preferred_width),
    )


def load_taskbar_font(pixel_height, *, bold=False, font_module=None, windows_dir=None):
    if font_module is None:
        from PIL import ImageFont as font_module

    pixel_height = max(8, int(pixel_height))
    windows_dir = windows_dir or os.environ.get("WINDIR", r"C:\Windows")
    font_names = (
        ("segoeuib.ttf", "seguisb.ttf", "segoeui.ttf")
        if bold
        else ("seguisb.ttf", "segoeui.ttf", "arial.ttf")
    )
    for font_name in font_names:
        font_path = os.path.join(windows_dir, "Fonts", font_name)
        try:
            return font_module.truetype(font_path, pixel_height)
        except (OSError, TypeError):
            continue
    try:
        return font_module.load_default(size=pixel_height)
    except TypeError:
        return font_module.load_default()


def ellipsize_taskbar_text(text, maximum_width, measure_text):
    text = str(text or "")
    maximum_width = max(0, int(maximum_width))
    if not text or maximum_width <= 0:
        return ""
    if measure_text(text) <= maximum_width:
        return text
    ellipsis = "…"
    if measure_text(ellipsis) > maximum_width:
        return ""
    low = 0
    high = len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if measure_text(text[:middle] + ellipsis) <= maximum_width:
            low = middle
        else:
            high = middle - 1
    return text[:low] + ellipsis


def render_taskbar_surface(
    width,
    height,
    state,
    *,
    light_theme,
    dpi=TASKBAR_DEFAULT_DPI,
    font_loader=load_taskbar_font,
):
    from PIL import Image, ImageDraw

    width = max(1, int(width))
    height = max(1, int(height))
    dpi = normalize_taskbar_dpi(dpi)
    metrics = taskbar_draw_metrics(dpi)
    image = Image.new(
        "RGBA",
        (width, height),
        (0, 0, 0, TASKBAR_HIT_TARGET_ALPHA),
    )
    draw = ImageDraw.Draw(image)

    source_state = state.get("source_state", "waiting")
    trend_state = state.get("trend_state", "neutral")
    palette = taskbar_draw_palette(
        light_theme=bool(light_theme),
        source_state=source_state,
        trend_state=trend_state,
    )
    brand_text = "Au"
    price_text = str(state.get("price") or "--")
    change_text = str(state.get("change") or "")
    brand_font = font_loader(metrics["brand_font_height"], bold=True)
    value_font = font_loader(metrics["value_font_height"], bold=False)

    def text_width(text, font):
        bounds = draw.textbbox((0, 0), text, font=font)
        return max(0, int(bounds[2] - bounds[0]))

    brand_width = text_width(brand_text, brand_font)
    price_width = text_width(price_text, value_font)
    change_width = text_width(change_text, value_font) if change_text else 0
    layout = layout_taskbar_content(
        width,
        brand_width=brand_width,
        price_width=price_width,
        change_width=change_width,
        dpi=dpi,
    )
    visible_price = ellipsize_taskbar_text(
        price_text,
        layout["price"][1],
        lambda value: text_width(value, value_font),
    )

    def draw_centered_text(text, segment, font, color):
        if not text or not segment:
            return
        left, _segment_width = segment
        bounds = draw.textbbox((0, 0), text, font=font)
        text_height = bounds[3] - bounds[1]
        top = ((height - text_height) // 2) - bounds[1]
        draw.text((left, top), text, font=font, fill=(*color, 255))

    draw_centered_text(brand_text, layout["brand"], brand_font, palette["brand"])
    draw_centered_text(visible_price, layout["price"], value_font, palette["price"])
    draw_centered_text(change_text, layout["change"], value_font, palette["trend"])

    if layout["arrow"]:
        arrow_left, arrow_width = layout["arrow"]
        center_x = arrow_left + (arrow_width // 2)
        center_y = height // 2
        half_height = metrics["arrow_half_height"]
        head_size = metrics["arrow_head_size"]
        stroke = metrics["arrow_stroke"]
        color = (*palette["trend"], 255)
        if trend_state == "up":
            tip_y = center_y - half_height
            end_y = center_y + half_height
            draw.line((center_x, end_y, center_x, tip_y), fill=color, width=stroke)
            draw.line(
                (center_x, tip_y, center_x - head_size, tip_y + head_size),
                fill=color,
                width=stroke,
            )
            draw.line(
                (center_x, tip_y, center_x + head_size, tip_y + head_size),
                fill=color,
                width=stroke,
            )
        elif trend_state == "down":
            tip_y = center_y + half_height
            end_y = center_y - half_height
            draw.line((center_x, end_y, center_x, tip_y), fill=color, width=stroke)
            draw.line(
                (center_x, tip_y, center_x - head_size, tip_y - head_size),
                fill=color,
                width=stroke,
            )
            draw.line(
                (center_x, tip_y, center_x + head_size, tip_y - head_size),
                fill=color,
                width=stroke,
            )
        else:
            draw.line(
                (center_x - head_size, center_y, center_x + head_size, center_y),
                fill=color,
                width=stroke,
            )
    return image


def premultiply_taskbar_surface(image):
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    source = image.tobytes()
    result = bytearray(len(source))
    for index in range(0, len(source), 4):
        red, green, blue, alpha = source[index:index + 4]
        result[index] = (blue * alpha + 127) // 255
        result[index + 1] = (green * alpha + 127) // 255
        result[index + 2] = (red * alpha + 127) // 255
        result[index + 3] = alpha
    return bytes(result)


def update_layered_taskbar_window(
    hwnd,
    image,
    *,
    ctypes_module,
    wintypes,
    user32,
    gdi32,
):
    class BitmapInfoHeader(ctypes_module.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", wintypes.LONG),
            ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", wintypes.LONG),
            ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    class RgbQuad(ctypes_module.Structure):
        _fields_ = [
            ("rgbBlue", wintypes.BYTE),
            ("rgbGreen", wintypes.BYTE),
            ("rgbRed", wintypes.BYTE),
            ("rgbReserved", wintypes.BYTE),
        ]

    class BitmapInfo(ctypes_module.Structure):
        _fields_ = [
            ("bmiHeader", BitmapInfoHeader),
            ("bmiColors", RgbQuad * 1),
        ]

    class BlendFunction(ctypes_module.Structure):
        _fields_ = [
            ("BlendOp", wintypes.BYTE),
            ("BlendFlags", wintypes.BYTE),
            ("SourceConstantAlpha", wintypes.BYTE),
            ("AlphaFormat", wintypes.BYTE),
        ]

    width, height = image.size
    screen_dc = user32.GetDC(None)
    if not screen_dc:
        return False
    memory_dc = None
    bitmap = None
    old_bitmap = None
    try:
        memory_dc = gdi32.CreateCompatibleDC(screen_dc)
        if not memory_dc:
            return False
        bitmap_info = BitmapInfo()
        bitmap_info.bmiHeader.biSize = ctypes_module.sizeof(BitmapInfoHeader)
        bitmap_info.bmiHeader.biWidth = width
        bitmap_info.bmiHeader.biHeight = -height
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB
        bits = ctypes_module.c_void_p()
        bitmap = gdi32.CreateDIBSection(
            screen_dc,
            ctypes_module.byref(bitmap_info),
            DIB_RGB_COLORS,
            ctypes_module.byref(bits),
            None,
            0,
        )
        if not bitmap or not bits.value:
            return False
        pixel_data = premultiply_taskbar_surface(image)
        ctypes_module.memmove(bits, pixel_data, len(pixel_data))
        old_bitmap = gdi32.SelectObject(memory_dc, bitmap)
        source_point = wintypes.POINT(0, 0)
        window_size = wintypes.SIZE(width, height)
        blend = BlendFunction(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        return bool(
            user32.UpdateLayeredWindow(
                hwnd,
                screen_dc,
                None,
                ctypes_module.byref(window_size),
                memory_dc,
                ctypes_module.byref(source_point),
                0,
                ctypes_module.byref(blend),
                ULW_ALPHA,
            )
        )
    finally:
        if old_bitmap and memory_dc:
            gdi32.SelectObject(memory_dc, old_bitmap)
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if memory_dc:
            gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, screen_dc)


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
    desired_width=None,
    minimum_width=None,
    margin=None,
    dpi=TASKBAR_DEFAULT_DPI,
):
    metrics = taskbar_layout_metrics(dpi)
    desired_width = (
        metrics["desired_width"] if desired_width is None else int(desired_width)
    )
    minimum_width = (
        metrics["minimum_width"] if minimum_width is None else int(minimum_width)
    )
    margin = metrics["margin"] if margin is None else int(margin)
    taskbar_rect = normalize_rect(taskbar_rect)
    tray_rect = normalize_rect(tray_rect)
    task_list_rect = normalize_rect(task_list_rect)
    if not taskbar_rect or not tray_rect or not task_list_rect:
        return None

    left, top, right, bottom = taskbar_rect
    taskbar_width = right - left
    taskbar_height = bottom - top
    if (
        taskbar_width <= taskbar_height
        or taskbar_height < metrics["minimum_taskbar_height"]
    ):
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
    width = min(desired_width, usable_width)
    if width < minimum_width:
        return None
    height = min(metrics["maximum_height"], taskbar_height - (2 * margin))
    if height < metrics["minimum_height"]:
        return None
    x = free_right - margin - width
    y = top + max(margin, (taskbar_height - height) // 2)
    return {
        "x": int(x),
        "y": int(y),
        "width": int(width),
        "height": int(height),
        "dpi": metrics["dpi"],
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
    text_state=None,
    ctypes_loader=_load_win32_types,
):
    try:
        taskbar_hwnd = find_primary_taskbar(user32)
        if not taskbar_hwnd:
            return None, {"visible": False, "reason": "taskbar_not_found"}
        dpi = get_window_dpi(user32, taskbar_hwnd)
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
        desired_width = (
            preferred_taskbar_window_width(text_state, dpi=dpi)
            if text_state is not None
            else None
        )
        layout = choose_taskbar_layout(
            taskbar_rect,
            tray_rect=tray_rect,
            task_list_rect=task_list_rect,
            start_rect=start_rect,
            desired_width=desired_width,
            dpi=dpi,
        )
        if not layout:
            return None, {
                "visible": False,
                "reason": "insufficient_taskbar_space",
                "taskbar_rect": taskbar_rect,
                "dpi": dpi,
            }
        return layout, {
            "visible": False,
            "reason": "ready",
            "taskbar_rect": taskbar_rect,
            "dpi": dpi,
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
    get_layout_state=None,
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

        bounds = (
            layout["x"],
            layout["y"],
            layout["width"],
            layout["height"],
        )
        previous = dict(get_layout_state() or {}) if get_layout_state else {}
        was_visible = bool(previous.get("visible"))
        position_changed = previous.get("bounds") != bounds

        if position_changed:
            positioned = user32.SetWindowPos(
                hwnd,
                ctypes.c_void_p(HWND_TOP),
                *bounds,
                SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            if not positioned:
                user32.ShowWindow(hwnd, 0)
                set_layout_state(
                    {**state, "visible": False, "reason": "position_error"}
                )
                return False
        elif not was_visible:
            user32.ShowWindow(hwnd, 4)

        next_state = {
            **state,
            "visible": True,
            "reason": "visible",
            "bounds": bounds,
        }
        set_layout_state(next_state)
        if position_changed or not was_visible:
            invalidate()
        return True
    except Exception:
        set_layout_state({"visible": False, "reason": "visibility_error"})
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
    dpi_provider=None,
):
    paint = paint_struct_type()
    hdc = user32.BeginPaint(hwnd, ctypes_module.byref(paint))
    if not hdc:
        return None
    try:
        client = wintypes.RECT()
        user32.GetClientRect(hwnd, ctypes_module.byref(client))
    finally:
        user32.EndPaint(hwnd, ctypes_module.byref(paint))
    dpi = normalize_taskbar_dpi(
        dpi_provider(hwnd) if dpi_provider else get_window_dpi(user32, hwnd)
    )
    surface = render_taskbar_surface(
        client.right,
        client.bottom,
        get_text_state(),
        light_theme=bool(light_theme_provider()),
        dpi=dpi,
    )
    return update_layered_taskbar_window(
        hwnd,
        surface,
        ctypes_module=ctypes_module,
        wintypes=wintypes,
        user32=user32,
        gdi32=gdi32,
    )


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
        try:
            user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        except (AttributeError, OSError):
            pass

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
    if msg == WM_MOUSEACTIVATE:
        return MA_NOACTIVATE
    if msg in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
        show_main_window()
        return 0
    if msg in (WM_RBUTTONUP, WM_CONTEXTMENU):
        show_context_menu(hwnd)
        return 0
    if msg in (WM_DISPLAYCHANGE, WM_SETTINGCHANGE, WM_DPICHANGED, WM_THEMECHANGED):
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
        try:
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT
        except AttributeError:
            pass
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
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        user32.ReleaseDC.restype = ctypes.c_int
        user32.UpdateLayeredWindow.argtypes = [
            wintypes.HWND,
            wintypes.HDC,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.HDC,
            ctypes.c_void_p,
            wintypes.COLORREF,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        user32.UpdateLayeredWindow.restype = wintypes.BOOL
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
        user32.PostMessageW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        ]
        user32.PostMessageW.restype = wintypes.BOOL
        user32.LoadCursorW.restype = wintypes.HANDLE
        user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        ctypes.windll.shell32.SHAppBarMessage.restype = ctypes.c_size_t
        ctypes.windll.shell32.SHAppBarMessage.argtypes = [
            wintypes.DWORD,
            ctypes.c_void_p,
        ]
        gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
        gdi32.CreateCompatibleDC.restype = wintypes.HDC
        gdi32.DeleteDC.argtypes = [wintypes.HDC]
        gdi32.DeleteDC.restype = wintypes.BOOL
        gdi32.CreateDIBSection.argtypes = [
            wintypes.HDC,
            ctypes.c_void_p,
            wintypes.UINT,
            ctypes.c_void_p,
            wintypes.HANDLE,
            wintypes.DWORD,
        ]
        gdi32.CreateDIBSection.restype = wintypes.HANDLE
        gdi32.SelectObject.restype = wintypes.HANDLE
        gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        gdi32.DeleteObject.argtypes = [wintypes.HANDLE]

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

        hwnd = create_taskbar_price_window(
            user32,
            class_name=class_name,
            instance=instance,
        )
        if not hwnd:
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
