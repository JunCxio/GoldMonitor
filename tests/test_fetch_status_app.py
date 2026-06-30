from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


def test_fetch_status_exposes_structured_source_state_for_cached_market_data():
    status = app.build_fetch_status(
        ok=False,
        message="使用缓存金价（缓存金价（新浪贵金属）），汇率已更新 7.1888（新浪汇率）",
        gold_ok=False,
        forex_ok=True,
        gold_cached=True,
        forex_cached=False,
        gold_source="缓存金价（新浪贵金属）",
        forex_source="新浪汇率",
        error="实时金价源暂不可用，正在使用缓存金价",
    )

    assert status["ok"] is False
    assert status["status"] == "degraded"
    assert status["degraded"] is True
    assert status["sources"]["gold"] == {
        "ok": False,
        "cached": True,
        "source": "缓存金价（新浪贵金属）",
    }
    assert status["sources"]["forex"] == {
        "ok": True,
        "cached": False,
        "source": "新浪汇率",
    }
    assert "缓存" in status["message"]


def test_fetch_status_marks_all_live_sources_ok_as_normal():
    status = app.build_fetch_status(
        ok=True,
        message="金价已更新（新浪贵金属），汇率已更新 7.1888（新浪汇率）",
        gold_ok=True,
        forex_ok=True,
        gold_cached=False,
        forex_cached=False,
        gold_source="新浪贵金属",
        forex_source="新浪汇率",
    )

    assert status["ok"] is True
    assert status["status"] == "ok"
    assert status["degraded"] is False
    assert status["sources"]["gold"]["cached"] is False
    assert status["sources"]["forex"]["cached"] is False


def test_source_health_state_includes_market_quality(monkeypatch):
    monkeypatch.setattr(app, "price_usd", 2350.0)
    monkeypatch.setattr(app, "price_rmb", 544.0)
    monkeypatch.setattr(app, "usdcny_rate", 7.2)
    monkeypatch.setattr(app, "last_fetch_ok", False)
    monkeypatch.setattr(app, "last_fetch_error", "实时金价源暂不可用，正在使用缓存金价")
    monkeypatch.setattr(app, "gold_price_cached", True)
    monkeypatch.setattr(app, "gold_price_error", "实时金价源暂不可用")
    monkeypatch.setattr(app, "gold_price_source", "缓存金价")
    monkeypatch.setattr(app, "usdcny_rate_cached", False)
    monkeypatch.setattr(app, "usdcny_rate_error", "")
    monkeypatch.setattr(app, "usdcny_rate_source", "新浪汇率")
    monkeypatch.setattr(app, "source_health", {
        "缓存金价": {
            "name": "缓存金价",
            "category": "gold",
            "ok": True,
            "cached": True,
            "fail_count": 0,
            "ok_count": 1,
        }
    })
    monkeypatch.setattr(app, "source_comparison_state", {"status": "insufficient", "summary": {}})

    state = app.get_source_health_state()

    assert state["quality"]["level"] == "stale"
    assert state["quality"]["score"] == 60
    assert "正在使用缓存行情" in state["quality"]["reasons"]


def test_risk_analysis_context_includes_market_quality(monkeypatch):
    monkeypatch.setattr(app, "price_usd", 2350.0)
    monkeypatch.setattr(app, "price_rmb", 544.0)
    monkeypatch.setattr(app, "usdcny_rate", 7.2)
    monkeypatch.setattr(app, "last_fetch_ok", False)
    monkeypatch.setattr(app, "last_fetch_error", "实时金价源暂不可用，正在使用缓存金价")
    monkeypatch.setattr(app, "gold_price_cached", True)
    monkeypatch.setattr(app, "gold_price_error", "实时金价源暂不可用")
    monkeypatch.setattr(app, "gold_price_source", "缓存金价")
    monkeypatch.setattr(app, "gold_price_time", "2026-06-30T10:00:00")
    monkeypatch.setattr(app, "usdcny_rate_cached", False)
    monkeypatch.setattr(app, "usdcny_rate_error", "")
    monkeypatch.setattr(app, "usdcny_rate_source", "新浪汇率")
    monkeypatch.setattr(app, "usdcny_rate_time", "2026-06-30T10:00:00")
    monkeypatch.setattr(app, "source_health", {
        "缓存金价": {
            "name": "缓存金价",
            "category": "gold",
            "ok": True,
            "cached": True,
            "fail_count": 0,
            "ok_count": 1,
        }
    })
    monkeypatch.setattr(app, "source_comparison_state", {"status": "insufficient", "summary": {}})

    context = app.build_risk_analysis_context()
    snapshot = app.build_risk_analysis_snapshot(context)

    assert context["market_quality"]["level"] == "stale"
    assert snapshot["market_quality"]["level"] == "stale"
