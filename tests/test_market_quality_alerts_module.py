import json
from datetime import datetime, timedelta, timezone


def observation(level="stale", reasons=None):
    abnormal = level != "normal"
    return {
        "source": "测试金价源",
        "rate_source": "测试汇率源",
        "source_at": "2026-08-26T00:00:00Z",
        "rate_source_at": "2026-08-26T00:00:00Z",
        "received_at": "2026-08-26T00:00:00Z",
        "quality_score": 40 if abnormal else 100,
        "quality_level": level,
        "usable_for_history": not abnormal,
        "usable_for_alert": not abnormal,
        "usable_for_automation": not abnormal,
        "blocked_reasons": list(reasons or (["金价来自缓存"] if abnormal else [])),
    }


def settings(**overrides):
    result = {
        "market_quality_alert_enabled": True,
        "market_quality_alert_threshold_minutes": 5,
        "market_quality_alert_local_enabled": True,
        "market_quality_alert_email_enabled": False,
        "market_quality_alert_webhook_enabled": False,
        "market_quality_recovery_enabled": True,
    }
    result.update(overrides)
    return result


def test_quality_alert_waits_for_threshold_and_notifies_once():
    from goldmonitor.market_quality_alerts import (
        empty_market_quality_alert_state,
        evaluate_market_quality_alert,
    )

    started = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    state = empty_market_quality_alert_state()
    first = evaluate_market_quality_alert(
        state,
        observation(),
        settings(),
        observed_at=started,
        session_id="session-a",
        segment_id="segment-a",
    )
    assert first["event"] is None
    before = evaluate_market_quality_alert(
        first["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(minutes=4, seconds=59),
        session_id="session-a",
        segment_id="segment-a",
    )
    assert before["event"] is None
    triggered = evaluate_market_quality_alert(
        before["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(minutes=5),
        session_id="session-a",
        segment_id="segment-a",
    )
    assert triggered["event"]["kind"] == "incident"
    assert triggered["event"]["duration_seconds"] == 300
    repeated = evaluate_market_quality_alert(
        triggered["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(minutes=8),
        session_id="session-a",
        segment_id="segment-a",
    )
    assert repeated["event"] is None
    assert repeated["state"]["notified_at"] == triggered["state"]["notified_at"]


def test_quality_alert_continues_across_sessions_without_counting_downtime():
    from goldmonitor.market_quality_alerts import (
        empty_market_quality_alert_state,
        evaluate_market_quality_alert,
    )

    started = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    first = evaluate_market_quality_alert(
        empty_market_quality_alert_state(),
        observation(),
        settings(),
        observed_at=started,
        session_id="session-a",
        segment_id="segment-a",
    )
    progressed = evaluate_market_quality_alert(
        first["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(minutes=2),
        session_id="session-a",
        segment_id="segment-a",
    )
    restarted = evaluate_market_quality_alert(
        progressed["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(hours=3),
        session_id="session-b",
        segment_id="segment-b",
    )
    assert restarted["state"]["accumulated_seconds"] == 120
    assert restarted["event"] is None
    triggered = evaluate_market_quality_alert(
        restarted["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(hours=3, minutes=3),
        session_id="session-b",
        segment_id="segment-b",
    )
    assert triggered["event"]["duration_seconds"] == 300
    assert triggered["event"]["segment_id"] == "segment-b"


def test_quality_alert_recovery_only_follows_notified_incident():
    from goldmonitor.market_quality_alerts import (
        empty_market_quality_alert_state,
        evaluate_market_quality_alert,
    )

    started = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    short = evaluate_market_quality_alert(
        empty_market_quality_alert_state(),
        observation(),
        settings(),
        observed_at=started,
        session_id="session-a",
        segment_id="segment-a",
    )
    recovered_short = evaluate_market_quality_alert(
        short["state"],
        observation("normal"),
        settings(),
        observed_at=started + timedelta(minutes=1),
        session_id="session-a",
        segment_id="segment-normal",
    )
    assert recovered_short["event"] is None

    notified = evaluate_market_quality_alert(
        short["state"],
        observation(),
        settings(),
        observed_at=started + timedelta(minutes=5),
        session_id="session-a",
        segment_id="segment-a",
    )
    recovery = evaluate_market_quality_alert(
        notified["state"],
        observation("normal"),
        settings(),
        observed_at=started + timedelta(minutes=6),
        session_id="session-a",
        segment_id="segment-normal",
    )
    assert recovery["event"]["kind"] == "recovery"
    assert recovery["event"]["segment_id"] == "segment-a"
    assert recovery["state"]["incident_active"] is False
    assert recovery["state"]["last_incident_duration_seconds"] == 300


def test_quality_alert_recovery_closes_incident_when_recovery_notice_is_disabled():
    from goldmonitor.market_quality_alerts import (
        empty_market_quality_alert_state,
        evaluate_market_quality_alert,
    )

    started = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    first = evaluate_market_quality_alert(
        empty_market_quality_alert_state(),
        observation(),
        settings(market_quality_recovery_enabled=False),
        observed_at=started,
        session_id="session-a",
        segment_id="segment-a",
    )
    notified = evaluate_market_quality_alert(
        first["state"],
        observation(),
        settings(market_quality_recovery_enabled=False),
        observed_at=started + timedelta(minutes=5),
        session_id="session-a",
        segment_id="segment-a",
    )
    notified["state"]["notification_alert_id"] = "alert-quality-1"

    recovery = evaluate_market_quality_alert(
        notified["state"],
        observation("normal"),
        settings(market_quality_recovery_enabled=False),
        observed_at=started + timedelta(minutes=6),
        session_id="session-a",
        segment_id="segment-normal",
    )

    assert recovery["event"] is None
    assert recovery["recovered_alert_id"] == "alert-quality-1"
    assert recovery["state"]["incident_active"] is False


def test_quality_alert_entry_uses_selected_channels_and_recovery_is_handled():
    from goldmonitor.market_quality_alerts import build_market_quality_alert_entry

    event = {
        "kind": "incident",
        "occurred_at": "2026-08-26T08:05:00Z",
        "incident_id": "incident-1",
        "first_seen_at": "2026-08-26T08:00:00Z",
        "duration_seconds": 300,
        "segment_id": "segment-a",
        "abnormal_observation": observation(
            "stale",
            ["金价来自缓存", "汇率来自缓存"],
        ),
        "current_observation": observation("stale"),
    }
    entry = build_market_quality_alert_entry(
        event,
        settings(
            market_quality_alert_email_enabled=True,
            market_quality_alert_webhook_enabled=True,
        ),
    )
    assert entry["type"] == "quality"
    assert entry["mode"] == "quality"
    assert entry["delivery_channels"] == ["local", "email", "webhook"]
    assert entry["market_quality_segment_id"] == "segment-a"
    assert "历史入库、预警判断、定投执行" in entry["message"]

    recovery = build_market_quality_alert_entry(
        {**event, "kind": "recovery", "current_observation": observation("normal")},
        settings(),
    )
    assert recovery["type"] == "recovery"
    assert recovery["handled"] is True
    assert recovery["handling_note"] == "行情质量已自动恢复"


def test_quality_alert_store_round_trip_and_rejects_future_schema(tmp_path):
    from goldmonitor.market_quality_alerts import (
        MarketQualityAlertStateStore,
        empty_market_quality_alert_state,
    )

    path = tmp_path / "market_quality_alert_state.json"
    store = MarketQualityAlertStateStore(
        path,
        now_factory=lambda: datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc),
    )
    state = empty_market_quality_alert_state()
    state.update({
        "incident_active": True,
        "incident_id": "incident-1",
        "first_seen_at": "2026-08-26T08:00:00Z",
        "accumulated_seconds": 120,
        "last_observed_at": "2026-08-26T08:02:00Z",
        "last_session_id": "session-a",
    })
    saved = store.save(state)
    assert store.load() == saved
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1

    payload["schema_version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert store.load() == empty_market_quality_alert_state()


def test_application_quality_recovery_closes_original_alert_without_recovery_notice(
    monkeypatch,
):
    import app

    current_settings = settings(market_quality_recovery_enabled=False)
    emitted_alerts = []
    handling_updates = []
    socket_events = []

    class Store:
        def save(self, state):
            return dict(state)

    class NotificationRuntime:
        def emit_alert(self, entry, title):
            emitted_alerts.append((dict(entry), title))

    monkeypatch.setattr(app, "get_settings_snapshot", lambda: dict(current_settings))
    monkeypatch.setattr(app, "_market_quality_alert_state_store", Store)
    monkeypatch.setattr(
        app,
        "_get_alert_notification_runtime",
        lambda: NotificationRuntime(),
    )
    monkeypatch.setattr(app, "_generate_alert_log_id", lambda: "quality-alert-1")
    monkeypatch.setattr(
        app,
        "update_alert_log_handling",
        lambda alert_id, handled=None, note=None: (
            handling_updates.append((alert_id, handled, note))
            or (
                True,
                {
                    "id": alert_id,
                    "handled": handled,
                    "handling_note": note,
                },
            )
        ),
    )
    monkeypatch.setattr(
        app.socketio,
        "emit",
        lambda event, payload: socket_events.append((event, payload)),
    )
    monkeypatch.setattr(app.runtime, "market_quality_session_id", "session-a")
    monkeypatch.setattr(app.runtime, "market_quality_alert_last_saved_monotonic", 0.0)

    started = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)
    abnormal = observation()
    history = [{
        **abnormal,
        "first_seen_at": started.isoformat(),
        "last_seen_at": started.isoformat(),
        "session_id": "session-a",
    }]
    first = app.process_market_quality_alert_state(
        {},
        abnormal,
        history,
        observed_at=started,
    )
    notified = app.process_market_quality_alert_state(
        first,
        abnormal,
        history,
        observed_at=started + timedelta(minutes=5),
    )
    recovered = app.process_market_quality_alert_state(
        notified,
        observation("normal"),
        history,
        observed_at=started + timedelta(minutes=6),
    )

    assert len(emitted_alerts) == 1
    assert emitted_alerts[0][0]["id"] == "quality-alert-1"
    assert handling_updates == [(
        "quality-alert-1",
        True,
        "行情质量恢复后自动关闭",
    )]
    assert socket_events == [(
        "alert_log_handling_updated",
        {
            "ok": True,
            "entry": {
                "id": "quality-alert-1",
                "handled": True,
                "handling_note": "行情质量恢复后自动关闭",
            },
        },
    )]
    assert recovered["incident_active"] is False
