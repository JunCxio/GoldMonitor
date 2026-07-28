import time
from datetime import datetime

from goldmonitor import market_data as market_data_core


def market_source_matches(descriptor, source_name):
    source_name = str(source_name or "").strip()
    if not source_name:
        return False
    candidates = {
        str(descriptor.get("name") or "").strip(),
        str(descriptor.get("cache_source") or "").strip(),
    }
    return any(
        candidate and (candidate == source_name or candidate in source_name)
        for candidate in candidates
    )


def build_market_adapter_catalog(registry, preferences, health_snapshot, fetch_status):
    health_snapshot = health_snapshot if isinstance(health_snapshot, dict) else {}
    fetch_status = fetch_status if isinstance(fetch_status, dict) else {}
    health_by_key = {
        str(item.get("key") or ""): item
        for item in health_snapshot.values()
        if isinstance(item, dict) and item.get("key")
    }
    fetch_sources = fetch_status.get("sources", {})
    result = {}
    metric_keys = (
        "sample_count",
        "success_count",
        "failure_count",
        "success_rate_pct",
        "cache_rate_pct",
        "average_latency_ms",
        "median_latency_ms",
        "consecutive_failures",
        "last_checked",
        "last_recovered_at",
        "error",
        "ok",
        "cached",
    )
    for category, ordered_keys in preferences["order"].items():
        enabled_keys = set(preferences["enabled"].get(category) or [])
        current_source = (
            fetch_sources.get(category)
            if isinstance(fetch_sources.get(category), dict)
            else {}
        )
        category_items = []
        for index, key in enumerate(ordered_keys):
            adapter = registry.get(key)
            if adapter is None:
                continue
            descriptor = adapter.descriptor()
            descriptor.update({
                "priority": (index + 1) * 10,
                "order": index,
                "enabled": key in enabled_keys,
                "current": market_source_matches(descriptor, current_source.get("source")),
                "current_cached": False,
                "active": False,
            })
            descriptor["current_cached"] = bool(
                descriptor["current"] and current_source.get("cached")
            )
            descriptor["active"] = bool(
                descriptor["current"]
                and descriptor["enabled"]
                and not current_source.get("cached")
            )
            metrics = health_by_key.get(key) or {}
            descriptor.update({metric_key: metrics.get(metric_key) for metric_key in metric_keys})
            category_items.append(descriptor)
        result[category] = category_items
    return result


def build_source_health_state(
    health_snapshot,
    *,
    comparison,
    adapters,
    preferences,
    fetch_status,
    window_size,
):
    state = market_data_core.build_source_health_state(
        health_snapshot,
        comparison=comparison,
        window_size=window_size,
    )
    adapter_by_key = {
        item.get("key"): item
        for category_items in adapters.values()
        for item in category_items
        if isinstance(item, dict) and item.get("key")
    }
    for item in state["items"]:
        adapter = adapter_by_key.get(item.get("key"))
        if not adapter:
            continue
        item.update({
            "enabled": adapter.get("enabled"),
            "active": adapter.get("active"),
            "current": adapter.get("current"),
            "order": adapter.get("order"),
        })
    operational_items = [
        item for item in state["items"]
        if not item.get("key") or item.get("enabled") is not False
    ]
    rolling_samples = sum(int(item.get("sample_count") or 0) for item in operational_items)
    rolling_successes = sum(int(item.get("success_count") or 0) for item in operational_items)
    state["summary"].update({
        "total": len(operational_items),
        "ok": sum(1 for item in operational_items if item.get("ok")),
        "failed": sum(1 for item in operational_items if item.get("ok") is False),
        "cached": sum(1 for item in operational_items if item.get("cached")),
        "rolling_samples": rolling_samples,
        "rolling_success_rate_pct": (
            round(rolling_successes / rolling_samples * 100, 1)
            if rolling_samples else None
        ),
    })
    state["adapters"] = adapters
    state["preferences"] = preferences
    state["quality"] = market_data_core.build_market_quality(
        fetch_status=fetch_status,
        source_health=state,
        comparison=comparison,
    )
    return state


def fetch_market_data_result(
    registry,
    *,
    save_xauusd_cache,
    save_usdcny_cache,
    fetch_usdcny_rate_result,
    load_valid_xauusd_cache,
    record_source_health,
    now_factory=datetime.now,
):
    errors = []
    for adapter in registry.category_adapters("gold"):
        result = adapter.fetch()
        data = result.value
        if data is None:
            if result.error:
                errors.append(result.error)
            continue
        try:
            save_xauusd_cache(data, adapter.cache_source)
        except (OSError, ValueError):
            pass
        if result.auxiliary_rate is not None:
            now_iso = now_factory().isoformat()
            try:
                rate_info = save_usdcny_cache(
                    result.auxiliary_rate,
                    adapter.cache_source,
                    now_iso,
                )
                return data, rate_info, adapter.cache_source, "", ""
            except (OSError, ValueError) as exc:
                return data, {
                    "value": result.auxiliary_rate,
                    "source": adapter.cache_source,
                    "timestamp": now_iso,
                    "cached": False,
                }, adapter.cache_source, "", f"汇率缓存保存失败: {exc}"
        rate_info, forex_error = fetch_usdcny_rate_result()
        return data, rate_info, adapter.cache_source, "", forex_error

    rate_info, forex_error = fetch_usdcny_rate_result()
    cached_gold = load_valid_xauusd_cache()
    gold_error = "；".join(errors) or "所有金价接口均不可用"
    if cached_gold:
        cache_source = cached_gold.get("source") or "缓存金价"
        record_source_health("缓存金价", "gold", True, gold_error, None, cached=True)
        return cached_gold, rate_info, f"缓存金价（{cache_source}）", gold_error, forex_error
    return None, rate_info, "", gold_error, forex_error


def aggregate_klines(history_items, builder, limit=96):
    return builder(history_items, limit=limit)


def background_loop(fetch_once, interval=10, sleep=time.sleep):
    while True:
        fetch_once()
        sleep(interval)


class MarketRuntime:
    def __init__(
        self,
        *,
        state_getter,
        state_committer,
        state_lock,
        refresh_lock,
        fetch_market_data_result,
        refresh_source_comparison,
        get_source_comparison_state,
        aggregate_klines,
        add_price_history_entry,
        emit,
        build_fetch_status,
        build_price_history_state,
        format_price_title,
        update_desktop_price_title,
        update_floating_price,
        check_alert_rules,
        now_factory=datetime.now,
        ounce_to_gram=31.1035,
    ):
        self.state_getter = state_getter
        self.state_committer = state_committer
        self.state_lock = state_lock
        self.refresh_lock = refresh_lock
        self.fetch_market_data_result = fetch_market_data_result
        self.refresh_source_comparison = refresh_source_comparison
        self.get_source_comparison_state = get_source_comparison_state
        self.aggregate_klines = aggregate_klines
        self.add_price_history_entry = add_price_history_entry
        self.emit = emit
        self.build_fetch_status = build_fetch_status
        self.build_price_history_state = build_price_history_state
        self.format_price_title = format_price_title
        self.update_desktop_price_title = update_desktop_price_title
        self.update_floating_price = update_floating_price
        self.check_alert_rules = check_alert_rules
        self.now_factory = now_factory
        self.ounce_to_gram = ounce_to_gram

    def fetch_once(self):
        if not self.refresh_lock.acquire(blocking=False):
            self.emit(
                "fetch_status",
                self.build_fetch_status(False, "已有行情刷新正在进行", retryable=False),
            )
            return False
        try:
            data, rate_info, source_name, gold_error, forex_error = self.fetch_market_data_result()
            now = self.now_factory()
            now_str = now.strftime("%H:%M:%S")
            now_iso = now.isoformat()
            today_str = now.strftime("%Y-%m-%d")
            source_comparison = (
                self.refresh_source_comparison(
                    data,
                    source_name,
                    primary_cached=bool(data.get("cached")) if isinstance(data, dict) else False,
                )
                if data is not None
                else self.get_source_comparison_state()
            )

            with self.state_lock:
                state = self.state_getter()
                if data is None:
                    state["last_fetch_ok"] = False
                    state["last_fetch_error"] = gold_error or "Stooq 金价接口无响应或返回格式异常"
                    state["last_fetch_time"] = now_iso
                    self.state_committer(state)
                    status = self.build_fetch_status(
                        False,
                        "无法获取金价数据，请检查网络或稍后重试",
                        gold_ok=False,
                        forex_ok=rate_info is not None,
                        error=state["last_fetch_error"],
                        gold_source=source_name,
                        forex_source=rate_info.get("source", "") if isinstance(rate_info, dict) else "",
                        forex_cached=bool(rate_info.get("cached")) if isinstance(rate_info, dict) else False,
                        gold_error=gold_error or "",
                        forex_error=forex_error or "",
                        retryable=True,
                    )
                    self.emit("fetch_error", status)
                    self.emit("fetch_status", status)
                    return False

                cny_rate = rate_info.get("value") if isinstance(rate_info, dict) else None
                rate_source = rate_info.get("source", "") if isinstance(rate_info, dict) else ""
                rate_time = rate_info.get("timestamp") if isinstance(rate_info, dict) else None
                rate_cached = bool(rate_info.get("cached")) if isinstance(rate_info, dict) else False
                source_name = source_name or data.get("source", "")
                gold_cached = bool(data.get("cached")) or str(source_name).startswith("缓存金价")
                gold_time = data.get("timestamp") if gold_cached else now_iso
                status_ok = not gold_cached and (
                    cny_rate is not None or state["usdcny_rate"] is not None
                )
                state["last_fetch_ok"] = status_ok
                if status_ok:
                    state["last_fetch_error"] = ""
                elif gold_cached:
                    state["last_fetch_error"] = gold_error or "实时金价源暂不可用，正在使用缓存金价"
                else:
                    state["last_fetch_error"] = forex_error or "汇率源暂未返回，人民币价格暂不可用"
                state["last_fetch_time"] = now_iso
                state["gold_price_source"] = source_name
                state["gold_price_time"] = gold_time
                state["gold_price_cached"] = gold_cached
                state["gold_price_error"] = gold_error or ""
                if cny_rate:
                    state["usdcny_rate"] = cny_rate
                    state["usdcny_rate_source"] = rate_source
                    state["usdcny_rate_time"] = rate_time
                    state["usdcny_rate_cached"] = rate_cached
                    state["usdcny_rate_error"] = forex_error or ""
                state["previous_usd"] = state["price_usd"]
                state["previous_rmb"] = state["price_rmb"]
                state["price_usd"] = data["close"]

                if state["usdcny_rate"]:
                    state["price_rmb"] = round(
                        state["price_usd"] * state["usdcny_rate"] / self.ounce_to_gram,
                        2,
                    )
                if state["previous_rmb"] is None:
                    state["previous_rmb"] = state["price_rmb"]

                if state["today_date"] != today_str:
                    state["today_date"] = today_str
                    state["today_open_usd"] = data["open"]
                    state["today_high_usd"] = data["high"]
                    state["today_low_usd"] = data["low"]
                    if state["usdcny_rate"]:
                        state["today_open_rmb"] = round(
                            state["today_open_usd"] * state["usdcny_rate"] / self.ounce_to_gram,
                            2,
                        )
                        state["today_high_rmb"] = round(
                            data["high"] * state["usdcny_rate"] / self.ounce_to_gram,
                            2,
                        )
                        state["today_low_rmb"] = round(
                            data["low"] * state["usdcny_rate"] / self.ounce_to_gram,
                            2,
                        )
                else:
                    if state["today_open_usd"] is None:
                        state["today_open_usd"] = data["open"]
                    state["today_high_usd"] = max(state["today_high_usd"] or 0, data["high"])
                    state["today_low_usd"] = min(state["today_low_usd"] or float("inf"), data["low"])
                    if state["usdcny_rate"]:
                        state["today_high_rmb"] = round(
                            state["today_high_usd"] * state["usdcny_rate"] / self.ounce_to_gram,
                            2,
                        )
                        state["today_low_rmb"] = round(
                            state["today_low_usd"] * state["usdcny_rate"] / self.ounce_to_gram,
                            2,
                        )
                        if state["today_open_rmb"] is None:
                            state["today_open_rmb"] = round(
                                state["today_open_usd"] * state["usdcny_rate"] / self.ounce_to_gram,
                                2,
                            )

                daily_change_usd = (
                    round(state["price_usd"] - state["today_open_usd"], 2)
                    if state["today_open_usd"] else 0
                )
                daily_pct_usd = (
                    round(daily_change_usd / state["today_open_usd"] * 100, 2)
                    if state["today_open_usd"] else 0
                )
                daily_change_rmb = (
                    round(state["price_rmb"] - state["today_open_rmb"], 2)
                    if state["price_rmb"] and state["today_open_rmb"] else 0
                )
                daily_pct_rmb = (
                    round(daily_change_rmb / state["today_open_rmb"] * 100, 2)
                    if state["today_open_rmb"] and state["today_open_rmb"] != 0 else 0
                )

                history_entry = {
                    "usd": state["price_usd"],
                    "rmb": state["price_rmb"],
                    "rate": state["usdcny_rate"],
                    "time": now_str,
                    "timestamp": now_iso,
                }
                state["price_history"].append(history_entry)
                if len(state["price_history"]) > 360:
                    state["price_history"] = state["price_history"][-360:]
                self.add_price_history_entry(history_entry)
                state["klines_5min"] = self.aggregate_klines(state["price_history"])

                chg_usd = (
                    round(state["price_usd"] - state["previous_usd"], 2)
                    if state["previous_usd"] else 0
                )
                pct_usd = (
                    round(chg_usd / state["previous_usd"] * 100, 2)
                    if state["previous_usd"] else 0
                )
                chg_rmb = (
                    round(state["price_rmb"] - state["previous_rmb"], 2)
                    if state["price_rmb"] and state["previous_rmb"] else 0
                )
                pct_rmb = (
                    round(chg_rmb / state["previous_rmb"] * 100, 2)
                    if state["previous_rmb"] and state["price_rmb"] else 0
                )
                if state["previous_rmb"] is None and state["price_rmb"] is not None:
                    state["previous_rmb"] = state["price_rmb"]

                daily_stats = {
                    "open_usd": state["today_open_usd"],
                    "high_usd": state["today_high_usd"],
                    "low_usd": state["today_low_usd"],
                    "open_rmb": state["today_open_rmb"],
                    "high_rmb": state["today_high_rmb"],
                    "low_rmb": state["today_low_rmb"],
                    "change_usd": daily_change_usd,
                    "pct_usd": daily_pct_usd,
                    "change_rmb": daily_change_rmb,
                    "pct_rmb": daily_pct_rmb,
                }
                self.state_committer(state)

                self.emit("price_update", {
                    "usd": state["price_usd"],
                    "rmb": state["price_rmb"],
                    "rate": state["usdcny_rate"],
                    "gold_source": state["gold_price_source"],
                    "gold_time": state["gold_price_time"],
                    "gold_cached": state["gold_price_cached"],
                    "gold_error": state["gold_price_error"],
                    "rate_source": state["usdcny_rate_source"],
                    "rate_time": state["usdcny_rate_time"],
                    "rate_cached": state["usdcny_rate_cached"],
                    "rate_error": state["usdcny_rate_error"],
                    "previous_usd": state["previous_usd"],
                    "previous_rmb": state["previous_rmb"],
                    "change_usd": chg_usd,
                    "change_pct_usd": pct_usd,
                    "change_rmb": chg_rmb,
                    "change_pct_rmb": pct_rmb,
                    "time": now_str,
                    "timestamp": now_iso,
                    "klines_5min": list(state["klines_5min"][-72:]),
                    "daily": daily_stats,
                    "source_comparison": source_comparison,
                })
                desktop_title = self.format_price_title(state["price_rmb"], state["price_usd"])
                self.update_desktop_price_title(desktop_title)
                self.update_floating_price(state["price_rmb"], state["price_usd"], pct_rmb)
                self.check_alert_rules(now_str, now=now)

                if cny_rate:
                    rate_message = (
                        f"使用缓存汇率 {cny_rate:.4f}（{rate_source}）"
                        if rate_cached else f"汇率已更新 {cny_rate:.4f}（{rate_source}）"
                    )
                else:
                    rate_message = "汇率暂未更新"
                gold_message = (
                    f"使用缓存金价（{source_name}）"
                    if gold_cached else f"金价已更新（{source_name}）"
                )
                self.emit("fetch_status", self.build_fetch_status(
                    status_ok,
                    f"{gold_message}，{rate_message}",
                    gold_ok=not gold_cached,
                    forex_ok=cny_rate is not None,
                    error="" if status_ok else state["last_fetch_error"],
                    gold_cached=gold_cached,
                    forex_cached=rate_cached,
                    gold_source=source_name,
                    forex_source=rate_source,
                    gold_error=gold_error or "",
                    forex_error=forex_error or "",
                    retryable=True,
                ))
                history_state = self.build_price_history_state(limit=240)
                history_state["scope"] = "live"
                self.emit("price_history_updated", history_state)
                return True
        finally:
            self.refresh_lock.release()

    def run(self, interval=10, sleep=time.sleep):
        while True:
            self.fetch_once()
            sleep(interval)
