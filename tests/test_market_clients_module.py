from types import SimpleNamespace


def test_default_registry_exposes_expected_sources_and_dynamic_fetchers():
    from goldmonitor.market_clients import build_default_registry

    calls = []
    registry = build_default_registry(
        fetch_sina_gold=lambda: calls.append("sina_gold") or ({"close": 1}, ""),
        fetch_eastmoney_gold=lambda: (None, "failed"),
        fetch_goldprice=lambda: (None, None, "failed"),
        fetch_stooq_gold=lambda: (None, "failed"),
        fetch_sina_forex=lambda: (7.2, ""),
        fetch_frankfurter_forex=lambda: (None, "failed"),
        fetch_stooq_forex=lambda: (None, "failed"),
    )

    assert [item.key for item in registry.category_adapters("gold")] == [
        "sina_gold", "eastmoney_gold", "goldprice", "stooq_gold",
    ]
    assert registry.get("sina_gold").fetch().value == {"close": 1}
    assert calls == ["sina_gold"]


def test_http_result_records_source_health():
    from goldmonitor.market_adapters import AdapterFetchResult
    from goldmonitor.market_clients import fetch_http_result

    health = []
    result = fetch_http_result(
        "https://example.test",
        "测试源",
        lambda payload: payload,
        category="gold",
        timeout=4,
        proxies={},
        requests_module=SimpleNamespace(),
        fetcher=lambda *args, **kwargs: AdapterFetchResult(value={"close": 2300}, started_at=12.0),
        record_health=lambda *args, **kwargs: health.append((args, kwargs)),
    )

    assert result.value["close"] == 2300
    assert health == [(('测试源', 'gold', True, '', 12.0), {})]


def test_news_fetch_keeps_successful_feeds_when_one_feed_fails():
    from goldmonitor.market_clients import fetch_gold_news

    class Response:
        def __init__(self, payload=None, text="", failed=False):
            self.payload = payload
            self.text = text
            self.failed = failed

        def raise_for_status(self):
            if self.failed:
                raise OSError("failed")

        def json(self):
            return self.payload

    responses = {
        "gdelt": Response(payload={"articles": []}),
        "good": Response(text="<rss />"),
        "bad": Response(failed=True),
    }
    items = fetch_gold_news(
        request_get=lambda url, **kwargs: responses[url],
        gdelt_url="gdelt",
        rss_sources=[
            {"url": "good", "name": "正常源", "kind": "market"},
            {"url": "bad", "name": "异常源", "kind": "market"},
        ],
        parse_gdelt=lambda payload: [{"title": "GDELT"}],
        parse_rss=lambda text, name, kind: [{"title": name}],
        normalize=lambda values: values,
        timeout=4,
        proxies={},
    )

    assert [item["title"] for item in items] == ["GDELT", "正常源"]
