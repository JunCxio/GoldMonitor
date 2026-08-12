import json
from datetime import datetime


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
