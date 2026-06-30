from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 8, 12, 0, 0)


def test_request_normalization_clamps_known_options_and_preserves_type_order():
    from goldmonitor.event_timeline import normalize_event_timeline_request

    normalized = normalize_event_timeline_request({
        "minutes": "240",
        "limit": "9999",
        "types": ["alert", "unknown", "news", "alert", "price_summary"],
    })

    assert normalized == {
        "minutes": 240,
        "limit": 500,
        "types": ["alert", "news", "price_summary"],
    }

    fallback = normalize_event_timeline_request({"minutes": "bad", "limit": 0, "types": []})
    assert fallback["minutes"] == 60
    assert fallback["limit"] == 300
    assert fallback["types"] == ["price_summary", "alert", "risk_analysis", "news", "data_status"]


def test_timeline_state_aggregates_injected_sources_without_side_effects():
    from goldmonitor.event_timeline import build_event_timeline_state

    base = fixed_now() - timedelta(minutes=30)
    points = [
        {
            "timestamp": (base + timedelta(minutes=i * 5)).isoformat(timespec="seconds"),
            "time": (base + timedelta(minutes=i * 5)).strftime("%H:%M:%S"),
            "usd": 2300.0 + i,
            "rmb": 540.0 + i,
            "rate": 7.3,
        }
        for i in range(3)
    ]
    state = build_event_timeline_state(
        minutes=60,
        limit=300,
        price_points=points,
        alert_entries=[
            {
                "id": "alert-test-1",
                "timestamp": (base + timedelta(minutes=7)).isoformat(timespec="seconds"),
                "time": (base + timedelta(minutes=7)).strftime("%H:%M:%S"),
                "type": "warning",
                "mode": "rmb",
                "message": "国内金价达到上涨关注条件",
                "handled": True,
                "handled_at": (base + timedelta(minutes=8)).isoformat(timespec="seconds"),
                "handling_note": "已电话确认",
                "notifications": [{"channel": "email", "status": "queued"}],
            },
            {"id": "bad-alert", "timestamp": "not-a-time", "message": "bad"},
        ],
        risk_items=[
            {
                "id": "risk-test-1",
                "analysis_time": (base + timedelta(minutes=10)).isoformat(timespec="seconds"),
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "content": "短线风险偏高。\n关注美元指数。",
                "structured": {"risk_level": "中", "summary": "短线风险偏高"},
                "snapshot": {
                    "data_quality": {"score": 85},
                    "market_quality": {"level": "normal", "score": 100, "label": "数据可信"},
                },
            },
            {"id": "bad-risk", "analysis_time": "not-a-time", "content": "bad"},
        ],
        news_items=[
            {
                "title": "美元回落支撑黄金",
                "url": "https://example.com/gold",
                "source": "Example",
                "time": (base + timedelta(minutes=15)).isoformat(timespec="seconds"),
                "topic": "美元",
                "summary": "美元指数回落。",
            },
            {"title": "bad", "url": "https://example.com/bad", "time": "not-a-time"},
        ],
        fetch_status={"ok": True, "message": "正常"},
        source_health_state={
            "items": [
                {
                    "name": "缓存金价",
                    "ok": True,
                    "cached": True,
                    "error": "实时金价源不可用，使用缓存",
                    "last_checked": (base + timedelta(minutes=18)).isoformat(timespec="seconds"),
                },
                {
                    "name": "无效时间来源",
                    "ok": False,
                    "cached": False,
                    "error": "时间异常",
                    "last_checked": "not-a-time",
                },
            ]
        },
        source_comparison_state={
            "status": "anomaly",
            "message": "数据源价差 0.80% ，建议核对行情源",
            "updated_at": (base + timedelta(minutes=22)).isoformat(timespec="seconds"),
        },
        now_factory=fixed_now,
    )

    assert state["range"]["minutes"] == 60
    assert state["price_summary"]["rmb"]["points"] == 3
    assert state["summary"]["skipped"] == 4
    assert [event["timestamp"] for event in state["events"]] == sorted(event["timestamp"] for event in state["events"])
    assert state["summary"]["by_type"]["price_summary"] == 1
    assert state["summary"]["by_type"]["alert"] == 1
    assert state["summary"]["by_type"]["risk_analysis"] == 1
    assert state["summary"]["by_type"]["news"] == 1
    assert state["summary"]["by_type"]["data_status"] == 2

    alert_event = next(event for event in state["events"] if event["type"] == "alert")
    assert alert_event["payload"]["message"] == "国内金价达到上涨关注条件"
    assert alert_event["payload"]["handled"] is True
    assert alert_event["payload"]["handled_at"] == (base + timedelta(minutes=8)).isoformat(timespec="seconds")
    assert alert_event["payload"]["handling_note"] == "已电话确认"
    assert alert_event["payload"]["notifications"] == [{"channel": "email", "status": "queued"}]

    risk_event = next(event for event in state["events"] if event["type"] == "risk_analysis")
    assert risk_event["title"] == "风险分析：中"
    assert risk_event["payload"]["provider"] == "deepseek"
    assert risk_event["payload"]["market_quality"]["level"] == "normal"

    news_event = next(event for event in state["events"] if event["type"] == "news")
    assert news_event["id"] == "news-https://example.com/gold"
    assert news_event["payload"]["url"] == "https://example.com/gold"

    data_sources = {event["source"] for event in state["events"] if event["type"] == "data_status"}
    assert data_sources == {"source_health", "source_comparison"}


def test_review_report_and_filename_are_stable_for_export():
    from goldmonitor.event_timeline import build_review_report, review_report_filename

    state = {
        "range": {"start": "2026-06-08T11:00:00", "end": "2026-06-08T12:00:00", "minutes": 60},
        "summary": {
            "total": 2,
            "skipped": 1,
            "by_type": {"price_summary": 1, "alert": 1, "risk_analysis": 0, "news": 0, "data_status": 0},
        },
        "price_summary": {
            "usd": {"points": 2, "start": 2300.0, "end": 2310.0, "high": 2310.0, "low": 2300.0, "change": 10.0, "change_pct": 0.4348},
            "rmb": {"points": 2, "start": 540.0, "end": 542.0, "high": 542.0, "low": 540.0, "change": 2.0, "change_pct": 0.3704},
        },
        "events": [
            {
                "type": "price_summary",
                "timestamp": "2026-06-08T12:00:00",
                "title": "价格摘要",
                "summary": "范围内共有 2 个价格点。",
            },
            {
                "type": "alert",
                "timestamp": "2026-06-08T11:30:00",
                "title": "价格预警",
                "summary": "国内金价达到上涨关注条件",
            },
        ],
    }

    report = build_review_report(state)
    assert "# GoldMonitor 复盘报告" in report
    assert "## 时间范围" in report
    assert "- 事件总数：2" in report
    assert "## 预警回顾" in report
    assert "国内金价达到上涨关注条件" in report

    assert review_report_filename(now=fixed_now()) == "GoldMonitor-review-report-20260608-120000.md"


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
    print("event timeline module checks passed.")
