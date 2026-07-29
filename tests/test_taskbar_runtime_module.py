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
        "x": 1527,
        "y": 1043,
        "width": 210,
        "height": 34,
        "orientation": "horizontal",
        "taskbar_rect": (0, 1040, 1920, 1080),
    }


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
        invalidate=lambda: calls.append("invalidate"),
        ctypes_loader=lambda: (ctypes_module, SimpleNamespace()),
    )

    assert result is True
    assert calls[0][0] == "position"
    assert calls[0][1][2:6] == (100, 200, 180, 32)
    assert calls[-2:] == [("show", 42, 4), "invalidate"]
    assert states[-1]["visible"] is True
    assert states[-1]["reason"] == "visible"


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
        TASKBAR_LAYOUT_TIMER_ID,
        WM_LBUTTONUP,
        WM_PAINT,
        WM_RBUTTONUP,
        WM_TIMER,
        handle_taskbar_window_message,
    )

    calls = []
    user32 = SimpleNamespace(DefWindowProcW=lambda *args: 99)
    kwargs = {
        "user32": user32,
        "draw_window": lambda hwnd: calls.append(("draw", hwnd)),
        "show_context_menu": lambda hwnd: calls.append(("menu", hwnd)),
        "show_main_window": lambda: calls.append("show"),
        "sync_visibility": lambda: calls.append("sync"),
    }

    assert handle_taskbar_window_message(42, WM_PAINT, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_LBUTTONUP, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_RBUTTONUP, 0, 0, **kwargs) == 0
    assert handle_taskbar_window_message(42, WM_TIMER, TASKBAR_LAYOUT_TIMER_ID, 0, **kwargs) == 0
    assert calls == [("draw", 42), "show", ("menu", 42), "sync"]


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
    assert calls == [expected]
