from datetime import datetime


def _reset_portfolio_runtime(app):
    app.portfolio_runtime_instance = None
    app.portfolio_investment_runtime_instance = None


def test_app_portfolio_investment_socket_crud_and_manual_execution(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(
        app,
        "PORTFOLIO_INVESTMENT_PLANS_PATH",
        str(tmp_path / "portfolio_investment_plans.json"),
    )
    monkeypatch.setattr(
        app,
        "PORTFOLIO_TRANSACTIONS_PATH",
        str(tmp_path / "portfolio_transactions.json"),
    )
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "portfolio_investment_plans", [])
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())
    monkeypatch.setattr(app, "price_rmb", 500.0)
    monkeypatch.setattr(app, "price_usd", 2500.0)
    _reset_portfolio_runtime(app)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("save_portfolio_investment_plan", {
        "name": "每周积累",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "target_count": 6,
        "frequency": "weekly",
        "weekday": 4,
        "time": "09:00",
        "start_date": "2026-01-01",
        "end_date": "2026-12-31",
        "enabled": True,
    })
    events = client.get_received()
    saved = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_saved"
    )
    state = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    plan_id = saved["plan"]["id"]
    assert saved["plan"]["frequency"] == "weekly"
    assert saved["plan"]["weekday"] == 4
    assert saved["plan"]["start_date"] == "2026-01-01"
    assert saved["plan"]["end_date"] == "2026-12-31"
    assert state["summary"]["total"] == 1

    client.emit("preview_portfolio_investment_schedule", {
        "id": plan_id,
        "request_id": "preview-1",
        "frequency": "monthly",
        "day": 31,
        "time": "08:30",
        "start_date": "2026-09-01",
        "end_date": "2026-11-30",
    })
    events = client.get_received()
    preview = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_schedule_preview"
    )
    assert preview["ok"] is True
    assert preview["id"] == plan_id
    assert preview["request_id"] == "preview-1"
    assert preview["items"] == [
        "2026-09-30T08:30:00",
        "2026-10-31T08:30:00",
        "2026-11-30T08:30:00",
    ]
    assert preview["projection"]["projected_total_cost"] == 6000.0
    assert preview["projection"]["projected_remaining_cost"] == 6000.0
    assert preview["projection"]["completion_limited_by_window"] is True

    client.emit("execute_portfolio_investment_plan", {"id": plan_id})
    events = client.get_received()
    executed = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_executed"
    )
    portfolio = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_updated"
    )
    assert executed["status"] == "completed"
    assert executed["transaction"]["source"] == "investment_plan"
    assert portfolio["items"][0]["name"] == "积存金"

    client.emit("get_portfolio_investment_plans")
    events = client.get_received()
    performance_state = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert performance_state["items"][0]["performance"]["execution_count"] == 1
    assert performance_state["items"][0]["performance"]["total_invested"] == 1000.0

    pending_run_at = performance_state["items"][0]["pending_run_at"]
    transaction_count = len(app.portfolio_transactions)
    client.emit("skip_portfolio_investment_plan", {
        "id": plan_id,
        "scheduled_at": pending_run_at,
    })
    events = client.get_received()
    skipped = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_skipped"
    )
    skipped_state = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert skipped["status"] == "skipped"
    assert skipped_state["items"][0]["last_result"] == "skipped"
    assert skipped_state["items"][0]["skip_count"] == 1
    assert skipped_state["items"][0]["next_run_at"] != pending_run_at
    assert len(app.portfolio_transactions) == transaction_count

    client.emit("toggle_portfolio_investment_plan", {"id": plan_id, "enabled": False})
    events = client.get_received()
    paused = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert paused["items"][0]["enabled"] is False

    client.emit("archive_portfolio_investment_plan", {"id": plan_id})
    events = client.get_received()
    archived_event = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_archived"
    )
    archived = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert archived_event["plan"]["archived_at"]
    assert archived["summary"]["total"] == 0
    assert archived["summary"]["archived"] == 1
    assert archived["items"][0]["performance"]["execution_count"] == 1

    client.emit("restore_portfolio_investment_plan", {"id": plan_id})
    events = client.get_received()
    restored_event = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_restored"
    )
    restored = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert restored_event["plan"]["archived_at"] == ""
    assert restored_event["plan"]["enabled"] is False
    assert restored["summary"]["total"] == 1

    client.emit("archive_portfolio_investment_plan", {"id": plan_id})
    client.get_received()
    client.emit("delete_portfolio_investment_plan", {"id": plan_id})
    events = client.get_received()
    deleted_event = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_deleted"
    )
    deleted = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert deleted_event["id"] == plan_id
    assert deleted["summary"]["all_total"] == 0
    assert len(app.portfolio_transactions) == transaction_count
    client.disconnect()


def test_app_delete_position_pauses_linked_investment_plan(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(
        app,
        "PORTFOLIO_INVESTMENT_PLANS_PATH",
        str(tmp_path / "portfolio_investment_plans.json"),
    )
    monkeypatch.setattr(
        app,
        "PORTFOLIO_TRANSACTIONS_PATH",
        str(tmp_path / "portfolio_transactions.json"),
    )
    transaction = {
        "id": "transaction-1",
        "position_id": "position-1",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 500.0,
        "quantity": 1.0,
        "fee": 0.0,
        "trade_date": "2026-08-01",
        "note": "",
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
    }
    plan = {
        "id": "plan-1",
        "name": "每月定投",
        "position_id": "position-1",
        "position_name": "金条",
        "mode": "rmb",
        "amount": 1000.0,
        "fee": 0.0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
        "last_scheduled_at": "",
        "last_executed_at": "",
        "last_transaction_id": "",
        "last_price": None,
        "last_quantity": None,
        "last_result": "waiting",
        "last_message": "等待首次执行",
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
    }
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [transaction])
    monkeypatch.setattr(app, "portfolio_investment_plans", [plan])
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())
    _reset_portfolio_runtime(app)

    ok, state = app.delete_portfolio_position("position-1")

    assert ok is True
    assert state["items"] == []
    assert state["investment_plans"]["items"][0]["enabled"] is False
    assert state["investment_plans"]["items"][0]["last_result"] == "orphaned"


def test_app_background_investment_task_executes_latest_due_plan(monkeypatch, tmp_path):
    import app

    monkeypatch.setattr(
        app,
        "PORTFOLIO_INVESTMENT_PLANS_PATH",
        str(tmp_path / "portfolio_investment_plans.json"),
    )
    monkeypatch.setattr(
        app,
        "PORTFOLIO_TRANSACTIONS_PATH",
        str(tmp_path / "portfolio_transactions.json"),
    )
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())
    monkeypatch.setattr(app, "price_rmb", 500.0)
    monkeypatch.setattr(app, "price_usd", 2500.0)
    monkeypatch.setattr(app, "portfolio_investment_plans", [{
        "id": "plan-due",
        "name": "每日积累",
        "position_id": "",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": 500.0,
        "fee": 0.0,
        "frequency": "daily",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "enabled": True,
        "next_run_at": "2026-08-01T09:00:00",
        "last_scheduled_at": "",
        "last_executed_at": "",
        "last_transaction_id": "",
        "last_price": None,
        "last_quantity": None,
        "last_result": "waiting",
        "last_message": "等待首次执行",
        "created_at": "2026-08-01T10:00:00",
        "updated_at": "2026-08-01T10:00:00",
    }])
    _reset_portfolio_runtime(app)
    runtime = app._get_portfolio_investment_runtime()
    runtime.now_factory = lambda: datetime(2026, 8, 12, 10, 0)

    result = app.run_portfolio_investment_plans()

    assert result["executed_count"] == 1
    assert len(app.portfolio_transactions) == 1
    assert app.portfolio_transactions[0]["scheduled_at"] == "2026-08-12T09:00:00"


def test_app_exports_investment_plan_execution_csv(monkeypatch, tmp_path):
    import app

    plan = {
        "id": "plan-export",
        "name": "每月积存",
        "position_id": "position-1",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": 1000.0,
        "fee": 2.0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
        "last_scheduled_at": "2026-08-15T09:00:00",
        "last_executed_at": "2026-08-15T09:05:00",
        "last_transaction_id": "execution-1",
        "last_price": 500.0,
        "last_quantity": 2.0,
        "last_result": "ok",
        "last_message": "定投买入流水已生成",
        "created_at": "2026-07-01T10:00:00",
        "updated_at": "2026-08-15T09:05:00",
    }
    transaction = {
        "id": "execution-1",
        "position_id": "position-1",
        "name": "积存金",
        "type": "buy",
        "mode": "rmb",
        "price": 500.0,
        "quantity": 2.0,
        "fee": 2.0,
        "trade_date": "2026-08-15",
        "source": "investment_plan",
        "source_id": "plan-export",
        "scheduled_at": "2026-08-15T09:00:00",
        "execution_kind": "scheduled",
        "planned_amount": 1000.0,
        "note": "定投计划：每月积存",
        "created_at": "2026-08-15T09:05:00",
        "updated_at": "2026-08-15T09:05:00",
    }
    saved = {}
    monkeypatch.setattr(
        app,
        "PORTFOLIO_INVESTMENT_PLANS_PATH",
        str(tmp_path / "portfolio_investment_plans.json"),
    )
    monkeypatch.setattr(
        app,
        "PORTFOLIO_TRANSACTIONS_PATH",
        str(tmp_path / "portfolio_transactions.json"),
    )
    monkeypatch.setattr(app, "portfolio_investment_plans", [plan])
    monkeypatch.setattr(app, "portfolio_transactions", [transaction])
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())

    def fake_save_export_file(filename, content):
        saved["filename"] = filename
        saved["content"] = content
        return f"/tmp/{filename}"

    monkeypatch.setattr(app, "save_export_file", fake_save_export_file)
    _reset_portfolio_runtime(app)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("export_portfolio_investment_executions", {"id": "plan-export"})
    events = client.get_received()
    exported = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_executions_exported"
    )

    assert exported["ok"] is True
    assert exported["plan_name"] == "每月积存"
    assert exported["count"] == 1
    assert exported["filename"].startswith("GoldMonitor-investment-executions-")
    assert exported["filename"].endswith(".csv")
    assert saved["filename"] == exported["filename"]
    assert "execution-1" in saved["content"]
    client.disconnect()


def test_app_rejects_execution_export_for_missing_investment_plan(monkeypatch):
    import app

    monkeypatch.setattr(app, "portfolio_investment_plans", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    _reset_portfolio_runtime(app)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("export_portfolio_investment_executions", {"id": "missing-plan"})
    events = client.get_received()
    error = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_executions_export_error"
    )

    assert error["message"] == "未找到定投计划"
    client.disconnect()


def test_app_simulates_investment_plan_history_with_request_id(monkeypatch, tmp_path):
    import app

    plan = {
        "id": "plan-simulation",
        "name": "每日定投",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": 1000.0,
        "fee": 1.0,
        "frequency": "daily",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "weekday": 1,
        "start_date": "2026-08-11",
        "end_date": "",
        "enabled": True,
        "created_at": "2026-08-01T08:00:00",
    }
    history = [
        {"timestamp": "2026-08-11T09:00:00", "rmb": 500.0, "usd": 2500.0},
        {"timestamp": "2026-08-12T09:00:00", "rmb": 510.0, "usd": 2550.0},
        {"timestamp": "2026-08-12T10:00:00", "rmb": 520.0, "usd": 2600.0},
    ]
    monkeypatch.setattr(
        app,
        "PORTFOLIO_INVESTMENT_PLANS_PATH",
        str(tmp_path / "portfolio_investment_plans.json"),
    )
    monkeypatch.setattr(app, "portfolio_investment_plans", [plan])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "portfolio_alerts", [])
    monkeypatch.setattr(app, "portfolio_import_backup", app.empty_portfolio_import_backup())
    monkeypatch.setattr(app, "_analytics_price_history", lambda days, limit=1000: history)
    _reset_portfolio_runtime(app)
    app._get_portfolio_investment_runtime().now_factory = lambda: datetime(2026, 8, 12, 10, 0)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("simulate_portfolio_investment_plan", {
        "id": "plan-simulation",
        "days": 7,
        "request_id": "simulation-1",
    })
    events = client.get_received()
    simulated = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plan_simulation"
    )

    assert simulated["ok"] is True
    assert simulated["id"] == "plan-simulation"
    assert simulated["request_id"] == "simulation-1"
    assert simulated["result"]["covered_count"] == 2
    assert simulated["result"]["latest_price"] == 520.0
    assert simulated["result"]["coverage"]["data_quality"]["point_count"] == 3
    assert simulated["result"]["coverage"]["data_quality"]["granularity"]["key"] == "daily"
    assert simulated["result"]["confidence"]["level"] == "medium"
    assert app.portfolio_transactions == []
    client.disconnect()


def test_app_rejects_invalid_or_missing_investment_simulation(monkeypatch):
    import app

    monkeypatch.setattr(app, "portfolio_investment_plans", [])
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "_analytics_price_history", lambda days, limit=1000: [])
    _reset_portfolio_runtime(app)
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()

    client.emit("simulate_portfolio_investment_plan", {
        "id": "missing-plan",
        "days": 30,
        "request_id": "missing",
    })
    missing_events = client.get_received()
    missing = next(
        item["args"][0]
        for item in missing_events
        if item["name"] == "portfolio_investment_plan_simulation_error"
    )
    assert missing == {
        "id": "missing-plan",
        "request_id": "missing",
        "message": "未找到定投计划",
    }

    plan = {
        "id": "plan-invalid-range",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "weekday": 1,
        "start_date": "",
        "end_date": "",
    }
    monkeypatch.setattr(app, "portfolio_investment_plans", [plan])
    _reset_portfolio_runtime(app)
    client.emit("simulate_portfolio_investment_plan", {
        "id": "plan-invalid-range",
        "days": 14,
        "request_id": "invalid",
    })
    invalid_events = client.get_received()
    invalid = next(
        item["args"][0]
        for item in invalid_events
        if item["name"] == "portfolio_investment_plan_simulation_error"
    )
    assert invalid["request_id"] == "invalid"
    assert invalid["message"] == "历史模拟仅支持 7、30 或 90 天"

    client.emit("simulate_portfolio_investment_plan", {
        "id": "plan-invalid-range",
        "request_id": "empty",
    })
    empty_events = client.get_received()
    empty = next(
        item["args"][0]
        for item in empty_events
        if item["name"] == "portfolio_investment_plan_simulation_error"
    )
    assert empty["request_id"] == "empty"
    assert empty["message"] == "历史模拟范围无效"
    client.disconnect()
