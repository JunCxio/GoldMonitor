import csv
import json
from datetime import datetime
from io import StringIO


def test_investment_plan_calculates_daily_monthly_and_yearly_runs():
    from goldmonitor.portfolio_investment import next_plan_run_at

    assert next_plan_run_at(
        {"frequency": "daily", "time": "09:00", "month": 1, "day": 1},
        datetime(2026, 8, 12, 8, 0),
    ) == datetime(2026, 8, 12, 9, 0)
    assert next_plan_run_at(
        {"frequency": "monthly", "time": "09:00", "month": 1, "day": 31},
        datetime(2026, 2, 28, 10, 0),
    ) == datetime(2026, 3, 31, 9, 0)
    assert next_plan_run_at(
        {"frequency": "yearly", "time": "09:00", "month": 2, "day": 29},
        datetime(2027, 1, 1, 0, 0),
    ) == datetime(2027, 2, 28, 9, 0)


def test_investment_plan_uses_latest_missed_run_only():
    from goldmonitor.portfolio_investment import latest_due_run_at

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

    assert latest_due_run_at(monthly, datetime(2026, 3, 15, 10, 0)) == datetime(2026, 2, 28, 9, 0)
    assert latest_due_run_at(yearly, datetime(2027, 8, 12, 10, 0)) == datetime(2027, 2, 28, 9, 0)


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
