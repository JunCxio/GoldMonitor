import pytest


def make_controller(*, os_name="posix", mode="taskbar"):
    from goldmonitor.runtime_state import ApplicationRuntimeState
    from goldmonitor.taskbar_controller import TaskbarPriceController

    runtime = ApplicationRuntimeState()
    runtime.desktop_runtime_active = os_name == "nt"
    settings = {
        "floating_price_enabled": True,
        "floating_price_windows_mode": mode,
        "floating_price_display_mode": "rmb_usd",
    }
    calls = []

    def save(snapshot):
        settings.update(snapshot)
        calls.append(("save", dict(snapshot)))
        return dict(settings)

    controller = TaskbarPriceController(
        runtime=runtime,
        os_name=lambda: os_name,
        get_settings=lambda: dict(settings),
        save_settings=save,
        public_settings_snapshot=lambda snapshot=None: dict(snapshot or settings),
        emit=lambda event, payload: calls.append(("emit", event, payload)),
        show_main_window=lambda: calls.append("show"),
        fetch_price_once=lambda: calls.append("fetch"),
        start_background_task=lambda target: calls.append(("thread", target)),
        apply_display_settings=lambda snapshot: calls.append(("apply", dict(snapshot))),
    )
    return controller, runtime, settings, calls


def test_taskbar_controller_updates_compact_runtime_text_off_windows():
    controller, runtime, _settings, calls = make_controller()

    controller.update_price(528.16, 2345.6, 0.42)

    assert runtime.taskbar_price_text == "¥528.16  $2,346  +0.42%"
    assert runtime.taskbar_price_value_text == "¥528.16  $2,346"
    assert runtime.taskbar_price_change_text == "+0.42%"
    assert runtime.taskbar_trend_state == "up"
    assert runtime.taskbar_source_state == "waiting"
    assert calls == []


def test_taskbar_controller_starts_one_worker_and_respects_mode():
    controller, runtime, settings, calls = make_controller(os_name="nt")
    worker = lambda: None

    controller.start_window(worker)
    controller.start_window(worker)

    assert runtime.taskbar_thread_started is True
    assert calls == [("thread", worker)]
    assert controller.mode_enabled(settings) is True
    settings["floating_price_windows_mode"] = "floating"
    assert controller.mode_enabled(settings) is False


def test_taskbar_controller_switches_windows_mode_through_shared_apply_chain():
    controller, _runtime, settings, calls = make_controller(os_name="nt")

    assert controller.set_windows_mode("both") == "both"
    assert settings["floating_price_windows_mode"] == "both"
    assert calls[-2][0] == "apply"
    assert calls[-1] == ("emit", "settings_updated", settings)

    with pytest.raises(ValueError):
        controller.set_windows_mode("unsupported")


def test_taskbar_controller_window_loop_binds_runtime_callbacks(monkeypatch):
    from goldmonitor import taskbar_controller as controller_module

    controller, runtime, _settings, _calls = make_controller(os_name="nt")
    runtime.taskbar_price_text = "¥528.16"
    captured = {}
    monkeypatch.setattr(
        controller_module.taskbar_runtime_core,
        "run_taskbar_price_window",
        lambda **kwargs: captured.update(kwargs) or "started",
    )

    assert controller.run_window() == "started"
    assert captured["get_text_state"]()["text"] == "¥528.16"
    captured["set_window_handle"](42)
    assert runtime.taskbar_hwnd == 42
    assert captured["set_taskbar_target"] == controller.set_taskbar_target
    assert captured["set_lifecycle_state"] == controller.set_lifecycle_state
    assert captured["clear_ready"] == runtime.taskbar_window_ready.clear
    assert captured["set_windows_mode"] == controller.set_windows_mode
    assert captured["sync_visibility"] == controller.sync_visibility


def test_taskbar_controller_layout_passes_compact_text_state(monkeypatch):
    import sys
    from types import SimpleNamespace

    from goldmonitor import taskbar_controller as controller_module

    controller, runtime, _settings, _calls = make_controller(os_name="nt")
    runtime.taskbar_price_value_text = "¥528.16"
    runtime.taskbar_price_change_text = "+0.42%"
    captured = {}
    monkeypatch.setattr(
        controller_module.taskbar_runtime_core,
        "select_taskbar_layout",
        lambda **kwargs: captured.update(kwargs) or (None, None, {}),
    )
    monkeypatch.setitem(
        sys.modules,
        "ctypes",
        SimpleNamespace(
            windll=SimpleNamespace(user32=object(), shell32=object()),
        ),
    )

    controller.layout()

    assert captured["text_state"]["price"] == "¥528.16"
    assert captured["text_state"]["change"] == "+0.42%"


def test_taskbar_controller_tracks_target_lifecycle_and_restart_count():
    controller, runtime, _settings, _calls = make_controller(os_name="nt")

    controller.set_taskbar_target(
        {
            "hwnd": 201,
            "kind": "secondary",
            "index": 1,
            "count": 2,
            "class_name": "Shell_SecondaryTrayWnd",
        }
    )
    controller.set_lifecycle_state(
        "explorer_restarting",
        increment_restart=True,
    )
    controller.set_layout_state({"visible": True, "reason": "visible"})

    assert runtime.taskbar_owner_hwnd == 201
    assert controller.taskbar_target()["kind"] == "secondary"
    assert runtime.taskbar_restart_count == 1
    assert runtime.taskbar_layout_state == {
        "taskbar_kind": "secondary",
        "taskbar_index": 1,
        "taskbar_count": 2,
        "taskbar_class_name": "Shell_SecondaryTrayWnd",
        "visible": True,
        "reason": "visible",
        "restart_count": 1,
    }


def test_taskbar_controller_resets_thread_state_after_window_loop_exits(monkeypatch):
    from goldmonitor import taskbar_controller as controller_module

    controller, runtime, _settings, _calls = make_controller(os_name="nt")
    runtime.taskbar_thread_started = True
    runtime.taskbar_window_ready.set()

    def run_window(**kwargs):
        kwargs["set_window_handle"](42)
        kwargs["set_taskbar_target"](
            {"hwnd": 101, "kind": "primary", "index": 0, "count": 1}
        )
        return 42

    monkeypatch.setattr(
        controller_module.taskbar_runtime_core,
        "run_taskbar_price_window",
        run_window,
    )

    assert controller.run_window() == 42
    assert runtime.taskbar_hwnd is None
    assert runtime.taskbar_owner_hwnd is None
    assert runtime.taskbar_target_state == {}
    assert runtime.taskbar_thread_started is False
    assert runtime.taskbar_window_ready.is_set() is False


def test_taskbar_controller_apply_settings_hides_when_floating_only(monkeypatch):
    controller, _runtime, _settings, _calls = make_controller(
        os_name="nt",
        mode="floating",
    )
    visibility = []
    monkeypatch.setattr(
        controller,
        "set_window_visible",
        lambda visible: visibility.append(visible),
    )

    controller.apply_settings()

    assert visibility == [False]
