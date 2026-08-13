import threading
import csv
from datetime import datetime
from io import StringIO
from types import SimpleNamespace


def _plan(**changes):
    plan = {
        "id": "plan-1",
        "name": "每月定投",
        "position_id": "position-1",
        "position_name": "金条",
        "mode": "rmb",
        "amount": 1000.0,
        "fee": 2.0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "enabled": True,
        "next_run_at": "2026-07-15T09:00:00",
        "last_scheduled_at": "",
        "last_executed_at": "",
        "last_transaction_id": "",
        "last_price": None,
        "last_quantity": None,
        "last_result": "waiting",
        "last_message": "等待首次执行",
        "created_at": "2026-06-01T10:00:00",
        "updated_at": "2026-06-01T10:00:00",
    }
    plan.update(changes)
    return plan


def _runtime(plan=None, *, price_rmb=500.0, price_usd=2500.0, transactions=None):
    from goldmonitor.portfolio import build_portfolio_state_from_transactions
    from goldmonitor.portfolio_investment_runtime import PortfolioInvestmentRuntime

    base_transactions = transactions if transactions is not None else [{
        "id": "transaction-existing",
        "position_id": "position-1",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 450.0,
        "quantity": 1.0,
        "fee": 0.0,
        "trade_date": "2026-06-01",
        "note": "",
        "created_at": "2026-06-01T10:00:00",
        "updated_at": "2026-06-01T10:00:00",
    }]
    state = SimpleNamespace(
        lock=threading.RLock(),
        investment_plan_lock=threading.RLock(),
        portfolio_investment_plans=[] if plan is None else [plan],
        portfolio_transactions=list(base_transactions),
        price_rmb=price_rmb,
        price_usd=price_usd,
    )
    events = []

    def save_plans(items):
        return [dict(item) for item in items]

    def save_transactions(items):
        return [dict(item) for item in items]

    runtime = PortfolioInvestmentRuntime(
        state,
        save_plans=save_plans,
        save_transactions=save_transactions,
        build_portfolio_state=lambda: build_portfolio_state_from_transactions(
            state.portfolio_transactions,
            {"rmb": state.price_rmb, "usd": state.price_usd},
        ),
        emit_event=lambda name, payload: events.append((name, payload)),
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
    )
    return runtime, state, events


def test_runtime_catches_up_latest_run_and_generates_sourced_transaction():
    runtime, state, events = _runtime(_plan())

    result = runtime.execute("plan-1", now=datetime(2026, 8, 20, 10, 0))

    assert result["status"] == "completed"
    transaction = result["transaction"]
    assert transaction["id"] == "investment-plan-1-scheduled-202608150900"
    assert transaction["price"] == 500.0
    assert transaction["quantity"] == 2.0
    assert transaction["source"] == "investment_plan"
    assert transaction["source_id"] == "plan-1"
    assert transaction["execution_kind"] == "catch_up"
    assert transaction["planned_amount"] == 1000.0
    assert state.portfolio_investment_plans[0]["next_run_at"] == "2026-09-15T09:00:00"
    assert events[-1][0] == "portfolio_updated"

    state_payload = runtime.state_payload(now=datetime(2026, 8, 20, 10, 0))
    performance = state_payload["items"][0]["performance"]
    assert performance["execution_count"] == 1
    assert performance["total_invested"] == 1002.0
    assert performance["market_value"] == 1000.0
    assert performance["pnl"] == -2.0


def test_runtime_uses_usd_price_and_creates_position_on_first_execution():
    runtime, state, _events = _runtime(
        _plan(
            position_id="",
            position_name="黄金账户",
            mode="usd",
            amount=5000.0,
            next_run_at="2026-08-12T09:00:00",
        ),
        transactions=[],
    )

    result = runtime.execute("plan-1", now=datetime(2026, 8, 12, 10, 0))

    assert result["transaction"]["price"] == 2500.0
    assert result["transaction"]["quantity"] == 2.0
    assert result["transaction"]["position_id"].startswith("position-")
    assert state.portfolio_investment_plans[0]["position_id"] == result["transaction"]["position_id"]


def test_runtime_waits_for_price_without_advancing_schedule():
    runtime, state, _events = _runtime(_plan(), price_rmb=None)

    result = runtime.execute("plan-1", now=datetime(2026, 8, 20, 10, 0))

    assert result["status"] == "waiting_price"
    assert state.portfolio_investment_plans[0]["next_run_at"] == "2026-07-15T09:00:00"
    assert len(state.portfolio_transactions) == 1


def test_runtime_deterministic_id_prevents_duplicate_transaction():
    runtime, state, _events = _runtime(_plan())
    now = datetime(2026, 8, 20, 10, 0)

    first = runtime.execute("plan-1", now=now)
    state.portfolio_investment_plans[0]["next_run_at"] = "2026-07-15T09:00:00"
    second = runtime.execute("plan-1", now=now)

    assert first["transaction"]["id"] == second["transaction"]["id"]
    assert len(state.portfolio_transactions) == 2


def test_runtime_manual_execution_and_deleted_position_handling():
    manual_runtime, manual_state, _events = _runtime(
        _plan(enabled=False, next_run_at="")
    )

    manual = manual_runtime.execute(
        "plan-1",
        force=True,
        now=datetime(2026, 8, 12, 10, 42),
    )
    assert manual["transaction"]["execution_kind"] == "manual"
    assert manual["transaction"]["id"] == "investment-plan-1-manual-202608121042"
    assert manual_state.portfolio_investment_plans[0]["next_run_at"] == ""

    orphan_runtime, orphan_state, _events = _runtime(_plan(), transactions=[])
    orphan = orphan_runtime.execute("plan-1", now=datetime(2026, 8, 20, 10, 0))
    assert orphan["status"] == "orphaned"
    assert orphan_state.portfolio_investment_plans[0]["last_result"] == "orphaned"


def test_runtime_reenable_and_pause_deleted_position():
    runtime, state, _events = _runtime(
        _plan(enabled=False, next_run_at="", last_result="orphaned")
    )

    enabled, _payload = runtime.toggle("plan-1", True)
    assert enabled["next_run_at"] == "2026-08-15T09:00:00"

    count, payload = runtime.pause_for_position("position-1")
    assert count == 1
    assert payload["items"][0]["enabled"] is False
    assert state.portfolio_investment_plans[0]["last_result"] == "orphaned"


def test_runtime_run_due_only_executes_due_plans():
    runtime, state, _events = _runtime(_plan())
    state.portfolio_investment_plans.append(_plan(
        id="plan-future",
        next_run_at="2026-09-15T09:00:00",
    ))

    result = runtime.run_due(now=datetime(2026, 8, 20, 10, 0))

    assert result["executed_count"] == 1
    assert len(state.portfolio_transactions) == 2


def test_runtime_builds_execution_csv_for_existing_plan():
    transactions = [{
        "id": "investment-plan-1-manual-202608121000",
        "position_id": "position-1",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 500.0,
        "quantity": 2.0,
        "fee": 2.0,
        "trade_date": "2026-08-12",
        "source": "investment_plan",
        "source_id": "plan-1",
        "execution_kind": "manual",
        "planned_amount": 1000.0,
        "created_at": "2026-08-12T10:00:00",
        "updated_at": "2026-08-12T10:00:00",
    }]
    runtime, _state, _events = _runtime(_plan(), transactions=transactions)

    content, count, plan = runtime.build_executions_csv("plan-1")
    rows = list(csv.DictReader(StringIO(content)))

    assert count == 1
    assert plan["name"] == "每月定投"
    assert rows[0]["execution_kind"] == "manual"


def test_runtime_rejects_execution_csv_for_missing_plan():
    import pytest

    runtime, _state, _events = _runtime(_plan())

    with pytest.raises(ValueError, match="未找到定投计划"):
        runtime.build_executions_csv("missing-plan")
