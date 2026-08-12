import logging
import threading
from datetime import datetime

from goldmonitor import notification_retry as notification_retry_core


class NotificationRetryRuntime:
    def __init__(
        self,
        *,
        get_settings,
        get_entries,
        resend,
        emit,
        now_factory=datetime.now,
        lock=None,
        logger=logging,
    ):
        self.get_settings = get_settings
        self.get_entries = get_entries
        self.resend = resend
        self.emit = emit
        self.now_factory = now_factory
        self.lock = lock or threading.Lock()
        self.logger = logger

    def status(self, now=None, force_due=False):
        settings = dict(self.get_settings() or {})
        return notification_retry_core.build_notification_retry_status(
            self.get_entries(),
            enabled=bool(settings.get("notification_auto_retry_enabled", False)),
            now=now or self.now_factory(),
            force_due=force_due,
        )

    def run_once(self, *, manual=False):
        if not self.lock.acquire(blocking=False):
            return {"ok": False, "status": "running", "message": "通知重试任务正在运行"}
        try:
            now = self.now_factory()
            status = self.status(now=now, force_due=manual)
            if not manual and not status.get("enabled"):
                return {"ok": False, "status": "disabled", **status}
            attempts = []
            for candidate in status.get("candidates", []):
                alert_id = candidate.get("id")
                if not alert_id:
                    continue
                try:
                    ok, entry = self.resend(
                        alert_id,
                        blocking=True,
                        automatic=not manual,
                    )
                except Exception:
                    self.logger.exception("重试告警通知失败")
                    ok, entry = False, None
                channel_results = notification_retry_core.retry_channel_results(
                    entry,
                    candidate.get("channels"),
                )
                delivered = bool(channel_results) and all(
                    item["ok"] for item in channel_results
                )
                attempts.append({
                    "id": alert_id,
                    "ok": bool(ok and delivered),
                    "persisted": bool(ok),
                    "channels": channel_results,
                    "entry": entry if isinstance(entry, dict) else None,
                })
            refreshed = self.status(now=self.now_factory())
            result = {
                "ok": all(item["ok"] for item in attempts) if attempts else True,
                "status": "completed",
                "manual": bool(manual),
                "attempted_count": len(attempts),
                "success_count": sum(1 for item in attempts if item["ok"]),
                "failure_count": sum(1 for item in attempts if not item["ok"]),
                "attempts": attempts,
                **refreshed,
            }
            if not manual:
                self.emit("notification_retry_status", result)
            return result
        finally:
            self.lock.release()
