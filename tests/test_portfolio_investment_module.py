import csv
import json
from datetime import datetime
from io import StringIO


def test_investment_plan_calculates_daily_weekly_monthly_and_yearly_runs():
    from goldmonitor.portfolio_investment import next_plan_run_at

    assert next_plan_run_at(
        {"frequency": "daily", "time": "09:00", "month": 1, "day": 1},
        datetime(2026, 8, 12, 8, 0),
    ) == datetime(2026, 8, 12, 9, 0)
    assert next_plan_run_at(
        {"frequency": "weekly", "time": "09:00", "weekday": 3},
        datetime(2026, 8, 12, 8, 0),
    ) == datetime(2026, 8, 12, 9, 0)
    assert next_plan_run_at(
        {"frequency": "weekly", "time": "09:00", "weekday": 3},
        datetime(2026, 8, 12, 10, 0),
    ) == datetime(2026, 8, 19, 9, 0)
    assert next_plan_run_at(
        {"frequency": "weekly", "time": "09:00", "weekday": 1},
        datetime(2026, 8, 14, 10, 0),
    ) == datetime(2026, 8, 17, 9, 0)
    assert next_plan_run_at(
        {"frequency": "monthly", "time": "09:00", "month": 1, "day": 31},
        datetime(2026, 2, 28, 10, 0),
    ) == datetime(2026, 3, 31, 9, 0)
    assert next_plan_run_at(
        {"frequency": "yearly", "time": "09:00", "month": 2, "day": 29},
        datetime(2027, 1, 1, 0, 0),
    ) == datetime(2027, 2, 28, 9, 0)


def test_investment_plan_uses_latest_missed_run_only():
    from goldmonitor.portfolio_investment import latest_due_run_at, pending_plan_run_at

    monthly = {
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 31,
        "next_run_at": "2026-01-31T09:00:00",
    }
    yearly = {
        "frequency": "yearly",
        "time": "09:00",
        "month": 2,
        "day": 29,
        "next_run_at": "2024-02-29T09:00:00",
    }
    weekly = {
        "frequency": "weekly",
        "time": "09:00",
        "weekday": 3,
        "next_run_at": "2026-07-01T09:00:00",
    }

    assert latest_due_run_at(monthly, datetime(2026, 3, 15, 10, 0)) == datetime(2026, 2, 28, 9, 0)
    assert latest_due_run_at(yearly, datetime(2027, 8, 12, 10, 0)) == datetime(2027, 2, 28, 9, 0)
    assert latest_due_run_at(weekly, datetime(2026, 8, 14, 10, 0)) == datetime(2026, 8, 12, 9, 0)
    assert latest_due_run_at(weekly, datetime(2026, 8, 12, 8, 0)) == datetime(2026, 8, 5, 9, 0)
    assert pending_plan_run_at(monthly, datetime(2026, 3, 15, 10, 0)) == datetime(2026, 2, 28, 9, 0)
    assert pending_plan_run_at(
        {**weekly, "next_run_at": "2026-08-19T09:00:00"},
        datetime(2026, 8, 14, 10, 0),
    ) == datetime(2026, 8, 19, 9, 0)


def test_investment_schedule_preview_handles_month_end_leap_year_and_window():
    import pytest

    from goldmonitor.portfolio_investment import investment_schedule_preview

    monthly = investment_schedule_preview(
        {
            "frequency": "monthly",
            "time": "09:00",
            "month": 1,
            "day": 31,
            "weekday": 1,
            "start_date": "",
            "end_date": "2026-04-30",
        },
        now=datetime(2026, 1, 30, 10, 0),
    )
    yearly = investment_schedule_preview(
        {
            "frequency": "yearly",
            "time": "09:00",
            "month": 2,
            "day": 29,
            "weekday": 1,
            "start_date": "",
            "end_date": "",
        },
        now=datetime(2026, 1, 1, 10, 0),
    )

    assert monthly == [
        "2026-01-31T09:00:00",
        "2026-02-28T09:00:00",
        "2026-03-31T09:00:00",
        "2026-04-30T09:00:00",
    ]
    assert yearly[:3] == [
        "2026-02-28T09:00:00",
        "2027-02-28T09:00:00",
        "2028-02-29T09:00:00",
    ]
    with pytest.raises(ValueError, match="结束日期不能早于开始日期"):
        investment_schedule_preview(
            {
                "frequency": "daily",
                "time": "09:00",
                "start_date": "2026-09-02",
                "end_date": "2026-09-01",
            },
            now=datetime(2026, 8, 1, 10, 0),
        )


def test_investment_plan_projection_calculates_budget_and_completion_dates():
    from goldmonitor.portfolio_investment import investment_plan_projection

    base = {
        "mode": "rmb",
        "amount": 1000,
        "fee": 2,
        "target_count": 3,
        "time": "09:00",
        "month": 1,
        "day": 31,
        "weekday": 1,
        "start_date": "",
        "end_date": "",
    }
    daily = investment_plan_projection(
        {**base, "frequency": "daily"},
        now=datetime(2026, 8, 12, 10, 0),
    )
    weekly = investment_plan_projection(
        {**base, "frequency": "weekly"},
        now=datetime(2026, 8, 12, 10, 0),
    )
    monthly = investment_plan_projection(
        {**base, "frequency": "monthly", "target_count": 7},
        now=datetime(2027, 8, 12, 10, 0),
    )
    yearly = investment_plan_projection(
        {
            **base,
            "frequency": "yearly",
            "month": 2,
            "day": 29,
            "target_count": 2,
        },
        now=datetime(2027, 1, 1, 10, 0),
    )

    assert daily["planned_cost_per_run"] == 1002.0
    assert daily["projected_total_cost"] == 3006.0
    assert daily["projected_remaining_cost"] == 3006.0
    assert daily["projected_completion_at"] == "2026-08-15T09:00:00"
    assert weekly["projected_completion_at"] == "2026-08-31T09:00:00"
    assert monthly["projected_completion_at"] == "2028-02-29T09:00:00"
    assert yearly["projected_completion_at"] == "2028-02-29T09:00:00"


def test_investment_plan_projection_uses_execution_count_and_reports_short_window():
    from goldmonitor.portfolio_investment import investment_plan_projection

    plan = {
        "id": "plan-budget",
        "mode": "usd",
        "amount": 500,
        "fee": 1,
        "target_count": 4,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "weekday": 1,
        "start_date": "",
        "end_date": "2026-10-31",
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
    }
    execution = {
        "id": "execution-manual",
        "type": "buy",
        "mode": "usd",
        "price": 2500,
        "quantity": 0.2,
        "fee": 1,
        "source": "investment_plan",
        "source_id": "plan-budget",
        "execution_kind": "manual",
    }
    ignored = {**execution, "id": "execution-other", "source_id": "other-plan"}
    projection = investment_plan_projection(
        plan,
        existing=plan,
        transactions=[execution, ignored],
        now=datetime(2026, 8, 12, 10, 0),
    )

    assert projection["mode"] == "usd"
    assert projection["completed_count"] == 1
    assert projection["remaining_count"] == 3
    assert projection["projected_total_cost"] == 2004.0
    assert projection["projected_remaining_cost"] == 1503.0
    assert projection["projected_completion_at"] == ""
    assert projection["completion_limited_by_window"] is True


def test_investment_plan_projection_is_absent_without_target_count():
    from goldmonitor.portfolio_investment import investment_plan_projection

    assert investment_plan_projection({"target_count": 0}) is None


def test_investment_plan_window_projection_respects_target_and_schedule_window():
    from goldmonitor.portfolio_investment import investment_plan_window_projection

    base = {
        "mode": "rmb",
        "amount": 100,
        "fee": 2,
        "frequency": "daily",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "weekday": 1,
        "start_date": "",
        "end_date": "",
        "enabled": True,
        "next_run_at": "2026-08-01T09:00:00",
    }
    limited = investment_plan_window_projection(
        {**base, "target_count": 3, "completed_count": 1},
        now=datetime(2026, 8, 12, 10, 0),
    )
    ended = investment_plan_window_projection(
        {**base, "end_date": "2026-08-13"},
        now=datetime(2026, 8, 12, 10, 0),
    )
    paused = investment_plan_window_projection(
        {**base, "enabled": False},
        now=datetime(2026, 8, 12, 10, 0),
    )

    assert limited["run_count"] == 2
    assert limited["projected_cost"] == 204.0
    assert limited["first_run_at"] == "2026-08-12T09:00:00"
    assert limited["last_run_at"] == "2026-08-13T09:00:00"
    assert ended["run_count"] == 2
    assert ended["projected_cost"] == 204.0
    assert paused["run_count"] == 0
    assert paused["projected_cost"] == 0.0


def test_investment_plan_state_summarizes_next_30_day_commitments_by_currency():
    from goldmonitor.portfolio_investment import investment_plan_state

    rmb_plan = {
        "id": "plan-rmb",
        "name": "人民币定投",
        "mode": "rmb",
        "amount": 100,
        "fee": 2,
        "target_count": 2,
        "frequency": "daily",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "weekday": 1,
        "enabled": True,
        "next_run_at": "2026-08-12T09:00:00",
    }
    usd_plan = {
        "id": "plan-usd",
        "name": "美元定投",
        "mode": "usd",
        "amount": 500,
        "fee": 1,
        "frequency": "weekly",
        "time": "09:00",
        "month": 1,
        "day": 1,
        "weekday": 1,
        "enabled": True,
        "next_run_at": "2026-08-17T09:00:00",
    }
    paused_plan = {**rmb_plan, "id": "plan-paused", "enabled": False}
    execution = {
        "id": "execution-rmb",
        "type": "buy",
        "mode": "rmb",
        "price": 50,
        "quantity": 2,
        "fee": 2,
        "source": "investment_plan",
        "source_id": "plan-rmb",
        "execution_kind": "scheduled",
    }
    summary = investment_plan_state(
        [rmb_plan, usd_plan, paused_plan],
        transactions=[execution],
        now=datetime(2026, 8, 12, 10, 0),
    )["summary"]

    assert summary["commitment_days"] == 30
    assert summary["commitment_plan_count"] == 2
    assert summary["commitment_run_count"] == 5
    assert summary["rmb_commitment"] == 102.0
    assert summary["usd_commitment"] == 2004.0


def test_investment_plan_state_exposes_future_schedule_from_pending_run():
    from goldmonitor.portfolio_investment import investment_plan_state

    state = investment_plan_state(
        [{
            "id": "plan-preview",
            "name": "每周积存",
            "mode": "rmb",
            "frequency": "weekly",
            "weekday": 3,
            "time": "09:00",
            "month": 1,
            "day": 1,
            "enabled": True,
            "next_run_at": "2026-08-12T09:00:00",
        }],
        now=datetime(2026, 8, 14, 10, 0),
    )

    assert state["items"][0]["upcoming_run_ats"] == [
        "2026-08-12T09:00:00",
        "2026-08-19T09:00:00",
        "2026-08-26T09:00:00",
        "2026-09-02T09:00:00",
        "2026-09-09T09:00:00",
    ]


def test_investment_plan_applies_optional_start_and_end_dates():
    import pytest

    from goldmonitor.portfolio_investment import (
        investment_plan_state,
        latest_due_run_at,
        next_plan_run_in_window,
        normalize_investment_plan,
    )

    plan = normalize_investment_plan(
        {
            "name": "季度积累",
            "position_name": "积存金",
            "mode": "rmb",
            "amount": 1000,
            "fee": 0,
            "frequency": "monthly",
            "day": 15,
            "time": "09:00",
            "start_date": "2026-10-01",
            "end_date": "2026-12-31",
            "enabled": True,
        },
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
        id_factory=lambda: "plan-window",
    )

    assert plan["next_run_at"] == "2026-10-15T09:00:00"
    pending = investment_plan_state([plan], now=datetime(2026, 9, 1, 10, 0))
    assert pending["items"][0]["status"] == "pending_start"
    assert pending["summary"]["enabled"] == 1
    assert latest_due_run_at(plan, datetime(2026, 9, 15, 10, 0)) is None
    assert next_plan_run_in_window(plan, datetime(2026, 12, 15, 10, 0)) is None

    completed_plan = {**plan, "next_run_at": ""}
    completed = investment_plan_state([completed_plan], now=datetime(2027, 1, 1, 10, 0))
    assert completed["items"][0]["status"] == "completed"
    assert completed["summary"]["enabled"] == 0

    supplied_outside_window = normalize_investment_plan(
        {
            **plan,
            "id": "plan-imported",
            "next_run_at": "2026-08-15T09:00:00",
        },
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
    )
    assert supplied_outside_window["next_run_at"] == "2026-10-15T09:00:00"

    with pytest.raises(ValueError, match="结束日期不能早于开始日期"):
        normalize_investment_plan(
            {**plan, "start_date": "2026-12-01", "end_date": "2026-11-30"},
            existing=plan,
            now_factory=lambda: datetime(2026, 8, 12, 10, 0),
        )


def test_investment_plan_reenable_starts_from_current_time():
    from goldmonitor.portfolio_investment import normalize_investment_plan

    existing = {
        "id": "plan-1",
        "name": "每月定投",
        "position_id": "position-1",
        "position_name": "金条",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "enabled": False,
        "next_run_at": "",
        "created_at": "2026-01-01T10:00:00",
    }
    payload = normalize_investment_plan(
        {**existing, "enabled": True},
        existing=existing,
        now_factory=lambda: datetime(2026, 8, 20, 10, 0),
    )

    assert payload["next_run_at"] == "2026-09-15T09:00:00"
    assert payload["created_at"] == "2026-01-01T10:00:00"


def test_investment_plan_weekly_schedule_change_recalculates_next_run():
    from goldmonitor.portfolio_investment import normalize_investment_plan

    existing = {
        "id": "plan-weekly",
        "name": "每周定投",
        "position_id": "position-1",
        "position_name": "金条",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "weekly",
        "time": "09:00",
        "weekday": 3,
        "month": 1,
        "day": 1,
        "enabled": True,
        "next_run_at": "2026-08-19T09:00:00",
        "created_at": "2026-08-01T10:00:00",
    }

    unchanged = normalize_investment_plan(
        dict(existing),
        existing=existing,
        now_factory=lambda: datetime(2026, 8, 13, 10, 0),
    )
    changed = normalize_investment_plan(
        {**existing, "weekday": 5},
        existing=existing,
        now_factory=lambda: datetime(2026, 8, 13, 10, 0),
    )

    assert unchanged["next_run_at"] == "2026-08-19T09:00:00"
    assert changed["next_run_at"] == "2026-08-14T09:00:00"


def test_old_monthly_plan_without_weekday_preserves_next_run():
    from goldmonitor.portfolio_investment import normalize_investment_plan

    existing = {
        "id": "plan-monthly",
        "name": "每月定投",
        "position_id": "position-1",
        "position_name": "金条",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
        "created_at": "2026-08-01T10:00:00",
    }

    payload = normalize_investment_plan(
        dict(existing),
        existing=existing,
        now_factory=lambda: datetime(2026, 8, 20, 10, 0),
    )

    assert payload["weekday"] == 1
    assert payload["next_run_at"] == "2026-09-15T09:00:00"


def test_investment_plan_store_round_trips_versioned_payload(tmp_path):
    from goldmonitor.portfolio_investment import InvestmentPlanStore

    path = tmp_path / "portfolio_investment_plans.json"
    store = InvestmentPlanStore(
        path,
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
        id_factory=lambda: "plan-generated",
    )
    saved = store.save([{
        "name": "每日积累",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": "100",
        "fee": "0",
        "frequency": "daily",
        "time": "09:00",
        "enabled": True,
    }])

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert saved[0]["id"] == "plan-generated"
    assert saved[0]["next_run_at"] == "2026-08-13T09:00:00"
    assert payload["schema_version"] == 1
    assert store.load() == saved


def test_investment_plan_target_count_is_optional_and_validated():
    import pytest

    from goldmonitor.portfolio_investment import normalize_investment_plan

    base = {
        "name": "十二期定投",
        "position_name": "积存金",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "monthly",
        "time": "09:00",
        "day": 15,
        "enabled": True,
    }
    unlimited = normalize_investment_plan(
        base,
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
        id_factory=lambda: "plan-unlimited",
    )
    limited = normalize_investment_plan(
        {**base, "target_count": "12"},
        now_factory=lambda: datetime(2026, 8, 12, 10, 0),
        id_factory=lambda: "plan-limited",
    )

    assert unlimited["target_count"] == 0
    assert limited["target_count"] == 12
    with pytest.raises(ValueError, match="目标期数"):
        normalize_investment_plan({**base, "target_count": 1.5})
    with pytest.raises(ValueError, match="目标期数"):
        normalize_investment_plan({**base, "target_count": 10001})


def test_investment_plan_state_completes_at_target_count_and_limits_preview():
    from goldmonitor.portfolio_investment import investment_plan_state

    plan = {
        "id": "plan-target",
        "name": "两期定投",
        "mode": "rmb",
        "amount": 1000,
        "fee": 0,
        "frequency": "monthly",
        "time": "09:00",
        "month": 1,
        "day": 15,
        "weekday": 1,
        "target_count": 2,
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
        "last_result": "ok",
    }
    transaction = {
        "type": "buy",
        "mode": "rmb",
        "price": 500.0,
        "quantity": 2.0,
        "fee": 0.0,
        "source": "investment_plan",
        "source_id": "plan-target",
        "execution_kind": "scheduled",
    }
    in_progress = investment_plan_state(
        [plan],
        transactions=[{**transaction, "id": "execution-1", "created_at": "2026-08-15T09:00:00"}],
        now=datetime(2026, 8, 20, 10, 0),
    )["items"][0]
    completed = investment_plan_state(
        [plan],
        transactions=[
            {**transaction, "id": "execution-1", "created_at": "2026-07-15T09:00:00"},
            {**transaction, "id": "execution-2", "created_at": "2026-08-15T09:00:00"},
        ],
        now=datetime(2026, 8, 20, 10, 0),
    )["items"][0]

    assert in_progress["status"] == "active"
    assert in_progress["completed_count"] == 1
    assert in_progress["remaining_count"] == 1
    assert in_progress["upcoming_run_ats"] == ["2026-09-15T09:00:00"]
    assert in_progress["projection"]["projected_total_cost"] == 2000.0
    assert in_progress["projection"]["projected_remaining_cost"] == 1000.0
    assert in_progress["projection"]["projected_completion_at"] == "2026-09-15T09:00:00"
    assert completed["status"] == "completed"
    assert completed["completed_count"] == 2
    assert completed["remaining_count"] == 0
    assert completed["enabled"] is False
    assert completed["next_run_at"] == ""
    assert completed["pending_run_at"] == ""
    assert completed["upcoming_run_ats"] == []
    assert completed["projection"]["projected_remaining_cost"] == 0.0
    assert completed["projection"]["projected_completion_at"] == ""


def test_investment_plan_state_calculates_performance_from_sourced_transactions():
    from goldmonitor.portfolio_investment import investment_plan_state

    plans = [{
        "id": "plan-1",
        "name": "每月定投",
        "mode": "rmb",
        "enabled": True,
        "next_run_at": "2026-09-15T09:00:00",
        "last_result": "ok",
    }]
    transactions = [
        {
            "id": "execution-2",
            "type": "buy",
            "mode": "rmb",
            "price": 600.0,
            "quantity": 2.0,
            "fee": 2.0,
            "created_at": "2026-08-12T10:00:00",
            "source": "investment_plan",
            "source_id": "plan-1",
            "execution_kind": "manual",
            "planned_amount": 1200.0,
        },
        {
            "id": "execution-1",
            "type": "buy",
            "mode": "rmb",
            "price": 500.0,
            "quantity": 2.0,
            "fee": 1.0,
            "created_at": "2026-07-15T09:00:00",
            "source": "investment_plan",
            "source_id": "plan-1",
            "execution_kind": "scheduled",
            "planned_amount": 1000.0,
        },
        {
            "id": "other-source",
            "type": "buy",
            "mode": "rmb",
            "price": 400.0,
            "quantity": 10.0,
            "fee": 0.0,
            "source": "manual",
            "source_id": "plan-1",
        },
    ]

    state = investment_plan_state(
        plans,
        transactions=transactions,
        prices={"rmb": 700.0},
        now=datetime(2026, 8, 12, 12, 0),
    )

    performance = state["items"][0]["performance"]
    assert performance["execution_count"] == 2
    assert performance["total_quantity"] == 4.0
    assert performance["gross_invested"] == 2200.0
    assert performance["total_fees"] == 3.0
    assert performance["total_invested"] == 2203.0
    assert performance["average_price"] == 550.0
    assert performance["average_cost"] == 550.75
    assert performance["market_value"] == 2800.0
    assert performance["pnl"] == 597.0
    assert round(performance["pnl_percent"], 4) == 27.0994
    assert [item["id"] for item in performance["recent_executions"]] == [
        "execution-2",
        "execution-1",
    ]
    assert state["summary"]["execution_count"] == 2
    assert state["summary"]["rmb_invested"] == 2203.0
    assert state["summary"]["usd_invested"] == 0.0


def test_investment_plan_performance_waits_for_current_price_and_limits_history():
    from goldmonitor.portfolio_investment import investment_plan_performance

    transactions = [
        {
            "id": f"execution-{index:02d}",
            "type": "buy",
            "price": 500.0 + index,
            "quantity": 1.0,
            "fee": 0.0,
            "created_at": f"2026-08-{index + 1:02d}T09:00:00",
            "source": "investment_plan",
            "source_id": "plan-1",
        }
        for index in range(12)
    ]

    performance = investment_plan_performance(
        {"id": "plan-1"},
        transactions,
        current_price=None,
    )

    assert performance["execution_count"] == 12
    assert performance["valuation_status"] == "waiting_price"
    assert performance["market_value"] is None
    assert performance["pnl"] is None
    assert len(performance["recent_executions"]) == 10
    assert performance["recent_executions"][0]["id"] == "execution-11"


def test_investment_plan_execution_csv_exports_all_matching_rows_in_time_order():
    from goldmonitor.portfolio_investment import build_investment_plan_executions_csv

    transactions = [
        {
            "id": f"execution-{index:02d}",
            "position_id": "position-1",
            "name": "积存金",
            "type": "buy",
            "mode": "rmb",
            "price": 500.0 + index,
            "quantity": 2.0,
            "fee": 1.0,
            "trade_date": f"2026-08-{index + 1:02d}",
            "created_at": f"2026-08-{index + 1:02d}T09:05:00",
            "source": "investment_plan",
            "source_id": "plan-1",
            "scheduled_at": f"2026-08-{index + 1:02d}T09:00:00",
            "execution_kind": "scheduled",
            "planned_amount": 1000.0,
            "note": "计划执行",
        }
        for index in range(12)
    ]
    transactions.extend([
        {
            "id": "manual-transaction",
            "type": "buy",
            "price": 400.0,
            "quantity": 1.0,
            "fee": 0.0,
            "source": "manual",
            "source_id": "plan-1",
        },
        {
            "id": "other-plan-execution",
            "type": "buy",
            "price": 450.0,
            "quantity": 1.0,
            "fee": 0.0,
            "source": "investment_plan",
            "source_id": "plan-2",
        },
    ])

    content, count = build_investment_plan_executions_csv(
        {"id": "plan-1", "name": "每月积存", "mode": "rmb"},
        transactions,
    )
    rows = list(csv.DictReader(StringIO(content)))

    assert count == 12
    assert len(rows) == 12
    assert rows[0]["transaction_id"] == "execution-00"
    assert rows[-1]["transaction_id"] == "execution-11"
    assert rows[0]["plan_name"] == "每月积存"
    assert rows[0]["gross_amount"] == "1000.0"
    assert rows[0]["total_cost"] == "1001.0"
    assert {row["transaction_id"] for row in rows}.isdisjoint({
        "manual-transaction",
        "other-plan-execution",
    })


def test_investment_plan_execution_csv_supports_plan_without_executions():
    from goldmonitor.portfolio_investment import build_investment_plan_executions_csv

    content, count = build_investment_plan_executions_csv(
        {"id": "plan-empty", "name": "尚未执行"},
        [],
    )
    rows = list(csv.DictReader(StringIO(content)))

    assert count == 0
    assert rows == []
    assert content.startswith("plan_id,plan_name,transaction_id,")
