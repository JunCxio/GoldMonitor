from datetime import datetime, timedelta

from goldmonitor.notification_delivery import notification_error_retryable


NOTIFICATION_RETRY_STATUSES = {"failed", "skipped"}
NOTIFICATION_RETRY_INTERVAL_MINUTES = 10
NOTIFICATION_RETRY_WINDOW_HOURS = 24
NOTIFICATION_RETRY_MAX_ROUNDS = 3
NOTIFICATION_RETRY_BATCH_LIMIT = 10


def _nonnegative_int(value):
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def parse_retry_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def retryable_notification(item):
    if not isinstance(item, dict):
        return False
    if str(item.get("status") or "") not in NOTIFICATION_RETRY_STATUSES:
        return False
    if "retryable" in item:
        return bool(item.get("retryable"))
    return notification_error_retryable(item.get("message"))


def _notification_items(value):
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def failed_notification_channels(entry, retryable_only=False):
    channels = []
    for item in _notification_items((entry or {}).get("notifications")):
        status = str(item.get("status") or "")
        channel = str(item.get("channel") or "").strip()
        if status not in NOTIFICATION_RETRY_STATUSES or not channel:
            continue
        if retryable_only and not retryable_notification(item):
            continue
        if channel not in channels:
            channels.append(channel)
    return channels


def retry_channel_results(entry, channels):
    expected = [str(channel or "").strip() for channel in list(channels or [])]
    expected = [channel for channel in expected if channel]
    items = {
        str(item.get("channel") or "").strip(): item
        for item in _notification_items((entry or {}).get("notifications"))
        if str(item.get("channel") or "").strip()
    }
    results = []
    for channel in expected:
        item = items.get(channel) or {}
        status = str(item.get("status") or "")
        results.append({
            "channel": channel,
            "status": status or "missing",
            "ok": status in {"sent", "queued"},
            "message": str(item.get("message") or ""),
        })
    return results


def build_retry_notifications(entry, planned, retryable_only=False):
    entry = entry if isinstance(entry, dict) else {}
    existing = _notification_items(entry.get("notifications"))
    planned_items = _notification_items(planned)
    planned_by_channel = {
        str(item.get("channel") or ""): item
        for item in planned_items
        if str(item.get("channel") or "")
    }

    if not existing and not retryable_only:
        notifications = [
            dict(item) for item in planned_items if item.get("status") == "pending"
        ]
        return {
            "notifications": notifications,
            "channels": [str(item.get("channel") or "") for item in notifications],
        }

    channels = []
    notifications = []
    for item in existing:
        channel = str(item.get("channel") or "").strip()
        status = str(item.get("status") or "")
        should_retry = status in NOTIFICATION_RETRY_STATUSES
        if should_retry and retryable_only:
            should_retry = retryable_notification(item)
        replacement = planned_by_channel.get(channel)
        if should_retry and replacement and replacement.get("status") == "pending":
            retry_item = dict(replacement)
            retry_item["previous_attempts"] = int(item.get("attempts") or 0)
            notifications.append(retry_item)
            channels.append(channel)
        else:
            notifications.append(item)
    return {"notifications": notifications, "channels": channels}


def _entry_origin_time(entry):
    for key in ("timestamp", "created_at"):
        parsed = parse_retry_datetime((entry or {}).get(key))
        if parsed:
            return parsed
    completed = [
        parse_retry_datetime(item.get("completed_at"))
        for item in _notification_items((entry or {}).get("notifications"))
    ]
    completed = [value for value in completed if value is not None]
    return min(completed) if completed else None


def _retry_due_time(entry):
    explicit = parse_retry_datetime((entry or {}).get("notification_retry_next_at"))
    if explicit:
        return explicit
    completed = [
        parse_retry_datetime(item.get("completed_at"))
        for item in _notification_items((entry or {}).get("notifications"))
        if retryable_notification(item)
    ]
    completed = [value for value in completed if value is not None]
    base = max(completed) if completed else _entry_origin_time(entry)
    return base + timedelta(minutes=NOTIFICATION_RETRY_INTERVAL_MINUTES) if base else None


def notification_retry_decision(
    entry,
    *,
    now=None,
    max_rounds=NOTIFICATION_RETRY_MAX_ROUNDS,
    window_hours=NOTIFICATION_RETRY_WINDOW_HOURS,
):
    now = now or datetime.now()
    channels = failed_notification_channels(entry, retryable_only=True)
    if not channels:
        return {"eligible": False, "reason": "not_retryable", "channels": []}
    origin = _entry_origin_time(entry)
    if not origin or now - origin > timedelta(hours=max(1, int(window_hours))):
        return {"eligible": False, "reason": "expired", "channels": channels}
    retry_count = _nonnegative_int(
        (entry or {}).get("notification_auto_retry_count")
    )
    if retry_count >= max(1, int(max_rounds)):
        return {"eligible": False, "reason": "exhausted", "channels": channels}
    due_at = _retry_due_time(entry) or now
    return {
        "eligible": due_at <= now,
        "reason": "due" if due_at <= now else "not_due",
        "channels": channels,
        "due_at": due_at.isoformat(timespec="seconds"),
        "retry_count": retry_count,
    }


def apply_notification_retry_metadata(entry, now=None):
    now = now or datetime.now()
    updated = dict(entry or {})
    notifications = _notification_items(updated.get("notifications"))
    updated["notifications"] = notifications
    if any(item.get("status") == "pending" for item in notifications):
        updated["notification_retry_next_at"] = ""
        return updated
    retryable_failures = [item for item in notifications if retryable_notification(item)]
    retry_count = _nonnegative_int(updated.get("notification_auto_retry_count"))
    origin = _entry_origin_time(updated)
    within_window = bool(
        origin
        and now - origin <= timedelta(hours=NOTIFICATION_RETRY_WINDOW_HOURS)
    )
    if retryable_failures and retry_count < NOTIFICATION_RETRY_MAX_ROUNDS and within_window:
        updated["notification_retry_next_at"] = (
            now + timedelta(minutes=NOTIFICATION_RETRY_INTERVAL_MINUTES)
        ).isoformat(timespec="seconds")
    else:
        updated["notification_retry_next_at"] = ""
    return updated


def build_notification_retry_status(
    entries,
    *,
    enabled,
    now=None,
    force_due=False,
):
    now = now or datetime.now()
    candidates = []
    pending_count = 0
    exhausted_count = 0
    expired_count = 0
    non_retryable_count = 0
    next_times = []
    for entry in _notification_items(entries):
        decision = notification_retry_decision(entry, now=now)
        reason = decision.get("reason")
        if reason in {"due", "not_due"}:
            pending_count += 1
        elif reason == "exhausted":
            exhausted_count += 1
        elif reason == "expired":
            expired_count += 1
        elif any(
            str(item.get("status") or "") in NOTIFICATION_RETRY_STATUSES
            for item in _notification_items(entry.get("notifications"))
        ):
            non_retryable_count += 1
        if reason == "due" or (force_due and reason == "not_due"):
            candidates.append({
                "id": str(entry.get("id") or ""),
                "channels": list(decision.get("channels") or []),
                "due_at": decision.get("due_at") or "",
            })
        elif reason == "not_due" and decision.get("due_at"):
            next_times.append(decision["due_at"])
    candidates.sort(key=lambda item: (item.get("due_at") or "", item.get("id") or ""))
    return {
        "enabled": bool(enabled),
        "pending_count": pending_count,
        "eligible_count": len(candidates),
        "exhausted_count": exhausted_count,
        "expired_count": expired_count,
        "non_retryable_count": non_retryable_count,
        "next_retry_at": min(next_times) if next_times else "",
        "interval_minutes": NOTIFICATION_RETRY_INTERVAL_MINUTES,
        "window_hours": NOTIFICATION_RETRY_WINDOW_HOURS,
        "max_rounds": NOTIFICATION_RETRY_MAX_ROUNDS,
        "candidates": candidates[:NOTIFICATION_RETRY_BATCH_LIMIT],
    }
