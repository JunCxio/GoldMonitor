import json
from datetime import datetime, timezone

import pytest


def _event(
    first_seen_at,
    last_seen_at,
    *,
    level="normal",
    usable=True,
    reason="",
    occurrences=1,
    session_id="session-1",
):
    return {
        "source": "测试金价",
        "rate_source": "测试汇率",
        "received_at": last_seen_at,
        "quality_score": 100 if level == "normal" else 40,
        "quality_level": level,
        "usable_for_history": usable,
        "usable_for_alert": usable,
        "usable_for_automation": usable,
        "blocked_reasons": [reason] if reason else [],
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "occurrences": occurrences,
        "session_id": session_id,
    }


def test_quality_event_does_not_merge_across_application_sessions():
    from goldmonitor.market_observation import record_market_quality_event

    observation = {
        "received_at": "2026-08-26T10:00:00Z",
        "quality_level": "normal",
        "quality_score": 100,
        "usable_for_history": True,
        "usable_for_alert": True,
        "usable_for_automation": True,
        "blocked_reasons": [],
    }
    first = record_market_quality_event(
        [],
        observation,
        observed_at="2026-08-26T10:00:00Z",
        session_id="first-session",
    )
    second = record_market_quality_event(
        first,
        observation,
        observed_at="2026-08-26T11:00:00Z",
        session_id="second-session",
    )

    assert len(second) == 2
    assert second[0]["occurrences"] == 1
    assert second[1]["session_id"] == "second-session"


def test_market_quality_summary_reports_incidents_duration_and_business_impact():
    from goldmonitor.market_quality_history import build_market_quality_history_summary

    events = [
        _event("2026-08-26T10:00:00Z", "2026-08-26T10:30:00Z"),
        _event(
            "2026-08-26T10:30:00Z",
            "2026-08-26T11:00:00Z",
            level="stale",
            usable=False,
            reason="金价来自缓存",
            occurrences=4,
        ),
    ]

    summary = build_market_quality_history_summary(
        events,
        now=datetime(2026, 8, 26, 11, 0, tzinfo=timezone.utc),
    )
    daily = summary["windows"]["24h"]

    assert summary["stored_events"] == 2
    assert daily["incident_count"] == 1
    assert daily["occurrence_count"] == 4
    assert daily["observed_seconds"] == 3600
    assert daily["abnormal_seconds"] == 1800
    assert daily["availability_pct"] == 50.0
    assert daily["affected_business"]["history"] == {
        "label": "历史入库",
        "incident_count": 1,
        "blocked_seconds": 1800,
    }
    assert daily["affected_business"]["alert"]["blocked_seconds"] == 1800
    assert daily["affected_business"]["automation"]["blocked_seconds"] == 1800
    assert daily["top_reasons"][0]["reason"] == "金价来自缓存"


def test_market_quality_store_migrates_legacy_list_and_bounds_retention(tmp_path):
    from goldmonitor.market_quality_history import MarketQualityHistoryStore

    path = tmp_path / "market_quality_history.json"
    path.write_text(
        json.dumps([
            _event("2026-07-01T10:00:00Z", "2026-07-01T10:01:00Z"),
            _event("2026-08-24T10:00:00Z", "2026-08-24T10:01:00Z"),
            _event("2026-08-25T10:00:00Z", "2026-08-25T10:01:00Z"),
            _event("2026-08-26T10:00:00Z", "2026-08-26T10:01:00Z"),
        ]),
        encoding="utf-8",
    )
    store = MarketQualityHistoryStore(
        path,
        retention_days=30,
        limit=2,
        now_factory=lambda: datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
    )

    loaded = store.load()
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert [item["first_seen_at"] for item in loaded] == [
        "2026-08-25T10:00:00Z",
        "2026-08-26T10:00:00Z",
    ]
    assert payload["schema_version"] == 1
    assert payload["retention_days"] == 30
    assert payload["max_events"] == 2
    assert len(payload["items"]) == 2


def test_market_quality_store_recovers_from_corrupt_or_future_payload(tmp_path):
    from goldmonitor.market_quality_history import MarketQualityHistoryStore

    path = tmp_path / "market_quality_history.json"
    store = MarketQualityHistoryStore(
        path,
        now_factory=lambda: datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
    )
    path.write_text("{invalid", encoding="utf-8")
    assert store.load() == []

    future_payload = {"schema_version": 99, "items": [_event(
        "2026-08-26T10:00:00Z",
        "2026-08-26T10:01:00Z",
    )]}
    path.write_text(json.dumps(future_payload), encoding="utf-8")
    assert store.load() == []
    with pytest.raises(OSError, match="schema version is not supported"):
        store.save([])
    assert json.loads(path.read_text(encoding="utf-8"))["schema_version"] == 99


def test_market_quality_store_record_merges_and_saves_current_session(tmp_path):
    from goldmonitor.market_quality_history import MarketQualityHistoryStore

    path = tmp_path / "market_quality_history.json"
    store = MarketQualityHistoryStore(
        path,
        now_factory=lambda: datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
    )
    observation = {
        "received_at": "2026-08-26T11:00:00Z",
        "quality_level": "stale",
        "quality_score": 40,
        "usable_for_history": False,
        "usable_for_alert": False,
        "usable_for_automation": False,
        "blocked_reasons": ["金价来自缓存"],
    }
    first = store.record(
        [],
        observation,
        observed_at="2026-08-26T11:00:00Z",
        session_id="session-1",
    )
    second = store.record(
        first,
        observation,
        observed_at="2026-08-26T11:01:00Z",
        session_id="session-1",
    )

    assert len(second) == 1
    assert second[0]["occurrences"] == 2
    assert second[0]["last_seen_at"] == "2026-08-26T11:01:00Z"
    assert store.load()[0]["occurrences"] == 2
