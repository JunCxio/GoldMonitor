import json
import sys
from datetime import datetime
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def sample_timeline_state():
    return {
        "range": {
            "start": "2026-07-12T20:00:00",
            "end": "2026-07-13T20:00:00",
            "minutes": 1440,
        },
        "summary": {
            "total": 5,
            "skipped": 0,
            "by_type": {
                "price_summary": 1,
                "alert": 2,
                "risk_analysis": 1,
                "news": 1,
                "data_status": 0,
                "review_note": 1,
            },
        },
        "price_summary": {
            "usd": {
                "points": 20,
                "start": 2380.0,
                "end": 2400.0,
                "high": 2410.0,
                "low": 2375.0,
                "change": 20.0,
                "change_pct": 0.84,
            },
            "rmb": {
                "points": 20,
                "start": 548.0,
                "end": 552.0,
                "high": 554.0,
                "low": 547.0,
                "change": 4.0,
                "change_pct": 0.73,
            },
        },
        "events": [
            {
                "id": "alert-1",
                "type": "alert",
                "timestamp": "2026-07-13T10:00:00",
                "title": "达到观察价",
                "summary": "人民币金价达到 550 元/克",
            },
            {
                "id": "risk-1",
                "type": "risk_analysis",
                "timestamp": "2026-07-13T18:00:00",
                "title": "风险分析：中等",
                "summary": "短期波动扩大。",
            },
            {
                "id": "review-note-1",
                "type": "review_note",
                "timestamp": "2026-07-13T19:00:00",
                "title": "复盘笔记",
                "summary": "记录今日上涨预警的后续表现。",
            },
        ],
    }


def test_build_daily_digest_reuses_timeline_quality_and_portfolio_data():
    from goldmonitor.daily_digest import build_daily_digest

    digest = build_daily_digest(
        sample_timeline_state(),
        portfolio_state={
            "rmb_summary": {
                "count": 2,
                "market_value": 12000.0,
                "pnl": 650.0,
                "pnl_percent": 5.72,
            },
            "usd_summary": {"count": 0, "market_value": 0, "pnl": 0, "pnl_percent": 0},
        },
        market_quality={
            "score": 70,
            "label": "部分降级",
            "reasons": ["1 个数据源异常"],
        },
        now=datetime(2026, 7, 13, 20, 0),
    )

    assert digest["subject"] == "[GoldMonitor] 每日摘要 2026-07-13"
    assert "RMB/克：548.00 -> 552.00" in digest["message"]
    assert "预警 2 条" in digest["message"]
    assert "复盘笔记 1 条" in digest["message"]
    assert "部分降级 / 70 分" in digest["message"]
    assert "人民币持仓：2 项" in digest["message"]
    assert "达到观察价：人民币金价达到 550 元/克" in digest["message"]
    assert digest["payload"]["kind"] == "daily_summary"
    assert digest["payload"]["event_summary"]["alert"] == 2
    assert digest["payload"]["event_summary"]["review_note"] == 1
    assert digest["payload"]["market_quality"]["score"] == 70


def test_build_daily_digest_handles_empty_history_without_calling_a_model():
    from goldmonitor.daily_digest import build_daily_digest

    digest = build_daily_digest(
        {
            "range": {},
            "summary": {"total": 0, "skipped": 0, "by_type": {}},
            "price_summary": {},
            "events": [],
        },
        portfolio_state={},
        market_quality={},
        now=datetime(2026, 7, 13, 8, 0),
    )

    assert "暂无可用价格历史" in digest["message"]
    assert "暂无关键事件" in digest["message"]
    assert digest["payload"]["generated_at"] == "2026-07-13T08:00:00"


def test_daily_digest_summarizes_investment_plans_and_attention():
    from goldmonitor.daily_digest import build_daily_digest

    digest = build_daily_digest(
        {"range": {}, "summary": {"by_type": {}}, "price_summary": {}, "events": []},
        portfolio_state={
            "investment_plans": {
                "summary": {"total": 3, "enabled": 2, "due": 1, "attention": 1},
                "items": [
                    {
                        "id": "plan-next",
                        "name": "每月积存",
                        "position_name": "积存金",
                        "mode": "rmb",
                        "amount": 1000.0,
                        "enabled": True,
                        "status": "active",
                        "next_run_at": "2026-08-15T09:00:00",
                        "last_result": "waiting",
                    },
                    {
                        "id": "plan-recent",
                        "name": "每日积累",
                        "position_name": "积存金",
                        "mode": "rmb",
                        "amount": 500.0,
                        "enabled": True,
                        "status": "due",
                        "next_run_at": "2026-08-13T09:00:00",
                        "last_executed_at": "2026-08-13T08:30:00",
                        "last_result": "ok",
                        "last_price": 955.2,
                        "last_quantity": 0.52345059,
                    },
                    {
                        "id": "plan-attention",
                        "name": "美元积累",
                        "position_name": "国际金",
                        "mode": "usd",
                        "amount": 200.0,
                        "enabled": False,
                        "status": "paused",
                        "last_result": "orphaned",
                        "last_message": "关联持仓已删除，请重新选择",
                        "updated_at": "2026-08-13T08:00:00",
                    },
                    {
                        "id": "plan-archived",
                        "name": "已归档异常计划",
                        "enabled": False,
                        "status": "archived",
                        "last_result": "orphaned",
                        "last_message": "不应进入摘要",
                        "archived_at": "2026-08-13T07:00:00",
                    },
                ],
            }
        },
        now=datetime(2026, 8, 13, 20, 0),
    )

    assert "定投计划" in digest["message"]
    assert "共 3 个，启用 2 个，待执行 1 个，需处理 1 个" in digest["message"]
    assert "下一次：每日积累，2026-08-13 09:00，¥500.00" in digest["message"]
    assert "最近执行：每日积累，2026-08-13 08:30，¥500.00，成交价 ¥955.20" in digest["message"]
    assert "需处理：美元积累，关联持仓已删除，请重新选择" in digest["message"]
    investment = digest["payload"]["investment_plan_summary"]
    assert investment["summary"] == {"total": 3, "enabled": 2, "due": 1, "attention": 1}
    assert investment["next_plan"]["id"] == "plan-recent"
    assert investment["recent_plan"]["id"] == "plan-recent"
    assert [item["id"] for item in investment["attention"]] == ["plan-attention"]


def test_daily_digest_keeps_latest_event_from_each_summary_category():
    from goldmonitor.daily_digest import build_daily_digest

    events = [
        {
            "type": "alert",
            "timestamp": f"2026-07-13T19:{minute:02d}:00",
            "title": f"预警 {minute}",
            "summary": "价格触发",
        }
        for minute in range(10, 16)
    ]
    events.extend([
        {
            "type": "risk_analysis",
            "timestamp": "2026-07-13T18:00:00",
            "title": "风险分析",
            "summary": "波动风险中等",
        },
        {
            "type": "news",
            "timestamp": "2026-07-13T17:00:00",
            "title": "市场新闻",
            "summary": "重要数据发布",
        },
        {
            "type": "data_status",
            "timestamp": "2026-07-13T16:00:00",
            "title": "数据状态",
            "summary": "行情源恢复",
        },
        {
            "type": "review_note",
            "timestamp": "2026-07-13T15:00:00",
            "title": "复盘笔记",
            "summary": "记录行情恢复后的观察结果",
        },
    ])

    digest = build_daily_digest(
        {
            "range": {},
            "summary": {"by_type": {}},
            "price_summary": {},
            "events": events,
        },
        now=datetime(2026, 7, 13, 20, 0),
    )

    recent_types = {item["type"] for item in digest["payload"]["recent_events"]}
    assert {"alert", "risk_analysis", "news", "data_status", "review_note"} <= recent_types
    assert "风险分析：波动风险中等" in digest["message"]
    assert "市场新闻：重要数据发布" in digest["message"]
    assert "数据状态：行情源恢复" in digest["message"]
    assert "复盘笔记：记录行情恢复后的观察结果" in digest["message"]


def test_daily_digest_state_store_is_versioned_and_records_scheduled_and_manual_results(tmp_path):
    from goldmonitor.daily_digest import DailyDigestStateStore

    path = tmp_path / "daily_digest_state.json"
    store = DailyDigestStateStore(str(path), now_factory=lambda: datetime(2026, 7, 13, 20, 5))

    assert store.load() == {
        "schema_version": 1,
        "last_attempt_at": "",
        "last_completed_at": "",
        "last_sent_at": "",
        "last_test_at": "",
        "last_status": "idle",
        "last_message": "",
        "last_channels": [],
        "updated_at": "",
    }

    scheduled = store.record_result(
        status="queued",
        message="摘要已提交发送",
        channels=["email"],
        sent=True,
        manual=False,
    )
    assert scheduled["last_attempt_at"] == "2026-07-13T20:05:00"
    assert scheduled["last_completed_at"] == "2026-07-13T20:05:00"
    assert scheduled["last_sent_at"] == "2026-07-13T20:05:00"
    assert scheduled["last_test_at"] == ""

    store.now_factory = lambda: datetime(2026, 7, 13, 20, 10)
    manual = store.record_result(
        status="skipped",
        message="Webhook 未配置",
        channels=["webhook"],
        sent=False,
        manual=True,
    )
    assert manual["last_completed_at"] == "2026-07-13T20:05:00"
    assert manual["last_sent_at"] == "2026-07-13T20:05:00"
    assert manual["last_test_at"] == "2026-07-13T20:10:00"

    persisted = json.loads(path.read_text(encoding="utf-8"))
    assert persisted["schema_version"] == 1
    assert persisted["last_status"] == "skipped"


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                if "tmp_path" in value.__code__.co_varnames:
                    continue
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("daily digest module checks passed.")
