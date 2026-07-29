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


def test_floating_controller_refreshes_macos_status_instead_of_window():
    controller, _runtime, _settings, calls = make_controller(
        os_name="posix",
        sys_platform="darwin",
    )

    controller.apply_settings()

    assert calls == ["macos_status"]
