import threading
from datetime import datetime
from types import SimpleNamespace


def _runtime(tmp_path, **overrides):
    from goldmonitor.daily_digest_runtime import DailyDigestRuntime

    state = SimpleNamespace(daily_digest_lock=threading.RLock())
    emitted = []
    sent = []
    options = {
        "state_path": lambda: str(tmp_path / "daily-digest.json"),
        "get_settings": lambda: {
            "daily_digest_enabled": True,
            "daily_digest_time": "20:00",
            "daily_digest_email_enabled": True,
            "daily_digest_webhook_enabled": False,
        },
        "build_timeline": lambda **kwargs: {
            "range": {},
            "summary": {"total": 0, "skipped": 0, "by_type": {}},
            "price_summary": {},
            "events": [],
            "request": kwargs,
        },
        "build_portfolio": lambda: {
            "rmb_summary": {"count": 0},
            "usd_summary": {"count": 0},
        },
        "get_source_health": lambda: {
            "quality": {"score": 100, "label": "数据可信", "reasons": []}
        },
        "email_sender": lambda digest, blocking=False: sent.append("email"),
        "webhook_sender": lambda digest, blocking=False: sent.append("webhook"),
        "emit": lambda event, payload: emitted.append((event, payload)),
        "timeline_max_limit": 2000,
        "timeline_types": ("alert", "news"),
        "now_factory": lambda: datetime(2026, 8, 11, 20, 5, 0),
    }
    options.update(overrides)
    runtime = DailyDigestRuntime(state, **options)
    return runtime, emitted, sent


def test_daily_digest_runtime_builds_snapshot_and_status(tmp_path):
    runtime, _emitted, _sent = _runtime(tmp_path)

    snapshot = runtime.build_snapshot()
    status = runtime.status_payload()

    assert snapshot["subject"] == "[GoldMonitor] 每日摘要 2026-08-11"
    assert status["enabled"] is True
    assert status["channels"] == ["email"]
    assert status["schedule"]["due"] is True


def test_daily_digest_runtime_records_scheduled_delivery(tmp_path):
    runtime, emitted, sent = _runtime(tmp_path)

    result = runtime.run_once(
        build_digest=lambda now: {
            "subject": "每日摘要",
            "message": "摘要内容",
            "payload": {},
        },
    )

    assert result["ok"] is True
    assert result["status"] == "sent"
    assert result["state"]["last_completed_at"] == "2026-08-11T20:05:00"
    assert sent == ["email"]
    assert emitted[-1][0] == "daily_digest_status"


def test_daily_digest_runtime_manual_run_does_not_complete_schedule(tmp_path):
    runtime, emitted, sent = _runtime(
        tmp_path,
        get_settings=lambda: {
            "daily_digest_enabled": False,
            "daily_digest_time": "20:00",
            "daily_digest_email_enabled": False,
            "daily_digest_webhook_enabled": True,
        },
    )

    result = runtime.run_once(
        force=True,
        manual=True,
        build_digest=lambda now: {
            "subject": "测试摘要",
            "message": "摘要内容",
            "payload": {},
        },
    )

    assert result["ok"] is True
    assert result["state"]["last_test_at"] == "2026-08-11T20:05:00"
    assert result["state"]["last_completed_at"] == ""
    assert sent == ["webhook"]
    assert emitted == []
