import json
from datetime import datetime
from pathlib import Path


def _prepare_rules_state(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "ALERT_RULES_PATH", str(tmp_path / "alert_rules.json"))
    monkeypatch.setattr(app, "alert_rules", [])
    monkeypatch.setattr(app, "alert_rule_migration_status", {"completed": True, "source_version": "1.0.7"})
    monkeypatch.setattr(app, "alert_rules_load_error", "")
    monkeypatch.setattr(app, "alert_rules_invalid_count", 0)
    app._sync_legacy_alert_rule_views()
    return app


def test_app_migrates_legacy_rule_files_once_and_preserves_corrupt_new_file(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(app, "ALERT_RULES_PATH", str(tmp_path / "alert_rules.json"))
    monkeypatch.setattr(app, "THRESHOLDS_PATH", str(tmp_path / "thresholds.json"))
    monkeypatch.setattr(app, "WATCH_TARGETS_PATH", str(tmp_path / "watch_targets.json"))
    monkeypatch.setattr(app, "PORTFOLIO_ALERTS_PATH", str(tmp_path / "portfolio_alerts.json"))

    app.save_thresholds({"upper_warning_rmb": 720})
    app.save_watch_targets([{
        "id": "target-budget",
        "mode": "rmb",
        "direction": "fall_to",
        "price": 688,
        "enabled": True,
    }])
    app.save_portfolio_alerts([{
        "id": "portfolio-alert-gold",
        "position_id": "position-gold",
        "take_profit_price": 760,
        "enabled": True,
    }])

    migrated = app.load_alert_rules()
    assert {item["kind"] for item in migrated} == {"price_threshold", "watch_target", "portfolio"}
    first_payload = json.loads(Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8"))
    assert first_payload["migration"]["completed"] is True

    app.save_thresholds({"upper_warning_rmb": 999})
    loaded_again = app.load_alert_rules()
    threshold = next(item for item in loaded_again if item["kind"] == "price_threshold")
    assert threshold["condition"]["value"] == 720

    Path(app.ALERT_RULES_PATH).write_text("{broken", encoding="utf-8")
    assert app.load_alert_rules() == []
    assert Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8") == "{broken"
    assert app.alert_rules_load_error


def test_unified_runtime_evaluation_persists_state_and_emits_rule_metadata(monkeypatch, tmp_path):
    app = _prepare_rules_state(monkeypatch, tmp_path)
    emitted_alerts = []
    emitted_events = []
    monkeypatch.setattr(app, "price_rmb", 725.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())
    monkeypatch.setattr(app, "emit_alert", lambda entry, title: emitted_alerts.append((dict(entry), title)))
    monkeypatch.setattr(app.socketio, "emit", lambda name, data=None, **kwargs: emitted_events.append((name, data)))

    state, rule = app.upsert_alert_rule_entry({
        "kind": "price_threshold",
        "name": "国内金价突破",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 720},
        "delivery": {"channels": [], "cooldown_minutes": 5},
    })
    assert state["total"] == 1

    triggers = app.check_alert_rules("14:00:00", now=datetime(2026, 7, 27, 14, 0, 0))
    assert len(triggers) == 1
    entry, title = emitted_alerts[0]
    assert title == "金价预警 - 国内金价突破"
    assert entry["rule_id"] == rule["id"]
    assert entry["rule_kind"] == "price_threshold"
    assert entry["delivery_channels"] == []
    assert entry["cooldown_minutes"] == 5
    assert "alert_rules_updated" in {name for name, _ in emitted_events}

    persisted = json.loads(Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8"))
    assert persisted["items"][0]["state"]["triggered"] is True
    assert app.check_alert_rules("14:00:10", now=datetime(2026, 7, 27, 14, 0, 10)) == []


def test_alert_rule_socket_crud_contract(monkeypatch, tmp_path):
    app = _prepare_rules_state(monkeypatch, tmp_path)
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("save_alert_rule", {
        "kind": "watch_target",
        "name": "预算观察",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "lte", "value": 688},
    })
    events = client.get_received()
    state = next(event["args"][0] for event in events if event["name"] == "alert_rules_updated")
    rule_id = state["items"][0]["id"]

    client.emit("toggle_alert_rule", {"id": rule_id, "enabled": False})
    events = client.get_received()
    toggled = next(event["args"][0] for event in events if event["name"] == "alert_rule_toggled")
    state = next(event["args"][0] for event in events if event["name"] == "alert_rules_updated")
    assert toggled == {"ok": True, "id": rule_id, "enabled": False}
    assert state["items"][0]["enabled"] is False

    client.emit("duplicate_alert_rule", {"id": rule_id})
    events = client.get_received()
    state = next(event["args"][0] for event in events if event["name"] == "alert_rules_updated")
    assert state["total"] == 2

    client.emit("delete_alert_rule", {"id": rule_id})
    state = next(event["args"][0] for event in client.get_received() if event["name"] == "alert_rules_updated")
    assert state["total"] == 1
    client.disconnect()


def test_alert_rule_socket_batch_operations_are_transactional(monkeypatch, tmp_path):
    app = _prepare_rules_state(monkeypatch, tmp_path)
    for value in (688, 680):
        app.upsert_alert_rule_entry({
            "kind": "watch_target",
            "scope": {"mode": "rmb"},
            "condition": {"operator": "lte", "value": value},
        })
    rule_ids = [item["id"] for item in app.alert_rules]
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("batch_update_alert_rules", {"ids": rule_ids, "action": "disable"})
    events = client.get_received()
    result = next(event["args"][0] for event in events if event["name"] == "alert_rules_batch_updated")
    state = next(event["args"][0] for event in events if event["name"] == "alert_rules_updated")
    assert result["count"] == 2
    assert all(item["enabled"] is False for item in state["items"])

    snapshot = json.loads(Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8"))
    client.emit("batch_update_alert_rules", {"ids": [rule_ids[0], "rule-missing"], "action": "delete"})
    error = next(event["args"][0] for event in client.get_received() if event["name"] == "alert_rule_error")
    assert "已不存在" in error["message"]
    assert json.loads(Path(app.ALERT_RULES_PATH).read_text(encoding="utf-8")) == snapshot
    client.disconnect()


def test_alert_rule_insight_reports_delivery_and_effectiveness(monkeypatch, tmp_path):
    app = _prepare_rules_state(monkeypatch, tmp_path)
    _, rule = app.upsert_alert_rule_entry({
        "kind": "price_threshold",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 720},
        "delivery": {"channels": ["local", "email"], "cooldown_minutes": 15},
    })
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {
        "email_warning_enabled": True,
        "smtp_server": "smtp.example.com",
        "smtp_sender": "sender@example.com",
        "smtp_recipient": "receiver@example.com",
        "smtp_password": "secret",
        "webhook_enabled": False,
        "alert_quiet_start": "",
        "alert_quiet_end": "",
        "alert_cooldown_minutes": 30,
    })
    monkeypatch.setattr(app, "alert_log_export_entries", lambda limit=None: [{
        "id": "alert-one",
        "rule_id": rule["id"],
        "rule_kind": "price_threshold",
        "timestamp": "2026-07-27T13:00:00",
        "mode": "rmb",
        "trigger_price": 721,
        "alert_direction": "up",
        "notification_summary": {"status": "sent"},
        "handled": True,
    }])
    monkeypatch.setattr(app, "_analytics_price_history", lambda days, limit=1000: [
        {"timestamp": "2026-07-27T13:00:00", "rmb": 721},
        {"timestamp": "2026-07-27T14:30:00", "rmb": 723},
    ])

    insight = app.build_alert_rule_insight(rule["id"], now=datetime(2026, 7, 27, 15, 0, 0))
    assert insight["effectiveness"]["period_alerts"] == 1
    assert insight["effectiveness"]["delivery"]["sent"] == 1
    assert insight["effectiveness"]["response"]["handled"] == 1
    assert insight["delivery"]["cooldown_minutes"] == 15
    assert insight["delivery"]["channels"][1]["ready"] is True

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("get_alert_rule_insight", {"id": rule["id"], "days": 30})
    payload = next(event["args"][0] for event in client.get_received() if event["name"] == "alert_rule_insight")
    assert payload["rule_id"] == rule["id"]
    assert payload["effectiveness"]["period_alerts"] == 1
    client.disconnect()


def test_alert_rule_history_simulation_supports_drafts_and_socket_errors(monkeypatch, tmp_path):
    app = _prepare_rules_state(monkeypatch, tmp_path)
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {
        "email_warning_enabled": True,
        "webhook_enabled": False,
        "alert_quiet_start": "",
        "alert_quiet_end": "",
        "alert_cooldown_minutes": 30,
    })
    monkeypatch.setattr(app, "_analytics_price_history", lambda days, limit=1000: [
        {"timestamp": "2026-07-20T09:00:00", "rmb": 719},
        {"timestamp": "2026-07-20T09:01:00", "rmb": 721},
        {"timestamp": "2026-07-20T09:02:00", "rmb": 719},
        {"timestamp": "2026-07-20T09:20:00", "rmb": 722},
    ])
    draft = {
        "kind": "price_threshold",
        "name": "历史模拟草稿",
        "scope": {"mode": "rmb"},
        "condition": {"operator": "gte", "value": 720},
        "delivery": {"channels": [], "cooldown_minutes": 10},
    }

    result = app.build_alert_rule_simulation(
        draft,
        days=7,
        now=datetime(2026, 7, 27, 15, 0, 0),
    )
    assert result["rule_id"] == "rule-preview"
    assert result["match_count"] == 2
    assert result["effective_trigger_count"] == 2
    assert result["cooldown_minutes"] == 10

    monkeypatch.setattr(app, "portfolio_transactions", [{
        "id": "buy-gold",
        "position_id": "position-gold",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 700,
        "quantity": 10,
        "fee": 0,
        "trade_date": "2026-07-20",
        "created_at": "2026-07-20T08:00:00",
    }])
    monkeypatch.setattr(app, "portfolio_positions", [])
    portfolio_result = app.build_alert_rule_simulation(
        {
            "kind": "portfolio",
            "name": "持仓浮盈模拟",
            "scope": {"position_id": "position-gold"},
            "condition": {"condition_key": "profit_percent", "value": 2},
            "delivery": {"channels": [], "cooldown_minutes": 10},
        },
        days=7,
        now=datetime(2026, 7, 27, 15, 0, 0),
    )
    assert portfolio_result["supported"] is True
    assert portfolio_result["usable"] is True
    assert portfolio_result["mode"] == "rmb"
    assert portfolio_result["portfolio"]["position_id"] == "position-gold"
    assert portfolio_result["portfolio"]["transaction_count"] == 1

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("simulate_alert_rule", {
        "request_id": "simulation-one",
        "days": 7,
        "rule": draft,
    })
    payload = next(
        event["args"][0]
        for event in client.get_received()
        if event["name"] == "alert_rule_simulation"
    )
    assert payload["request_id"] == "simulation-one"
    assert payload["usable"] is True

    client.emit("simulate_alert_rule", {
        "request_id": "simulation-invalid",
        "days": 14,
        "rule": draft,
    })
    error = next(
        event["args"][0]
        for event in client.get_received()
        if event["name"] == "alert_rule_simulation_error"
    )
    assert error["request_id"] == "simulation-invalid"
    assert "7、30 或 90 天" in error["message"]
    client.disconnect()
