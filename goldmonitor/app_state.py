def _recent_items(items, limit):
    if not isinstance(items, list):
        return []
    return list(items[-int(limit):])


def _latest_history_time(items):
    if not isinstance(items, list) or not items:
        return None
    latest = items[-1]
    if not isinstance(latest, dict):
        return None
    return latest.get("time")


def build_price_api_state(market):
    market = market if isinstance(market, dict) else {}
    price_history = market.get("price_history")
    return {
        "usd": market.get("price_usd"),
        "rmb": market.get("price_rmb"),
        "rate": market.get("usdcny_rate"),
        "gold_source": market.get("gold_price_source"),
        "gold_time": market.get("gold_price_time"),
        "gold_cached": bool(market.get("gold_price_cached")),
        "gold_error": market.get("gold_price_error") or "",
        "rate_source": market.get("usdcny_rate_source"),
        "rate_time": market.get("usdcny_rate_time"),
        "rate_cached": bool(market.get("usdcny_rate_cached")),
        "rate_error": market.get("usdcny_rate_error") or "",
        "previous_usd": market.get("previous_usd"),
        "previous_rmb": market.get("previous_rmb"),
        "time": _latest_history_time(price_history),
        "ok": bool(market.get("last_fetch_ok")),
        "klines_5min": _recent_items(market.get("klines_5min"), 72),
    }


def build_socket_init_state(
    market,
    thresholds=None,
    volatility_config=None,
    watch_targets=None,
    portfolio=None,
    settings=None,
    alert_log=None,
    fetch_status=None,
    source_health=None,
    source_comparison=None,
    price_history_state=None,
    daily=None,
    news=None,
    risk_analysis_history=None,
):
    market = market if isinstance(market, dict) else {}
    state = build_price_api_state(market)
    state.update({
        "history": _recent_items(market.get("price_history"), 60),
        "thresholds": dict(thresholds or {}),
        "volatility_config": dict(volatility_config or {}),
        "watch_targets": watch_targets or {},
        "portfolio": portfolio or {},
        "settings": settings or {},
        "alert_log": _recent_items(alert_log, 20),
        "fetch_status": fetch_status or {},
        "source_health": source_health or {},
        "source_comparison": source_comparison or {},
        "price_history_state": price_history_state or {},
        "daily": daily or {},
    })
    if news is not None:
        state["news"] = news
    if risk_analysis_history is not None:
        state["risk_analysis_history"] = risk_analysis_history
    return state
