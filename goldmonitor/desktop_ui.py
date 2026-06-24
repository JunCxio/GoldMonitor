from datetime import datetime
import math


DEFAULT_FLOATING_PRICE_PRESET = "compact"

FLOATING_PRICE_PRESETS = {
    "minimal": {
        "size": (178, 40),
        "radius": 10,
        "title_font": -13,
        "meta_font": -9,
        "status_font": -8,
        "title_rect": (8, 2, -8, 20),
        "meta_rect": (8, 19, -8, -2),
        "status_rect": None,
    },
    "compact": {
        "size": (220, 52),
        "radius": 14,
        "title_font": -15,
        "meta_font": -10,
        "status_font": -9,
        "title_rect": (10, 3, -9, 21),
        "meta_rect": (10, 21, -9, 36),
        "status_rect": (10, 36, -9, -3),
    },
    "standard": {
        "size": (292, 78),
        "radius": 18,
        "title_font": -17,
        "meta_font": -12,
        "status_font": -11,
        "title_rect": (14, 7, -14, 30),
        "meta_rect": (14, 31, -14, 52),
        "status_rect": (14, 54, -14, -6),
    },
}


def format_price_title(app_name, rmb=None, usd=None):
    if rmb is not None and usd is not None:
        return f"{app_name} ¥{rmb:,.2f}/克 | ${usd:,.2f}/oz"
    if rmb is not None:
        return f"{app_name} ¥{rmb:,.2f}/克"
    if usd is not None:
        return f"{app_name} ${usd:,.2f}/oz"
    return app_name


def format_macos_status_title(settings, rmb=None, usd=None):
    settings = settings if isinstance(settings, dict) else {}
    if not settings.get("floating_price_enabled", True):
        return "金价"
    display_mode = settings.get("floating_price_display_mode", "rmb_usd")
    if display_mode == "usd_only" and usd is not None:
        return f"${usd:,.0f}"
    if display_mode == "rmb_only" and rmb is not None:
        return f"¥{rmb:,.2f}"
    if rmb is not None and usd is not None:
        return f"¥{rmb:,.2f} ${usd:,.0f}"
    if rmb is not None:
        return f"¥{rmb:,.2f}"
    if usd is not None:
        return f"${usd:,.0f}"
    return "金价 --"


def _parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _format_trend(pct):
    if pct is None:
        return "", "neutral"
    try:
        pct_value = float(pct)
    except (TypeError, ValueError):
        return "", "neutral"
    if not math.isfinite(pct_value):
        return "", "neutral"
    if pct_value > 0:
        return f"{pct_value:+.2f}%", "up"
    if pct_value < 0:
        return f"{pct_value:+.2f}%", "down"
    return f"{pct_value:+.2f}%", "neutral"


def _source_state(gold_cached=False, rate_cached=False, fetch_ok=False, fetch_error=""):
    if not fetch_ok and fetch_error:
        return "error", "异常"
    if gold_cached or rate_cached:
        return "cached", "缓存"
    if fetch_ok:
        return "live", "实时"
    return "waiting", "等待"


def format_floating_price_text(
    settings,
    rmb=None,
    usd=None,
    pct=None,
    fetch_time=None,
    source_name="",
    gold_cached=False,
    rate_cached=False,
    fetch_ok=False,
    fetch_error="",
):
    settings = settings if isinstance(settings, dict) else {}
    display_mode = settings.get("floating_price_display_mode", "rmb_usd")
    trend, trend_state = _format_trend(pct)

    parsed_time = _parse_iso_datetime(fetch_time)
    time_label = parsed_time.strftime("%H:%M") if parsed_time else "等待更新"
    source_state, source_label = _source_state(gold_cached, rate_cached, fetch_ok, fetch_error)
    status = f"{time_label} · {source_name or '行情源'} · {source_label}"

    if rmb is None and usd is None:
        return "黄金 --", "等待行情数据", status, "neutral", source_state

    if display_mode == "usd_only" and usd is not None:
        return f"黄金 ${usd:,.2f}/oz", trend or "双击打开主窗口", status, trend_state, source_state

    if rmb is not None:
        primary = f"黄金 ¥{rmb:,.2f}/克"
        if display_mode == "rmb_only" and trend:
            secondary = trend
        elif display_mode == "rmb_only":
            secondary = "双击打开主窗口"
        elif usd is not None and trend:
            secondary = f"${usd:,.2f}/oz  {trend}"
        elif usd is not None:
            secondary = f"${usd:,.2f}/oz"
        elif trend:
            secondary = trend
        else:
            secondary = "双击打开主窗口"
        return primary, secondary, status, trend_state, source_state

    if usd is not None:
        return f"黄金 ${usd:,.2f}/oz", trend or "双击打开主窗口", status, trend_state, source_state

    return "黄金 --", "等待行情数据", status, "neutral", source_state


def floating_window_metrics(settings, default_preset=DEFAULT_FLOATING_PRICE_PRESET, presets=None):
    settings = settings if isinstance(settings, dict) else {}
    presets = presets or FLOATING_PRICE_PRESETS
    preset = settings.get("floating_price_preset", default_preset)
    if preset not in presets:
        preset = default_preset
    return presets[preset]


def floating_rect(rect_config, width, height):
    if not rect_config:
        return None
    left, top, right, bottom = rect_config
    if right < 0:
        right = width + right
    if bottom < 0:
        bottom = height + bottom
    return left, top, right, bottom


def floating_window_size(settings, default_preset=DEFAULT_FLOATING_PRICE_PRESET, presets=None):
    return floating_window_metrics(settings, default_preset=default_preset, presets=presets)["size"]


def floating_window_radius(settings, default_preset=DEFAULT_FLOATING_PRICE_PRESET, presets=None):
    return floating_window_metrics(settings, default_preset=default_preset, presets=presets)["radius"]


def clamp_floating_position(x, y, window_size, work_area, edge_margin=8):
    width, height = window_size
    left, top, right, bottom = work_area
    min_x = left + edge_margin
    min_y = top + edge_margin
    max_x = max(min_x, right - width - edge_margin)
    max_y = max(min_y, bottom - height - edge_margin)
    return max(min_x, min(int(x), max_x)), max(min_y, min(int(y), max_y))


def default_floating_position(work_area, width, height, margin=16):
    _left, _top, right, bottom = work_area
    return right - width - margin, bottom - height - margin


def snap_floating_position(x, y, window_size, work_area, enabled=True, threshold=28, edge_margin=8):
    if not enabled:
        return x, y
    width, height = window_size
    left, top, right, bottom = work_area
    distances = [
        (abs(x - left), left + edge_margin, y),
        (abs((right - width) - x), right - width - edge_margin, y),
        (abs(y - top), x, top + edge_margin),
        (abs((bottom - height) - y), x, bottom - height - edge_margin),
    ]
    distance, snap_x, snap_y = min(distances, key=lambda item: item[0])
    if distance <= threshold:
        return clamp_floating_position(snap_x, snap_y, window_size, work_area, edge_margin=edge_margin)
    return x, y


def resolve_floating_position(settings, window_size, work_area):
    settings = settings if isinstance(settings, dict) else {}
    x = settings.get("floating_price_x")
    y = settings.get("floating_price_y")
    if not settings.get("floating_price_position_saved") or x is None or y is None:
        width, height = window_size
        x, y = default_floating_position(work_area, width, height)
    return clamp_floating_position(x, y, window_size, work_area)
