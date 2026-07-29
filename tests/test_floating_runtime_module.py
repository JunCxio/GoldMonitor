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


class FakeDWORD:
    def __init__(self, value=0):
        self.value = value


class FakeUnicodeBuffer:
    def __init__(self):
        self.value = ""

    def __len__(self):
        return 256


class FakeFullscreenCtypes(FakeCtypes):
    @staticmethod
    def create_unicode_buffer(_size):
        return FakeUnicodeBuffer()

    @staticmethod
    def sizeof(_value):
        return 40


class MonitorInfo:
    def __init__(self):
        self.cbSize = 0
        self.rcMonitor = Rect()


class FullscreenUser32:
    def __init__(
        self,
        *,
        foreground=77,
        class_name="ApplicationFrameWindow",
        process_id=200,
        window_rect=None,
        monitor_rect=None,
        visible=True,
        iconic=False,
        process_lookup_ok=True,
    ):
        self.foreground = foreground
        self.class_name = class_name
        self.process_id = process_id
        self.window_rect = window_rect or Rect(0, 0, 1920, 1080)
        self.monitor_rect = monitor_rect or Rect(0, 0, 1920, 1080)
        self.visible = visible
        self.iconic = iconic
        self.process_lookup_ok = process_lookup_ok

    def GetForegroundWindow(self):
        return self.foreground

    def IsWindowVisible(self, _hwnd):
        return self.visible

    def IsIconic(self, _hwnd):
        return self.iconic

    def GetClassNameW(self, _hwnd, buffer, _length):
        buffer.value = self.class_name
        return len(self.class_name)

    def GetWindowThreadProcessId(self, _hwnd, process_id):
        process_id.value = self.process_id
        return 1 if self.process_lookup_ok else 0

    def GetWindowRect(self, _hwnd, rect):
        rect.left = self.window_rect.left
        rect.top = self.window_rect.top
        rect.right = self.window_rect.right
        rect.bottom = self.window_rect.bottom
        return True

    def MonitorFromWindow(self, _hwnd, _flags):
        return 9

    def GetMonitorInfoW(self, _monitor, monitor_info):
        monitor_info.rcMonitor = self.monitor_rect
        return True


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
        "sync": [],
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
        "is_position_locked": lambda: False,
        "sync_visibility": lambda: calls["sync"].append(True),
    }
    return state, calls, user32, dependencies


def test_lparam_point_decodes_signed_coordinates():
    from goldmonitor.floating_runtime import get_lparam_point

    assert get_lparam_point((20 << 16) | 10) == (10, 20)
    assert get_lparam_point((0xFFEC << 16) | 0xFFF6) == (-10, -20)


def test_window_rect_fullscreen_check_allows_small_edge_tolerance():
    from goldmonitor.floating_runtime import window_rect_covers_monitor

    monitor = Rect(0, 0, 1920, 1080)

    assert window_rect_covers_monitor(Rect(1, -1, 1919, 1079), monitor) is True
    assert window_rect_covers_monitor(Rect(0, 0, 1917, 1080), monitor) is False


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"foreground": 42}, False),
        ({"visible": False}, False),
        ({"iconic": True}, False),
        ({"class_name": "Progman"}, False),
        ({"class_name": "WorkerW"}, False),
        ({"process_lookup_ok": False}, False),
        ({"process_id": 100}, False),
        ({"window_rect": Rect(0, 0, 1920, 1040)}, False),
        ({}, True),
    ],
)
def test_foreground_fullscreen_detection_excludes_non_application_windows(
    overrides,
    expected,
):
    from goldmonitor.floating_runtime import is_foreground_window_fullscreen

    user32 = FullscreenUser32(**overrides)
    wintypes = SimpleNamespace(RECT=Rect, DWORD=FakeDWORD)

    assert is_foreground_window_fullscreen(
        42,
        user32=user32,
        current_process_id=100,
        monitor_info_type=MonitorInfo,
        ctypes_loader=lambda: (FakeFullscreenCtypes, wintypes),
    ) is expected


def test_fullscreen_hiding_can_be_disabled_in_settings():
    from goldmonitor.floating_runtime import should_hide_for_fullscreen

    assert should_hide_for_fullscreen(
        42,
        user32=SimpleNamespace(),
        get_settings=lambda: {"floating_price_hide_on_fullscreen": False},
    ) is False


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


def test_locked_window_does_not_start_dragging():
    from goldmonitor.floating_runtime import (
        WM_LBUTTONDOWN,
        handle_floating_window_message,
    )

    state, _calls, user32, dependencies = make_message_dependencies()
    dependencies["is_position_locked"] = lambda: True

    assert handle_floating_window_message(
        42,
        WM_LBUTTONDOWN,
        0,
        (6 << 16) | 5,
        **dependencies,
    ) == 0
    assert state["drag"] is None
    assert user32.captured == []


def test_window_messages_route_paint_actions_and_default_processing():
    from goldmonitor.floating_runtime import (
        WM_CAPTURECHANGED,
        WM_CONTEXTMENU,
        WM_DISPLAYCHANGE,
        WM_LBUTTONDBLCLK,
        WM_PAINT,
        WM_TIMER,
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
    assert calls["sync"] == [True]

    assert handle_floating_window_message(7, WM_TIMER, 1, 0, **dependencies) == 0
    assert calls["sync"] == [True, True]

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
        (1005, ("toggle", "floating_price_lock_position")),
        (1006, ("toggle", "floating_price_hide_on_fullscreen")),
        (1007, ("toggle", "floating_price_always_on_top")),
        (1008, "reset"),
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
        get_settings=lambda: {
            "floating_price_lock_position": True,
            "floating_price_hide_on_fullscreen": True,
            "floating_price_always_on_top": False,
        },
        toggle_setting=lambda key: calls.append(("toggle", key)),
        reset_position=lambda: calls.append("reset"),
    )

    assert result == command
    assert expected in calls
    assert user32.destroyed == [88]
    assert [item[3] for item in user32.items] == [
        "打开主界面",
        "风险分析",
        "刷新行情",
        None,
        "锁定位置",
        "全屏时自动隐藏",
        "始终置顶",
        "重置位置",
        None,
        "隐藏悬浮条",
    ]
    assert user32.items[4][1] & 0x0008
    assert user32.items[5][1] & 0x0008
    assert not user32.items[6][1] & 0x0008


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
        "get_settings": lambda: {},
        "toggle_setting": lambda key: None,
        "reset_position": lambda: None,
        "is_position_locked": lambda: False,
        "sync_visibility": lambda: None,
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


def test_visibility_is_suppressed_without_repainting_during_fullscreen():
    from goldmonitor.floating_runtime import set_window_visible

    calls = []

    class RecordedFunction:
        def __init__(self, callback):
            self.callback = callback
            self.argtypes = None

        def __call__(self, *args):
            return self.callback(*args)

    visibility = {"value": True}
    user32 = SimpleNamespace(
        ShowWindow=RecordedFunction(
            lambda hwnd, command: calls.append(("show", hwnd, command))
        ),
        IsWindowVisible=lambda _hwnd: visibility["value"],
    )
    ctypes_module = SimpleNamespace(
        windll=SimpleNamespace(user32=user32),
        c_void_p=object,
        c_int=object,
    )

    result = set_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        get_positioned=lambda: True,
        position_window=lambda *args: calls.append("position"),
        apply_opacity=lambda *args: calls.append("opacity"),
        invalidate_window=lambda: calls.append("invalidate"),
        should_suppress=lambda hwnd, target: True,
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    )

    assert result is False
    assert calls == [("show", 42, 0)]

    visibility["value"] = False
    result = set_window_visible(
        True,
        hwnd=42,
        os_name="nt",
        get_positioned=lambda: True,
        position_window=lambda *args: calls.append("position"),
        apply_opacity=lambda *args: calls.append("opacity"),
        invalidate_window=lambda: calls.append("invalidate"),
        should_suppress=lambda hwnd, target: True,
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    )

    assert result is False
    assert calls == [("show", 42, 0)]


def test_app_window_loop_wrapper_resolves_current_runtime_callbacks(monkeypatch):
    import app
    from goldmonitor import floating_controller as controller_module

    captured = {}
    monkeypatch.setattr(
        controller_module.floating_runtime_core,
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
