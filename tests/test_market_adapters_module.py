import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class FakeRequestException(Exception):
    pass


class FakeTimeout(FakeRequestException):
    pass


class FakeConnectionError(FakeRequestException):
    pass


class FakeHTTPError(FakeRequestException):
    def __init__(self, status_code):
        super().__init__(f"HTTP {status_code}")
        self.response = type("Response", (), {"status_code": status_code})()


class FakeResponse:
    def __init__(self, text="", payload=None, error=None):
        self.text = text
        self.payload = payload
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class FakeRequests:
    Timeout = FakeTimeout
    ConnectionError = FakeConnectionError
    HTTPError = FakeHTTPError
    RequestException = FakeRequestException

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def adapter(**overrides):
    from goldmonitor.market_adapters import MarketSourceAdapter

    values = {
        "key": "source",
        "name": "测试行情源",
        "category": "gold",
        "priority": 10,
        "cache_source": "测试缓存",
        "provides_forex_rate": False,
        "fetcher": lambda: ({"close": 2300}, ""),
    }
    values.update(overrides)
    return MarketSourceAdapter(**values)


def test_adapter_normalizes_two_and_three_value_fetch_results():
    from goldmonitor.market_adapters import AdapterFetchResult

    gold = adapter(fetcher=lambda: ({"close": 2300}, "")).fetch(monotonic=lambda: 12.5)
    assert gold == AdapterFetchResult(value={"close": 2300}, error="", started_at=12.5)
    assert gold.ok is True

    combined = adapter(fetcher=lambda: ({"close": 2300}, 7.2, "")).fetch(monotonic=lambda: 13.0)
    assert combined.value["close"] == 2300
    assert combined.auxiliary_rate == 7.2
    assert combined.started_at == 13.0
    assert combined.ok is True

    failed = adapter(fetcher=lambda: (None, "数据不可用")).fetch(monotonic=lambda: 14.0)
    assert failed.ok is False
    assert failed.error == "数据不可用"


def test_adapter_descriptor_excludes_fetcher_and_invalid_output_is_safe():
    source = adapter(fetcher=lambda: object())
    descriptor = source.descriptor()
    assert descriptor == {
        "key": "source",
        "name": "测试行情源",
        "category": "gold",
        "priority": 10,
        "cache_source": "测试缓存",
        "provides_forex_rate": False,
    }
    assert "fetcher" not in descriptor
    assert not any(callable(value) for value in descriptor.values())
    result = source.fetch(monotonic=lambda: 2.0)
    assert result.ok is False
    assert result.error == "测试行情源返回格式异常"


def test_registry_validates_keys_and_orders_by_priority_then_registration():
    from goldmonitor.market_adapters import MarketAdapterRegistry

    first = adapter(key="first", priority=20)
    second = adapter(key="second", priority=10)
    third = adapter(key="third", priority=10)
    forex = adapter(key="forex", category="forex", priority=1)
    registry = MarketAdapterRegistry([first, second, third, forex])

    assert [item.key for item in registry.category_adapters("gold")] == ["second", "third", "first"]
    assert registry.get("second") is second
    assert registry.get("missing") is None
    assert [item["key"] for item in registry.catalog("gold")] == ["second", "third", "first"]
    assert [item["key"] for item in registry.catalog()] == ["forex", "second", "third", "first"]

    with pytest.raises(ValueError, match="duplicate market adapter key"):
        registry.register(adapter(key="second"))


def test_fetch_http_source_supports_text_json_and_parser_shapes():
    from goldmonitor.market_adapters import fetch_http_source

    text_requests = FakeRequests(response=FakeResponse(text="2300.50"))
    text_result = fetch_http_source(
        "https://example.test/gold",
        "新浪贵金属",
        lambda payload: (float(payload), ""),
        headers={"User-Agent": "test"},
        timeout=3,
        proxies={"https": "http://proxy.test"},
        requests_module=text_requests,
        monotonic=lambda: 10.0,
    )
    assert text_result.value == 2300.5
    assert text_result.started_at == 10.0
    assert text_requests.calls == [("https://example.test/gold", {
        "headers": {"User-Agent": "test"},
        "timeout": 3,
        "proxies": {"https": "http://proxy.test"},
    })]

    json_requests = FakeRequests(response=FakeResponse(payload={"price": 2301, "rate": 7.2}))
    json_result = fetch_http_source(
        "https://example.test/combined",
        "GoldPrice",
        lambda payload: (payload["price"], payload["rate"], ""),
        "json",
        requests_module=json_requests,
        monotonic=lambda: 11.0,
    )
    assert json_result.value == 2301
    assert json_result.auxiliary_rate == 7.2
    assert json_result.ok is True


def test_fetch_http_source_distinguishes_request_failures():
    from goldmonitor.market_adapters import fetch_http_source

    cases = [
        ("新浪汇率", FakeTimeout(), "新浪汇率请求超时"),
        ("GoldPrice", FakeTimeout(), "GoldPrice 请求超时"),
        ("新浪汇率", FakeConnectionError(), "新浪汇率网络连接失败"),
        ("GoldPrice", FakeHTTPError(503), "GoldPrice HTTP错误 503"),
        ("GoldPrice", FakeRequestException("bad gateway"), "GoldPrice 请求失败: bad gateway"),
    ]
    for source_label, failure, expected in cases:
        result = fetch_http_source(
            "https://example.test",
            source_label,
            lambda payload: (payload, ""),
            requests_module=FakeRequests(error=failure),
            monotonic=lambda: 20.0,
        )
        assert result.error == expected
        assert result.started_at == 20.0
        assert result.ok is False


def test_fetch_http_source_reports_json_format_errors_separately():
    from goldmonitor.market_adapters import fetch_http_source

    bad_json = json.JSONDecodeError("bad json", "{", 1)
    result = fetch_http_source(
        "https://example.test",
        "GoldPrice",
        lambda payload: (payload, ""),
        "json",
        requests_module=FakeRequests(response=FakeResponse(payload=bad_json)),
        monotonic=lambda: 30.0,
    )
    assert result.error == "GoldPrice 返回格式异常"
    assert result.ok is False


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
    print("market adapters module checks passed.")
