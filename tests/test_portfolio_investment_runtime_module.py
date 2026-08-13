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
    assert state_payload["summary"]["actual_execution_count"] == 1
    assert state_payload["summary"]["rmb_actual_invested"] == 1002.0
    assert state_payload["summary"]["actual_trend"][-1]["rmb_invested"] == 1002.0
    assert state_payload["summary"]["automatic_execution_count"] == 1
    assert state_payload["summary"]["on_time_execution_count"] == 0
    assert state_payload["summary"]["catch_up_execution_count"] == 1
    assert state_payload["summary"]["on_time_rate"] == 0.0
    assert state_payload["items"][0]["reliability"] == {
        "days": 90,
        "automatic_execution_count": 1,
        "on_time_execution_count": 0,
        "catch_up_execution_count": 1,
        "manual_execution_count": 0,
        "unclassified_execution_count": 0,
        "on_time_rate": 0.0,
    }
    assert state_payload["items"][0]["variance"] == {
        "days": 90,
        "execution_count": 1,
        "covered_execution_count": 1,
        "uncovered_execution_count": 0,
        "planned_amount": 1000.0,
        "actual_cost": 1002.0,
        "difference": 2.0,
        "difference_percent": 0.2,
        "fee": 2.0,
        "rounding_difference": 0.0,
        "latest": {
            "id": "investment-plan-1-scheduled-202608150900",
            "timestamp": "2026-08-20T10:00:00",
            "execution_kind": "catch_up",
            "planned_amount": 1000.0,
            "actual_cost": 1002.0,
            "difference": 2.0,
            "difference_percent": 0.2,
            "fee": 2.0,
        },
    }


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


def test_runtime_previews_edited_schedule_without_persisting_plan():
    runtime, state, _events = _runtime(_plan())
    original = dict(state.portfolio_investment_plans[0])

    result = runtime.preview_schedule({
        "id": "plan-1",
        "request_id": "preview-3",
        "frequency": "weekly",
        "weekday": 5,
        "time": "10:30",
        "amount": 1200,
        "fee": 3,
        "target_count": 4,
        "start_date": "2026-08-14",
        "end_date": "2026-09-01",
    })

    assert result == {
        "ok": True,
        "id": "plan-1",
        "request_id": "preview-3",
        "items": [
            "2026-08-14T10:30:00",
            "2026-08-21T10:30:00",
            "2026-08-28T10:30:00",
        ],
        "projection": {
            "mode": "rmb",
            "target_count": 4,
            "completed_count": 0,
            "remaining_count": 4,
            "planned_cost_per_run": 1203.0,
            "projected_total_cost": 4812.0,
            "projected_remaining_cost": 4812.0,
            "projected_completion_at": "",
            "completion_limited_by_window": True,
            "completion_out_of_range": False,
        },
    }
    assert state.portfolio_investment_plans[0] == original


def test_runtime_archives_restores_and_permanently_deletes_plan():
    import pytest

    runtime, state, _events = _runtime(_plan())
    transaction_count = len(state.portfolio_transactions)

    with pytest.raises(ValueError, match="请先归档"):
        runtime.delete("plan-1")

    archived, archived_state = runtime.archive("plan-1")
    assert archived["archived_at"] == "2026-08-12T10:00:00"
    assert archived["enabled"] is False
    assert archived["next_run_at"] == ""
    assert archived_state["items"][0]["status"] == "archived"
    assert archived_state["summary"]["total"] == 0
    assert archived_state["summary"]["all_total"] == 1
    assert archived_state["summary"]["archived"] == 1
    assert len(state.portfolio_transactions) == transaction_count

    with pytest.raises(ValueError, match="已归档计划不能执行"):
        runtime.execute("plan-1", force=True)
    with pytest.raises(ValueError, match="已归档计划需先恢复"):
        runtime.toggle("plan-1", True)

    restored, restored_state = runtime.restore("plan-1")
    assert restored["archived_at"] == ""
    assert restored["enabled"] is False
    assert restored["next_run_at"] == ""
    assert restored_state["items"][0]["status"] == "paused"
    assert restored_state["summary"]["total"] == 1
    assert restored_state["summary"]["archived"] == 0

    runtime.archive("plan-1")
    ok, deleted_state = runtime.delete("plan-1")
    assert ok is True
    assert deleted_state["summary"] == {
        "total": 0,
        "all_total": 0,
        "archived": 0,
        "enabled": 0,
        "due": 0,
        "attention": 0,
        "execution_count": 0,
        "rmb_invested": 0.0,
        "usd_invested": 0.0,
        "actual_days": 30,
        "actual_execution_count": 0,
        "rmb_actual_invested": 0.0,
        "usd_actual_invested": 0.0,
        "actual_trend_months": 6,
        "actual_trend": [
            {"month": "2026-03", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
            {"month": "2026-04", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
            {"month": "2026-05", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
            {"month": "2026-06", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
            {"month": "2026-07", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
            {"month": "2026-08", "execution_count": 0, "rmb_invested": 0.0, "usd_invested": 0.0},
        ],
        "reliability_days": 90,
        "automatic_execution_count": 0,
        "on_time_execution_count": 0,
        "catch_up_execution_count": 0,
        "manual_execution_count": 0,
        "unclassified_execution_count": 0,
        "on_time_rate": None,
        "commitment_days": 30,
        "commitment_plan_count": 0,
        "commitment_run_count": 0,
        "rmb_commitment": 0.0,
        "usd_commitment": 0.0,
        "commitment_items": [],
        "commitment_calendar": [],
    }
    assert len(state.portfolio_transactions) == transaction_count


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


def test_runtime_executes_latest_due_weekly_plan_and_advances_one_week():
    runtime, state, _events = _runtime(_plan(
        frequency="weekly",
        weekday=3,
        next_run_at="2026-07-01T09:00:00",
    ))

    result = runtime.execute("plan-1", now=datetime(2026, 8, 14, 10, 0))

    assert result["status"] == "completed"
    assert result["transaction"]["scheduled_at"] == "2026-08-12T09:00:00"
    assert result["transaction"]["execution_kind"] == "catch_up"
    assert state.portfolio_investment_plans[0]["next_run_at"] == "2026-08-19T09:00:00"


def test_runtime_skips_one_pending_run_without_generating_transaction():
    import pytest

    runtime, state, _events = _runtime(_plan(
        frequency="weekly",
        weekday=3,
        next_run_at="2026-07-01T09:00:00",
    ))
    transaction_count = len(state.portfolio_transactions)

    result = runtime.skip_next(
        "plan-1",
        "2026-08-12T09:00:00",
        now=datetime(2026, 8, 14, 10, 0),
    )

    plan = state.portfolio_investment_plans[0]
    assert result["status"] == "skipped"
    assert len(state.portfolio_transactions) == transaction_count
    assert plan["enabled"] is True
    assert plan["next_run_at"] == "2026-08-19T09:00:00"
    assert plan["last_skipped_scheduled_at"] == "2026-08-12T09:00:00"
    assert plan["last_skipped_at"] == "2026-08-14T10:00:00"
    assert plan["skip_count"] == 1
    assert plan["last_result"] == "skipped"

    with pytest.raises(ValueError, match="执行时间已变化"):
        runtime.skip_next(
            "plan-1",
            "2026-08-12T09:00:00",
            now=datetime(2026, 8, 14, 10, 1),
        )
    assert state.portfolio_investment_plans[0]["next_run_at"] == "2026-08-19T09:00:00"
    assert state.portfolio_investment_plans[0]["skip_count"] == 1


def test_runtime_respects_start_date_and_completes_after_last_scheduled_run():
    import pytest

    future_runtime, future_state, _events = _runtime(_plan(
        frequency="daily",
        start_date="2026-08-20",
        end_date="2026-08-22",
        next_run_at="2026-08-20T09:00:00",
    ))

    future = future_runtime.execute(
        "plan-1",
        force=True,
        now=datetime(2026, 8, 19, 10, 0),
    )
    assert future["status"] == "not_started"
    assert len(future_state.portfolio_transactions) == 1

    final_runtime, final_state, _events = _runtime(_plan(
        frequency="daily",
        start_date="2026-08-20",
        end_date="2026-08-22",
        next_run_at="2026-08-22T09:00:00",
    ))
    executed = final_runtime.execute("plan-1", now=datetime(2026, 8, 23, 10, 0))
    assert executed["status"] == "completed"
    assert executed["transaction"]["scheduled_at"] == "2026-08-22T09:00:00"
    assert final_state.portfolio_investment_plans[0]["next_run_at"] == ""
    assert final_runtime.state_payload(now=datetime(2026, 8, 23, 10, 0))["items"][0]["status"] == "completed"

    final_runtime.now_factory = lambda: datetime(2026, 8, 23, 10, 0)
    with pytest.raises(ValueError, match="结束日期已过"):
        final_runtime.toggle("plan-1", True)


def test_runtime_stops_after_target_count_and_can_continue_after_target_increase():
    import pytest

    existing_execution = {
        "id": "investment-plan-1-scheduled-202607150900",
        "position_id": "position-1",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 500.0,
        "quantity": 2.0,
        "fee": 2.0,
        "trade_date": "2026-07-15",
        "source": "investment_plan",
        "source_id": "plan-1",
        "scheduled_at": "2026-07-15T09:00:00",
        "execution_kind": "scheduled",
        "planned_amount": 1000.0,
        "created_at": "2026-07-15T09:00:00",
        "updated_at": "2026-07-15T09:00:00",
    }
    runtime, state, _events = _runtime(
        _plan(target_count=2, next_run_at="2026-08-15T09:00:00"),
        transactions=[existing_execution],
    )

    completed = runtime.execute("plan-1", now=datetime(2026, 8, 20, 10, 0))
    plan = state.portfolio_investment_plans[0]
    assert completed["status"] == "completed"
    assert completed["message"] == "已完成 2/2 期定投"
    assert plan["enabled"] is False
    assert plan["next_run_at"] == ""
    assert runtime.state_payload(now=datetime(2026, 8, 20, 10, 1))["items"][0]["status"] == "completed"

    blocked = runtime.execute("plan-1", force=True, now=datetime(2026, 8, 20, 10, 2))
    assert blocked["status"] == "plan_completed"
    assert len(state.portfolio_transactions) == 2
    with pytest.raises(ValueError, match="达到目标期数"):
        runtime.toggle("plan-1", True)

    runtime.now_factory = lambda: datetime(2026, 8, 20, 10, 3)
    updated, _payload = runtime.upsert({**plan, "target_count": 3, "enabled": True})
    assert updated["enabled"] is True
    assert updated["next_run_at"] == "2026-09-15T09:00:00"


def test_runtime_skip_does_not_consume_target_count():
    runtime, state, _events = _runtime(_plan(
        target_count=1,
        frequency="weekly",
        weekday=3,
        next_run_at="2026-07-01T09:00:00",
    ))

    result = runtime.skip_next(
        "plan-1",
        "2026-08-12T09:00:00",
        now=datetime(2026, 8, 14, 10, 0),
    )
    plan = result["state"]["items"][0]
    assert plan["completed_count"] == 0
    assert plan["remaining_count"] == 1
    assert plan["status"] == "active"
    assert state.portfolio_investment_plans[0]["enabled"] is True


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
