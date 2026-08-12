import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional


TASK_STATES = {"waiting", "running", "ok", "error", "disabled", "idle"}


@dataclass(frozen=True)
class ScheduledTask:
    name: str
    label: str
    interval_seconds: float
    runner: Callable[[], Any]
    result_handler: Optional[Callable[[Any], Dict[str, Any]]] = None


def normalize_task_result(result):
    if isinstance(result, bool):
        return {
            "state": "ok" if result else "error",
            "message": "任务执行完成" if result else "任务执行失败",
            "result": "completed" if result else "failed",
        }
    if not isinstance(result, dict):
        return {
            "state": "ok",
            "message": "任务执行完成",
            "result": "completed",
        }

    status = str(result.get("status") or "completed")
    message = str(result.get("message") or "").strip()
    if status == "disabled":
        state = "disabled"
    elif status in {"not_due", "running"}:
        state = "idle"
    elif result.get("ok") is False:
        state = "error"
    else:
        state = "ok"
    return {
        "state": state,
        "message": message or status,
        "result": status,
    }


class TaskSchedulerRuntime:
    def __init__(
        self,
        *,
        now_factory=datetime.now,
        monotonic_factory=time.monotonic,
        logger=logging,
    ):
        self.now_factory = now_factory
        self.monotonic_factory = monotonic_factory
        self.logger = logger
        self.lock = threading.RLock()
        self.tasks: Dict[str, ScheduledTask] = {}
        self.task_states: Dict[str, Dict[str, Any]] = {}

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
        task_name = str(name or "").strip()
        if not task_name:
            raise ValueError("后台任务名称不能为空")
        interval = float(interval_seconds)
        if interval <= 0:
            raise ValueError("后台任务周期必须大于 0")
        now = self.now_factory()
        task = ScheduledTask(
            name=task_name,
            label=str(label or task_name),
            interval_seconds=interval,
            runner=runner,
            result_handler=result_handler,
        )
        with self.lock:
            if task_name in self.tasks:
                raise ValueError(f"后台任务已注册: {task_name}")
            self.tasks[task_name] = task
            self.task_states[task_name] = {
                "name": task.name,
                "label": task.label,
                "interval_seconds": task.interval_seconds,
                "state": "waiting",
                "last_started_at": "",
                "last_completed_at": "",
                "last_success_at": "",
                "last_error_at": "",
                "last_message": "等待首次运行",
                "last_result": "waiting",
                "last_duration_ms": None,
                "next_run_at": (
                    now if run_immediately else now + timedelta(seconds=interval)
                ),
                "run_count": 0,
                "failure_count": 0,
            }
        return task

    def run_due(self, now=None):
        current = now or self.now_factory()
        with self.lock:
            due_names = [
                name
                for name, state in self.task_states.items()
                if state["state"] != "running" and state["next_run_at"] <= current
            ]
        return [self.run_task(name, now=current) for name in due_names]

    def run_task(self, name, *, now=None, force=False):
        started_at = now or self.now_factory()
        with self.lock:
            task = self.tasks.get(name)
            if task is None:
                raise KeyError(f"未注册的后台任务: {name}")
            state = self.task_states[name]
            if state["state"] == "running":
                return {"ran": False, "reason": "running", "task": self._public_state(state)}
            if not force and state["next_run_at"] > started_at:
                return {"ran": False, "reason": "not_due", "task": self._public_state(state)}
            state["state"] = "running"
            state["last_started_at"] = started_at
            state["last_message"] = "正在运行"

        monotonic_started = self.monotonic_factory()
        try:
            result = task.runner()
            handler = task.result_handler or normalize_task_result
            outcome = dict(handler(result) or {})
            outcome_state = str(outcome.get("state") or "ok")
            if outcome_state not in TASK_STATES - {"waiting", "running"}:
                raise ValueError(f"无效的后台任务状态: {outcome_state}")
            message = str(outcome.get("message") or "任务执行完成")
            result_name = str(outcome.get("result") or outcome_state)
        except Exception as exc:
            self.logger.exception("后台任务执行失败: %s", task.label)
            outcome_state = "error"
            message = str(exc) or "任务执行失败"
            result_name = "exception"

        completed_at = self.now_factory()
        duration_ms = max(0, round((self.monotonic_factory() - monotonic_started) * 1000))
        with self.lock:
            state = self.task_states[name]
            state["state"] = outcome_state
            state["last_completed_at"] = completed_at
            state["last_message"] = message
            state["last_result"] = result_name
            state["last_duration_ms"] = duration_ms
            state["next_run_at"] = completed_at + timedelta(seconds=task.interval_seconds)
            state["run_count"] += 1
            if outcome_state == "error":
                state["last_error_at"] = completed_at
                state["failure_count"] += 1
            else:
                state["last_success_at"] = completed_at
            public_state = self._public_state(state)
        return {"ran": True, "task": public_state}

    def status(self, now=None):
        current = now or self.now_factory()
        with self.lock:
            tasks = [self._public_state(state) for state in self.task_states.values()]
        return {
            "updated_at": current.isoformat(timespec="seconds"),
            "summary": {
                "total": len(tasks),
                "running": sum(item["state"] == "running" for item in tasks),
                "error": sum(item["state"] == "error" for item in tasks),
                "disabled": sum(item["state"] == "disabled" for item in tasks),
                "waiting": sum(item["state"] == "waiting" for item in tasks),
            },
            "tasks": tasks,
        }

    def run_loop(self, *, sleep=time.sleep, tick_interval=30):
        interval = float(tick_interval)
        if interval <= 0:
            raise ValueError("调度检查周期必须大于 0")
        while True:
            try:
                self.run_due()
            except Exception:
                self.logger.exception("后台任务调度检查失败")
            sleep(interval)

    @staticmethod
    def _public_state(state):
        payload = dict(state)
        for key in (
            "last_started_at",
            "last_completed_at",
            "last_success_at",
            "last_error_at",
            "next_run_at",
        ):
            value = payload.get(key)
            payload[key] = value.isoformat(timespec="seconds") if value else ""
        interval = payload.get("interval_seconds")
        if isinstance(interval, float) and interval.is_integer():
            payload["interval_seconds"] = int(interval)
        return payload
