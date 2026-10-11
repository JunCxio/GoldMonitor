from pathlib import Path
from datetime import datetime
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
from goldmonitor.market_adapters import (
    AdapterFetchResult,
    MarketAdapterRegistry,
    MarketSourceAdapter,
    configure_registry,
    normalize_source_preferences,
    source_preference_defaults,
)
from goldmonitor.custom_market_sources import normalize_custom_sources, parse_custom_gold


def adapter(key, name, category, priority, output):
    return MarketSourceAdapter(
        key=key,
        name=name,
        category=category,
        priority=priority,
        cache_source=name,
        provides_forex_rate=isinstance(output, tuple) and len(output) == 3,
        fetcher=lambda: output,
    )


def sample_gold(close=2350.0):
    return {
        "date": "2026-07-27",
        "time": "12:00:00",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
    }


def test_source_preferences_validate_enablement_and_configure_runtime_order():
    registry = MarketAdapterRegistry([
        adapter("gold_a", "金价 A", "gold", 10, (sample_gold(), "")),
        adapter("gold_b", "金价 B", "gold", 20, (sample_gold(), "")),
        adapter("forex_a", "汇率 A", "forex", 10, (7.2, "")),
    ])
    defaults = source_preference_defaults(registry)
    preferences = normalize_source_preferences(
        enabled={"gold": ["gold_b"], "forex": ["forex_a"]},
        order={"gold": ["gold_b", "gold_a"], "forex": ["forex_a"]},
        defaults=defaults,
        strict=True,
    )
    configured, normalized = configure_registry(
        registry,
        preferences["enabled"],
        preferences["order"],
        strict=True,
    )

    assert [item.key for item in configured.category_adapters("gold")] == ["gold_b"]
    assert normalized["order"]["gold"] == ["gold_b", "gold_a"]
    with pytest.raises(ValueError, match="金价数据源至少启用一个"):
        normalize_source_preferences(
            enabled={"gold": [], "forex": ["forex_a"]},
            order=defaults,
            defaults=defaults,
            strict=True,
        )


def test_app_runtime_registry_uses_saved_source_order_and_enabled_state(monkeypatch):
    settings = {
        **app.DEFAULT_SETTINGS,
        "market_source_enabled": {
            "gold": ["stooq_gold", "sina_gold"],
            "forex": ["frankfurter_forex"],
        },
        "market_source_order": {
            "gold": ["stooq_gold", "sina_gold", "goldprice", "eastmoney_gold"],
            "forex": ["frankfurter_forex", "sina_forex", "stooq_forex"],
        },
    }
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: settings)

    registry = app.build_market_adapter_registry()

    assert [item.key for item in registry.category_adapters("gold")] == ["sina_gold", "gold_api"]
    assert [item.key for item in registry.category_adapters("forex")] == ["frankfurter_forex"]


def test_market_fetch_follows_user_configured_order(monkeypatch, tmp_path):
    calls = []
    registry = MarketAdapterRegistry([
        adapter("gold_a", "金价 A", "gold", 10, (sample_gold(2300.0), 7.2, "")),
        MarketSourceAdapter(
            key="gold_b",
            name="金价 B",
            category="gold",
            priority=20,
            cache_source="金价 B",
            provides_forex_rate=True,
            fetcher=lambda: calls.append("gold_b") or (sample_gold(2400.0), 7.3, ""),
        ),
    ])
    first = registry.get("gold_a")
    registry = MarketAdapterRegistry([
        MarketSourceAdapter(
            key=first.key,
            name=first.name,
            category=first.category,
            priority=first.priority,
            cache_source=first.cache_source,
            provides_forex_rate=True,
            fetcher=lambda: calls.append("gold_a") or (sample_gold(2300.0), 7.2, ""),
        ),
        registry.get("gold_b"),
    ])
    monkeypatch.setattr(app, "_build_market_adapter_registry", lambda: registry)
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: {
        "market_source_enabled": {"gold": ["gold_b", "gold_a"]},
        "market_source_order": {"gold": ["gold_b", "gold_a"]},
    })
    monkeypatch.setattr(app, "MARKET_CACHE_PATH", str(tmp_path / "market_cache.json"))

    data, rate_info, source, gold_error, forex_error = app.fetch_market_data_result()

    assert calls == ["gold_b"]
    assert data["close"] == 2400.0
    assert rate_info["value"] == 7.3
    assert source == "金价 B"
    assert gold_error == ""
    assert forex_error == ""


def test_app_source_preference_update_rejects_empty_category_and_persists_valid_state(monkeypatch):
    current = dict(app.DEFAULT_SETTINGS)
    saved_payloads = []
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: dict(current))

    def fake_save(payload):
        saved_payloads.append(payload)
        return payload

    monkeypatch.setattr(app, "save_settings", fake_save)

    with pytest.raises(ValueError, match="汇率数据源至少启用一个"):
        app.update_market_source_preferences({
            "enabled": {"gold": ["sina_gold"], "forex": []},
            "order": app.MARKET_SOURCE_DEFAULT_ORDER,
        })

    preferences = app.update_market_source_preferences({
        "enabled": {"gold": ["gold_api"], "forex": ["frankfurter_forex"]},
        "order": {
            "gold": ["gold_api", "sina_gold"],
            "forex": ["frankfurter_forex", "sina_forex"],
        },
    })

    assert saved_payloads[-1]["market_source_enabled"]["gold"] == ["gold_api"]
    assert preferences["order"]["gold"][0] == "gold_api"


def test_market_catalog_marks_current_source_and_exposes_rolling_metrics(monkeypatch):
    monkeypatch.setattr(app, "get_fetch_status", lambda: {
        "sources": {
            "gold": {"source": "Gold API", "cached": False},
            "forex": {"source": "Frankfurter", "cached": False},
        }
    })
    health = {
        "Gold API": {
            "key": "gold_api",
            "sample_count": 10,
            "success_count": 9,
            "success_rate_pct": 90.0,
            "median_latency_ms": 180.0,
            "consecutive_failures": 0,
            "ok": True,
        }
    }

    catalog = app.get_market_adapter_catalog(health_snapshot=health)
    gold_api = next(item for item in catalog["gold"] if item["key"] == "gold_api")

    assert gold_api["current"] is True
    assert gold_api["active"] is True
    assert gold_api["sample_count"] == 10
    assert gold_api["success_rate_pct"] == 90.0


def test_disabled_source_failure_does_not_degrade_operational_summary(monkeypatch):
    settings = {
        **app.DEFAULT_SETTINGS,
        "market_source_enabled": {
            "gold": ["sina_gold"],
            "forex": list(app.MARKET_SOURCE_DEFAULT_ORDER["forex"]),
        },
    }
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: settings)
    monkeypatch.setattr(app, "source_comparison_state", {"status": "insufficient", "summary": {}})
    monkeypatch.setattr(app, "source_health", {
        "新浪贵金属": {
            "name": "新浪贵金属",
            "key": "sina_gold",
            "category": "gold",
            "ok": True,
            "samples": [{"checked_at": "2026-07-27T12:00:00", "ok": True, "cached": False, "elapsed_ms": 100}],
        },
        "Gold API": {
            "name": "Gold API",
            "key": "gold_api",
            "category": "gold",
            "ok": False,
            "samples": [{"checked_at": "2026-07-27T12:00:00", "ok": False, "cached": False, "elapsed_ms": 200}],
        },
        "东方财富": {
            "name": "东方财富",
            "key": "eastmoney_gold",
            "category": "gold",
            "ok": False,
            "samples": [{"checked_at": "2026-07-27T12:00:00", "ok": False, "cached": False, "elapsed_ms": 200}],
        },
    })

    state = app.get_source_health_state()

    assert state["summary"]["failed"] == 0
    assert state["market_observation"] == app.market_observation
    assert state["market_quality_history"] == app.market_quality_history
    assert state["market_quality_summary"]["stored_events"] == len(
        app.market_quality_history
    )
    disabled = next(item for item in state["items"] if item["key"] == "gold_api")
    assert disabled["enabled"] is False
    assert all(item.get("key") != "eastmoney_gold" for item in state["items"])


def test_manual_source_retry_returns_probe_result(monkeypatch):
    registry = MarketAdapterRegistry([
        adapter("probe", "探测源", "forex", 10, (7.22, "")),
    ])
    monkeypatch.setattr(app, "_build_market_adapter_registry", lambda: registry)

    result = app.retry_market_source("probe")

    assert result["ok"] is True
    assert result["name"] == "探测源"
    assert result["message"] == "数据源探测成功"


def test_market_source_socket_contracts_publish_update_and_retry_results(monkeypatch):
    class ImmediateThread:
        def __init__(self, target, daemon=None):
            self.target = target

        def start(self):
            self.target()

    source_state = {"items": [], "summary": {}, "adapters": {"gold": [], "forex": []}}
    custom_actions = []
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app, "fetch_price_once", lambda: None)
    monkeypatch.setattr(app, "update_market_source_preferences", lambda data: data)
    monkeypatch.setattr(app, "upsert_custom_market_source", lambda data: custom_actions.append(("save", data)))
    monkeypatch.setattr(app, "delete_custom_market_source", lambda key: custom_actions.append(("delete", key)))
    monkeypatch.setattr(app, "get_source_health_state", lambda: source_state)
    monkeypatch.setattr(app, "public_settings_snapshot", lambda settings=None: {})
    monkeypatch.setattr(app, "retry_market_source", lambda key: {
        "ok": True,
        "key": key,
        "name": "测试源",
        "message": "数据源探测成功",
        "source_health": source_state,
    })

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("update_market_sources", {
        "enabled": {"gold": ["sina_gold"], "forex": ["sina_forex"]},
        "order": app.MARKET_SOURCE_DEFAULT_ORDER,
    })
    update_events = client.get_received()
    assert any(item["name"] == "market_sources_updated" for item in update_events)
    assert any(item["name"] == "source_health_updated" for item in update_events)

    client.emit("retry_market_source", {"key": "sina_gold"})
    retry_events = [item for item in client.get_received() if item["name"] == "market_source_retry_result"]
    assert retry_events[0]["args"][0]["pending"] is True
    assert retry_events[-1]["args"][0]["ok"] is True

    client.emit("upsert_custom_market_source", {"name": "我的来源"})
    assert custom_actions[-1] == ("save", {"name": "我的来源"})
    assert any(item["name"] == "market_sources_updated" for item in client.get_received())
    client.emit("delete_custom_market_source", {"key": "custom_test"})
    assert custom_actions[-1] == ("delete", "custom_test")
    assert any(item["name"] == "market_sources_updated" for item in client.get_received())
    client.disconnect()


def test_custom_gold_source_requires_a_fresh_quote_time():
    source = {
        "key": "custom_" + "a" * 32,
        "name": "示例接口",
        "url": "https://example.com/gold",
        "price_path": "data.0.price",
        "time_path": "data.0.updatedAt",
    }
    assert normalize_custom_sources([source], strict=True) == [source]
    now = datetime.fromisoformat("2026-10-12T10:00:00+08:00")
    payload = {"data": [{"price": "4100.25", "updatedAt": "2026-10-12T09:59:00+08:00"}]}
    value, error = parse_custom_gold(payload, source, now=now)
    assert error == ""
    assert value["close"] == 4100.25
    assert datetime.fromisoformat(value["timestamp"]).astimezone() == datetime.fromisoformat(
        payload["data"][0]["updatedAt"]
    )

    payload["data"][0]["updatedAt"] = str(int(datetime.fromisoformat(
        "2026-10-12T09:59:00+08:00"
    ).timestamp() * 1000))
    assert parse_custom_gold(payload, source, now=now)[0]["close"] == 4100.25

    payload["data"][0]["updatedAt"] = "2026-10-10T09:59:00+08:00"
    assert "已过期" in parse_custom_gold(payload, source, now=now)[1]
    with pytest.raises(ValueError, match="HTTPS"):
        normalize_custom_sources([{**source, "url": "http://localhost/gold"}], strict=True)


def test_custom_gold_source_save_register_and_delete(monkeypatch):
    current = dict(app.DEFAULT_SETTINGS)
    current["market_source_enabled"] = {
        category: list(keys) for category, keys in app.MARKET_SOURCE_DEFAULT_ORDER.items()
    }
    current["market_source_order"] = {
        category: list(keys) for category, keys in app.MARKET_SOURCE_DEFAULT_ORDER.items()
    }
    monkeypatch.setattr(app, "get_settings_snapshot", lambda: dict(current))

    def save(payload):
        current.clear()
        current.update(payload)
        return dict(current)

    monkeypatch.setattr(app, "save_settings", save)
    key = app.upsert_custom_market_source({
        "name": "备用报价",
        "url": "https://example.com/gold",
        "price_path": "price",
        "time_path": "updatedAt",
    })
    assert key in current["market_source_enabled"]["gold"]
    assert key in current["market_source_order"]["gold"]
    assert app._build_market_adapter_registry().get(key).name == "自定义：备用报价"

    monkeypatch.setattr(app, "record_source_health", lambda *args, **kwargs: None)

    def fake_http(url, label, parser, response_type, **kwargs):
        assert url == "https://example.com/gold"
        assert response_type == "json"
        value, error = parser({"price": 4123.5, "updatedAt": datetime.now().astimezone().isoformat()})
        return AdapterFetchResult(value=value, error=error)

    monkeypatch.setattr(app.market_adapters_core, "fetch_http_source", fake_http)
    assert app._build_market_adapter_registry().get(key).fetch().value["close"] == 4123.5

    app.delete_custom_market_source(key)
    assert current["market_custom_sources"] == []
    assert app._build_market_adapter_registry().get(key) is None
