import threading
import time
from datetime import datetime, timedelta

import pytest


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
    assert status["summary"]["delayed"] == 0
    assert status["tasks"][0]["last_duration_ms"] is None
    assert status["tasks"][0]["schedule_delayed"] is False


def test_scheduler_reports_task_after_schedule_delay_grace_period():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        schedule_delay_grace_seconds=60,
    )
    scheduler.register(
        "news",
        "资讯刷新",
        900,
        lambda: True,
        run_immediately=False,
    )

    clock.advance(960)
    within_grace = scheduler.status()
    clock.advance(1)
    delayed = scheduler.status()

    assert within_grace["summary"]["delayed"] == 0
    assert within_grace["tasks"][0]["schedule_delay_seconds"] == 60
    assert delayed["summary"]["delayed"] == 1
    assert delayed["tasks"][0]["schedule_delayed"] is True
    assert delayed["tasks"][0]["schedule_delay_seconds"] == 61
    assert delayed["schedule_delay_grace_seconds"] == 60


def test_scheduler_clears_schedule_delay_after_manual_check():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        schedule_delay_grace_seconds=60,
    )
    scheduler.register(
        "news",
        "资讯刷新",
        900,
        lambda: True,
        run_immediately=False,
    )
    clock.advance(961)
    assert scheduler.status()["tasks"][0]["schedule_delayed"] is True

    scheduler.run_task("news", force=True)
    status = scheduler.status()

    assert status["summary"]["delayed"] == 0
    assert status["tasks"][0]["schedule_delayed"] is False
    assert status["tasks"][0]["schedule_delay_seconds"] == 0


def test_scheduler_does_not_report_running_task_as_delayed():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    started = threading.Event()
    release = threading.Event()

    def run():
        started.set()
        assert release.wait(timeout=2)
        return True

    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        schedule_delay_grace_seconds=60,
    )
    scheduler.register("news", "资讯刷新", 900, run)
    worker = threading.Thread(target=lambda: scheduler.run_task("news"))
    worker.start()
    assert started.wait(timeout=2)
    clock.advance(120)

    status = scheduler.status()
    release.set()
    worker.join(timeout=2)

    assert status["summary"]["delayed"] == 0
    assert status["tasks"][0]["state"] == "running"
    assert status["tasks"][0]["schedule_delayed"] is False
    assert status["tasks"][0]["schedule_delay_seconds"] == 0


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


def test_scheduler_notifies_once_at_failure_threshold_and_once_after_recovery():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    events = []
    results = [False, False, False, False, True]
    scheduler = TaskSchedulerRuntime(
        now_factory=clock.now,
        failure_alert_threshold=3,
        event_handler=events.append,
    )
    scheduler.register("news", "资讯刷新", 30, lambda: results.pop(0))

    for _ in range(5):
        scheduler.run_due()
        clock.advance(30)

    notable = [event for event in events if event["type"] != "completed"]
    assert [event["type"] for event in notable] == [
        "failure_threshold",
        "recovered",
    ]
    assert notable[0]["task"]["consecutive_failures"] == 3
    assert notable[0]["task"]["attention_required"] is True
    assert notable[1]["task"]["consecutive_failures"] == 0
    assert notable[1]["task"]["attention_required"] is False
    assert scheduler.status()["summary"]["attention"] == 0


def test_task_event_notification_builds_failure_and_recovery_copy():
    from goldmonitor.task_scheduler import build_task_event_notification

    failure = build_task_event_notification({
        "type": "failure_threshold",
        "task": {
            "label": "资讯刷新",
            "consecutive_failures": 3,
            "last_message": "资讯刷新失败",
        },
    })
    recovered = build_task_event_notification({
        "type": "recovered",
        "task": {"label": "资讯刷新"},
    })

    assert failure == {
        "title": "后台任务需要处理",
        "body": "资讯刷新已连续失败 3 次。最近结果：资讯刷新失败",
    }
    assert recovered == {
        "title": "后台任务已恢复",
        "body": "资讯刷新已恢复正常运行。",
    }
    assert build_task_event_notification({"type": "completed"}) is None


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


def test_scheduler_rejects_overlapping_manual_runs():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    started = threading.Event()
    release = threading.Event()
    first_result = []

    def run():
        started.set()
        assert release.wait(timeout=2)
        return True

    scheduler = TaskSchedulerRuntime(now_factory=clock.now)
    scheduler.register("news", "资讯刷新", 900, run, run_immediately=False)
    worker = threading.Thread(
        target=lambda: first_result.append(
            scheduler.run_task("news", force=True)
        ),
    )
    worker.start()
    assert started.wait(timeout=2)

    duplicate = scheduler.run_task("news", force=True)
    release.set()
    worker.join(timeout=2)

    assert duplicate["ran"] is False
    assert duplicate["reason"] == "running"
    assert duplicate["task"]["state"] == "running"
    assert first_result[0]["ran"] is True
    assert scheduler.status()["tasks"][0]["run_count"] == 1


def test_manual_task_failure_updates_failure_state_and_next_schedule():
    from goldmonitor.task_scheduler import TaskSchedulerRuntime

    clock = Clock(datetime(2026, 8, 12, 10, 0, 0))
    scheduler = TaskSchedulerRuntime(now_factory=clock.now)
    scheduler.register(
        "news",
        "资讯刷新",
        900,
        lambda: False,
        run_immediately=False,
    )

    result = scheduler.run_task("news", force=True)

    assert result["task"]["state"] == "error"
    assert result["task"]["consecutive_failures"] == 1
    assert result["task"]["next_run_at"] == "2026-08-12T10:15:00"


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


def test_application_price_history_health_task_result_is_user_readable():
    import app

    healthy = app._price_history_health_task_result({
        "ok": True,
        "status": "healthy",
        "issues": [],
    })
    empty = app._price_history_health_task_result({
        "ok": True,
        "status": "empty",
        "issues": [],
    })
    attention = app._price_history_health_task_result({
        "ok": True,
        "status": "attention",
        "issues": ["汇总记录缺失", "JSON 中存在可补时间点"],
    })
    unavailable = app._price_history_health_task_result({
        "ok": False,
        "status": "unavailable",
        "issues": ["历史数据库完整性检查未通过"],
    })

    assert healthy == {
        "state": "ok",
        "result": "healthy",
        "message": "历史数据状态正常",
    }
    assert empty == {
        "state": "idle",
        "result": "empty",
        "message": "尚无历史数据，本轮无需检查",
    }
    assert attention == {
        "state": "error",
        "result": "attention",
        "message": "发现 2 项历史数据问题，请在历史数据维护中查看",
    }
    assert unavailable == {
        "state": "error",
        "result": "unavailable",
        "message": "历史数据库暂不可检查，请在历史数据维护中查看",
    }


def test_application_scheduler_registers_price_history_health_check(monkeypatch):
    import app

    registrations = []

    class Scheduler:
        def register(
            self,
            name,
            label,
            interval_seconds,
            runner,
            *,
            result_handler=None,
            run_immediately=True,
        ):
            registrations.append({
                "name": name,
                "label": label,
                "interval_seconds": interval_seconds,
                "runner": runner,
                "result_handler": result_handler,
                "run_immediately": run_immediately,
            })

    scheduler = Scheduler()
    monkeypatch.setattr(app.runtime, "task_scheduler_runtime_instance", None)
    monkeypatch.setattr(
        app.task_scheduler_core,
        "TaskSchedulerRuntime",
        lambda **_kwargs: scheduler,
    )
    monkeypatch.setattr(
        app,
        "diagnose_price_history_maintenance",
        lambda: {"ok": True, "status": "healthy", "issues": []},
    )

    assert app._get_task_scheduler_runtime() is scheduler
    history_task = next(
        item for item in registrations if item["name"] == "price_history_health"
    )

    assert history_task["label"] == "历史数据检查"
    assert history_task["interval_seconds"] == 6 * 60 * 60
    assert history_task["run_immediately"] is True
    assert history_task["runner"]() == {
        "ok": True,
        "status": "healthy",
        "issues": [],
    }
    assert history_task["result_handler"] is app._price_history_health_task_result


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


def test_application_background_task_status_includes_sanitized_retry_queue(monkeypatch):
    import app

    scheduler_status = {
        "summary": {
            "total": 3,
            "error": 0,
            "running": 0,
            "disabled": 1,
            "delayed": 0,
        },
        "tasks": [
            {"name": "news", "state": "ok"},
            {"name": "notification_retry", "state": "disabled"},
        ],
    }
    retry_status = {
        "enabled": False,
        "pending_count": 2,
        "eligible_count": 1,
        "exhausted_count": 1,
        "expired_count": 2,
        "non_retryable_count": 3,
        "next_retry_at": "2026-08-12T12:10:00",
        "interval_minutes": 10,
        "window_hours": 24,
        "max_rounds": 3,
        "candidates": [{"id": "private-alert-id"}],
    }

    class Scheduler:
        def status(self):
            return scheduler_status

    monkeypatch.setattr(app, "_get_task_scheduler_runtime", lambda: Scheduler())
    monkeypatch.setattr(app, "notification_retry_status", lambda: retry_status)

    result = app.get_background_task_status()
    queue = result["tasks"][1]["queue"]

    assert queue["available"] is True
    assert queue["stopped_count"] == 6
    assert queue["attention_required"] is True
    assert "candidates" not in queue
    assert result["summary"]["queue_attention"] == 1
    assert result["summary"]["queue_stopped"] == 6


def test_application_background_task_status_handles_retry_queue_failure(monkeypatch):
    import app

    class Scheduler:
        def status(self):
            return {
                "summary": {"total": 1},
                "tasks": [{"name": "notification_retry", "state": "idle"}],
            }

    monkeypatch.setattr(app, "_get_task_scheduler_runtime", lambda: Scheduler())
    monkeypatch.setattr(
        app,
        "notification_retry_status",
        lambda: (_ for _ in ()).throw(RuntimeError("数据库不可用")),
    )

    result = app.get_background_task_status()
    queue = result["tasks"][0]["queue"]

    assert queue["available"] is False
    assert queue["attention_required"] is True
    assert result["summary"]["queue_attention"] == 1


def test_application_manual_background_task_uses_allowlist(monkeypatch):
    import app

    calls = []

    class Scheduler:
        def run_task(self, name, *, force=False):
            calls.append((name, force))
            return {"ran": True, "task": {"name": name, "state": "ok"}}

    monkeypatch.setattr(app, "_get_task_scheduler_runtime", lambda: Scheduler())

    result = app.run_background_task_now("daily_digest")
    history_result = app.run_background_task_now("price_history_health")

    assert result["ran"] is True
    assert history_result["ran"] is True
    assert calls == [
        ("daily_digest", True),
        ("price_history_health", True),
    ]
    with pytest.raises(ValueError, match="不支持的后台任务"):
        app.run_background_task_now("unknown")


def test_background_task_run_socket_returns_pending_result_and_status(monkeypatch):
    import app

    task = {
        "name": "daily_digest",
        "label": "每日摘要",
        "state": "disabled",
        "last_message": "每日摘要未启用",
    }
    expected_status = {
        "summary": {"total": 3, "error": 0, "running": 0, "disabled": 1},
        "tasks": [task],
    }
    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda name: {"ran": True, "task": task},
    )
    monkeypatch.setattr(app, "get_background_task_status", lambda: expected_status)

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("run_background_task", {"name": "daily_digest"})
    received = []
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        received.extend(client.get_received())
        names = [item["name"] for item in received]
        if "background_task_status" in names and names.count("background_task_run_result") >= 2:
            break
        time.sleep(0.01)

    results = [
        item["args"][0]
        for item in received
        if item["name"] == "background_task_run_result"
    ]
    assert results[0] == {
        "ok": None,
        "pending": True,
        "name": "daily_digest",
        "message": "正在检查后台任务...",
    }
    assert results[-1]["ok"] is True
    assert results[-1]["task"] == task
    assert results[-1]["message"] == "每日摘要未启用"
    status = next(
        item["args"][0]
        for item in received
        if item["name"] == "background_task_status"
    )
    assert status == expected_status


def test_background_task_run_socket_rejects_unknown_task(monkeypatch):
    import app

    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda name: (_ for _ in ()).throw(ValueError("不支持的后台任务")),
    )

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("run_background_task", {"name": "unknown"})
    received = []
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        received.extend(client.get_received())
        results = [
            item["args"][0]
            for item in received
            if item["name"] == "background_task_run_result"
        ]
        if len(results) >= 2:
            break
        time.sleep(0.01)

    assert results[-1] == {
        "ok": False,
        "name": "unknown",
        "message": "不支持的后台任务。",
    }


def test_background_task_run_socket_reports_running_task(monkeypatch):
    import app

    running_task = {
        "name": "news",
        "label": "资讯刷新",
        "state": "running",
        "last_message": "正在运行",
    }
    monkeypatch.setattr(
        app,
        "run_background_task_now",
        lambda name: {
            "ran": False,
            "reason": "running",
            "task": running_task,
        },
    )

    client = app.socketio.test_client(
        app.app,
        auth={"token": app.SOCKET_ACCESS_TOKEN},
    )
    client.get_received()
    client.emit("run_background_task", {"name": "news"})
    received = []
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        received.extend(client.get_received())
        results = [
            item["args"][0]
            for item in received
            if item["name"] == "background_task_run_result"
        ]
        if len(results) >= 2:
            break
        time.sleep(0.01)

    assert results[-1] == {
        "ok": False,
        "name": "news",
        "reason": "running",
        "task": running_task,
        "message": "该任务正在运行，请稍后再试。",
    }


def test_application_task_event_sends_desktop_notification_and_broadcasts(monkeypatch):
    import app

    notifications = []
    broadcasts = []
    expected_status = {"summary": {"attention": 1}, "tasks": []}
    monkeypatch.setattr(
        app,
        "send_desktop_notification",
        lambda title, body: notifications.append((title, body)),
    )
    monkeypatch.setattr(
        app,
        "_get_task_scheduler_runtime",
        lambda: type("Scheduler", (), {"status": lambda self: expected_status})(),
    )
    monkeypatch.setattr(
        app.socketio,
        "emit",
        lambda event, payload: broadcasts.append((event, payload)),
    )

    app._handle_background_task_event({
        "type": "failure_threshold",
        "task": {
            "label": "资讯刷新",
            "consecutive_failures": 3,
            "last_message": "网络不可用",
        },
    })

    assert notifications == [(
        "后台任务需要处理",
        "资讯刷新已连续失败 3 次。最近结果：网络不可用",
    )]
    assert broadcasts == [("background_task_status", expected_status)]
