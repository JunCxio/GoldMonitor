from types import SimpleNamespace

import pytest


class Rect:
    def __init__(self, left=0, top=0, right=0, bottom=0):
        self.left = left
        self.top = top
        self.right = right
        self.bottom = bottom


class Point:
    def __init__(self, x=0, y=0):
        self.x = x
        self.y = y


class FakeCtypes:
    @staticmethod
    def byref(value):
        return value


class FakeUser32:
    def __init__(self):
        self.rect = Rect(100, 110, 320, 162)
        self.cursor = Point(120, 140)
        self.captured = []
        self.released = 0
        self.default_messages = []

    def GetWindowRect(self, hwnd, rect):
        rect.left = self.rect.left
        rect.top = self.rect.top
        rect.right = self.rect.right
        rect.bottom = self.rect.bottom
        return True

    def GetCursorPos(self, point):
        point.x = self.cursor.x
        point.y = self.cursor.y
        return True

    def SetCapture(self, hwnd):
        self.captured.append(hwnd)

    def ReleaseCapture(self):
        self.released += 1
        return True

    def DefWindowProcW(self, hwnd, msg, wparam, lparam):
        self.default_messages.append((hwnd, msg, wparam, lparam))
        return 99


def make_message_dependencies():
    state = {"drag": None}
    calls = {
        "draw": [],
        "context": [],
        "position": [],
        "save": [],
        "show": [],
    }
    user32 = FakeUser32()
    wintypes = SimpleNamespace(RECT=Rect, POINT=Point)
    dependencies = {
        "ctypes_module": FakeCtypes,
        "wintypes": wintypes,
        "user32": user32,
        "get_drag_state": lambda: state["drag"],
        "set_drag_state": lambda value: state.update(drag=value),
        "clamp_position": lambda x, y, target: (x, y),
        "position_window": (
            lambda hwnd, target, x=None, y=None:
            calls["position"].append((hwnd, x, y))
        ),
        "save_position": (
            lambda x, y: calls["save"].append((x, y)) or (x + 1, y + 1)
        ),
        "show_main_window": lambda: calls["show"].append(True),
        "draw_window": lambda hwnd: calls["draw"].append(hwnd),
        "show_context_menu": lambda hwnd: calls["context"].append(hwnd),
    }
    return state, calls, user32, dependencies


def test_lparam_point_decodes_signed_coordinates():
    from goldmonitor.floating_runtime import get_lparam_point

    assert get_lparam_point((20 << 16) | 10) == (10, 20)
    assert get_lparam_point((0xFFEC << 16) | 0xFFF6) == (-10, -20)


def test_window_message_drag_flow_moves_and_persists_position():
    from goldmonitor.floating_runtime import (
        MK_LBUTTON,
        WM_LBUTTONDOWN,
        WM_LBUTTONUP,
        WM_MOUSEMOVE,
        handle_floating_window_message,
    )

    state, calls, user32, dependencies = make_message_dependencies()
    hwnd = 42

    result = handle_floating_window_message(
        hwnd,
        WM_LBUTTONDOWN,
        0,
        (6 << 16) | 5,
        **dependencies,
    )
    assert result == 0
    assert state["drag"] == {
        "offset_x": 5,
        "offset_y": 6,
        "start_x": 100,
        "start_y": 110,
        "moved": False,
    }
    assert user32.captured == [hwnd]

    handle_floating_window_message(
        hwnd,
        WM_MOUSEMOVE,
        MK_LBUTTON,
        0,
        **dependencies,
    )
    assert calls["position"] == [(hwnd, 115, 134)]
    assert state["drag"]["moved"] is True

    user32.rect = Rect(115, 134, 335, 186)
    handle_floating_window_message(
        hwnd,
        WM_LBUTTONUP,
        0,
        0,
        **dependencies,
    )
    assert state["drag"] is None
    assert user32.released == 1
    assert calls["save"] == [(115, 134)]
    assert calls["position"][-1] == (hwnd, 116, 135)


def test_window_messages_route_paint_actions_and_default_processing():
    from goldmonitor.floating_runtime import (
        WM_CAPTURECHANGED,
        WM_CONTEXTMENU,
        WM_DISPLAYCHANGE,
        WM_LBUTTONDBLCLK,
        WM_PAINT,
        handle_floating_window_message,
    )

    state, calls, user32, dependencies = make_message_dependencies()
    state["drag"] = {"moved": False}

    assert handle_floating_window_message(7, WM_PAINT, 0, 0, **dependencies) == 0
    assert calls["draw"] == [7]

    assert handle_floating_window_message(7, WM_CONTEXTMENU, 0, 0, **dependencies) == 0
    assert calls["context"] == [7]

    assert handle_floating_window_message(7, WM_DISPLAYCHANGE, 0, 0, **dependencies) == 0
    assert calls["position"] == [(7, None, None)]

    assert handle_floating_window_message(7, WM_LBUTTONDBLCLK, 0, 0, **dependencies) == 0
    assert state["drag"] is None
    assert calls["show"] == [True]

    state["drag"] = {"moved": False}
    assert handle_floating_window_message(7, WM_CAPTURECHANGED, 0, 0, **dependencies) == 0
    assert state["drag"] is None

    assert handle_floating_window_message(7, 9999, 2, 3, **dependencies) == 99
    assert user32.default_messages == [(7, 9999, 2, 3)]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (1001, "show"),
        (1002, "hide"),
        (1003, "refresh"),
        (1004, "risk"),
    ],
)
def test_context_menu_routes_selected_command(command, expected):
    from goldmonitor.floating_runtime import show_floating_context_menu

    calls = []

    class MenuUser32:
        def __init__(self):
            self.items = []
            self.destroyed = []

        def GetCursorPos(self, point):
            point.x = 300
            point.y = 200
            return True

        def CreatePopupMenu(self):
            return 88

        def AppendMenuW(self, menu, flags, item_id, label):
            self.items.append((menu, flags, item_id, label))

        def SetForegroundWindow(self, hwnd):
            calls.append(("foreground", hwnd))

        def TrackPopupMenu(self, menu, flags, x, y, reserved, hwnd, rect):
            calls.append(("track", x, y, hwnd))
            return command

        def DestroyMenu(self, menu):
            self.destroyed.append(menu)

    user32 = MenuUser32()
    result = show_floating_context_menu(
        42,
        ctypes_module=FakeCtypes,
        wintypes=SimpleNamespace(POINT=Point),
        user32=user32,
        show_main_window=lambda: calls.append("show"),
        set_enabled=lambda enabled: calls.append("hide" if not enabled else "show"),
        refresh_price=lambda: calls.append("refresh"),
        open_risk_analysis=lambda: calls.append("risk"),
    )

    assert result == command
    assert expected in calls
    assert user32.destroyed == [88]
    assert [item[3] for item in user32.items] == [
        "打开主界面",
        "风险分析",
        "刷新行情",
        None,
        "隐藏悬浮条",
    ]


def test_window_loop_failure_sets_ready_and_logs_once():
    from goldmonitor.floating_runtime import run_floating_price_window

    ready = []
    warnings = []
    callbacks = {
        "window_size": lambda: (220, 52),
        "window_metrics": lambda: {},
        "floating_rect": lambda rect, width, height: rect,
        "get_text_state": lambda: {},
        "clamp_position": lambda x, y, user32=None: (x, y),
        "position_window": lambda hwnd, user32=None, x=None, y=None: None,
        "save_position": lambda x, y: (x, y),
        "resolve_position": lambda user32, width, height: (0, 0),
        "set_window_handle": lambda hwnd: None,
        "apply_corner_preference": lambda hwnd: None,
        "apply_opacity": lambda hwnd, user32=None: None,
        "set_window_visible": lambda visible: None,
        "window_enabled": lambda: True,
        "set_ready": lambda: ready.append(True),
        "show_main_window": lambda: None,
        "set_enabled": lambda enabled: None,
        "refresh_price": lambda: None,
        "open_risk_analysis": lambda: None,
        "get_drag_state": lambda: None,
        "set_drag_state": lambda value: None,
        "is_topmost": lambda: False,
    }
    logger = SimpleNamespace(
        warning=lambda message, exc_info=False: warnings.append((message, exc_info))
    )

    result = run_floating_price_window(
        **callbacks,
        ctypes_loader=lambda: (_ for _ in ()).throw(RuntimeError("unsupported")),
        logger=logger,
    )

    assert result is None
    assert ready == [True]
    assert warnings == [("桌面金价悬浮条启动失败", True)]


def test_position_persistence_only_writes_changed_coordinates():
    from goldmonitor.floating_runtime import save_window_position

    settings = {
        "floating_price_position_saved": False,
        "floating_price_x": None,
        "floating_price_y": None,
    }
    saved = []
    emitted = []

    first = save_window_position(
        20,
        30,
        clamp_position=lambda x, y: (max(8, x), max(8, y)),
        snap_position=lambda x, y: (24, 32),
        get_settings=lambda: dict(settings),
        save_settings=lambda snapshot: settings.update(snapshot) or saved.append(dict(snapshot)),
        emit_settings_updated=lambda: emitted.append(True),
    )
    second = save_window_position(
        24,
        32,
        clamp_position=lambda x, y: (x, y),
        snap_position=lambda x, y: (x, y),
        get_settings=lambda: dict(settings),
        save_settings=lambda snapshot: saved.append(dict(snapshot)),
        emit_settings_updated=lambda: emitted.append(True),
    )

    assert first == (24, 32)
    assert second == (24, 32)
    assert settings["floating_price_position_saved"] is True
    assert settings["floating_price_x"] == 24
    assert settings["floating_price_y"] == 32
    assert len(saved) == 1
    assert emitted == [True]


def test_visibility_setting_persists_and_reapplies_runtime_state():
    from goldmonitor.floating_runtime import set_enabled

    settings = {"floating_price_enabled": True}
    calls = []

    set_enabled(
        False,
        get_settings=lambda: dict(settings),
        save_settings=lambda snapshot: settings.update(snapshot) or calls.append("save"),
        set_window_visible=lambda visible: calls.append(("visible", visible)),
        apply_settings=lambda snapshot: calls.append(("apply", snapshot["floating_price_enabled"])),
        public_settings_snapshot=lambda snapshot: dict(snapshot),
        emit=lambda event, payload: calls.append((event, payload["floating_price_enabled"])),
    )
    set_enabled(
        False,
        get_settings=lambda: dict(settings),
        save_settings=lambda snapshot: calls.append("unexpected_save"),
        set_window_visible=lambda visible: calls.append(("visible", visible)),
        apply_settings=lambda snapshot: calls.append("unexpected_apply"),
        public_settings_snapshot=lambda snapshot: dict(snapshot),
        emit=lambda event, payload: calls.append("unexpected_emit"),
    )

    assert settings["floating_price_enabled"] is False
    assert calls == [
        "save",
        ("apply", False),
        ("settings_updated", False),
        ("visible", False),
    ]


def test_opacity_is_converted_to_layered_window_alpha():
    from goldmonitor.floating_runtime import apply_window_opacity

    calls = []
    user32 = SimpleNamespace(
        SetLayeredWindowAttributes=(
            lambda hwnd, color, alpha, flags: calls.append((hwnd, color, alpha, flags))
        )
    )

    apply_window_opacity(
        42,
        os_name="nt",
        get_settings=lambda: {"floating_price_opacity": 50},
        user32=user32,
        ctypes_loader=lambda: (SimpleNamespace(), SimpleNamespace()),
    )

    assert calls == [(42, 0, 127, 0x00000002)]


def test_app_window_loop_wrapper_resolves_current_runtime_callbacks(monkeypatch):
    import app

    captured = {}
    monkeypatch.setattr(
        app.floating_runtime_core,
        "run_floating_price_window",
        lambda **kwargs: captured.update(kwargs) or "started",
    )
    monkeypatch.setattr(app, "_floating_primary_text", "主价格")
    monkeypatch.setattr(app, "_floating_secondary_text", "辅助价格")
    monkeypatch.setattr(app, "_floating_status_text", "实时")
    monkeypatch.setattr(app, "_floating_trend_state", "up")
    monkeypatch.setattr(app, "_floating_source_state", "live")

    assert app._floating_price_window_loop() == "started"
    assert captured["get_text_state"]() == {
        "primary": "主价格",
        "secondary": "辅助价格",
        "status": "实时",
        "trend_state": "up",
        "source_state": "live",
    }
    assert captured["get_drag_state"]() is app._floating_drag_state
    assert app._get_lparam_point((20 << 16) | 10) == (10, 20)


def test_app_starts_floating_window_worker_only_once(monkeypatch):
    import app

    created = []

    class Thread:
        def __init__(self, target, daemon=False):
            created.append({"target": target, "daemon": daemon, "started": False})
            self.item = created[-1]

        def start(self):
            self.item["started"] = True

    monkeypatch.setattr(app, "_floating_thread_started", False)
    monkeypatch.setattr(app, "_is_floating_price_available", lambda: True)
    monkeypatch.setattr(app.threading, "Thread", Thread)

    app.start_floating_price_window()
    app.start_floating_price_window()

    assert created == [{
        "target": app._floating_price_window_loop,
        "daemon": True,
        "started": True,
    }]
