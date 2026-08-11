from datetime import datetime


ALERT_CHANNEL_KEYS = {
    "email": {
        "warning": "email_warning_enabled",
        "critical": "email_critical_enabled",
        "volatility": "email_volatility_enabled",
    },
    "webhook": {
        "warning": "webhook_warning_enabled",
        "critical": "webhook_critical_enabled",
        "volatility": "webhook_volatility_enabled",
    },
}


def time_to_minutes(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (ValueError, TypeError):
        return None
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


def is_alert_quiet_time(settings, now=None):
    settings = settings or {}
    start = time_to_minutes(settings.get("alert_quiet_start"))
    end = time_to_minutes(settings.get("alert_quiet_end"))
    if start is None or end is None or start == end:
        return False
    now = now or datetime.now()
    current = now.hour * 60 + now.minute
    if start < end:
        return start <= current < end
    return current >= start or current < end


def alert_cooldown_key(entry):
    source = str(entry.get("source") or "alert")
    identifier = (
        entry.get("rule_id")
        or entry.get("threshold_key")
        or entry.get("watch_target_id")
        or entry.get("portfolio_alert_id")
        or entry.get("portfolio_position_id")
        or source
    )
    if entry.get("portfolio_alert_condition"):
        identifier = f"{identifier}:{entry.get('portfolio_alert_condition')}"
    return ":".join(
        [
            str(entry.get("type") or "warning"),
            str(entry.get("mode") or "all"),
            source,
            str(identifier),
        ]
    )


def evaluate_alert_delivery(entry, settings, cooldown_state, now=None):
    if entry.get("force_notify"):
        return {"deliver": True, "reason": ""}
    settings = settings or {}
    cooldown_state = cooldown_state if isinstance(cooldown_state, dict) else {}
    now = now or datetime.now()
    delivery_channels = entry.get("delivery_channels")
    if isinstance(delivery_channels, list) and not delivery_channels:
        return {"deliver": False, "reason": "no_channels"}
    if is_alert_quiet_time(settings, now):
        return {"deliver": False, "reason": "quiet_time"}
    try:
        cooldown_value = entry.get("cooldown_minutes")
        if cooldown_value in (None, "", "inherit"):
            cooldown_value = settings.get("alert_cooldown_minutes", 0)
        cooldown_minutes = int(cooldown_value or 0)
    except (TypeError, ValueError):
        cooldown_minutes = 0
    if cooldown_minutes <= 0:
        return {"deliver": True, "reason": ""}
    key = alert_cooldown_key(entry)
    last_time = cooldown_state.get(key)
    if last_time and (now - last_time).total_seconds() < cooldown_minutes * 60:
        remaining = int(
            cooldown_minutes * 60 - (now - last_time).total_seconds()
        )
        return {
            "deliver": False,
            "reason": "cooldown",
            "remaining_seconds": max(1, remaining),
        }
    cooldown_state[key] = now
    return {"deliver": True, "reason": ""}
