import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 8, 12, 0, 0)


def test_market_parsers_normalize_supported_sources():
    from goldmonitor.market_data import (
        parse_eastmoney_gold,
        parse_frankfurter_forex,
        parse_goldprice_rates,
        parse_sina_forex,
        parse_sina_gold,
        parse_stooq_ohlc_csv,
    )

    rate, error = parse_sina_forex('var hq_str_fx_susdcny="美元人民币,7.1234,7.1200";')
    assert error == ""
    assert rate == 7.1234

    frankfurter_rate, frankfurter_error = parse_frankfurter_forex({"rates": {"CNY": 7.2345}})
    assert frankfurter_error == ""
    assert frankfurter_rate == 7.2345

    sina_gold, sina_error = parse_sina_gold(
        'var hq_str_hf_XAU="2300.50,2301.20,2290.10,2295.00,2310.00,2288.00,11:30:00";',
        now=fixed_now(),
    )
    assert sina_error == ""
    assert sina_gold["date"] == "2026-06-08"
    assert sina_gold["time"] == "11:30:00"
    assert sina_gold["close"] == 2300.5
    assert sina_gold["open"] == 2295.0
    assert sina_gold["high"] == 2310.0
    assert sina_gold["low"] == 2288.0

    eastmoney_gold, eastmoney_error = parse_eastmoney_gold({
        "data": {"f43": 235050, "f46": 234000, "f44": 236000, "f45": 233000, "f59": 2}
    }, now=fixed_now())
    assert eastmoney_error == ""
    assert eastmoney_gold == {
        "date": "2026-06-08",
        "time": "12:00:00",
        "open": 2340.0,
        "high": 2360.0,
        "low": 2330.0,
        "close": 2350.5,
    }

    goldprice_gold, cny_rate, goldprice_error = parse_goldprice_rates({
        "items": [
            {"curr": "USD", "xauPrice": 2350.5},
            {"curr": "CNY", "xauPrice": 17000.0},
        ]
    }, now=fixed_now())
    assert goldprice_error == ""
    assert goldprice_gold["close"] == 2350.5
    assert round(cny_rate, 6) == round(17000.0 / 2350.5, 6)

    stooq_gold, stooq_error = parse_stooq_ohlc_csv("XAUUSD,2026-06-08,12:00:00,2340,2360,2330,2350,,Gold\n")
    assert stooq_error == ""
    assert stooq_gold["close"] == 2350.0


def test_market_cache_store_preserves_sections_and_validates_age():
    from goldmonitor.market_data import MarketCacheStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = str(Path(tmp_dir) / "market_cache.json")
        store = MarketCacheStore(path, max_age_seconds=7 * 24 * 60 * 60, now_factory=fixed_now)

        saved_rate = store.save_usdcny(7.25, "测试汇率", "2026-06-08T11:00:00")
        assert saved_rate == {
            "value": 7.25,
            "source": "测试汇率",
            "timestamp": "2026-06-08T11:00:00",
            "cached": False,
        }

        saved_gold = store.save_xauusd({
            "date": "2026-06-08",
            "time": "11:30:00",
            "open": 2340,
            "high": 2360,
            "low": 2330,
            "close": 2350,
        }, "测试金价", "2026-06-08T11:30:00")
        assert saved_gold["cached"] is False
        assert saved_gold["source"] == "测试金价"

        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        assert set(payload) == {"usdcny", "xauusd"}
        assert store.load_valid_usdcny()["value"] == 7.25
        assert store.load_valid_xauusd()["close"] == 2350.0
        assert store.load_usdcny()["cached"] is True
        assert store.load_xauusd()["cached"] is True

        stale_time = (fixed_now() - timedelta(days=8)).isoformat()
        store.save_usdcny(7.1, "过期汇率", stale_time)
        assert store.load_valid_usdcny() is None

        future_time = (fixed_now() + timedelta(minutes=1)).isoformat()
        store.save_xauusd({"close": 2360}, "未来金价", future_time)
        assert store.load_valid_xauusd() is None


def test_source_health_and_comparison_are_pure_state_helpers():
    from goldmonitor.market_data import build_source_comparison_state, record_source_health

    health = {}
    first = record_source_health(health, "新浪贵金属", "gold", True, "", started_at=10.0, now_monotonic=10.125, now=fixed_now())
    assert first["ok_count"] == 1
    assert first["fail_count"] == 0
    assert first["elapsed_ms"] == 125

    second = record_source_health(health, "新浪贵金属", "gold", False, "测试失败", now=fixed_now())
    assert second["ok_count"] == 1
    assert second["fail_count"] == 1
    assert second["error"] == "测试失败"

    comparison = build_source_comparison_state([
        {"name": "A", "usd": 2300.0, "checked_at": fixed_now().isoformat(), "cached": False},
        {"name": "B", "usd": 2320.0, "checked_at": fixed_now().isoformat(), "cached": False},
        {"name": "缓存", "usd": 2310.0, "checked_at": fixed_now().isoformat(), "cached": True},
    ], stale_seconds=300, anomaly_pct=0.5, now=fixed_now())
    assert comparison["summary"]["compared"] == 2
    assert comparison["status"] == "anomaly"
    assert comparison["summary"]["low_source"] == "A"
    assert comparison["summary"]["high_source"] == "B"


def test_source_health_uses_bounded_rolling_window_and_persists_metrics():
    from goldmonitor.market_data import SourceMetricsStore, record_source_health

    health = {}
    record_source_health(
        health,
        "测试源",
        "gold",
        True,
        started_at=10.0,
        now_monotonic=10.1,
        now=fixed_now(),
        window_size=3,
        source_key="test_gold",
    )
    record_source_health(
        health,
        "测试源",
        "gold",
        False,
        "第一次失败",
        started_at=20.0,
        now_monotonic=20.3,
        now=fixed_now() + timedelta(seconds=1),
        window_size=3,
        source_key="test_gold",
    )
    failed = record_source_health(
        health,
        "测试源",
        "gold",
        False,
        "第二次失败",
        started_at=30.0,
        now_monotonic=30.5,
        now=fixed_now() + timedelta(seconds=2),
        window_size=3,
        source_key="test_gold",
    )
    assert failed["sample_count"] == 3
    assert failed["success_rate_pct"] == 33.3
    assert failed["consecutive_failures"] == 2
    assert failed["median_latency_ms"] == 300.0

    recovered = record_source_health(
        health,
        "测试源",
        "gold",
        True,
        started_at=40.0,
        now_monotonic=40.1,
        now=fixed_now() + timedelta(seconds=3),
        window_size=3,
        source_key="test_gold",
    )
    assert len(recovered["samples"]) == 3
    assert recovered["consecutive_failures"] == 0
    assert recovered["last_recovered_at"] == "2026-06-08T12:00:03"

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "source_metrics.json"
        store = SourceMetricsStore(path, window_size=3)
        payload = store.save(health)
        loaded = store.load()

    assert payload["schema_version"] == 1
    assert loaded["测试源"]["key"] == "test_gold"
    assert loaded["测试源"]["sample_count"] == 3
    assert loaded["测试源"]["success_rate_pct"] == 33.3


def test_source_metrics_store_ignores_invalid_or_future_schema():
    from goldmonitor.market_data import SourceMetricsStore

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "source_metrics.json"
        store = SourceMetricsStore(path)
        path.write_text('{"schema_version":"invalid","sources":{}}', encoding="utf-8")
        assert store.load() == {}

        path.write_text('{"schema_version":2,"sources":{"测试源":{"name":"测试源"}}}', encoding="utf-8")
        assert store.load() == {}


def test_market_quality_summarizes_fetch_health_cache_and_source_anomaly():
    from goldmonitor.market_data import build_market_quality

    normal = build_market_quality(
        fetch_status={"ok": True, "degraded": False, "gold_cached": False, "forex_cached": False},
        source_health={"summary": {"failed": 0, "cached": 0}},
        comparison={"status": "normal", "message": "数据源价差 0.10% ，处于正常范围"},
    )
    assert normal["level"] == "normal"
    assert normal["score"] == 100
    assert normal["label"] == "数据可信"
    assert normal["reasons"] == []
    assert normal["deductions"] == []

    stale = build_market_quality(
        fetch_status={"ok": False, "degraded": True, "gold_cached": True, "forex_cached": False},
        source_health={"summary": {"failed": 0, "cached": 1}},
        comparison={"status": "insufficient"},
    )
    assert stale["level"] == "stale"
    assert stale["score"] == 60
    assert "正在使用缓存行情" in stale["reasons"]

    degraded = build_market_quality(
        fetch_status={"ok": False, "degraded": True, "gold_cached": False, "forex_cached": False},
        source_health={"summary": {"failed": 2, "cached": 0}},
        comparison={"status": "insufficient"},
    )
    assert degraded["level"] == "degraded"
    assert degraded["score"] == 70
    assert "2 个数据源异常" in degraded["reasons"]

    anomaly = build_market_quality(
        fetch_status={"ok": True, "degraded": False, "gold_cached": False, "forex_cached": False},
        source_health={"summary": {"failed": 0, "cached": 0}},
        comparison={"status": "anomaly", "message": "数据源价差 0.87% ，建议核对行情源"},
    )
    assert anomaly["level"] == "anomaly"
    assert anomaly["score"] == 50
    assert "数据源价差异常" in anomaly["reasons"]


def test_market_quality_applies_rolling_reliability_and_failure_deductions():
    from goldmonitor.market_data import build_market_quality

    quality = build_market_quality(
        fetch_status={"ok": True, "degraded": False, "gold_cached": False, "forex_cached": False},
        source_health={
            "summary": {"failed": 0, "cached": 0},
            "adapters": {
                "gold": [{
                    "active": True,
                    "sample_count": 10,
                    "success_count": 7,
                    "consecutive_failures": 2,
                    "last_checked": fixed_now().isoformat(),
                }],
                "forex": [],
            },
        },
        comparison={"status": "normal", "summary": {"spread_pct": 0.1, "threshold_pct": 0.5}},
        now=fixed_now(),
    )

    assert quality["level"] == "degraded"
    assert quality["score"] == 82
    assert quality["components"]["active_success_rate_pct"] == 70.0
    assert {item["code"] for item in quality["deductions"]} == {
        "rolling_reliability",
        "consecutive_failures",
    }


def test_market_observation_blocks_cache_and_cross_source_anomaly():
    from goldmonitor.market_observation import build_market_observation

    observation = build_market_observation(
        {
            "open": 2300,
            "high": 2320,
            "low": 2290,
            "close": 2310,
            "timestamp": "2026-08-26T11:59:30Z",
            "cached": True,
        },
        source="缓存金价（测试源）",
        received_at="2026-08-26T12:00:00Z",
        rate_value=7.2,
        rate_source="测试汇率",
        rate_source_at="2026-08-26T12:00:00Z",
        gold_cached=True,
        comparison={"status": "anomaly", "message": "跨源价差超过阈值"},
    )

    assert observation["quality_level"] == "anomaly"
    assert observation["quality_score"] == 10
    assert observation["usable_for_history"] is False
    assert observation["usable_for_alert"] is False
    assert observation["usable_for_automation"] is False
    assert observation["blocked_reasons"] == [
        "金价来自缓存",
        "跨源价差超过阈值",
    ]


def test_market_quality_history_merges_consecutive_states_and_keeps_transitions():
    from goldmonitor.market_observation import record_market_quality_event

    normal = {
        "source": "测试金价",
        "rate_source": "测试汇率",
        "received_at": "2026-08-26T12:00:00Z",
        "quality_level": "normal",
        "quality_score": 100,
        "usable_for_history": True,
        "usable_for_alert": True,
        "usable_for_automation": True,
        "blocked_reasons": [],
    }
    history = record_market_quality_event([], normal)
    history = record_market_quality_event(
        history,
        {**normal, "received_at": "2026-08-26T12:00:10Z"},
    )
    assert len(history) == 1
    assert history[0]["occurrences"] == 2
    assert history[0]["first_seen_at"] == "2026-08-26T12:00:00Z"
    assert history[0]["last_seen_at"] == "2026-08-26T12:00:10Z"

    blocked = {
        **normal,
        "received_at": "2026-08-26T12:00:20Z",
        "is_cached": True,
        "gold_cached": True,
        "quality_level": "stale",
        "quality_score": 60,
        "usable_for_history": False,
        "usable_for_alert": False,
        "usable_for_automation": False,
        "blocked_reasons": ["金价来自缓存"],
    }
    history = record_market_quality_event(history, blocked)
    assert len(history) == 2
    assert history[-1]["quality_level"] == "stale"
    assert history[-1]["occurrences"] == 1


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
    print("market data module checks passed.")
