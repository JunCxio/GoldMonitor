from datetime import datetime, timezone


UTC = timezone.utc


def local_timezone():
    return datetime.now().astimezone().tzinfo or UTC


def parse_datetime(value, naive_timezone=None):
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
    if parsed.tzinfo is None:
        if naive_timezone is None:
            parsed = parsed.astimezone()
        else:
            parsed = parsed.replace(tzinfo=naive_timezone)
    return parsed.astimezone(UTC)


def to_utc(value, naive_timezone=None):
    return parse_datetime(value, naive_timezone=naive_timezone)


def to_local_naive(value, naive_timezone=None, target_timezone=None):
    parsed = parse_datetime(value, naive_timezone=naive_timezone)
    if parsed is None:
        return None
    local = parsed.astimezone(target_timezone) if target_timezone else parsed.astimezone()
    return local.replace(tzinfo=None)


def iso_utc(value, naive_timezone=None, timespec="seconds"):
    parsed = parse_datetime(value, naive_timezone=naive_timezone)
    if parsed is None:
        return ""
    return parsed.isoformat(timespec=timespec).replace("+00:00", "Z")
