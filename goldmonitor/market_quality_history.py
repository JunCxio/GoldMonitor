import json
import os
from datetime import datetime, timedelta

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload
from goldmonitor.market_observation import (
    MARKET_OBSERVATION_FIELDS,
    market_observation_snapshot,
    record_market_quality_event,
)
from goldmonitor.time_utils import iso_utc, parse_datetime


MARKET_QUALITY_HISTORY_SCHEMA_VERSION = 1
DEFAULT_MARKET_QUALITY_HISTORY_LIMIT = 2000
DEFAULT_MARKET_QUALITY_RETENTION_DAYS = 30
DEFAULT_MARKET_QUALITY_RECENT_LIMIT = 20

MARKET_QUALITY_BUSINESS_GATES = (
    ("history", "历史入库", "usable_for_history"),
    ("alert", "预警判断", "usable_for_alert"),
    ("automation", "定投执行", "usable_for_automation"),
)


def _positive_int(value, default=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, number)


def normalize_market_quality_event(value):
    if not isinstance(value, dict):
        return None
    snapshot = market_observation_snapshot(value)
    first_seen_at = iso_utc(value.get("first_seen_at") or snapshot.get("received_at"))
    last_seen_at = iso_utc(value.get("last_seen_at") or first_seen_at)
    first_seen = parse_datetime(first_seen_at)
    last_seen = parse_datetime(last_seen_at)
    if first_seen is None or last_seen is None:
        return None
    if last_seen < first_seen:
        last_seen = first_seen
        last_seen_at = iso_utc(last_seen)
    event = {
        field: snapshot.get(field)
        for field in MARKET_OBSERVATION_FIELDS
        if field in snapshot
    }
    event.update({
        "first_seen_at": first_seen_at,
        "last_seen_at": last_seen_at,
        "occurrences": _positive_int(value.get("occurrences"), 1),
        "session_id": str(value.get("session_id") or ""),
    })
    event["blocked_reasons"] = list(snapshot.get("blocked_reasons") or [])
    return event


def prune_market_quality_events(
    events,
    *,
    now=None,
    retention_days=DEFAULT_MARKET_QUALITY_RETENTION_DAYS,
    limit=DEFAULT_MARKET_QUALITY_HISTORY_LIMIT,
):
    now_value = parse_datetime(now or datetime.now().astimezone())
    cutoff = now_value - timedelta(days=max(1, int(retention_days or 1)))
    normalized = []
    for raw_event in list(events or []):
        event = normalize_market_quality_event(raw_event)
        if event is None:
            continue
        last_seen = parse_datetime(event["last_seen_at"])
        if last_seen is None or last_seen < cutoff:
            continue
        normalized.append(event)
    normalized.sort(
        key=lambda item: (
            parse_datetime(item.get("first_seen_at")),
            parse_datetime(item.get("last_seen_at")),
        )
    )
    return normalized[-max(1, int(limit or 1)):]


def recent_market_quality_events(
    events,
    limit=DEFAULT_MARKET_QUALITY_RECENT_LIMIT,
):
    return [
        dict(item)
        for item in list(events or [])[-max(1, int(limit or 1)):]
        if isinstance(item, dict)
    ]


def market_quality_event_is_abnormal(event):
    if not isinstance(event, dict):
        return False
    if str(event.get("quality_level") or "") != "normal":
        return True
    return any(event.get(field) is not True for _, _, field in MARKET_QUALITY_BUSINESS_GATES)


def market_quality_segment_id(event):
    normalized = normalize_market_quality_event(event)
    if normalized is None:
        return ""
    return (
        "data-status-market-quality-"
        f"{str(normalized.get('session_id') or '')}-"
        f"{str(normalized.get('first_seen_at') or '')}"
    )


def _event_overlap_seconds(event, window_start, window_end):
    first_seen = parse_datetime(event.get("first_seen_at"))
    last_seen = parse_datetime(event.get("last_seen_at"))
    if first_seen is None or last_seen is None:
        return 0
    overlap_start = max(first_seen, window_start)
    overlap_end = min(last_seen, window_end)
    return max(0, int((overlap_end - overlap_start).total_seconds()))


def _window_summary(events, *, now, window_seconds):
    window_start = now - timedelta(seconds=window_seconds)
    incidents = []
    observed_seconds = 0
    abnormal_seconds = 0
    affected = {
        key: {
            "label": label,
            "incident_count": 0,
            "blocked_seconds": 0,
        }
        for key, label, _field in MARKET_QUALITY_BUSINESS_GATES
    }
    reasons = {}
    occurrence_count = 0
    for event in events:
        first_seen = parse_datetime(event.get("first_seen_at"))
        last_seen = parse_datetime(event.get("last_seen_at"))
        if first_seen is None or last_seen is None:
            continue
        if last_seen < window_start or first_seen > now:
            continue
        overlap_seconds = _event_overlap_seconds(event, window_start, now)
        observed_seconds += overlap_seconds
        if not market_quality_event_is_abnormal(event):
            continue
        incidents.append(event)
        occurrence_count += _positive_int(event.get("occurrences"), 1)
        abnormal_seconds += overlap_seconds
        for key, _label, field in MARKET_QUALITY_BUSINESS_GATES:
            if event.get(field) is False:
                affected[key]["incident_count"] += 1
                affected[key]["blocked_seconds"] += overlap_seconds
        for reason in list(event.get("blocked_reasons") or []):
            reason = str(reason or "").strip()
            if not reason:
                continue
            item = reasons.setdefault(
                reason,
                {"reason": reason, "incident_count": 0, "blocked_seconds": 0},
            )
            item["incident_count"] += 1
            item["blocked_seconds"] += overlap_seconds
    normal_seconds = max(0, observed_seconds - abnormal_seconds)
    availability_pct = (
        round(normal_seconds / observed_seconds * 100, 1)
        if observed_seconds > 0
        else None
    )
    reason_items = sorted(
        reasons.values(),
        key=lambda item: (
            -int(item["blocked_seconds"]),
            -int(item["incident_count"]),
            item["reason"],
        ),
    )
    return {
        "window_seconds": window_seconds,
        "incident_count": len(incidents),
        "occurrence_count": occurrence_count,
        "observed_seconds": observed_seconds,
        "normal_seconds": normal_seconds,
        "abnormal_seconds": abnormal_seconds,
        "availability_pct": availability_pct,
        "affected_business": affected,
        "top_reasons": reason_items[:5],
    }


def build_market_quality_history_summary(events, *, now=None):
    now_value = parse_datetime(now or datetime.now().astimezone())
    normalized = [
        event
        for event in (normalize_market_quality_event(item) for item in list(events or []))
        if event is not None
    ]
    return {
        "stored_events": len(normalized),
        "latest_event_at": normalized[-1]["last_seen_at"] if normalized else "",
        "windows": {
            "24h": _window_summary(normalized, now=now_value, window_seconds=24 * 60 * 60),
            "7d": _window_summary(normalized, now=now_value, window_seconds=7 * 24 * 60 * 60),
        },
    }


class MarketQualityHistoryStore:
    def __init__(
        self,
        path,
        *,
        retention_days=DEFAULT_MARKET_QUALITY_RETENTION_DAYS,
        limit=DEFAULT_MARKET_QUALITY_HISTORY_LIMIT,
        now_factory=None,
    ):
        self.path = str(path or "")
        self.retention_days = max(1, int(retention_days or 1))
        self.limit = max(1, int(limit or 1))
        self.now_factory = now_factory or datetime.now

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except (OSError, json.JSONDecodeError):
            return []
        is_legacy = isinstance(payload, list) or (
            isinstance(payload, dict) and "schema_version" not in payload
        )
        if isinstance(payload, dict) and not is_legacy:
            try:
                schema_version = int(payload.get("schema_version"))
            except (TypeError, ValueError):
                return []
            if schema_version != MARKET_QUALITY_HISTORY_SCHEMA_VERSION:
                return []
            if not isinstance(payload.get("items"), list):
                return []
        elif not is_legacy:
            return []
        normalized = prune_market_quality_events(
            unwrap_item_payload(payload),
            now=self.now_factory(),
            retention_days=self.retention_days,
            limit=self.limit,
        )
        if is_legacy:
            try:
                return self.save(normalized)
            except OSError:
                return normalized
        return normalized

    def save(self, events):
        if not self.path:
            raise OSError("market quality history path is empty")
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as file_handle:
                    existing_payload = json.load(file_handle)
            except (OSError, json.JSONDecodeError):
                existing_payload = None
            if isinstance(existing_payload, dict) and "schema_version" in existing_payload:
                try:
                    existing_version = int(existing_payload.get("schema_version"))
                except (TypeError, ValueError) as exc:
                    raise OSError("market quality history schema version is invalid") from exc
                if existing_version != MARKET_QUALITY_HISTORY_SCHEMA_VERSION:
                    raise OSError(
                        "market quality history schema version is not supported"
                    )
        normalized = prune_market_quality_events(
            events,
            now=self.now_factory(),
            retention_days=self.retention_days,
            limit=self.limit,
        )
        payload = wrap_item_payload(
            normalized,
            updated_at=iso_utc(self.now_factory()),
            schema_version=MARKET_QUALITY_HISTORY_SCHEMA_VERSION,
            retention_days=self.retention_days,
            max_events=self.limit,
        )
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        temporary_path = self.path + ".tmp"
        try:
            with open(temporary_path, "w", encoding="utf-8") as file_handle:
                json.dump(payload, file_handle, ensure_ascii=False, indent=2)
            os.replace(temporary_path, self.path)
        except Exception:
            try:
                os.remove(temporary_path)
            except FileNotFoundError:
                pass
            raise
        return normalized

    def record(self, history, observation, *, observed_at="", session_id=""):
        events = record_market_quality_event(
            history,
            observation,
            observed_at=observed_at,
            session_id=session_id,
            limit=self.limit,
        )
        return self.save(events)
