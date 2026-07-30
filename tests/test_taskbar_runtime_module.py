from types import SimpleNamespace

import pytest


def test_taskbar_layout_uses_only_free_horizontal_space():
    from goldmonitor.taskbar_runtime import choose_taskbar_layout

    layout = choose_taskbar_layout(
        (0, 1040, 1920, 1080),
        start_rect=(0, 1040, 60, 1080),
        task_list_rect=(60, 1040, 1450, 1080),
        tray_rect=(1740, 1040, 1920, 1080),
    )

    assert layout == {
        "x": 1513,
        "y": 1043,
        "width": 224,
        "height": 34,
        "dpi": 96,
        "orientation": "horizontal",
        "taskbar_rect": (0, 1040, 1920, 1080),
    }


def test_taskbar_discovery_returns_primary_and_bounded_secondary_targets():
    from goldmonitor.taskbar_runtime import (
        discover_taskbars,
        find_secondary_taskbars,
    )

    secondary_handles = {None: 201, 201: 202, 202: None}
    user32 = SimpleNamespace(
        FindWindowW=lambda class_name, title: 101,
        FindWindowExW=lambda parent, previous, class_name, title: secondary_handles[
            previous
        ],
    )

    assert discover_taskbars(user32) == [
        {
            "hwnd": 101,
            "kind": "primary",
            "index": 0,
            "class_name": "Shell_TrayWnd",
            "count": 3,
        },
        {
            "hwnd": 201,
            "kind": "secondary",
            "index": 1,
            "class_name": "Shell_SecondaryTrayWnd",
            "count": 3,
        },
        {
            "hwnd": 202,
            "kind": "secondary",
            "index": 2,
            "class_name": "Shell_SecondaryTrayWnd",
            "count": 3,
        },
    ]

    repeated = SimpleNamespace(FindWindowExW=lambda *args: 201)
    assert find_secondary_taskbars(repeated, limit=16) == [201]


def test_taskbar_selection_prefers_primary_and_falls_back_to_secondary(monkeypatch):
    from goldmonitor import taskbar_runtime

    targets = [
        {"hwnd": 101, "kind": "primary", "index": 0, "count": 2},
        {"hwnd": 201, "kind": "secondary", "index": 1, "count": 2},
    ]
    calls = []
    monkeypatch.setattr(taskbar_runtime, "discover_taskbars", lambda user32: targets)

    def resolve(**kwargs):
        target = kwargs["taskbar_target"]
        calls.append(target["hwnd"])
        if target["kind"] == "primary":
            return None, {"reason": "insufficient_taskbar_space"}
        return {"x": 10}, {"reason": "ready", "taskbar_kind": "secondary"}

    monkeypatch.setattr(taskbar_runtime, "resolve_taskbar_layout", resolve)

    target, layout, state = taskbar_runtime.select_taskbar_layout(
        user32=object(),
        shell32=object(),
    )

    assert calls == [101, 201]
    assert target == targets[1]
    assert layout == {"x": 10}
    assert state["taskbar_kind"] == "secondary"
    assert state["candidate_failures"] == [
        {
            "taskbar_kind": "primary",
            "taskbar_index": 0,
            "reason": "insufficient_taskbar_space",
        }
    ]

    calls.clear()
    monkeypatch.setattr(
        taskbar_runtime,
        "resolve_taskbar_layout",
        lambda **kwargs: calls.append(kwargs["taskbar_target"]["hwnd"])
        or ({"x": 20}, {"reason": "ready"}),
    )
    selected, _layout, state = taskbar_runtime.select_taskbar_layout(
        user32=object(),
        shell32=object(),
    )
    assert selected == targets[0]
    assert calls == [101]
    assert state["candidate_failures"] == []


def test_taskbar_layout_and_draw_metrics_scale_with_window_dpi():
    from goldmonitor.taskbar_runtime import (
        choose_taskbar_layout,
        get_window_dpi,
        taskbar_draw_metrics,
        taskbar_layout_metrics,
    )

    assert taskbar_layout_metrics(144) == {
        "dpi": 144,
        "desired_width": 336,
        "minimum_width": 156,
        "margin": 5,
        "maximum_height": 51,
        "minimum_height": 36,
        "minimum_taskbar_height": 42,
    }
    assert taskbar_draw_metrics(192) == {
        "dpi": 192,
        "padding": 12,
        "gap": 10,
        "arrow_width": 18,
        "arrow_gap": 6,
        "minimum_price_width": 84,
        "brand_font_height": 28,
        "value_font_height": 26,
        "arrow_stroke": 4,
        "arrow_half_height": 10,
        "arrow_head_size": 8,
    }
    assert get_window_dpi(SimpleNamespace(GetDpiForWindow=lambda hwnd: 144), 42) == 144
    assert get_window_dpi(SimpleNamespace(), 42) == 96

    layout = choose_taskbar_layout(
        (0, 1560, 2880, 1620),
        start_rect=(0, 1560, 90, 1620),
        task_list_rect=(90, 1560, 2175, 1620),
        tray_rect=(2610, 1560, 2880, 1620),
        dpi=144,
    )
    assert layout == {
        "x": 2269,
        "y": 1565,
        "width": 336,
        "height": 50,
        "dpi": 144,
        "orientation": "horizontal",
        "taskbar_rect": (0, 1560, 2880, 1620),
    }


def test_taskbar_window_width_tracks_visible_content():
    from goldmonitor.taskbar_runtime import preferred_taskbar_window_width

    widths = {
        "Au": 18,
        "--": 14,
        "¥879.83": 52,
        "+0.42%": 47,
    }
    font_loader = lambda height, bold=False: (height, bold)
    measure_text = lambda text, font: widths[text]

    assert preferred_taskbar_window_width(
        {"price": "--", "change": ""},
        font_loader=font_loader,
        measure_text=measure_text,
    ) == 104
    assert preferred_taskbar_window_width(
        {"price": "¥879.83", "change": "+0.42%"},
        font_loader=font_loader,
        measure_text=measure_text,
    ) == 151


def test_taskbar_content_layout_prioritizes_brand_trend_and_price_readability():
    from goldmonitor.taskbar_runtime import layout_taskbar_content

    layout = layout_taskbar_content(
        224,
        brand_width=18,
        price_width=110,
        change_width=50,
    )

    assert layout == {
        "brand": (12, 18),
        "price": (35, 110),
        "arrow": (150, 9),
        "change": (162, 50),
        "total_width": 200,
        "price_clipped": False,
    }

    compact = layout_taskbar_content(
        154,
        brand_width=18,
        price_width=110,
        change_width=50,
    )
    assert compact["price"] == (29, 52)
    assert compact["change"] == (98, 50)
    assert compact["price_clipped"] is True


def test_taskbar_palette_adapts_to_system_theme_and_source_state():
    from goldmonitor.taskbar_runtime import taskbar_draw_palette

    light = taskbar_draw_palette(
        light_theme=True,
        source_state="live",
        trend_state="up",
    )
    dark = taskbar_draw_palette(
        light_theme=False,
        source_state="error",
        trend_state="down",
    )

    assert light["price"] == (32, 38, 45)
    assert light["brand"] == (154, 106, 10)
    assert light["trend"] == (201, 52, 63)
    assert dark["price"] == (241, 244, 247)
    assert dark["brand"] == (255, 107, 118)
    assert dark["trend"] == (76, 197, 138)


def test_taskbar_theme_detection_reads_windows_system_theme():
    from goldmonitor.taskbar_runtime import taskbar_uses_light_theme

    closed = []
    registry = SimpleNamespace(
        HKEY_CURRENT_USER=1,
        OpenKey=lambda root, path: 42,
        QueryValueEx=lambda key, name: (1, 4),
        CloseKey=lambda key: closed.append(key),
    )

    assert taskbar_uses_light_theme(lambda: registry) is True
    assert closed == [42]
    assert taskbar_uses_light_theme(lambda: (_ for _ in ()).throw(OSError())) is False


def test_taskbar_window_keeps_transparent_surface_fully_interactive():
    Image = pytest.importorskip("PIL.Image")

    from goldmonitor.taskbar_runtime import (
        WS_EX_LAYERED,
        WS_EX_NOACTIVATE,
        WS_EX_TOOLWINDOW,
        premultiply_taskbar_surface,
        render_taskbar_surface,
        taskbar_window_ex_style,
    )

    surface = render_taskbar_surface(
        224,
        34,
        {
            "price": "¥879.83",
            "change": "+0.42%",
            "trend_state": "up",
            "source_state": "live",
        },
        light_theme=True,
    )

    assert taskbar_window_ex_style() == (
        WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE
    )
    assert surface.mode == "RGBA"
    assert surface.getpixel((0, 0))[3] == 1
    assert surface.getchannel("A").getextrema() == (1, 255)
    assert all(alpha > 0 for alpha in surface.getchannel("A").tobytes())
    assert any(0 < alpha < 255 for alpha in surface.getchannel("A").tobytes())

    pixel = Image.new("RGBA", (1, 1), (100, 50, 25, 128))
    assert premultiply_taskbar_surface(pixel) == bytes((13, 25, 50, 128))


def test_taskbar_window_is_created_as_shell_owned_popup():
    from goldmonitor.taskbar_runtime import create_taskbar_price_window

    calls = []
    user32 = SimpleNamespace(CreateWindowExW=lambda *args: calls.append(args) or 42)

    assert create_taskbar_price_window(
        user32,
        taskbar_owner=84,
        class_name="GoldMonitorTaskbarPriceWindow",
        instance=7,
    ) == 42
    assert calls[0][8] == 84

    assert create_taskbar_price_window(
        user32,
        taskbar_owner=None,
        class_name="GoldMonitorTaskbarPriceWindow",
        instance=7,
    ) is None


def test_taskbar_layered_window_uploads_premultiplied_pixels():
    import ctypes
    from ctypes import wintypes

    Image = pytest.importorskip("PIL.Image")

    from goldmonitor.taskbar_runtime import update_layered_taskbar_window

    buffer = (ctypes.c_ubyte * 4)()
    calls = []

    def create_dib_section(hdc, bitmap_info, usage, bits, section, offset):
        bits._obj.value = ctypes.addressof(buffer)
        return 3

    user32 = SimpleNamespace(
        GetDC=lambda hwnd: 1,
        ReleaseDC=lambda hwnd, hdc: calls.append(("release", hwnd, hdc)) or 1,
        UpdateLayeredWindow=lambda *args: calls.append(("update", args[-1])) or True,
    )
    gdi32 = SimpleNamespace(
        CreateCompatibleDC=lambda hdc: 2,
        CreateDIBSection=create_dib_section,
        SelectObject=lambda hdc, value: 4,
        DeleteObject=lambda value: calls.append(("delete_object", value)) or True,
        DeleteDC=lambda hdc: calls.append(("delete_dc", hdc)) or True,
    )

    image = Image.new("RGBA", (1, 1), (100, 50, 25, 128))
    assert update_layered_taskbar_window(
        42,
        image,
        ctypes_module=ctypes,
        wintypes=wintypes,
        user32=user32,
        gdi32=gdi32,
    ) is True
    assert bytes(buffer) == bytes((13, 25, 50, 128))
    assert calls[-1] == ("release", None, 1)


def test_taskbar_draw_updates_layered_surface_without_color_key(monkeypatch):
    import ctypes
    from ctypes import wintypes

    from goldmonitor import taskbar_runtime

    class PaintStruct(ctypes.Structure):
        _fields_ = [("unused", ctypes.c_int)]

    calls = []

    def get_client_rect(hwnd, pointer):
        pointer._obj.left = 0
        pointer._obj.top = 0
        pointer._obj.right = 336
        pointer._obj.bottom = 51
        return True

    user32 = SimpleNamespace(
        BeginPaint=lambda hwnd, pointer: 7,
        EndPaint=lambda hwnd, pointer: True,
        GetClientRect=get_client_rect,
    )
    surface = object()
    monkeypatch.setattr(
        taskbar_runtime,
        "render_taskbar_surface",
        lambda width, height, state, **kwargs: calls.append(
            ("render", width, height, state, kwargs)
        ) or surface,
    )
    monkeypatch.setattr(
        taskbar_runtime,
        "update_layered_taskbar_window",
        lambda hwnd, image, **kwargs: calls.append(("update", hwnd, image)) or True,
    )

    assert taskbar_runtime.draw_taskbar_window(
        42,
        ctypes_module=ctypes,
        wintypes=wintypes,
        user32=user32,
        gdi32=SimpleNamespace(),
        paint_struct_type=PaintStruct,
        get_text_state=lambda: {
            "price": "¥879.83",
            "change": "+0.42%",
            "trend_state": "up",
            "source_state": "live",
        },
        light_theme_provider=lambda: True,
        dpi_provider=lambda hwnd: 144,
    ) is True

    assert calls[0][0:3] == ("render", 336, 51)
    assert calls[0][4] == {"light_theme": True, "dpi": 144}
    assert calls[1] == ("update", 42, surface)


def test_taskbar_layout_rejects_vertical_or_fully_occupied_taskbars():
    from goldmonitor.taskbar_runtime import choose_taskbar_layout

    assert choose_taskbar_layout(
        (0, 0, 48, 1080),
        task_list_rect=(0, 60, 48, 900),
        tray_rect=(0, 900, 48, 1080),
    ) is None
    assert choose_taskbar_layout(
        (0, 1040, 1920, 1080),
        start_rect=(0, 1040, 60, 1080),
        task_list_rect=(60, 1040, 1740, 1080),
        tray_rect=(1740, 1040, 1920, 1080),
    ) is None


def test_secondary_taskbar_layout_does_not_require_notification_area(monkeypatch):
    from goldmonitor import taskbar_runtime

    rects = {
        201: (1920, 1040, 3840, 1080),
        301: (1980, 1040, 3500, 1080),
        302: (1920, 1040, 1980, 1080),
    }

    def find_region(user32, parent, class_names, **kwargs):
        if "TrayNotifyWnd" in class_names:
            return None
        if "MSTaskListWClass" in class_names:
            return 301
        if "Start" in class_names:
            return 302
        return None

    monkeypatch.setattr(taskbar_runtime, "find_descendant_window", find_region)
    monkeypatch.setattr(
        taskbar_runtime,
        "get_window_rect",
        lambda user32, hwnd, **kwargs: rects.get(hwnd),
    )
    monkeypatch.setattr(taskbar_runtime, "get_window_dpi", lambda user32, hwnd: 96)
    monkeypatch.setattr(
        taskbar_runtime,
        "taskbar_is_auto_hidden",
        lambda *args, **kwargs: False,
    )

    layout, state = taskbar_runtime.resolve_taskbar_layout(
        user32=object(),
        shell32=object(),
        taskbar_target={
            "hwnd": 201,
            "kind": "secondary",
            "index": 1,
            "count": 2,
        },
    )

    assert layout["x"] == 3613
    assert layout["taskbar_rect"] == rects[201]
    assert state["reason"] == "ready"
    assert state["taskbar_kind"] == "secondary"
    assert state["taskbar_index"] == 1


def test_taskbar_auto_hide_state_uses_shell_appbar_contract():
    from goldmonitor.taskbar_runtime import taskbar_is_auto_hidden

    shell32 = SimpleNamespace(SHAppBarMessage=lambda message, data: 1)

    assert taskbar_is_auto_hidden(42, shell32=shell32) is True
    shell32.SHAppBarMessage = lambda message, data: 0
    assert taskbar_is_auto_hidden(42, shell32=shell32) is False


def test_taskbar_visibility_positions_without_activation_and_tracks_state():
    import ctypes as real_ctypes

    from goldmonitor.taskbar_runtime import set_taskbar_window_visible

    calls = []
    states = []
    user32 = SimpleNamespace(
        ShowWindow=lambda hwnd, command: calls.append(("show", hwnd, command)),
        SetWindowPos=lambda *args: calls.append(("position", args)) or True,
    )
    ctypes_module = SimpleNamespace(
        windll=SimpleNamespace(user32=user32),
        c_void_p=real_ctypes.c_void_p,
        sizeof=real_ctypes.sizeof,
    )
    layout = {"x": 100, "y": 200, "width": 180, "height": 32}

    result = set_taskbar_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        layout_provider=lambda: (layout, {"reason": "ready"}),
        should_suppress=lambda hwnd, target: False,
        set_layout_state=lambda state: states.append(state),
        get_layout_state=lambda: states[-1] if states else {},
        invalidate=lambda: calls.append("invalidate"),
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    )

    assert result is True
    assert calls[0][0] == "position"
    assert calls[0][1][2:6] == (100, 200, 180, 32)
    assert calls[-1] == "invalidate"
    assert states[-1]["visible"] is True
    assert states[-1]["reason"] == "visible"

    call_count = len(calls)
    assert set_taskbar_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        layout_provider=lambda: (layout, {"reason": "ready"}),
        should_suppress=lambda hwnd, target: False,
        set_layout_state=lambda state: states.append(state),
        get_layout_state=lambda: states[-1],
        invalidate=lambda: calls.append("invalidate"),
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    ) is True
    assert len(calls) == call_count


def test_taskbar_visibility_hides_for_fullscreen_or_missing_space():
    import ctypes as real_ctypes

    from goldmonitor.taskbar_runtime import set_taskbar_window_visible

    calls = []
    states = []
    user32 = SimpleNamespace(
        ShowWindow=lambda hwnd, command: calls.append((hwnd, command)),
        SetWindowPos=lambda *args: calls.append(args),
    )
    ctypes_module = SimpleNamespace(
        windll=SimpleNamespace(user32=user32),
        c_void_p=real_ctypes.c_void_p,
        sizeof=real_ctypes.sizeof,
    )

    assert set_taskbar_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        layout_provider=lambda: (None, {"visible": False, "reason": "insufficient_taskbar_space"}),
        should_suppress=lambda hwnd, target: False,
        set_layout_state=lambda state: states.append(state),
        invalidate=lambda: None,
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    ) is False
    assert calls[-1] == (42, 0)
    assert states[-1]["reason"] == "insufficient_taskbar_space"

    layout = {"x": 100, "y": 200, "width": 180, "height": 32}
    assert set_taskbar_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        layout_provider=lambda: (layout, {"reason": "ready"}),
        should_suppress=lambda hwnd, target: True,
        set_layout_state=lambda state: states.append(state),
        invalidate=lambda: None,
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    ) is False
    assert states[-1]["reason"] == "fullscreen"


def test_taskbar_window_messages_keep_interaction_non_activating():
    from goldmonitor.taskbar_runtime import (
        MA_NOACTIVATE,
        TASKBAR_LAYOUT_TIMER_ID,
        WM_DESTROY,
        WM_DPICHANGED,
        WM_ERASEBKGND,
        WM_LBUTTONUP,
        WM_MOUSEACTIVATE,
        WM_PAINT,
        WM_RBUTTONUP,
        WM_TIMER,
        handle_taskbar_window_message,
    )

    calls = []
    user32 = SimpleNamespace(
        DefWindowProcW=lambda *args: 99,
        KillTimer=lambda hwnd, timer_id: calls.append(("kill_timer", hwnd, timer_id)),
        PostQuitMessage=lambda exit_code: calls.append(("quit", exit_code)),
    )
    kwargs = {
        "user32": user32,
        "draw_window": lambda hwnd: calls.append(("draw", hwnd)),
        "show_context_menu": lambda hwnd: calls.append(("menu", hwnd)) or 0,
        "show_main_window": lambda: calls.append("show"),
        "sync_visibility": lambda: calls.append("sync"),
    }

    assert handle_taskbar_window_message(42, WM_PAINT, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_ERASEBKGND, 0, 0, **kwargs) == 1
    assert handle_taskbar_window_message(42, WM_MOUSEACTIVATE, 0, 0, **kwargs) == MA_NOACTIVATE
    assert handle_taskbar_window_message(42, WM_LBUTTONUP, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_RBUTTONUP, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_DPICHANGED, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_TIMER, TASKBAR_LAYOUT_TIMER_ID, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_DESTROY, 0, 0, **kwargs) == 0
    assert calls == [
        ("draw", 42),
        "show",
        ("menu", 42),
        "sync",
        "sync",
        ("kill_timer", 42, TASKBAR_LAYOUT_TIMER_ID),
        ("quit", 0),
    ]


def test_taskbar_supervisor_rebuilds_after_session_loss_while_enabled():
    from goldmonitor.taskbar_runtime import run_taskbar_window_supervisor

    enabled = iter((True, True, True, False))
    sessions = iter((42, 43))
    calls = []

    result = run_taskbar_window_supervisor(
        window_enabled=lambda: next(enabled),
        run_session=lambda: calls.append("session") or next(sessions),
        on_session_lost=lambda: calls.append("restart"),
        restart_wait=lambda delay: calls.append(("wait", delay)),
    )

    assert result == 43
    assert calls == ["session", "restart", ("wait", 1.0), "session"]


def test_taskbar_supervisor_stops_without_rebuild_when_feature_is_disabled():
    from goldmonitor.taskbar_runtime import run_taskbar_window_supervisor

    enabled = iter((True, False))
    calls = []

    assert run_taskbar_window_supervisor(
        window_enabled=lambda: next(enabled),
        run_session=lambda: calls.append("session") or 42,
        on_session_lost=lambda: calls.append("restart"),
        restart_wait=lambda delay: calls.append(("wait", delay)),
    ) == 42
    assert calls == ["session"]


@pytest.mark.parametrize(
    ("command", "expected"),
    (
        (2001, "show"),
        (2002, "refresh"),
        (2003, "risk"),
        (2004, ("mode", "floating")),
        (2005, ("mode", "taskbar")),
        (2006, ("mode", "both")),
        (2007, ("enabled", False)),
    ),
)
def test_taskbar_context_menu_dispatches_supported_actions(command, expected):
    import ctypes
    from ctypes import wintypes

    from goldmonitor.taskbar_runtime import show_taskbar_context_menu

    calls = []

    def get_cursor_pos(pointer):
        pointer._obj.x = 10
        pointer._obj.y = 20
        return True

    user32 = SimpleNamespace(
        GetCursorPos=get_cursor_pos,
        CreatePopupMenu=lambda: 99,
        AppendMenuW=lambda *args: None,
        SetForegroundWindow=lambda hwnd: None,
        TrackPopupMenu=lambda *args: command,
        DestroyMenu=lambda menu: None,
        PostMessageW=lambda *args: calls.append(("post", args)),
    )

    result = show_taskbar_context_menu(
        42,
        ctypes_module=ctypes,
        wintypes=wintypes,
        user32=user32,
        show_main_window=lambda: calls.append("show"),
        set_enabled=lambda enabled: calls.append(("enabled", enabled)),
        refresh_price=lambda: calls.append("refresh"),
        open_risk_analysis=lambda: calls.append("risk"),
        get_settings=lambda: {"floating_price_windows_mode": "taskbar"},
        set_windows_mode=lambda mode: calls.append(("mode", mode)),
    )

    assert result == command
    assert calls == [("post", (42, 0, 0, 0)), expected]
