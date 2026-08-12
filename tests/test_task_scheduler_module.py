from datetime import datetime, timedelta


class Clock:
    def __init__(self, value):
        self.value = value
        self.monotonic_value = 10.0

    def now(self):
        return self.value

    def monotonic(self):
        return self.monotonic_value

    def advance(self, seconds):
        self.value += timedelta(seconds=seconds)
        self.monotonic_value += seconds


def test_scheduler_runs_due_tasks_and_records_status():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    calls = []
    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        monotonic_factory=clock.monotonic,
    )
    scheduler.register(
        "news",
        "资讯刷新",
        900,
        lambda: calls.append("news") or True,
    )

    result = scheduler.run_due()
    status = scheduler.status()

    assert len(result) == 1
    assert calls == ["news"]
    assert status["tasks"][0]["state"] == "ok"
    assert status["tasks"][0]["run_count"] == 1
    assert status["tasks"][0]["last_completed_at"] == "2026-08-12T10:00:00"
    assert status["tasks"][0]["next_run_at"] == "2026-08-12T10:15:00"


def test_scheduler_summary_reports_tasks_waiting_for_first_run():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    scheduler = TaskSchedulerRuntime(now_factory=clock.now)
    scheduler.register(
        "news",
        "资讯刷新",
        900,
        lambda: True,
        run_immediately=False,
    )

    status = scheduler.status()

    assert status["summary"]["waiting"] == 1
    assert status["tasks"][0]["last_duration_ms"] is None


def test_scheduler_skips_tasks_until_their_next_run():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    calls = []
    scheduler = TaskSchedulerRuntime(now_factory=clock.now)
    scheduler.register("news", "资讯刷新", 900, lambda: calls.append("news"))

    scheduler.run_due()
    clock.advance(899)
    assert scheduler.run_due() == []
    clock.advance(1)
    scheduler.run_due()

    assert calls == ["news", "news"]


def test_scheduler_isolates_task_exceptions_and_keeps_running_other_tasks():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    calls = []

    class Logger:
        def exception(self, *args, **kwargs):
            calls.append("logged")

    scheduler = TaskSchedulerRuntime(now_factory=clock.now, logger=Logger())

    def fail():
        calls.append("failed")
        raise RuntimeError("网络不可用")

    scheduler.register("digest", "每日摘要", 30, fail)
    scheduler.register("retry", "通知重试", 30, lambda: calls.append("retry") or {"ok": True, "status": "completed"})

    scheduler.run_due()
    status = scheduler.status()

    assert calls == ["failed", "logged", "retry"]
    assert [item["state"] for item in status["tasks"]] == ["error", "ok"]
    assert status["tasks"][0]["failure_count"] == 1
    assert status["summary"]["error"] == 1


def test_scheduler_treats_disabled_and_not_due_results_as_normal_checks():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    scheduler = TaskSchedulerRuntime(now_factory=clock.now)
    scheduler.register(
        "digest",
        "每日摘要",
        30,
        lambda: {"ok": False, "status": "not_due", "message": "当前无需发送每日摘要"},
    )
    scheduler.register(
        "retry",
        "通知重试",
        30,
        lambda: {"ok": False, "status": "disabled", "message": "自动重试未开启"},
    )

    scheduler.run_due()
    tasks = scheduler.status()["tasks"]

    assert tasks[0]["state"] == "idle"
    assert tasks[0]["failure_count"] == 0
    assert tasks[1]["state"] == "disabled"
    assert tasks[1]["failure_count"] == 0


def test_scheduler_records_duration_and_force_run():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))

    def run():
        clock.monotonic_value += 0.125
        return {"ok": True, "status": "completed", "message": "处理完成"}

    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        monotonic_factory=clock.monotonic,
    )
    scheduler.register("retry", "通知重试", 30, run, run_immediately=False)

    assert scheduler.run_due() == []
    result = scheduler.run_task("retry", force=True)

    assert result["ran"] is True
    assert result["task"]["last_duration_ms"] == 125
    assert result["task"]["last_message"] == "处理完成"


def test_application_notification_retry_task_result_is_user_readable():
    import app

    disabled = app._notification_retry_task_result({"ok": False, "status": "disabled"})
    completed = app._notification_retry_task_result({
        "ok": True,
        "status": "completed",
        "attempted_count": 0,
        "success_count": 0,
        "failure_count": 0,
    })
    failed = app._notification_retry_task_result({
        "ok": False,
        "status": "completed",
        "attempted_count": 2,
        "success_count": 1,
        "failure_count": 1,
    })

    assert disabled == {
        "state": "disabled",
        "result": "disabled",
        "message": "自动重试未开启",
    }
    assert completed["message"] == "本轮没有待重试通知"
    assert failed["state"] == "error"
    assert failed["message"] == "重试完成，1 项成功，1 项失败"


def test_background_task_status_socket_returns_scheduler_snapshot(monkeypatch):
    import app

    expected = {
        "updated_at": "2026-08-12T10:00:00",
        "summary": {"total": 3, "error": 0, "running": 0, "disabled": 1},
        "tasks": [{"name": "news", "label": "资讯刷新", "state": "ok"}],
    }
    monkeypatch.setattr(app, "get_background_task_status", lambda: expected)

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("get_background_task_status")
    received = client.get_received()

    payload = next(
        item["args"][0]
        for item in received
        if item["name"] == "background_task_status"
    )
    assert payload == expected
