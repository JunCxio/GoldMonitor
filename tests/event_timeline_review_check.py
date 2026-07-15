import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def authorized_client():
    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    if not client.is_connected():
        raise SystemExit("authorized socket client must connect")
    client.get_received()
    return client


def find_event(received, name):
    for event in received:
        if event.get("name") == name:
            args = event.get("args") or []
            return args[0] if args else {}
    return None


def assert_timeline_event_shape(event):
    for key in ("id", "type", "timestamp", "title", "summary", "source", "payload"):
        if key not in event:
            raise SystemExit(f"timeline event must include {key}: {event}")


with tempfile.TemporaryDirectory() as tmp_dir:
    original_appdata_dir = app.APPDATA_DIR
    original_export_dir = app.EXPORT_DIR
    original_price_history_path = app.PRICE_HISTORY_PATH
    original_review_notes_path = app.REVIEW_NOTES_PATH
    original_price_archive = list(app.price_archive)
    original_price_history = list(app.price_history)
    original_alert_log = list(app.alert_log)
    original_risk_history = list(app.risk_analysis_history)
    original_news_items = list(app.news_items)
    original_review_notes = list(app.review_notes)
    original_source_health = dict(app.source_health)
    original_source_comparison_state = dict(app.source_comparison_state)
    original_last_fetch_ok = app.last_fetch_ok
    original_last_fetch_error = app.last_fetch_error
    original_price_usd = app.price_usd
    original_run_risk_analysis = app.run_risk_analysis
    original_refresh_gold_news = app.refresh_gold_news
    original_fetch_gold_news = app.fetch_gold_news

    try:
        app.APPDATA_DIR = str(Path(tmp_dir) / "appdata")
        app.EXPORT_DIR = str(Path(tmp_dir) / "exports")
        app.PRICE_HISTORY_PATH = str(Path(tmp_dir) / "price_history.json")
        app.REVIEW_NOTES_PATH = str(Path(tmp_dir) / "review_notes.json")
        now = datetime.now()
        base_time = now - timedelta(minutes=30)

        app.price_archive = [
            {
                "timestamp": (base_time + timedelta(minutes=i * 5)).isoformat(timespec="seconds"),
                "time": (base_time + timedelta(minutes=i * 5)).strftime("%H:%M:%S"),
                "usd": 2300.0 + i,
                "rmb": 540.0 + i,
                "rate": 7.3,
            }
            for i in range(3)
        ]
        app.price_history = list(app.price_archive)
        app.alert_log = [
            {
                "id": "alert-test-1",
                "timestamp": (base_time + timedelta(minutes=7)).isoformat(timespec="seconds"),
                "time": (base_time + timedelta(minutes=7)).strftime("%H:%M:%S"),
                "type": "warning",
                "mode": "rmb",
                "message": "国内金价达到上涨关注条件",
                "read": False,
                "acknowledged": False,
                "notifications": [{"channel": "email", "label": "邮件", "status": "queued", "message": "已提交"}],
                "related_news": [{"title": "黄金相关新闻", "url": "https://example.com/news"}],
            },
            {
                "id": "alert-bad-time",
                "timestamp": "not-a-time",
                "time": "",
                "type": "warning",
                "mode": "rmb",
                "message": "无效时间警报",
            },
        ]
        app.risk_analysis_history = [
            {
                "id": "risk-test-1",
                "analysis_time": (base_time + timedelta(minutes=10)).isoformat(timespec="seconds"),
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "content": "短线风险偏高。\n关注美元指数。",
                "structured": {"risk_level": "中", "summary": "短线风险偏高"},
                "snapshot": {"data_quality": {"score": 85, "level": "A"}},
                "usage": None,
            },
            {
                "id": "risk-bad-time",
                "analysis_time": "not-a-time",
                "provider": "deepseek",
                "model": "deepseek-v4-pro",
                "content": "无效时间分析",
                "structured": {},
                "snapshot": {},
                "usage": None,
            },
        ]
        app.news_items = [
            {
                "title": "美元回落支撑黄金",
                "url": "https://example.com/gold",
                "source": "Example",
                "time": (base_time + timedelta(minutes=15)).isoformat(timespec="seconds"),
                "topic": "美元",
                "summary": "美元指数回落。",
            },
            {
                "title": "无效时间新闻",
                "url": "https://example.com/bad",
                "source": "Example",
                "time": "not-a-time",
                "topic": "市场",
                "summary": "",
            },
        ]
        app.review_notes = [
            {
                "id": "note-review-1",
                "timestamp": (base_time + timedelta(minutes=25)).isoformat(timespec="seconds"),
                "title": "复盘上涨预警",
                "content": "记录预警触发后的价格变化和数据质量。",
                "related_event_id": "alert-test-1",
                "related_event_type": "alert",
                "related_event_title": "国内金价上涨关注",
                "created_at": (base_time + timedelta(minutes=25)).isoformat(timespec="seconds"),
                "updated_at": (base_time + timedelta(minutes=25)).isoformat(timespec="seconds"),
            },
            {"id": "note-bad-time", "timestamp": "not-a-time", "content": "无效时间笔记"},
        ]
        app.source_health = {
            "缓存金价": {
                "name": "缓存金价",
                "category": "gold",
                "ok": True,
                "cached": True,
                "error": "实时金价源不可用，使用缓存",
                "last_checked": (base_time + timedelta(minutes=18)).isoformat(timespec="seconds"),
                "elapsed_ms": None,
                "ok_count": 1,
                "fail_count": 0,
            },
            "失效来源": {
                "name": "失效来源",
                "category": "gold",
                "ok": False,
                "cached": False,
                "error": "请求超时",
                "last_checked": (base_time + timedelta(minutes=20)).isoformat(timespec="seconds"),
                "elapsed_ms": 4000,
                "ok_count": 0,
                "fail_count": 1,
            },
            "无效时间来源": {
                "name": "无效时间来源",
                "category": "gold",
                "ok": False,
                "cached": False,
                "error": "时间异常",
                "last_checked": "not-a-time",
                "elapsed_ms": None,
                "ok_count": 0,
                "fail_count": 1,
            },
        }
        app.source_comparison_state = {
            "items": [],
            "summary": {"spread_pct": 0.8, "threshold_pct": 0.5, "low_source": "A", "high_source": "B"},
            "status": "anomaly",
            "message": "数据源价差 0.80% ，建议核对行情源",
            "updated_at": (base_time + timedelta(minutes=22)).isoformat(timespec="seconds"),
        }
        app.last_fetch_ok = True
        app.last_fetch_error = ""
        app.price_usd = 2302.0

        def fail_risk_analysis(*args, **kwargs):
            raise SystemExit("review report export must not call run_risk_analysis")

        def fail_news_refresh(*args, **kwargs):
            raise SystemExit("event timeline must not refresh news")

        app.run_risk_analysis = fail_risk_analysis
        app.refresh_gold_news = fail_news_refresh
        app.fetch_gold_news = fail_news_refresh

        state = app.build_event_timeline_state(minutes=60, limit=300)
        for key in ("range", "filters", "summary", "price_summary", "events", "updated_at"):
            if key not in state:
                raise SystemExit(f"timeline state must include {key}: {state}")
        if state["range"]["minutes"] != 60:
            raise SystemExit(f"timeline range minutes must be preserved: {state['range']}")
        if state["price_summary"]["usd"]["points"] != 3 or state["price_summary"]["rmb"]["points"] != 3:
            raise SystemExit(f"timeline price summary must include USD and RMB points: {state['price_summary']}")
        if state["summary"]["skipped"] < 3:
            raise SystemExit(f"invalid-time records must be counted as skipped: {state['summary']}")

        events = state["events"]
        if [event["timestamp"] for event in events] != sorted(event["timestamp"] for event in events):
            raise SystemExit(f"timeline events must be sorted by time: {events}")
        for event in events:
            assert_timeline_event_shape(event)

        by_type = state["summary"]["by_type"]
        for event_type in ("price_summary", "alert", "risk_analysis", "news", "data_status", "review_note"):
            if by_type.get(event_type, 0) < 1:
                raise SystemExit(f"timeline must include {event_type} events, got {by_type}")

        alert_event = next(event for event in events if event["type"] == "alert")
        if alert_event["payload"].get("message") != "国内金价达到上涨关注条件":
            raise SystemExit(f"alert event must preserve the original message: {alert_event}")
        if alert_event["payload"].get("mode") != "rmb" or not alert_event["payload"].get("notifications"):
            raise SystemExit(f"alert event must preserve mode and notifications: {alert_event}")

        risk_event = next(event for event in events if event["type"] == "risk_analysis")
        if risk_event["payload"].get("provider") != "deepseek" or risk_event["payload"].get("model") != "deepseek-v4-pro":
            raise SystemExit(f"risk event must preserve provider and model: {risk_event}")
        if risk_event["payload"].get("structured", {}).get("risk_level") != "中":
            raise SystemExit(f"risk event must preserve structured fields: {risk_event}")

        news_event = next(event for event in events if event["type"] == "news")
        if news_event["payload"].get("url") != "https://example.com/gold":
            raise SystemExit(f"news event must preserve URL: {news_event}")

        data_events = [event for event in events if event["type"] == "data_status"]
        if not any(event["source"] == "source_health" and event["payload"].get("cached") for event in data_events):
            raise SystemExit(f"data status events must include cached source health: {data_events}")
        if not any(event["source"] == "source_comparison" for event in data_events):
            raise SystemExit(f"data status events must include source comparison anomalies: {data_events}")

        note_event = next(event for event in events if event["type"] == "review_note")
        if note_event["payload"].get("related_event_id") != "alert-test-1":
            raise SystemExit(f"review note event must preserve related event: {note_event}")

        alert_only = app.build_event_timeline_state(minutes=60, limit=300, types=["alert"])
        if {event["type"] for event in alert_only["events"]} != {"alert"}:
            raise SystemExit(f"type filtering must only return requested event types: {alert_only['events']}")

        limited = app.build_event_timeline_state(minutes=60, limit=2)
        if len(limited["events"]) != 2:
            raise SystemExit(f"limit must cap returned events: {limited['events']}")

        empty_state = app.build_event_timeline_state(minutes=60, limit=300, types=["alert"])
        app.alert_log = []
        empty_state = app.build_event_timeline_state(minutes=60, limit=300, types=["alert"])
        if empty_state["events"] or empty_state["summary"]["total"] != 0:
            raise SystemExit(f"empty alert history must return an empty event list: {empty_state}")

        app.alert_log = original_alert_log
        socket_alert = {
            "id": "alert-socket-1",
            "timestamp": (base_time + timedelta(minutes=7)).isoformat(timespec="seconds"),
            "time": (base_time + timedelta(minutes=7)).strftime("%H:%M:%S"),
            "type": "warning",
            "mode": "rmb",
            "message": "Socket 警报",
        }
        app.alert_log = [socket_alert]
        client = authorized_client()
        try:
            client.emit("get_event_timeline", {"minutes": 60, "limit": 300, "types": ["alert"]})
            received = client.get_received()
            updated = find_event(received, "event_timeline_updated")
            if not updated or updated["summary"]["by_type"].get("alert") != 1:
                raise SystemExit(f"get_event_timeline must emit event_timeline_updated: {received}")

            client.emit("export_review_report", {
                "minutes": 60,
                "limit": 300,
                "types": ["alert", "price_summary", "review_note"],
            })
            received = client.get_received()
            exported = find_event(received, "review_report_exported")
            if not exported or not exported.get("saved_path"):
                raise SystemExit(f"export_review_report must emit review_report_exported: {received}")
            saved_path = Path(exported["saved_path"])
            if not saved_path.exists():
                raise SystemExit(f"review report file must exist: {exported}")
            if "GoldMonitor-review-report" not in saved_path.name:
                raise SystemExit(f"review report filename must include prefix: {saved_path.name}")
            content = saved_path.read_text(encoding="utf-8")
            for required in (
                "# GoldMonitor 复盘报告",
                "## 时间范围",
                "## 价格摘要",
                "## 事件概览",
                "## 预警回顾",
                "## 复盘笔记",
                "记录预警触发后的价格变化和数据质量。",
            ):
                if required not in content:
                    raise SystemExit(f"review report missing section {required}: {content}")
        finally:
            client.disconnect()

        unauthorized = app.socketio.test_client(app.app)
        if unauthorized.is_connected():
            unauthorized.disconnect()
            raise SystemExit("unauthorized socket client must not connect")
    finally:
        app.APPDATA_DIR = original_appdata_dir
        app.EXPORT_DIR = original_export_dir
        app.PRICE_HISTORY_PATH = original_price_history_path
        app.REVIEW_NOTES_PATH = original_review_notes_path
        app.price_archive = original_price_archive
        app.price_history = original_price_history
        app.alert_log = original_alert_log
        app.risk_analysis_history = original_risk_history
        app.news_items = original_news_items
        app.review_notes = original_review_notes
        app.source_health = original_source_health
        app.source_comparison_state = original_source_comparison_state
        app.last_fetch_ok = original_last_fetch_ok
        app.last_fetch_error = original_last_fetch_error
        app.price_usd = original_price_usd
        app.run_risk_analysis = original_run_risk_analysis
        app.refresh_gold_news = original_refresh_gold_news
        app.fetch_gold_news = original_fetch_gold_news

print("event timeline review checks passed.")
