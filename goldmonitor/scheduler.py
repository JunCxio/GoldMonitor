from datetime import datetime


def parse_iso_datetime(value):
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


def parse_daily_time(value):
    text = str(value or "").strip()
    try:
        hour_text, minute_text = text.split(":", 1)
        hour = int(hour_text)
        minute = int(minute_text)
    except (AttributeError, TypeError, ValueError):
        return None
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None
    return hour, minute


def daily_task_due(schedule_time, last_completed_at="", now=None):
    now = now or datetime.now()
    parsed_time = parse_daily_time(schedule_time)
    if not parsed_time:
        return {
            "due": False,
            "reason": "invalid_schedule",
            "scheduled_at": "",
        }

    hour, minute = parsed_time
    scheduled_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    decision = {
        "due": False,
        "reason": "before_schedule",
        "scheduled_at": scheduled_at.isoformat(timespec="seconds"),
    }

    completed_at = parse_iso_datetime(last_completed_at)
    if completed_at and completed_at.date() >= now.date():
        decision["reason"] = "already_completed"
        return decision
    if now < scheduled_at:
        return decision

    decision.update({"due": True, "reason": "due"})
    return decision
