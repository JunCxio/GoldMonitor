from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from goldmonitor.market_adapters import AdapterFetchResult, MarketAdapterRegistry, MarketSourceAdapter


def sample_gold(close=2300.0):
    return {
        "date": "2026-07-13",
        "time": "12:00:00",
        "open": close - 5,
        "high": close + 10,
        "low": close - 20,
        "close": close,
    }


def test_market_adapter_catalog_has_stable_category_order_and_metadata():
    catalog = app.get_market_adapter_catalog()

    assert [item["name"] for item in catalog["gold"]] == [
        "新浪贵金属",
        "东方财富",
        "GoldPrice",
        "Stooq",
    ]
    assert [item["name"] for item in catalog["forex"]] == [
        "新浪",
        "Frankfurter",
        "Stooq",
    ]
    assert [item["key"] for item in catalog["gold"]] == [
        "sina_gold",
        "eastmoney_gold",
        "goldprice",
        "stooq_gold",
    ]
    assert catalog["gold"][2]["provides_forex_rate"] is True
    assert all("fetcher" not in item for items in catalog.values() for item in items)


def test_default_registry_resolves_compatibility_fetchers_at_call_time(monkeypatch):
    expected = sample_gold()
    monkeypatch.setattr(app, "fetch_sina_gold_result", lambda: (expected, ""))

    registry = app.build_market_adapter_registry()
    result = registry.get("sina_gold").fetch()

    assert result.value == expected
    assert result.error == ""


def test_compatibility_http_fetchers_use_common_executor(monkeypatch):
    calls = []

    def fake_fetch(url, source_label, parser, response_type="text", **kwargs):
        calls.append((url, source_label, response_type, kwargs))
        if source_label == "GoldPrice":
            return AdapterFetchResult(value=sample_gold(2350.0), auxiliary_rate=7.2, started_at=12.0)
        return AdapterFetchResult(value=sample_gold(), started_at=11.0)

    health = []
    monkeypatch.setattr(app.market_adapters_core, "fetch_http_source", fake_fetch)
    monkeypatch.setattr(app, "record_source_health", lambda *args, **kwargs: health.append((args, kwargs)))

    stooq_data, stooq_error = app.fetch_gold_data_result(app.GOLD_URL, "Stooq 金价源")
    goldprice_data, goldprice_rate, goldprice_error = app.fetch_goldprice_data_result()

    assert stooq_data["close"] == 2300.0
    assert stooq_error == ""
    assert goldprice_data["close"] == 2350.0
    assert goldprice_rate == 7.2
    assert goldprice_error == ""
    assert [(item[1], item[2]) for item in calls] == [
        ("Stooq 金价源", "text"),
        ("GoldPrice", "json"),
    ]
    assert health[0][0] == ("Stooq 金价源", "gold", True, "", 11.0)
    assert health[1][0] == ("GoldPrice", "gold", True, "", 12.0)


def test_market_fetch_uses_registry_priority_and_preserves_goldprice_rate(monkeypatch, tmp_path):
    calls = []

    def gold_adapter(key, name, priority, output, provides_rate=False):
        return MarketSourceAdapter(
            key=key,
            name=name,
            category="gold",
            priority=priority,
            cache_source=name,
            provides_forex_rate=provides_rate,
            fetcher=lambda: calls.append(key) or output,
        )

    registry = MarketAdapterRegistry([
        gold_adapter("failed", "失败源", 10, (None, "失败源请求超时")),
        gold_adapter("combined", "组合源", 20, (sample_gold(2360.0), 7.25, ""), True),
        gold_adapter("unused", "未调用源", 30, (sample_gold(2400.0), "")),
    ])
    monkeypatch.setattr(app, "build_market_adapter_registry", lambda: registry)
    monkeypatch.setattr(app, "MARKET_CACHE_PATH", str(tmp_path / "market_cache.json"))

    data, rate_info, source, gold_error, forex_error = app.fetch_market_data_result()

    assert calls == ["failed", "combined"]
    assert data["close"] == 2360.0
    assert rate_info["value"] == 7.25
    assert rate_info["source"] == "组合源"
    assert source == "组合源"
    assert gold_error == ""
    assert forex_error == ""


def test_forex_fetch_uses_registry_and_keeps_error_joining_and_cache(monkeypatch, tmp_path):
    calls = []

    def forex_adapter(key, name, priority, output):
        return MarketSourceAdapter(
            key=key,
            name=name,
            category="forex",
            priority=priority,
            cache_source=name,
            provides_forex_rate=False,
            fetcher=lambda: calls.append(key) or output,
        )

    registry = MarketAdapterRegistry([
        forex_adapter("first", "第一汇率源", 10, (None, "第一汇率源请求超时")),
        forex_adapter("second", "第二汇率源", 20, (7.24, "")),
        forex_adapter("unused", "未调用汇率源", 30, (7.3, "")),
    ])
    monkeypatch.setattr(app, "build_market_adapter_registry", lambda: registry)
    monkeypatch.setattr(app, "MARKET_CACHE_PATH", str(tmp_path / "market_cache.json"))

    rate_info, error = app.fetch_usdcny_rate_result()

    assert calls == ["first", "second"]
    assert rate_info["value"] == 7.24
    assert rate_info["source"] == "第二汇率源"
    assert rate_info["cached"] is False
    assert error == ""


def test_source_comparison_and_health_expose_registry_catalog(monkeypatch):
    expected = sample_gold(2340.0)
    registry = MarketAdapterRegistry([
        MarketSourceAdapter(
            key="probe",
            name="探测源",
            category="gold",
            priority=1,
            cache_source="探测源",
            provides_forex_rate=False,
            fetcher=lambda: (expected, ""),
        )
    ])
    monkeypatch.setattr(app, "build_market_adapter_registry", lambda: registry)
    monkeypatch.setattr(app, "last_source_comparison_probe_at", 0.0)
    monkeypatch.setattr(app, "source_price_samples", {})
    monkeypatch.setattr(app, "source_comparison_state", {})
    monkeypatch.setattr(app.time, "monotonic", lambda: app.SOURCE_COMPARISON_REFRESH_SECONDS + 1)

    comparison = app.refresh_source_comparison()
    health = app.get_source_health_state()

    assert comparison["items"][0]["name"] == "探测源"
    assert health["adapters"]["gold"][0]["key"] == "probe"
