import os
from types import SimpleNamespace

import pytest


class CapturedThread:
    created = []

    def __init__(self, target, daemon=False):
        self.target = target
        self.daemon = daemon
        self.started = False
        self.__class__.created.append(self)

    def start(self):
        self.started = True


class EventHook:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


class FakeWindow:
    def __init__(self):
        self.hidden = False
        self.shown = False
        self.restored = False
        self.events = SimpleNamespace(shown=EventHook(), closing=EventHook())

    def hide(self):
        self.hidden = True

    def show(self):
        self.shown = True

    def restore(self):
        self.restored = True


class FakeUser32:
    def __init__(self, hwnd=42, icon=84):
        self.hwnd = hwnd
        self.icon = icon
        self.calls = []

    def FindWindowW(self, parent, title):
        self.calls.append(("find", parent, title))
        return self.hwnd

    def LoadImageW(self, instance, path, image_type, width, height, flags):
        self.calls.append(("load", path, image_type, width, height, flags))
        return self.icon

    def SendMessageW(self, hwnd, message, slot, icon):
        self.calls.append(("send", hwnd, message, slot, icon))

    def ShowWindow(self, hwnd, command):
        self.calls.append(("show", hwnd, command))

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("foreground", hwnd))


def test_start_thread_once_marks_state_and_reuses_existing_worker():
    from goldmonitor.desktop_runtime import start_thread_once

    state = {"started": False}
    target = object()
    CapturedThread.created = []

    first = start_thread_once(
        is_started=lambda: state["started"],
        mark_started=lambda value: state.update(started=value),
        target=target,
        thread_factory=CapturedThread,
    )
    second = start_thread_once(
        is_started=lambda: state["started"],
        mark_started=lambda value: state.update(started=value),
        target=target,
        thread_factory=CapturedThread,
    )

    assert first is True
    assert second is False
    assert state["started"] is True
    assert len(CapturedThread.created) == 1
    assert CapturedThread.created[0].target is target
    assert CapturedThread.created[0].daemon is True
    assert CapturedThread.created[0].started is True


def test_periodic_task_logs_failure_and_continues_before_sleeping():
    from goldmonitor.desktop_runtime import run_periodic_task

    calls = []
    errors = []

    def task():
        calls.append("run")
        if len(calls) == 1:
            raise RuntimeError("failed")

    def sleep(seconds):
        assert seconds == 30
        if len(calls) == 2:
            raise StopIteration

    logger = SimpleNamespace(exception=lambda message: errors.append(message))

    with pytest.raises(StopIteration):
        run_periodic_task(
            task,
            interval=30,
            sleep=sleep,
            logger=logger,
            error_message="执行每日摘要任务失败",
        )

    assert calls == ["run", "run"]
    assert errors == ["执行每日摘要任务失败"]


def test_window_visibility_and_exit_use_injected_platform_dependencies():
    from goldmonitor.desktop_runtime import exit_application, hide_main_window, show_main_window

    window = FakeWindow()
    user32 = FakeUser32()
    ctypes = SimpleNamespace(windll=SimpleNamespace(user32=user32))
    state = {"hwnd": None}

    hide_main_window(
        get_window=lambda: window,
        os_name="nt",
        get_window_hwnd=lambda: state["hwnd"],
        set_window_hwnd=lambda value: state.update(hwnd=value),
        find_window_hwnd=lambda: 42,
        ctypes_loader=lambda: ctypes,
    )
    show_main_window(
        get_window=lambda: window,
        os_name="nt",
        sys_platform="win32",
        process_id=123,
        run_macos_script=lambda script, wait=False: None,
        get_window_hwnd=lambda: state["hwnd"],
        set_window_hwnd=lambda value: state.update(hwnd=value),
        find_window_hwnd=lambda: 0,
        ctypes_loader=lambda: ctypes,
    )

    assert window.hidden is True
    assert window.shown is True
    assert window.restored is True
    assert state["hwnd"] == 42
    assert ("show", 42, 0) in user32.calls
    assert ("show", 42, 9) in user32.calls
    assert ("foreground", 42) in user32.calls

    macos_scripts = []
    show_main_window(
        get_window=lambda: None,
        os_name="posix",
        sys_platform="darwin",
        process_id=456,
        run_macos_script=lambda script, wait=False: macos_scripts.append((script, wait)),
        get_window_hwnd=lambda: None,
        set_window_hwnd=lambda value: None,
        find_window_hwnd=lambda: None,
        ctypes_loader=lambda: ctypes,
    )
    assert "unix id is 456" in macos_scripts[0][0]
    assert macos_scripts[0][1] is False

    stopped = []
    exits = []
    icon = SimpleNamespace(stop=lambda: stopped.append(True))
    exit_application(get_tray_icon=lambda: icon, process_exit=lambda code: exits.append(code))
    assert stopped == [True]
    assert exits == [0]


def test_tray_icon_builds_menu_and_starts_tooltip_worker():
    from goldmonitor.desktop_runtime import create_tray_icon

    actions = []
    drawn = []
    icon_image = object()

    class ImageModule:
        @staticmethod
        def new(mode, size, color):
            assert (mode, size, color) == ("RGBA", (64, 64), (0, 0, 0, 0))
            return icon_image

    class ImageDrawModule:
        @staticmethod
        def Draw(image):
            assert image is icon_image
            return SimpleNamespace(ellipse=lambda bounds, fill: drawn.append((bounds, fill)))

    class MenuItem:
        def __init__(self, label, action, default=False):
            self.label = label
            self.action = action
            self.default = default

    class Icon:
        def __init__(self, name, image, title, menu):
            self.name = name
            self.image = image
            self.title = title
            self.menu = menu
            self.ran = False

        def run(self):
            self.ran = True

    pystray = SimpleNamespace(
        MenuItem=MenuItem,
        Menu=SimpleNamespace(SEPARATOR=object()),
        Icon=Icon,
    )
    CapturedThread.created = []
    stored = []

    icon = create_tray_icon(
        base_dir="/application",
        path_exists=lambda path: False,
        image_loader=lambda: (ImageModule, ImageDrawModule),
        pystray_loader=lambda: pystray,
        set_tray_icon=stored.append,
        show_window=lambda: actions.append("show"),
        refresh_price=lambda: actions.append("refresh"),
        open_risk_analysis=lambda: actions.append("risk"),
        toggle_floating_price=lambda: actions.append("floating"),
        exit_application=lambda: actions.append("exit"),
        format_title=lambda: "金价监控",
        thread_factory=CapturedThread,
        sleep=lambda seconds: None,
    )

    assert icon is stored[0]
    assert icon.ran is True
    assert drawn == [([4, 4, 60, 60], "#e8b830")]
    assert [item.label for item in icon.menu if isinstance(item, MenuItem)] == [
        "显示窗口",
        "刷新行情",
        "风险分析",
        "切换悬浮条",
        "退出",
    ]
    assert icon.menu[0].default is True
    for item in icon.menu:
        if isinstance(item, MenuItem):
            item.action(icon, item)
    assert actions == ["show", "refresh", "risk", "floating", "exit"]
    assert len(CapturedThread.created) == 1
    assert CapturedThread.created[0].daemon is True
    assert CapturedThread.created[0].started is True


def test_window_close_decision_routes_exit_hide_and_dialog():
    from goldmonitor.desktop_runtime import handle_window_closing

    events = []
    snapshot = {"close_behavior": "ask", "close_remembered": False}

    result = handle_window_closing(
        "macos",
        get_settings_snapshot=lambda: dict(snapshot),
        close_behavior_decision=lambda settings, platform: "ask",
        hide_window=lambda: events.append("hide"),
        exit_application=lambda: events.append("exit"),
        emit=lambda name, payload: events.append((name, payload)),
    )
    assert result is False
    assert events == [("show_close_dialog", snapshot)]

    events.clear()
    handle_window_closing(
        "windows",
        get_settings_snapshot=lambda: dict(snapshot),
        close_behavior_decision=lambda settings, platform: "minimize_to_tray",
        hide_window=lambda: events.append("hide"),
        exit_application=lambda: events.append("exit"),
        emit=lambda name, payload: events.append((name, payload)),
    )
    assert events == ["hide"]

    events.clear()
    handle_window_closing(
        "other",
        get_settings_snapshot=lambda: dict(snapshot),
        close_behavior_decision=lambda settings, platform: "ask",
        hide_window=lambda: events.append("hide"),
        exit_application=lambda: events.append("exit"),
        emit=lambda name, payload: events.append((name, payload)),
    )
    assert events == ["exit"]


def test_desktop_window_wires_events_backend_and_windows_shell_state():
    from goldmonitor.desktop_runtime import DesktopBridge, start_desktop_window

    created = []
    started = []
    stored_windows = []
    stored_hwnds = []
    hidden = []
    emitted = []
    window = FakeWindow()
    user32 = FakeUser32()
    ctypes = SimpleNamespace(windll=SimpleNamespace(user32=user32))

    class Webview:
        @staticmethod
        def create_window(**kwargs):
            created.append(kwargs)
            return window

        @staticmethod
        def start(**kwargs):
            started.append(kwargs)

    bridge = DesktopBridge(lambda: {"ok": True})
    result = start_desktop_window(
        app_name="金价监控",
        url="http://127.0.0.1:5000",
        base_dir="/application",
        start_hidden=True,
        os_name="nt",
        sys_platform="win32",
        bridge=bridge,
        get_window=lambda: stored_windows[0] if stored_windows else None,
        set_window=stored_windows.append,
        set_window_hwnd=stored_hwnds.append,
        create_macos_status_item=lambda: None,
        get_settings_snapshot=lambda: {"close_behavior": "ask", "close_remembered": False},
        close_behavior_decision=lambda settings, platform: "ask",
        hide_window=lambda: hidden.append(True),
        exit_application=lambda: None,
        emit=lambda name, payload: emitted.append((name, payload)),
        path_exists=lambda path: True,
        ctypes_loader=lambda: ctypes,
        webview_loader=lambda: Webview,
    )

    assert result is window
    assert stored_windows == [window]
    assert created[0]["title"] == "金价监控"
    assert created[0]["url"] == "http://127.0.0.1:5000"
    assert created[0]["hidden"] is True
    assert created[0]["maximized"] is False
    assert created[0]["js_api"] is bridge
    assert started == [{"gui": "edgechromium"}]
    assert len(window.events.shown.handlers) == 1
    assert len(window.events.closing.handlers) == 1

    window.events.shown.handlers[0]()
    assert stored_hwnds == [42]
    assert hidden == [True]
    assert any(
        call[0] == "load"
        and call[1].endswith(os.path.join("static", "icon.ico"))
        for call in user32.calls
    )

    assert window.events.closing.handlers[0]() is False
    assert emitted == [(
        "show_close_dialog",
        {"close_behavior": "ask", "close_remembered": False},
    )]
    assert bridge.choose_export_dir() == {"ok": True}


def test_app_wrappers_keep_runtime_state_and_bridge_callbacks_patchable(monkeypatch):
    import app

    CapturedThread.created = []
    monkeypatch.setattr(app, "_background_fetch_started", False)
    monkeypatch.setattr(app, "_task_scheduler_started", False)
    monkeypatch.setattr(app.threading, "Thread", CapturedThread)
    background = object()
    scheduler = object()
    monkeypatch.setattr(app, "background_loop", background)
    monkeypatch.setattr(app, "task_scheduler_loop", scheduler)

    assert app.start_background_fetching() is True
    assert app.start_background_fetching() is False
    assert app.start_task_scheduler() is True
    assert app.start_task_scheduler() is False
    assert [thread.target for thread in CapturedThread.created] == [background, scheduler]

    bridge = app.DesktopBridge()
    monkeypatch.setattr(app, "choose_export_dir_for_desktop", lambda: {"ok": True, "path": "/tmp"})
    assert bridge.choose_export_dir() == {"ok": True, "path": "/tmp"}
