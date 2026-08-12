import os


def _count_unread_alerts(recent_alerts):
    return sum(1 for item in recent_alerts if isinstance(item, dict) and not item.get("read"))


def _notification_summary_status(entry):
    if not isinstance(entry, dict):
        return ""
    summary = entry.get("notification_summary")
    if isinstance(summary, dict):
        return str(summary.get("status") or "")
    notifications = entry.get("notifications")
    if not isinstance(notifications, list):
        return ""
    statuses = {str(item.get("status") or "") for item in notifications if isinstance(item, dict)}
    if "muted" in statuses:
        return "muted"
    if ("failed" in statuses or "skipped" in statuses) and ("sent" in statuses or "queued" in statuses):
        return "partial"
    if "failed" in statuses:
        return "failed"
    if "skipped" in statuses:
        return "skipped"
    if "pending" in statuses:
        return "pending"
    if "sent" in statuses:
        return "sent"
    if "queued" in statuses:
        return "queued"
    if statuses == {"disabled"}:
        return "disabled"
    return ""


def _path_state(path):
    text = str(path or "")
    return {
        "path": text,
        "exists": bool(text and os.path.exists(text)),
    }


def build_health_summary(
    fetch_status,
    source_health,
    price_history,
    watch_targets,
    risk_history_count,
    recent_alerts,
    paths,
    storage_manifest=None,
    background_tasks=None,
):
    fetch_status = fetch_status if isinstance(fetch_status, dict) else {}
    source_health = source_health if isinstance(source_health, dict) else {}
    price_history = price_history if isinstance(price_history, dict) else {}
    watch_targets = watch_targets if isinstance(watch_targets, dict) else {}
    recent_alerts = recent_alerts if isinstance(recent_alerts, list) else []
    paths = paths if isinstance(paths, dict) else {}
    background_tasks = background_tasks if isinstance(background_tasks, dict) else {}

    messages = []
    source_summary = source_health.get("summary") if isinstance(source_health.get("summary"), dict) else {}
    failed_sources = int(source_summary.get("failed") or 0)
    cached_sources = int(source_summary.get("cached") or 0)
    notification_statuses = [_notification_summary_status(item) for item in recent_alerts]
    notification_muted_alerts = sum(1 for status in notification_statuses if status == "muted")
    notification_problem_alerts = sum(1 for status in notification_statuses if status in {"failed", "partial", "skipped"})
    task_summary = background_tasks.get("summary") if isinstance(background_tasks.get("summary"), dict) else {}
    task_attention_count = int(task_summary.get("attention") or 0)
    task_error_count = int(task_summary.get("error") or 0)
    task_delayed_count = int(task_summary.get("delayed") or 0)

    if fetch_status.get("ok") is False:
        messages.append(str(fetch_status.get("message") or "行情数据异常"))
    if failed_sources:
        messages.append(f"{failed_sources} 个数据源异常")
    if cached_sources:
        messages.append(f"{cached_sources} 个数据源使用缓存")
    if notification_problem_alerts:
        messages.append(f"{notification_problem_alerts} 条警报通知未完全送达")
    if notification_muted_alerts:
        messages.append(f"{notification_muted_alerts} 条警报处于静默或冷却记录")
    if task_attention_count:
        messages.append(f"{task_attention_count} 个后台任务连续失败并需要处理")
    elif task_error_count:
        messages.append(f"{task_error_count} 个后台任务最近运行失败")
    if task_delayed_count:
        messages.append(f"{task_delayed_count} 个后台任务调度延迟")
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
            "notification_muted_alerts": notification_muted_alerts,
            "notification_problem_alerts": notification_problem_alerts,
            "background_task_errors": task_error_count,
            "background_task_attention": task_attention_count,
            "background_task_delayed": task_delayed_count,
        },
        "storage": (
            {key: dict(value) for key, value in sorted(storage_manifest.items())}
            if isinstance(storage_manifest, dict)
            else {key: _path_state(value) for key, value in sorted(paths.items())}
        ),
    }
