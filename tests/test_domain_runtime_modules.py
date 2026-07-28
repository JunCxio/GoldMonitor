from datetime import datetime


def _state():
    from goldmonitor.runtime_state import create_runtime_state

    return create_runtime_state(
        default_port=5000,
        app_name="金价监控",
        threshold_modes=("usd", "rmb"),
        threshold_types=(
            "upper_warning",
            "upper_critical",
            "lower_warning",
            "lower_critical",
        ),
        source_health={},
    )


def test_alert_runtime_syncs_unified_rules_into_legacy_views():
    from goldmonitor import alert_rules as alert_rules_core
    from goldmonitor.alert_runtime import AlertRuntime

    state = _state()
    rules, _rule = alert_rules_core.upsert_alert_rule(
        [],
        {
            "kind": "price_threshold",
            "name": "人民币上涨关注",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "gte", "value": 700},
            "alert_level": "warning",
            "legacy": {"source": "threshold", "key": "upper_warning_rmb"},
        },
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
        id_factory=lambda: "rule-1",
    )
    state.alert_rules = rules
    runtime = AlertRuntime(
        state,
        rule_store_factory=lambda: None,
        load_thresholds=dict,
        load_watch_targets=list,
        load_portfolio_alerts=list,
        build_portfolio_state=lambda: {"items": []},
        normalize_volatility=lambda value: value,
        save_watch_targets=lambda items: items,
        emit_event=lambda *args: None,
        emit_alert=lambda *args: None,
        get_settings=dict,
        alert_log_reader=lambda **kwargs: [],
        history_reader=lambda *args, **kwargs: [],
        history_timestamp=lambda value: None,
        alert_log_export_limit=1000,
        simulation_point_limit=30000,
        threshold_modes=("usd", "rmb"),
        threshold_types=(
            "upper_warning",
            "upper_critical",
            "lower_warning",
            "lower_critical",
        ),
        watch_target_note_limit=200,
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
    )

    runtime.sync_legacy_views()

    assert state.thresholds["upper_warning_rmb"] == 700.0
    assert state.watch_targets == []
    assert state.portfolio_alerts == []


def test_portfolio_runtime_builds_state_and_attaches_alert_status():
    from goldmonitor import portfolio as portfolio_core
    from goldmonitor.portfolio_runtime import PortfolioRuntime

    state = _state()
    state.price_rmb = 700.0
    state.portfolio_positions = [portfolio_core.normalize_portfolio_position(
        {
            "name": "实物金",
            "mode": "rmb",
            "entry_price": 680,
            "quantity": 10,
        },
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
        id_factory=lambda: "position-1",
    )]
    state.portfolio_alerts = [{
        "id": "alert-1",
        "position_id": "position-1",
        "enabled": True,
        "triggered": False,
    }]
    runtime = PortfolioRuntime(
        state,
        save_positions=lambda items: items,
        save_transactions=lambda items: items,
        save_import_backup=lambda snapshot, summary=None: {},
        clear_import_backup=dict,
        save_alerts=lambda items: items,
        import_backup_state=lambda backup: backup,
        persist_alert_rules=lambda items: items,
        emit_event=lambda *args: None,
        emit_alert=lambda *args: None,
        history_reader=lambda *args, **kwargs: [],
        alert_log_reader=lambda **kwargs: [],
        history_timestamp=lambda value: None,
        alert_log_export_limit=1000,
        now_factory=lambda: datetime(2026, 7, 28, 12, 0),
    )

    result = runtime.build_state()

    assert result["total"] == 1
    assert result["items"][0]["current_price"] == 700.0
    assert result["items"][0]["alert"]["id"] == "alert-1"
    assert result["alerts"]["total"] == 1
    assert PortfolioRuntime.analytics_days("30") == 30
    assert PortfolioRuntime.analytics_days("bad") == 90
