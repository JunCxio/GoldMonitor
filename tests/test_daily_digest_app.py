from datetime import datetime

import pytest


def digest_settings(**updates):
    import app

    settings = dict(app.DEFAULT_SETTINGS)
    settings.update({
        "daily_digest_enabled": True,
        "daily_digest_time": "20:00",
        "daily_digest_email_enabled": True,
        "daily_digest_webhook_enabled": False,
    })
    settings.update(updates)
    return settings


def configure_digest_app(monkeypatch, tmp_path, settings=None):
    import app

    monkeypatch.setattr(app, "DAILY_DIGEST_STATE_PATH", str(tmp_path / "daily_digest_state.json"))
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: dict(settings or digest_settings()))
    monkeypatch.setattr(
        app,
        "build_event_timeline_state",
        lambda minutes=None, limit=None, types=None: {
            "range": {"start": "2026-07-12T20:00:00", "end": "2026-07-13T20:00:00", "minutes": 1440},
            "summary": {"total": 1, "skipped": 0, "by_type": {"alert": 1}},
            "price_summary": {
                "rmb": {"points": 2, "start": 550, "end": 552, "high": 553, "low": 549, "change": 2, "change_pct": 0.36},
                "usd": {"points": 2, "start": 2380, "end": 2390, "high": 2395, "low": 2375, "change": 10, "change_pct": 0.42},
            },
            "events": [],
        },
    )
    monkeypatch.setattr(
        app,
        "build_portfolio_state",
        lambda: {"rmb_summary": {"count": 0}, "usd_summary": {"count": 0}},
    )
    monkeypatch.setattr(
        app,
        "get_source_health_state",
        lambda: {"quality": {"score": 100, "label": "数据可信", "reasons": []}},
    )
    return app


def test_scheduled_digest_sends_selected_channels_once_per_local_day(monkeypatch, tmp_path):
    app = configure_digest_app(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(app.DailyDigestEmailNotifier, "send", lambda digest, blocking=False: sent.append("email"))
    monkeypatch.setattr(app.DailyDigestWebhookNotifier, "send", lambda digest, blocking=False: sent.append("webhook"))

    first = app.run_daily_digest_once(now=datetime(2026, 7, 13, 20, 5), blocking=True)
    second = app.run_daily_digest_once(now=datetime(2026, 7, 13, 21, 0), blocking=True)

    assert first["ok"] is True
    assert first["status"] == "queued"
    assert first["state"]["last_completed_at"] == "2026-07-13T20:05:00"
    assert sent == ["email"]
    assert second["ok"] is False
    assert second["reason"] == "already_completed"
    assert sent == ["email"]


def test_manual_digest_test_does_not_consume_scheduled_delivery(monkeypatch, tmp_path):
    settings = digest_settings(daily_digest_enabled=False)
    app = configure_digest_app(monkeypatch, tmp_path, settings=settings)
    sent = []
    monkeypatch.setattr(app.DailyDigestEmailNotifier, "send", lambda digest, blocking=False: sent.append("email"))
    monkeypatch.setattr(app.DailyDigestWebhookNotifier, "send", lambda digest, blocking=False: sent.append("webhook"))

    result = app.run_daily_digest_once(
        now=datetime(2026, 7, 13, 9, 0),
        force=True,
        manual=True,
        blocking=True,
    )

    assert result["ok"] is True
    assert sent == ["email"]
    assert result["state"]["last_test_at"] == "2026-07-13T09:00:00"
    assert result["state"]["last_completed_at"] == ""


def test_scheduled_digest_without_channels_completes_day_without_retry(monkeypatch, tmp_path):
    settings = digest_settings(
        daily_digest_email_enabled=False,
        daily_digest_webhook_enabled=False,
    )
    app = configure_digest_app(monkeypatch, tmp_path, settings=settings)

    first = app.run_daily_digest_once(now=datetime(2026, 7, 13, 20, 5), blocking=True)
    second = app.run_daily_digest_once(now=datetime(2026, 7, 13, 20, 6), blocking=True)

    assert first["ok"] is False
    assert first["status"] == "skipped"
    assert first["state"]["last_completed_at"] == "2026-07-13T20:05:00"
    assert second["status"] == "not_due"
    assert second["reason"] == "already_completed"


def test_scheduled_digest_with_invalid_email_config_completes_day_without_retry(monkeypatch, tmp_path):
    app = configure_digest_app(monkeypatch, tmp_path)
    sent = []

    def reject_email(digest, blocking=False):
        sent.append("email")
        return "SMTP 配置不完整"

    monkeypatch.setattr(app.DailyDigestEmailNotifier, "send", reject_email)

    first = app.run_daily_digest_once(now=datetime(2026, 7, 13, 20, 5), blocking=True)
    second = app.run_daily_digest_once(now=datetime(2026, 7, 13, 20, 6), blocking=True)

    assert first["ok"] is False
    assert first["state"]["last_completed_at"] == "2026-07-13T20:05:00"
    assert first["state"]["last_sent_at"] == ""
    assert sent == ["email"]
    assert second["status"] == "not_due"
    assert second["reason"] == "already_completed"


def test_daily_digest_preview_socket_returns_content_without_sending(monkeypatch, tmp_path):
    app = configure_digest_app(monkeypatch, tmp_path)
    sent = []
    monkeypatch.setattr(app.DailyDigestEmailNotifier, "send", lambda digest, blocking=False: sent.append("email"))
    monkeypatch.setattr(app.DailyDigestWebhookNotifier, "send", lambda digest, blocking=False: sent.append("webhook"))

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("preview_daily_digest")
    received = client.get_received()

    payload = next(item["args"][0] for item in received if item["name"] == "daily_digest_previewed")
    assert payload["ok"] is True
    assert payload["subject"].startswith("[GoldMonitor] 每日摘要")
    assert "价格变化" in payload["message"]
    assert sent == []


def test_socket_connect_includes_daily_digest_status(monkeypatch, tmp_path):
    app = configure_digest_app(monkeypatch, tmp_path)
    expected = {"enabled": True, "time": "20:00", "state": {"last_status": "idle"}}
    monkeypatch.setattr(app, "daily_digest_status_payload", lambda now=None: expected)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    received = client.get_received()

    init_state = next(item["args"][0] for item in received if item["name"] == "init_state")
    assert init_state["daily_digest_status"] == expected


def test_manual_digest_socket_sends_result_and_updated_status(monkeypatch, tmp_path):
    app = configure_digest_app(monkeypatch, tmp_path)
    calls = []
    run_daily_digest_once = app.run_daily_digest_once
    monkeypatch.setattr(app.DailyDigestEmailNotifier, "send", lambda digest, blocking=False: None)

    def tracked_run_daily_digest_once(**kwargs):
        calls.append(kwargs)
        return run_daily_digest_once(now=datetime(2026, 7, 13, 9, 0), **kwargs)

    class ImmediateThread:
        def __init__(self, target, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            self.target()

    monkeypatch.setattr(app, "run_daily_digest_once", tracked_run_daily_digest_once)
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    other_client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    other_client.get_received()
    client.emit("test_daily_digest")
    received = client.get_received()
    other_received = other_client.get_received()

    assert calls == [{"force": True, "manual": True, "blocking": True}]
    test_result = next(item["args"][0] for item in received if item["name"] == "daily_digest_test_result")
    updated_status = next(item["args"][0] for item in received if item["name"] == "daily_digest_status")
    assert test_result["ok"] is True
    assert test_result["state"]["last_test_at"] == "2026-07-13T09:00:00"
    assert test_result["state"]["last_completed_at"] == ""
    assert updated_status["state"]["last_completed_at"] == ""
    assert not any(item["name"] == "daily_digest_test_result" for item in other_received)


def test_daily_digest_loop_runs_once_before_waiting(monkeypatch):
    import app

    calls = []
    monkeypatch.setattr(app, "run_daily_digest_once", lambda: calls.append("run"))

    def stop_after_first_iteration(seconds):
        assert seconds == 30
        raise StopIteration

    monkeypatch.setattr(app.time, "sleep", stop_after_first_iteration)

    with pytest.raises(StopIteration):
        app.daily_digest_loop()

    assert calls == ["run"]


def test_daily_digest_scheduler_starts_only_once(monkeypatch):
    import app

    created = []

    class CapturedThread:
        def __init__(self, target, daemon=False):
            created.append({"target": target, "daemon": daemon, "started": False})
            self.item = created[-1]

        def start(self):
            self.item["started"] = True

    monkeypatch.setattr(app, "_daily_digest_scheduler_started", False)
    monkeypatch.setattr(app.threading, "Thread", CapturedThread)

    app.start_daily_digest_scheduler()
    app.start_daily_digest_scheduler()

    assert created == [{"target": app.daily_digest_loop, "daemon": True, "started": True}]
