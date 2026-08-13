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

    client.emit("delete_portfolio_investment_plan", {"id": plan_id})
    events = client.get_received()
    deleted = next(
        item["args"][0]
        for item in events
        if item["name"] == "portfolio_investment_plans_updated"
    )
    assert deleted["summary"]["total"] == 0
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
