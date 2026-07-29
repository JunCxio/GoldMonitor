from datetime import datetime

from goldmonitor import market_adapters as market_adapters_core


def build_default_registry(
    *,
    fetch_sina_gold,
    fetch_eastmoney_gold,
    fetch_goldprice,
    fetch_stooq_gold,
    fetch_sina_forex,
    fetch_frankfurter_forex,
    fetch_stooq_forex,
):
    adapter = market_adapters_core.MarketSourceAdapter
    return market_adapters_core.MarketAdapterRegistry([
        adapter("sina_gold", "新浪贵金属", "gold", 10, "新浪贵金属", False, fetch_sina_gold),
        adapter("eastmoney_gold", "东方财富", "gold", 20, "东方财富", False, fetch_eastmoney_gold),
        adapter("goldprice", "GoldPrice", "gold", 30, "GoldPrice", True, fetch_goldprice),
        adapter("stooq_gold", "Stooq", "gold", 40, "Stooq", False, fetch_stooq_gold),
        adapter("sina_forex", "新浪", "forex", 10, "新浪", False, fetch_sina_forex),
        adapter("frankfurter_forex", "Frankfurter", "forex", 20, "Frankfurter", False, fetch_frankfurter_forex),
        adapter("stooq_forex", "Stooq", "forex", 30, "Stooq", False, fetch_stooq_forex),
    ])


def fetch_http_result(
    url,
    source_label,
    parser,
    *,
    category,
    response_type="text",
    headers=None,
    timeout,
    proxies,
    requests_module,
    fetcher,
    record_health,
):
    result = fetcher(
        url,
        source_label,
        parser,
        response_type,
        headers=headers,
        timeout=timeout,
        proxies=proxies,
        requests_module=requests_module,
    )
    record_health(
        source_label,
        category,
        result.value is not None,
        result.error,
        result.started_at,
    )
    return result


def fetch_usdcny_rate_result(
    registry,
    *,
    save_cache,
    load_valid_cache,
    record_health,
    now_factory=datetime.now,
):
    errors = []
    for adapter in registry.category_adapters("forex"):
        result = adapter.fetch()
        if result.value is not None:
            now_iso = now_factory().isoformat()
            try:
                return save_cache(result.value, adapter.cache_source, now_iso), ""
            except (OSError, ValueError) as exc:
                return {
                    "value": result.value,
                    "source": adapter.cache_source,
                    "timestamp": now_iso,
                    "cached": False,
                }, f"汇率缓存保存失败: {exc}"
        if result.error:
            errors.append(result.error)

    cached = load_valid_cache()
    if cached:
        record_health(
            "缓存汇率",
            "forex",
            True,
            "实时汇率源不可用，使用缓存",
            None,
            cached=True,
        )
        return cached, "；".join(errors)
    return None, "；".join(errors) or "所有汇率源均不可用"


def fetch_gold_news(
    *,
    request_get,
    gdelt_url,
    rss_sources,
    parse_gdelt,
    parse_rss,
    normalize,
    timeout,
    proxies,
):
    items = []
    gdelt_response = request_get(gdelt_url, timeout=timeout, proxies=proxies)
    gdelt_response.raise_for_status()
    items.extend(parse_gdelt(gdelt_response.json()))

    for source in rss_sources:
        try:
            response = request_get(source["url"], timeout=timeout, proxies=proxies)
            response.raise_for_status()
            items.extend(parse_rss(response.text, source["name"], source["kind"]))
        except Exception:
            continue
    return normalize(items)
