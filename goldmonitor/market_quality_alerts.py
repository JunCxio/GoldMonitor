import json
import os
from datetime import datetime

from goldmonitor.market_observation import market_observation_snapshot
from goldmonitor.market_quality_history import market_quality_event_is_abnormal
from goldmonitor.time_utils import iso_utc, parse_datetime, to_local_naive


MARKET_QUALITY_ALERT_STATE_SCHEMA_VERSION = 1
DEFAULT_MARKET_QUALITY_ALERT_THRESHOLD_MINUTES = 5


def empty_market_quality_alert_state():
    return {
        "schema_version": MARKET_QUALITY_ALERT_STATE_SCHEMA_VERSION,
        "incident_active": False,
        "incident_id": "",
        "first_seen_at": "",
        "accumulated_seconds": 0,
        "last_observed_at": "",
        "last_session_id": "",
        "last_segment_id": "",
        "notified_at": "",
        "notified_segment_id": "",
        "notification_alert_id": "",
        "last_recovered_at": "",
        "last_incident_duration_seconds": 0,
        "last_incident_id": "",
        "last_transition": "",
        "last_transition_at": "",
        "last_abnormal_observation": {},
        "updated_at": "",
    }


def _non_negative_int(value, default=0):
    try:
        number = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(0, number)


def _timestamp(value):
    return iso_utc(value)


def _observation_snapshot(value):
    snapshot = market_observation_snapshot(value)
    if not snapshot:
        return {}
    snapshot["blocked_reasons"] = list(snapshot.get("blocked_reasons") or [])
    return snapshot


def normalize_market_quality_alert_state(value):
    state = empty_market_quality_alert_state()
    if not isinstance(value, dict):
        return state
    state.update({
        "incident_active": bool(value.get("incident_active")),
        "incident_id": str(value.get("incident_id") or ""),
        "first_seen_at": _timestamp(value.get("first_seen_at")),
        "accumulated_seconds": _non_negative_int(
            value.get("accumulated_seconds")
        ),
        "last_observed_at": _timestamp(value.get("last_observed_at")),
        "last_session_id": str(value.get("last_session_id") or ""),
        "last_segment_id": str(value.get("last_segment_id") or ""),
        "notified_at": _timestamp(value.get("notified_at")),
        "notified_segment_id": str(value.get("notified_segment_id") or ""),
        "notification_alert_id": str(value.get("notification_alert_id") or ""),
        "last_recovered_at": _timestamp(value.get("last_recovered_at")),
        "last_incident_duration_seconds": _non_negative_int(
            value.get("last_incident_duration_seconds")
        ),
        "last_incident_id": str(value.get("last_incident_id") or ""),
        "last_transition": str(value.get("last_transition") or ""),
        "last_transition_at": _timestamp(value.get("last_transition_at")),
        "last_abnormal_observation": _observation_snapshot(
            value.get("last_abnormal_observation")
        ),
        "updated_at": _timestamp(value.get("updated_at")),
    })
    if not state["incident_active"]:
        state.update({
            "incident_id": "",
            "first_seen_at": "",
            "accumulated_seconds": 0,
            "last_observed_at": "",
            "last_session_id": "",
            "last_segment_id": "",
            "notified_at": "",
            "notified_segment_id": "",
            "notification_alert_id": "",
            "last_abnormal_observation": {},
        })
    elif not state["incident_id"] or not state["first_seen_at"]:
        return empty_market_quality_alert_state()
    return state


def selected_market_quality_alert_channels(settings):
    settings = settings if isinstance(settings, dict) else {}
    channels = []
    if settings.get("market_quality_alert_local_enabled", True):
        channels.append("local")
    if settings.get("market_quality_alert_email_enabled", False):
        channels.append("email")
    if settings.get("market_quality_alert_webhook_enabled", False):
        channels.append("webhook")
    return channels


def market_quality_alert_threshold_seconds(settings):
    settings = settings if isinstance(settings, dict) else {}
    minutes = _non_negative_int(
        settings.get(
            "market_quality_alert_threshold_minutes",
            DEFAULT_MARKET_QUALITY_ALERT_THRESHOLD_MINUTES,
        ),
        DEFAULT_MARKET_QUALITY_ALERT_THRESHOLD_MINUTES,
    )
    return max(1, min(60, minutes or DEFAULT_MARKET_QUALITY_ALERT_THRESHOLD_MINUTES)) * 60


def _incident_id(session_id, observed_at):
    compact_time = str(observed_at or "").replace(":", "").replace("-", "")
    return f"market-quality-{str(session_id or 'session')}-{compact_time}"


def _elapsed_seconds(previous_at, current_at):
    previous = parse_datetime(previous_at)
    current = parse_datetime(current_at)
    if previous is None or current is None or current <= previous:
        return 0
    return max(0, int((current - previous).total_seconds()))


def _transition_event(kind, state, observation, occurred_at, segment_id):
    abnormal = dict(state.get("last_abnormal_observation") or {})
    current = _observation_snapshot(observation)
    return {
        "kind": kind,
        "occurred_at": occurred_at,
        "incident_id": str(state.get("incident_id") or ""),
        "first_seen_at": str(state.get("first_seen_at") or ""),
        "duration_seconds": _non_negative_int(state.get("accumulated_seconds")),
        "segment_id": str(segment_id or state.get("last_segment_id") or ""),
        "incident_alert_id": str(state.get("notification_alert_id") or ""),
        "abnormal_observation": abnormal,
        "current_observation": current,
    }


def evaluate_market_quality_alert(
    state,
    observation,
    settings,
    *,
    observed_at,
    session_id="",
    segment_id="",
):
    now_text = _timestamp(observed_at)
    current = normalize_market_quality_alert_state(state)
    if not now_text:
        return {"state": current, "event": None}
    if not bool((settings or {}).get("market_quality_alert_enabled", True)):
        reset = empty_market_quality_alert_state()
        reset.update({
            "last_recovered_at": current.get("last_recovered_at", ""),
            "last_incident_duration_seconds": current.get(
                "last_incident_duration_seconds",
                0,
            ),
            "last_incident_id": current.get("last_incident_id", ""),
            "last_transition": "disabled",
            "last_transition_at": now_text,
            "updated_at": now_text,
        })
        return {"state": reset, "event": None}

    abnormal = market_quality_event_is_abnormal(observation)
    if abnormal:
        if not current["incident_active"]:
            current.update({
                "incident_active": True,
                "incident_id": _incident_id(session_id, now_text),
                "first_seen_at": now_text,
                "accumulated_seconds": 0,
                "notified_at": "",
                "notified_segment_id": "",
                "notification_alert_id": "",
                "last_transition": "observing",
                "last_transition_at": now_text,
            })
        elif str(current.get("last_session_id") or "") == str(session_id or ""):
            current["accumulated_seconds"] += _elapsed_seconds(
                current.get("last_observed_at"),
                now_text,
            )
        current.update({
            "last_observed_at": now_text,
            "last_session_id": str(session_id or ""),
            "last_segment_id": str(segment_id or current.get("last_segment_id") or ""),
            "last_abnormal_observation": _observation_snapshot(observation),
            "updated_at": now_text,
        })
        threshold_seconds = market_quality_alert_threshold_seconds(settings)
        if not current["notified_at"] and current["accumulated_seconds"] >= threshold_seconds:
            current.update({
                "notified_at": now_text,
                "notified_segment_id": str(
                    segment_id or current.get("last_segment_id") or ""
                ),
                "last_transition": "notified",
                "last_transition_at": now_text,
            })
            return {
                "state": current,
                "event": _transition_event(
                    "incident",
                    current,
                    observation,
                    now_text,
                    current["notified_segment_id"],
                ),
            }
        return {"state": current, "event": None}

    if not current["incident_active"]:
        current["updated_at"] = now_text
        return {"state": current, "event": None}

    recovery_event = None
    recovered_alert_id = ""
    if current["notified_at"]:
        recovered_alert_id = str(current.get("notification_alert_id") or "")
    if current["notified_at"] and bool(
        (settings or {}).get("market_quality_recovery_enabled", True)
    ):
        recovery_event = _transition_event(
            "recovery",
            current,
            observation,
            now_text,
            current.get("last_segment_id") or current.get("notified_segment_id"),
        )
    cleared = empty_market_quality_alert_state()
    cleared.update({
        "last_recovered_at": now_text,
        "last_incident_duration_seconds": current["accumulated_seconds"],
        "last_incident_id": current["incident_id"],
        "last_transition": "recovered",
        "last_transition_at": now_text,
        "updated_at": now_text,
    })
    return {
        "state": cleared,
        "event": recovery_event,
        "recovered_alert_id": recovered_alert_id,
    }


def build_market_quality_alert_status(state, settings, *, now=None):
    current = normalize_market_quality_alert_state(state)
    settings = settings if isinstance(settings, dict) else {}
    enabled = bool(settings.get("market_quality_alert_enabled", True))
    threshold_seconds = market_quality_alert_threshold_seconds(settings)
    elapsed = current["accumulated_seconds"] if current["incident_active"] else 0
    remaining = max(0, threshold_seconds - elapsed)
    if not enabled:
        status = "disabled"
    elif current["incident_active"] and current["notified_at"]:
        status = "notified"
    elif current["incident_active"]:
        status = "countdown"
    else:
        status = "monitoring"
    return {
        "enabled": enabled,
        "status": status,
        "threshold_minutes": threshold_seconds // 60,
        "elapsed_seconds": elapsed,
        "remaining_seconds": remaining,
        "incident_active": current["incident_active"],
        "incident_id": current["incident_id"],
        "first_seen_at": current["first_seen_at"],
        "notified_at": current["notified_at"],
        "notification_alert_id": current["notification_alert_id"],
        "segment_id": current["last_segment_id"] or current["notified_segment_id"],
        "channels": selected_market_quality_alert_channels(settings),
        "recovery_enabled": bool(settings.get("market_quality_recovery_enabled", True)),
        "last_recovered_at": current["last_recovered_at"],
        "last_incident_duration_seconds": current[
            "last_incident_duration_seconds"
        ],
        "updated_at": current["updated_at"] or _timestamp(now or datetime.now()),
    }


def _duration_text(seconds):
    total = max(0, _non_negative_int(seconds))
    if total < 60:
        return f"{total} 秒"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} 分钟" + (f" {seconds} 秒" if seconds else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时" + (f" {minutes} 分钟" if minutes else "")


def _business_impact_text(observation):
    observation = observation if isinstance(observation, dict) else {}
    labels = []
    if observation.get("usable_for_history") is False:
        labels.append("历史入库")
    if observation.get("usable_for_alert") is False:
        labels.append("预警判断")
    if observation.get("usable_for_automation") is False:
        labels.append("定投执行")
    return "、".join(labels)


def build_market_quality_alert_entry(event, settings):
    event = event if isinstance(event, dict) else {}
    settings = settings if isinstance(settings, dict) else {}
    kind = str(event.get("kind") or "incident")
    abnormal = event.get("abnormal_observation")
    abnormal = abnormal if isinstance(abnormal, dict) else {}
    current = event.get("current_observation")
    current = current if isinstance(current, dict) else {}
    duration = _duration_text(event.get("duration_seconds"))
    reasons = [
        str(reason).strip()
        for reason in list(abnormal.get("blocked_reasons") or [])
        if str(reason or "").strip()
    ]
    impact = _business_impact_text(abnormal)
    if kind == "recovery":
        title = "行情质量已恢复"
        message = f"行情质量已恢复，本次异常累计 {duration}。"
        if current.get("source"):
            message += f" 当前行情源：{current['source']}。"
        alert_type = "recovery"
    else:
        title = "行情质量持续异常"
        message = f"行情质量异常已持续 {duration}。"
        if impact:
            message += f" 当前已阻止{impact}。"
        if reasons:
            message += " 主要原因：" + "；".join(reasons[:3]) + "。"
        alert_type = "quality"
    occurred_at = str(event.get("occurred_at") or "")
    local_time = to_local_naive(occurred_at)
    entry = {
        "type": alert_type,
        "mode": "quality",
        "source": "market_quality",
        "title": title,
        "message": message,
        "time": local_time.strftime("%H:%M:%S") if local_time else "",
        "timestamp": occurred_at,
        "delivery_channels": selected_market_quality_alert_channels(settings),
        "cooldown_minutes": 0,
        "market_quality_event": kind,
        "market_quality_incident_id": str(event.get("incident_id") or ""),
        "market_quality_first_seen_at": str(event.get("first_seen_at") or ""),
        "market_quality_duration_seconds": _non_negative_int(
            event.get("duration_seconds")
        ),
        "market_quality_segment_id": str(event.get("segment_id") or ""),
        "market_quality_level": str(abnormal.get("quality_level") or ""),
        "market_quality_score": abnormal.get("quality_score"),
        "market_quality_blocked_reasons": reasons,
        "market_quality_business_impact": impact,
        "market_quality_observation": abnormal,
        "market_quality_recovery_observation": current if kind == "recovery" else {},
    }
    if kind == "recovery":
        entry.update({
            "handled": True,
            "handled_at": occurred_at,
            "handling_note": "行情质量已自动恢复",
        })
    return entry


class MarketQualityAlertStateStore:
    def __init__(self, path, *, now_factory=None):
        self.path = str(path or "")
        self.now_factory = now_factory or datetime.now

    def load(self):
        if not self.path or not os.path.exists(self.path):
            return empty_market_quality_alert_state()
        try:
            with open(self.path, "r", encoding="utf-8") as file_handle:
                payload = json.load(file_handle)
        except (OSError, json.JSONDecodeError):
            return empty_market_quality_alert_state()
        if not isinstance(payload, dict):
            return empty_market_quality_alert_state()
        try:
            schema_version = int(payload.get("schema_version"))
        except (TypeError, ValueError):
            return empty_market_quality_alert_state()
        if schema_version != MARKET_QUALITY_ALERT_STATE_SCHEMA_VERSION:
            return empty_market_quality_alert_state()
        return normalize_market_quality_alert_state(payload.get("state"))

    def save(self, state):
        if not self.path:
            raise OSError("market quality alert state path is empty")
        normalized = normalize_market_quality_alert_state(state)
        normalized["updated_at"] = normalized.get("updated_at") or _timestamp(
            self.now_factory()
        )
        payload = {
            "schema_version": MARKET_QUALITY_ALERT_STATE_SCHEMA_VERSION,
            "updated_at": _timestamp(self.now_factory()),
            "state": normalized,
        }
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
