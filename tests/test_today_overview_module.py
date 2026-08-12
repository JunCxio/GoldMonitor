from copy import deepcopy
from datetime import datetime
import json


def test_today_overview_separates_today_activity_from_cross_day_attention():
    from goldmonitor.today_overview import build_today_overview

    alerts = [
        {
            "id": "alert-old-critical",
            "timestamp": "2026-08-11T23:50:00",
            "type": "critical",
            "rule_name": "夜间下跌警报",
            "message": "价格跌破关键位置",
            "read": False,
            "handled": False,
            "notification_summary": {"status": "failed"},
        },
        {
            "id": "alert-today-handled",
            "timestamp": "2026-08-12T08:00:00",
            "type": "warning",
            "message": "价格达到观察位置",
            "read": True,
            "handled": True,
            "notification_summary": {"status": "sent"},
        },
        {
            "id": "alert-today-unhandled",
            "timestamp": "2026-08-12T09:30:00",
            "type": "warning",
            "message": "短时波动达到阈值",
            "read": False,
            "handled": False,
            "notification_summary": {"status": "sent"},
        },
        {
            "id": "alert-old-delivery",
            "timestamp": "2026-08-10T18:00:00",
            "type": "warning",
            "message": "邮件与 Webhook 部分送达",
            "read": True,
            "handled": True,
            "notification_summary": {"status": "partial"},
        },
    ]
    rules = {
        "items": [
            {"id": "rule-waiting", "name": "等待行情", "kind": "price_threshold", "state": {"status": "waiting_data"}},
            {"id": "rule-orphaned", "name": "缺失持仓", "kind": "portfolio", "state": {"status": "orphaned"}},
            {"id": "rule-expired", "name": "过期观察", "kind": "watch_target", "state": {"status": "expired"}},
            {"id": "rule-disabled", "name": "停用规则", "kind": "watch_target", "state": {"status": "disabled"}},
        ]
    }
    portfolio = {
        "total": 2,
        "rmb_summary": {"count": 1, "market_value": 12000.0, "total_pnl": 650.0},
        "usd_summary": {"count": 1, "market_value": 4200.0, "total_pnl": -80.0},
        "transactions": [
            {
                "id": "transaction-today",
                "name": "积存金",
                "type": "buy",
                "mode": "rmb",
                "price": 720.0,
                "quantity": 10,
                "trade_date": "2026-08-12",
                "created_at": "2026-08-12T08:30:00",
            },
            {
                "id": "transaction-yesterday",
                "name": "国际金",
                "type": "sell",
                "mode": "usd",
                "trade_date": "2026-08-11",
                "created_at": "2026-08-12T09:00:00",
            },
        ],
    }
    risks = [
        {
            "id": "risk-today",
            "analysis_time": "2026-08-12T09:45:00",
            "provider": "deepseek",
            "structured": {"risk_level": "中", "summary": "波动有所扩大"},
        },
        {"id": "risk-old", "analysis_time": "2026-08-11T20:00:00", "content": "旧分析"},
    ]
    notes = [
        {
            "id": "note-today",
            "timestamp": "2026-08-12T09:50:00",
            "title": "盘中观察",
            "content": "记录波动后的表现。",
        }
    ]

    result = build_today_overview(
        alert_entries=alerts,
        alert_rules=rules,
        market_quality={"level": "anomaly", "score": 45, "label": "价差异常", "reasons": ["跨源价差超过阈值"]},
        fetch_status={"ok": True},
        portfolio_state=portfolio,
        risk_items=risks,
        review_notes=notes,
        last_viewed_at="2026-08-12T09:00:00",
        now=datetime(2026, 8, 12, 10, 0),
    )

    assert result["schema_version"] == 1
    assert result["range"] == {
        "date": "2026-08-12",
        "start": "2026-08-12T00:00:00",
        "end": "2026-08-13T00:00:00",
        "timezone": "local",
    }
    assert result["summary"] == {
        "attention_total": 7,
        "activity_total": 5,
        "new_since_last_view": 3,
        "alerts_today": 2,
        "unread_alerts": 2,
        "unhandled_alerts": 2,
        "notification_issues": 2,
        "rule_issues": 3,
        "rules_waiting_data": 1,
        "rules_orphaned": 1,
        "rules_expired": 1,
        "portfolio_positions": 2,
        "portfolio_transactions_today": 1,
        "risk_analyses_today": 1,
        "review_notes_today": 1,
    }
    attention_ids = [item["id"] for item in result["attention"]["items"]]
    assert attention_ids[0] == "alert:alert-old-critical"
    assert attention_ids.count("alert:alert-old-critical") == 1
    combined = result["attention"]["items"][0]
    assert combined["reason_codes"] == ["unhandled", "notification_issue"]
    assert combined["occurred_today"] is False
    assert "rule:rule-disabled" not in attention_ids
    assert result["portfolio"]["current"]["rmb"]["total_pnl"] == 650.0
    assert [item["id"] for item in result["portfolio"]["transactions_today"]] == [
        "portfolio_transaction:transaction-today"
    ]
    assert result["recent"]["risk_analysis"]["id"] == "risk-today"
    assert result["recent"]["review_note"]["id"] == "note-today"


def test_today_overview_does_not_drop_old_unresolved_items_at_midnight():
    from goldmonitor.today_overview import build_today_overview

    result = build_today_overview(
        alert_entries=[
            {
                "id": "old-unhandled",
                "timestamp": "2026-08-11T21:00:00",
                "handled": False,
                "read": True,
                "notification_summary": {"status": "sent"},
            },
            {
                "id": "old-finished",
                "timestamp": "2026-08-11T20:00:00",
                "handled": True,
                "read": True,
                "notification_summary": {"status": "sent"},
            },
        ],
        now=datetime(2026, 8, 12, 0, 5),
    )

    assert result["summary"]["alerts_today"] == 0
    assert result["summary"]["unhandled_alerts"] == 1
    assert [item["source_id"] for item in result["attention"]["items"]] == ["old-unhandled"]
    assert result["activity"]["items"] == []


def test_today_overview_ignores_initial_market_waiting_and_normal_quality():
    from goldmonitor.today_overview import build_today_overview

    initial = build_today_overview(
        market_quality={},
        fetch_status={"ok": False, "message": "正在等待首次行情数据返回", "error": ""},
        now=datetime(2026, 8, 12, 8, 0),
    )
    normal = build_today_overview(
        market_quality={"level": "normal", "score": 100, "label": "数据可信"},
        fetch_status={"ok": True},
        now=datetime(2026, 8, 12, 8, 0),
    )

    assert initial["summary"]["attention_total"] == 0
    assert normal["summary"]["attention_total"] == 0


def test_today_overview_is_deterministic_limits_output_and_does_not_mutate_inputs():
    from goldmonitor.today_overview import build_today_overview

    alerts = [
        {
            "id": f"alert-{index}",
            "timestamp": f"2026-08-12T09:{index:02d}:00",
            "handled": False,
            "read": False,
            "message": f"警报 {index}",
        }
        for index in range(5)
    ]
    original = deepcopy(alerts)

    first = build_today_overview(
        alert_entries=alerts,
        last_viewed_at="invalid",
        attention_limit=2,
        activity_limit=3,
        now=datetime(2026, 8, 12, 10, 0),
    )
    second = build_today_overview(
        alert_entries=alerts,
        last_viewed_at="invalid",
        attention_limit=2,
        activity_limit=3,
        now=datetime(2026, 8, 12, 10, 0),
    )

    assert first == second
    assert alerts == original
    assert first["attention"]["total"] == 5
    assert first["attention"]["truncated"] is True
    assert len(first["attention"]["items"]) == 2
    assert [item["source_id"] for item in first["attention"]["items"]] == ["alert-4", "alert-3"]
    assert first["activity"]["total"] == 5
    assert first["activity"]["truncated"] is True
    assert [item["source_id"] for item in first["activity"]["items"]] == ["alert-4", "alert-3", "alert-2"]
    assert first["summary"]["new_since_last_view"] == 0


def test_today_overview_accepts_legacy_notification_items_and_skips_bad_records():
    from goldmonitor.today_overview import build_today_overview

    result = build_today_overview(
        alert_entries=[
            None,
            "invalid",
            {
                "id": "legacy-partial",
                "timestamp": "2026-08-12T08:00:00Z",
                "handled": True,
                "read": True,
                "notifications": [
                    {"channel": "email", "status": "sent"},
                    {"channel": "webhook", "status": "failed"},
                ],
            },
            {
                "id": "invalid-time",
                "timestamp": "not-a-time",
                "handled": True,
                "read": True,
            },
        ],
        risk_items=[{"id": "bad-risk", "analysis_time": "not-a-time"}],
        review_notes=[{"id": "bad-note", "timestamp": "not-a-time"}],
        now=datetime(2026, 8, 12, 10, 0),
    )

    assert result["summary"]["notification_issues"] == 1
    assert result["summary"]["alerts_today"] == 1
    assert result["summary"]["activity_total"] == 1
    assert result["attention"]["items"][0]["notification_status"] == "partial"
    assert result["recent"] == {"risk_analysis": None, "review_note": None}


def test_today_overview_state_store_is_versioned_and_recovers_from_invalid_json(tmp_path):
    from goldmonitor.today_overview import TodayOverviewStateStore

    path = tmp_path / "today_overview_state.json"
    store = TodayOverviewStateStore(
        str(path),
        now_factory=lambda: datetime(2026, 8, 12, 10, 30),
    )

    assert store.load() == {
        "schema_version": 1,
        "last_viewed_at": "",
        "updated_at": "",
    }
    saved = store.mark_viewed()
    assert saved == {
        "schema_version": 1,
        "last_viewed_at": "2026-08-12T10:30:00",
        "updated_at": "2026-08-12T10:30:00",
    }
    assert json.loads(path.read_text(encoding="utf-8")) == saved

    path.write_text("not-json", encoding="utf-8")
    assert store.load()["last_viewed_at"] == ""
