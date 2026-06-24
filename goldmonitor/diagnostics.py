import os


def _count_unread_alerts(recent_alerts):
    return sum(1 for item in recent_alerts if isinstance(item, dict) and not item.get("read"))


def _path_state(path):
    text = str(path or "")
    return {
        "path": text,
        "exists": bool(text and os.path.exists(text)),
    }


def build_health_summary(fetch_status, source_health, price_history, watch_targets, risk_history_count, recent_alerts, paths):
    fetch_status = fetch_status if isinstance(fetch_status, dict) else {}
    source_health = source_health if isinstance(source_health, dict) else {}
    price_history = price_history if isinstance(price_history, dict) else {}
    watch_targets = watch_targets if isinstance(watch_targets, dict) else {}
    recent_alerts = recent_alerts if isinstance(recent_alerts, list) else []
    paths = paths if isinstance(paths, dict) else {}

    messages = []
    source_summary = source_health.get("summary") if isinstance(source_health.get("summary"), dict) else {}
    failed_sources = int(source_summary.get("failed") or 0)
    cached_sources = int(source_summary.get("cached") or 0)

    if fetch_status.get("ok") is False:
        messages.append(str(fetch_status.get("message") or "行情数据异常"))
    if failed_sources:
        messages.append(f"{failed_sources} 个数据源异常")
    if cached_sources:
        messages.append(f"{cached_sources} 个数据源使用缓存")
    if not int(price_history.get("total") or 0):
        messages.append("暂无价格历史样本")

    status = "ok"
    if messages:
        status = "degraded"

    return {
        "status": status,
        "messages": messages,
        "counts": {
            "price_history_points": int(price_history.get("total") or 0),
            "watch_targets_total": int(watch_targets.get("total") or 0),
            "watch_targets_enabled": int(watch_targets.get("enabled") or 0),
            "watch_targets_triggered": int(watch_targets.get("triggered") or 0),
            "risk_history": int(risk_history_count or 0),
            "recent_alerts": len(recent_alerts),
            "unread_alerts": _count_unread_alerts(recent_alerts),
            "failed_sources": failed_sources,
            "cached_sources": cached_sources,
        },
        "storage": {key: _path_state(value) for key, value in sorted(paths.items())},
    }

