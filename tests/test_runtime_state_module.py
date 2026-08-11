def test_runtime_state_factory_initializes_independent_mutable_state():
    from goldmonitor.runtime_state import create_runtime_state

    first = create_runtime_state(
        default_port=5000,
        app_name="金价监控",
        threshold_modes=("usd", "rmb"),
        threshold_types=("upper", "lower"),
        source_health={"source-a": {"ok": True}},
    )
    second = create_runtime_state(
        default_port=5001,
        app_name="测试实例",
        threshold_modes=("usd",),
        threshold_types=("upper",),
        source_health={},
    )

    assert first.server_port == 5000
    assert first.last_desktop_title == "金价监控"
    assert first.thresholds == {
        "upper_usd": None,
        "lower_usd": None,
        "upper_rmb": None,
        "lower_rmb": None,
    }
    first.price_history.append({"usd": 2300})
    first.alert_rules.append({"id": "rule-1"})
    assert second.price_history == []
    assert second.alert_rules == []
    assert first.lock is not second.lock


def test_runtime_state_exposes_service_slots_without_module_globals():
    from goldmonitor.runtime_state import ApplicationRuntimeState

    state = ApplicationRuntimeState()

    assert state.market_runtime_instance is None
    assert state.portfolio_runtime_instance is None
    assert state.alert_runtime_instance is None
    assert state.config_restore_service is None
    assert state.data_archive_runtime_instance is None
    assert state.news_runtime_instance is None
    assert state.diagnostics_runtime_instance is None
    assert state.update_runtime_instance is None
    assert state.floating_controller_instance is None
    assert state.taskbar_controller_instance is None
    assert state.taskbar_hwnd is None
    assert state.taskbar_owner_hwnd is None
    assert state.taskbar_target_state == {}
    assert state.taskbar_restart_count == 0
    assert state.taskbar_layout_state == {}
