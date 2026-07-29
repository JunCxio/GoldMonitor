from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_price_titles_follow_available_prices_and_display_mode():
    from goldmonitor.desktop_ui import format_macos_status_title, format_price_title

    assert format_price_title("GoldMonitor", rmb=528.1, usd=2345.6) == (
        "GoldMonitor ¥528.10/克 | $2,345.60/oz"
    )
    assert format_price_title("GoldMonitor", rmb=528.1) == "GoldMonitor ¥528.10/克"
    assert format_price_title("GoldMonitor", usd=2345.6) == "GoldMonitor $2,345.60/oz"
    assert format_price_title("GoldMonitor") == "GoldMonitor"

    assert format_macos_status_title({"floating_price_enabled": False}, 528.1, 2345.6) == "金价"
    assert format_macos_status_title({"floating_price_display_mode": "usd_only"}, 528.1, 2345.6) == "$2,346"
    assert format_macos_status_title({"floating_price_display_mode": "rmb_only"}, 528.1, 2345.6) == "¥528.10"
    assert format_macos_status_title({"floating_price_display_mode": "rmb_usd"}, 528.1, 2345.6) == (
        "¥528.10 $2,346"
    )
    assert format_macos_status_title({"floating_price_display_mode": "rmb_usd"}, None, None) == "金价 --"


def test_floating_price_text_formats_trend_time_and_source_state():
    from goldmonitor.desktop_ui import format_floating_price_text

    assert format_floating_price_text(
        {"floating_price_display_mode": "rmb_usd"},
        rmb=528.12,
        usd=2345.67,
        pct=-0.45,
        fetch_time="2026-06-12T10:09:30",
        source_name="Sina",
        gold_cached=False,
        rate_cached=False,
        fetch_ok=True,
        fetch_error="",
    ) == (
        "黄金 ¥528.12/克",
        "$2,345.67/oz  -0.45%",
        "10:09 · Sina · 实时",
        "down",
        "live",
    )
    assert format_floating_price_text(
        {"floating_price_display_mode": "usd_only"},
        rmb=528.12,
        usd=2345.67,
        pct=0.3,
        fetch_time=None,
        source_name="",
        gold_cached=True,
        rate_cached=False,
        fetch_ok=True,
        fetch_error="",
    ) == (
        "黄金 $2,345.67/oz",
        "+0.30%",
        "等待更新 · 行情源 · 缓存",
        "up",
        "cached",
    )

    assert format_floating_price_text(
        {"floating_price_display_mode": "rmb_only"},
        rmb=None,
        usd=None,
        pct=None,
        fetch_time="bad-time",
        source_name="EastMoney",
        gold_cached=False,
        rate_cached=False,
        fetch_ok=False,
        fetch_error="timeout",
    ) == (
        "黄金 --",
        "等待行情数据",
        "等待更新 · EastMoney · 异常",
        "neutral",
        "error",
    )


def test_taskbar_price_text_is_compact_and_respects_display_mode():
    from goldmonitor.desktop_ui import format_taskbar_price_text

    assert format_taskbar_price_text(
        {"floating_price_display_mode": "rmb_usd"},
        rmb=528.16,
        usd=2345.6,
        pct=0.42,
    ) == ("¥528.16  $2,346  +0.42%", "up")
    assert format_taskbar_price_text(
        {"floating_price_display_mode": "usd_only"},
        rmb=528.16,
        usd=2345.6,
        pct=-0.2,
    ) == ("$2,346  -0.20%", "down")
    assert format_taskbar_price_text({}, None, None, None) == ("金价 --", "neutral")


def test_floating_window_metrics_and_geometry_are_deterministic():
    from goldmonitor.desktop_ui import (
        clamp_floating_position,
        default_floating_position,
        floating_rect,
        floating_window_z_order,
        floating_window_metrics,
        floating_window_radius,
        floating_window_size,
        resolve_floating_position,
        snap_floating_position,
    )

    settings = {"floating_price_preset": "unknown"}
    assert floating_window_z_order({}) == "notopmost"
    assert floating_window_z_order({"floating_price_always_on_top": False}) == "notopmost"
    assert floating_window_z_order({"floating_price_always_on_top": True}) == "topmost"
    assert floating_window_metrics(settings)["size"] == (220, 52)
    assert floating_window_size(settings) == (220, 52)
    assert floating_window_radius(settings) == 14
    assert floating_rect((10, 3, -9, 21), width=220, height=52) == (10, 3, 211, 21)
    assert floating_rect(None, width=220, height=52) is None

    work_area = (0, 0, 1280, 720)
    size = (220, 52)
    assert clamp_floating_position(-100, 999, size, work_area) == (8, 660)
    assert default_floating_position(work_area, width=220, height=52) == (1044, 652)
    assert snap_floating_position(3, 400, size, work_area, enabled=True) == (8, 400)
    assert snap_floating_position(300, 400, size, work_area, enabled=True) == (300, 400)
    assert snap_floating_position(3, 400, size, work_area, enabled=False) == (3, 400)

    assert resolve_floating_position(
        {"floating_price_position_saved": False},
        size,
        work_area,
    ) == (1044, 652)
    assert resolve_floating_position(
        {"floating_price_position_saved": True, "floating_price_x": -20, "floating_price_y": 999},
        size,
        work_area,
    ) == (8, 660)


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("desktop ui module checks passed.")
