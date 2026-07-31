import pytest


def make_controller(*, os_name="posix", sys_platform="linux"):
    from goldmonitor.floating_controller import FloatingPriceController
    from goldmonitor.runtime_state import ApplicationRuntimeState

    runtime = ApplicationRuntimeState()
    runtime.desktop_runtime_active = os_name == "nt"
    settings = {
        "floating_price_enabled": True,
        "floating_price_preset": "compact",
        "floating_price_snap_edge": True,
        "floating_price_opacity": 94,
        "floating_price_always_on_top": False,
        "floating_price_hide_on_fullscreen": True,
        "floating_price_lock_position": False,
    }
    calls = []
    controller = FloatingPriceController(
        runtime=runtime,
        default_settings={"floating_price_preset": "compact"},
        presets={"compact": {}},
        os_name=lambda: os_name,
        sys_platform=lambda: sys_platform,
        get_settings=lambda: dict(settings),
        save_settings=lambda snapshot: calls.append(("save", snapshot)),
        public_settings_snapshot=lambda snapshot=None: dict(snapshot or settings),
        emit=lambda event, payload: calls.append(("emit", event, payload)),
        show_main_window=lambda: calls.append("show"),
        fetch_price_once=lambda: calls.append("fetch"),
        refresh_macos_status_item=lambda: calls.append("macos_status"),
        start_background_task=lambda target: calls.append(("thread", target)),
    )
    return controller, runtime, settings, calls


def test_floating_controller_updates_text_state_without_desktop_window(monkeypatch):
    controller, runtime, _settings, calls = make_controller()
    monkeypatch.setattr(
        controller,
        "format_price_text",
        lambda *args: ("主价格", "辅助价格", "实时", "up", "live"),
    )

    controller.update_price(520.0, 2400.0, 0.6)

    assert runtime.floating_primary_text == "主价格"
    assert runtime.floating_secondary_text == "辅助价格"
    assert runtime.floating_status_text == "实时"
    assert runtime.floating_trend_state == "up"
    assert runtime.floating_source_state == "live"
    assert calls == []


def test_floating_controller_starts_only_one_window_worker():
    controller, runtime, _settings, calls = make_controller(os_name="nt")
    worker = lambda: None

    controller.start_window(worker=worker)
    controller.start_window(worker=worker)

    assert runtime.floating_thread_started is True
    assert calls == [("thread", worker)]


def test_floating_controller_window_loop_binds_runtime_state(monkeypatch):
    from goldmonitor import floating_controller as controller_module

    controller, runtime, _settings, _calls = make_controller(os_name="nt")
    runtime.floating_primary_text = "黄金 520.00"
    runtime.floating_secondary_text = "2400.00 USD/oz"
    captured = {}
    monkeypatch.setattr(
        controller_module.floating_runtime_core,
        "run_floating_price_window",
        lambda **kwargs: captured.update(kwargs) or "started",
    )

    assert controller.run_window() == "started"
    assert captured["get_text_state"]()["primary"] == "黄金 520.00"
    assert captured["get_drag_state"]() is None
    captured["set_drag_state"]({"moved": True})
    assert runtime.floating_drag_state == {"moved": True}
    assert captured["get_settings"]()["floating_price_hide_on_fullscreen"] is True
    assert captured["is_position_locked"]() is False
    assert captured["toggle_setting"] == controller.toggle_setting
    assert captured["reset_position"] == controller.reset_position
    assert captured["sync_visibility"] == controller.sync_visibility


def test_floating_controller_toggles_supported_runtime_setting(monkeypatch):
    controller, _runtime, settings, calls = make_controller(os_name="nt")
    applied = []

    def save(snapshot):
        settings.update(snapshot)
        calls.append(("save", dict(snapshot)))
        return dict(settings)

    monkeypatch.setattr(controller, "save_settings", save)
    monkeypatch.setattr(
        controller,
        "apply_settings",
        lambda snapshot: applied.append(dict(snapshot)),
    )

    assert controller.toggle_setting("floating_price_always_on_top") is True
    assert settings["floating_price_always_on_top"] is True
    assert applied[-1]["floating_price_always_on_top"] is True
    assert calls[-1] == (
        "emit",
        "settings_updated",
        settings,
    )

    with pytest.raises(ValueError):
        controller.toggle_setting("floating_price_unknown")


def test_floating_controller_resets_saved_position(monkeypatch):
    controller, runtime, settings, calls = make_controller(os_name="nt")
    settings.update({
        "floating_price_position_saved": True,
        "floating_price_x": 320,
        "floating_price_y": 180,
    })
    runtime.floating_hwnd = 42
    runtime.floating_positioned = True
    positioned = []
    synced = []

    def save(snapshot):
        settings.update(snapshot)
        calls.append(("save", dict(snapshot)))
        return dict(settings)

    monkeypatch.setattr(controller, "save_settings", save)
    monkeypatch.setattr(
        controller,
        "position_window",
        lambda hwnd: positioned.append(hwnd),
    )
    monkeypatch.setattr(
        controller,
        "sync_visibility",
        lambda: synced.append(True),
    )

    controller.reset_position()

    assert settings["floating_price_position_saved"] is False
    assert settings["floating_price_x"] is None
    assert settings["floating_price_y"] is None
    assert runtime.floating_positioned is False
    assert positioned == [42]
    assert synced == [True]
    assert calls[-1] == ("emit", "settings_updated", settings)


def test_floating_controller_refreshes_macos_status_instead_of_window():
    controller, _runtime, _settings, calls = make_controller(
        os_name="posix",
        sys_platform="darwin",
    )

    controller.apply_settings()

    assert calls == ["macos_status"]


def test_floating_controller_hides_window_in_tray_only_mode(monkeypatch):
    controller, _runtime, settings, _calls = make_controller(os_name="nt")
    settings["floating_price_windows_mode"] = "tray"
    visibility = []
    monkeypatch.setattr(
        controller,
        "set_window_visible",
        lambda visible: visibility.append(visible),
    )

    controller.apply_settings()

    assert visibility == [False]


def test_application_coordinates_floating_window_and_native_tray_state(monkeypatch):
    import app

    calls = []

    class Controller:
        def __init__(self, name):
            self.name = name

        def apply_settings(self, settings, worker=None):
            calls.append((self.name, "apply", settings, worker))

        def update_price(self, rmb, usd, pct, worker=None):
            calls.append((self.name, "update", rmb, usd, pct, worker))

    floating = Controller("floating")
    monkeypatch.setattr(app, "_get_floating_controller", lambda: floating)

    settings = {"floating_price_windows_mode": "both"}
    app.apply_floating_price_settings(settings)
    app.update_floating_price(528.1, 2345.6, 0.2)

    assert calls[0][:3] == ("floating", "apply", settings)
    assert calls[1][0:5] == ("floating", "update", 528.1, 2345.6, 0.2)
    assert app.runtime.desktop_price_change_pct == 0.2
