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
