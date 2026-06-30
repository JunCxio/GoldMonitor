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
