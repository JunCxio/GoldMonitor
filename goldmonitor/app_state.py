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
    notification_retry_status=None,
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
    if notification_retry_status is not None:
        state["notification_retry_status"] = notification_retry_status
    return state


def build_runtime_socket_init_state(
    runtime,
    *,
    market_state,
    get_watch_targets,
    get_portfolio,
    get_settings,
    get_fetch_status,
    get_source_health,
    get_source_comparison,
    get_price_history,
    get_alert_rules,
    get_alert_profiles,
    get_daily_digest_status,
    get_news,
    get_risk_history,
    get_notification_retry_status,
    get_background_task_status,
):
    with runtime.lock:
        state = build_socket_init_state(
            market_state(),
            thresholds=dict(runtime.thresholds),
            volatility_config=dict(runtime.volatility_config),
            watch_targets=get_watch_targets(),
            portfolio=get_portfolio(),
            settings=get_settings(),
            alert_log=runtime.alert_log,
            fetch_status=get_fetch_status(),
            source_health=get_source_health(),
            source_comparison=get_source_comparison(),
            price_history_state=get_price_history(limit=240),
            daily={
                "open_usd": runtime.today_open_usd,
                "high_usd": runtime.today_high_usd,
                "low_usd": runtime.today_low_usd,
                "open_rmb": runtime.today_open_rmb,
                "high_rmb": runtime.today_high_rmb,
                "low_rmb": runtime.today_low_rmb,
            },
        )
        state["alert_rules"] = get_alert_rules()
        state["alert_profiles"] = get_alert_profiles()
        state["daily_digest_status"] = get_daily_digest_status()
        state["notification_retry_status"] = get_notification_retry_status()
        state["background_task_status"] = get_background_task_status()
    state["news"] = get_news()
    state["risk_analysis_history"] = get_risk_history()
    return state
