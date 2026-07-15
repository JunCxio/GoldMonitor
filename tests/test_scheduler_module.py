import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_daily_task_due_runs_once_after_local_schedule_time():
    from goldmonitor.scheduler import daily_task_due

    before = daily_task_due(
        "20:00",
        last_completed_at="",
        now=datetime(2026, 7, 13, 19, 59),
    )
    due = daily_task_due(
        "20:00",
        last_completed_at="",
        now=datetime(2026, 7, 13, 20, 0),
    )
    completed = daily_task_due(
        "20:00",
        last_completed_at="2026-07-13T20:01:00",
        now=datetime(2026, 7, 13, 22, 0),
    )
    next_day = daily_task_due(
        "20:00",
        last_completed_at="2026-07-13T20:01:00",
        now=datetime(2026, 7, 14, 21, 0),
    )

    assert before == {
        "due": False,
        "reason": "before_schedule",
        "scheduled_at": "2026-07-13T20:00:00",
    }
    assert due == {
        "due": True,
        "reason": "due",
        "scheduled_at": "2026-07-13T20:00:00",
    }
    assert completed == {
        "due": False,
        "reason": "already_completed",
        "scheduled_at": "2026-07-13T20:00:00",
    }
    assert next_day["due"] is True
    assert next_day["scheduled_at"] == "2026-07-14T20:00:00"


def test_daily_task_due_rejects_invalid_schedule_and_recovers_from_invalid_state():
    from goldmonitor.scheduler import daily_task_due

    invalid_schedule = daily_task_due(
        "25:00",
        last_completed_at="",
        now=datetime(2026, 7, 13, 20, 0),
    )
    invalid_state = daily_task_due(
        "08:30",
        last_completed_at="not-a-time",
        now=datetime(2026, 7, 13, 9, 0),
    )

    assert invalid_schedule == {
        "due": False,
        "reason": "invalid_schedule",
        "scheduled_at": "",
    }
    assert invalid_state["due"] is True


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("scheduler module checks passed.")
