import json
import math
import os
import secrets
from datetime import datetime

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


THRESHOLD_LEVELS = [
    ("upper_warning", "warning", "上涨关注"),
    ("upper_critical", "critical", "突破上限"),
    ("lower_warning", "warning", "下跌关注"),
    ("lower_critical", "critical", "跌破下限"),
]
THRESHOLD_MODES = ("usd", "rmb")
WATCH_TARGET_DIRECTIONS = {"rise_to", "fall_to"}
WATCH_TARGET_NOTE_LIMIT = 120


def normalize_volatility_config(raw):
    data = {"percent": None, "minutes": 10, "enabled": False}
    if isinstance(raw, dict):
        try:
            percent = float(raw["percent"]) if raw.get("percent") not in (None, "") else None
            data["percent"] = percent if percent is not None and math.isfinite(percent) and percent > 0 else None
        except (TypeError, ValueError):
            data["percent"] = None
        try:
            data["minutes"] = max(1, int(raw.get("minutes", 10)))
        except (TypeError, ValueError):
            data["minutes"] = 10
        data["enabled"] = bool(raw.get("enabled")) and data["percent"] is not None
    return data


def normalize_thresholds(raw, defaults, current_volatility_config=None):
    data = dict(defaults)
    current_volatility_config = current_volatility_config or {"percent": None, "minutes": 10, "enabled": False}
    if isinstance(raw, dict):
        for key in data:
            value = raw.get(key)
            if value in (None, ""):
                data[key] = None
                continue
            try:
                data[key] = float(value)
            except (TypeError, ValueError):
                data[key] = None
        data["volatility_config"] = normalize_volatility_config(
            raw.get("volatility_config", current_volatility_config)
        )
    else:
        data["volatility_config"] = normalize_volatility_config(current_volatility_config)
    return data


def build_threshold_alert(
    mode,
    price,
    now_str,
    thresholds,
    alerted_flags,
    usdcny_rate=None,
    usdcny_rate_cached=False,
    usdcny_rate_source="",
):
    if price is None:
        return None

    unit = "$" if mode == "usd" else "¥"
    mode_label = "国际金价" if mode == "usd" else "国内金价"

    for key_suffix, level, label in THRESHOLD_LEVELS:
        key = f"{key_suffix}_{mode}"
        value = thresholds.get(key)
        if value is None:
            continue

        is_upper = "upper" in key_suffix
        triggered = (is_upper and price >= value) or (not is_upper and price <= value)

        if triggered:
            if alerted_flags.get(key):
                return None
            alerted_flags[key] = True

            rate_note = ""
            if mode == "rmb" and usdcny_rate:
                rate_kind = "缓存汇率" if usdcny_rate_cached else "实时汇率"
                rate_note = f"；{rate_kind} {usdcny_rate:.4f}"
                if usdcny_rate_source:
                    rate_note += f"（{usdcny_rate_source}）"
            message = f"[{mode_label}] {label}: {unit}{price:,.2f} (阈值 {unit}{value:,.2f}{rate_note})"
            return {
                "key": key,
                "title": f"金价预警 - {label}",
                "alert": {
                    "time": now_str,
                    "type": level,
                    "mode": mode,
                    "source": "threshold",
                    "threshold_key": key,
                    "threshold_value": value,
                    "trigger_price": price,
                    "alert_direction": "up" if is_upper else "down",
                    "message": message,
                },
            }

        if alerted_flags.get(key):
            alerted_flags[key] = False
    return None


class ThresholdStore:
    def __init__(self, json_path, defaults, current_volatility_config=None, now_factory=None):
        self.json_path = json_path
        self.defaults = defaults
        self.current_volatility_config = current_volatility_config or {"percent": None, "minutes": 10, "enabled": False}
        self.now_factory = now_factory or datetime.now

    def normalize(self, raw):
        return normalize_thresholds(raw, self.defaults, self.current_volatility_config)

    def load(self):
        if not os.path.exists(self.json_path):
            return self.normalize({})
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                return self.normalize(json.load(f))
        except (OSError, json.JSONDecodeError):
            return self.normalize({})

    def save(self, data):
        normalized = self.normalize(data)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(normalized, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized


def generate_watch_target_id():
    return "target-" + secrets.token_hex(8)


def coerce_watch_target_bool(value, default):
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off", ""}:
            return False
    return bool(default)


def normalize_watch_target(item, existing=None, now_factory=None, id_factory=None, note_limit=WATCH_TARGET_NOTE_LIMIT):
    if not isinstance(item, dict):
        raise ValueError("观察项格式无效")

    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_watch_target_id
    now = now_factory().isoformat(timespec="seconds")
    target_id = str(item.get("id") or existing.get("id") or id_factory()).strip()
    if not target_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in target_id):
        target_id = id_factory()

    mode = str(item.get("mode", existing.get("mode", "rmb")) or "").strip().lower()
    if mode not in THRESHOLD_MODES:
        raise ValueError("观察单位无效")

    direction = str(item.get("direction", existing.get("direction", "fall_to")) or "").strip().lower()
    if direction not in WATCH_TARGET_DIRECTIONS:
        raise ValueError("观察方向无效")

    raw_price = item.get("price", existing.get("price"))
    try:
        price = float(raw_price)
    except (TypeError, ValueError):
        raise ValueError("请输入有效的目标价格")
    if not math.isfinite(price) or price <= 0:
        raise ValueError("请输入有效的目标价格")

    previous_price = existing.get("price")
    try:
        previous_price = float(previous_price)
    except (TypeError, ValueError):
        previous_price = None
    target_changed = (
        existing
        and (
            existing.get("mode") != mode
            or existing.get("direction") != direction
            or previous_price != price
        )
    )

    note = str(item.get("note", existing.get("note", "")) or "").strip()
    if len(note) > note_limit:
        note = note[:note_limit]

    triggered = coerce_watch_target_bool(item.get("triggered", existing.get("triggered", False)), False)
    triggered_at = str(item.get("triggered_at", existing.get("triggered_at", "")) or "").strip()
    last_trigger_price = item.get("last_trigger_price", existing.get("last_trigger_price"))
    if last_trigger_price in (None, ""):
        last_trigger_price = None
    else:
        try:
            last_trigger_price = float(last_trigger_price)
        except (TypeError, ValueError):
            last_trigger_price = None

    if target_changed:
        triggered = False
        triggered_at = ""
        last_trigger_price = None

    created_at = str(item.get("created_at") or existing.get("created_at") or now)
    updated_at = now if existing else str(item.get("updated_at") or now)

    return {
        "id": target_id,
        "mode": mode,
        "direction": direction,
        "price": price,
        "note": note,
        "enabled": coerce_watch_target_bool(item.get("enabled", existing.get("enabled", True)), True),
        "triggered": triggered,
        "created_at": created_at,
        "updated_at": updated_at,
        "triggered_at": triggered_at if triggered else "",
        "last_trigger_price": last_trigger_price if triggered else None,
    }


def normalize_watch_targets(items, now_factory=None, id_factory=None):
    if not isinstance(items, list):
        return []
    normalized = []
    seen = set()
    for item in items:
        try:
            target = normalize_watch_target(item, now_factory=now_factory, id_factory=id_factory)
        except ValueError:
            continue
        target_id = target.get("id")
        if target_id in seen:
            continue
        seen.add(target_id)
        normalized.append(target)
    return normalized


def watch_targets_state(items):
    items = [dict(item) for item in list(items or [])]
    return {
        "items": items,
        "total": len(items),
        "enabled": sum(1 for item in items if item.get("enabled")),
        "triggered": sum(1 for item in items if item.get("triggered")),
    }


def find_watch_target_index(items, target_id):
    target_id = str(target_id or "").strip()
    if not target_id:
        return -1
    for index, item in enumerate(list(items or [])):
        if isinstance(item, dict) and item.get("id") == target_id:
            return index
    return -1


def watch_target_triggered(target, current_price):
    if current_price is None:
        return False
    direction = target.get("direction")
    target_price = target.get("price")
    if target_price is None:
        return False
    if direction == "rise_to":
        return current_price >= target_price
    if direction == "fall_to":
        return current_price <= target_price
    return False


def build_watch_target_alert_message(target, current_price):
    mode = target.get("mode")
    unit = "$" if mode == "usd" else "¥"
    mode_label = "国际金价" if mode == "usd" else "国内金价"
    direction_label = "上涨至" if target.get("direction") == "rise_to" else "下跌至"
    note = str(target.get("note") or "").strip()
    note_part = f"；备注：{note}" if note else ""
    return (
        f"[{mode_label}] 目标价观察: 当前 {unit}{current_price:,.2f}，"
        f"已{direction_label}目标 {unit}{target.get('price', 0):,.2f}{note_part}"
    )


def check_watch_targets(items, prices, now_factory=None):
    now_factory = now_factory or datetime.now
    triggered_entries = []
    next_items = [dict(item) for item in list(items or [])]
    for index, target in enumerate(list(next_items)):
        if not target.get("enabled") or target.get("triggered"):
            continue
        current_price = prices.get(target.get("mode")) if isinstance(prices, dict) else None
        if not watch_target_triggered(target, current_price):
            continue
        triggered_at = now_factory().isoformat(timespec="seconds")
        updated = dict(target)
        updated["triggered"] = True
        updated["triggered_at"] = triggered_at
        updated["last_trigger_price"] = current_price
        updated["updated_at"] = triggered_at
        next_items[index] = normalize_watch_target(updated, existing=target, now_factory=now_factory)
        triggered_entries.append({"target": next_items[index], "current_price": current_price})
    return next_items, triggered_entries


class WatchTargetStore:
    def __init__(self, json_path, now_factory=None, id_factory=None):
        self.json_path = json_path
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_watch_target_id

    def normalize(self, items):
        return normalize_watch_targets(items, now_factory=self.now_factory, id_factory=self.id_factory)

    def load(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, items):
        normalized = self.normalize(items)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        payload = wrap_item_payload(normalized)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized


def build_volatility_alert(history, config, now_str, last_checked_at=None, now_factory=None):
    now_factory = now_factory or datetime.now
    if not config.get("enabled") or config.get("percent") is None:
        return None, last_checked_at

    percent = config["percent"]
    minutes = config.get("minutes", 10)
    points_needed = max(1, int(minutes * 60 / 10))

    if len(history) < points_needed:
        return None, last_checked_at

    now = now_factory()
    if last_checked_at and (now - last_checked_at).seconds < 60:
        return None, last_checked_at

    window = history[-points_needed:]
    usd_prices = [point["usd"] for point in window if point.get("usd") is not None]
    if len(usd_prices) < points_needed:
        return None, now

    start_price = usd_prices[0]
    end_price = usd_prices[-1]
    if start_price == 0:
        return None, now

    change_pct = abs((end_price - start_price) / start_price * 100)
    if change_pct >= percent:
        direction = "上涨" if end_price > start_price else "下跌"
        message = f"[波动预警] {minutes}分钟内{direction} {change_pct:.2f}% (${start_price:,.2f} → ${end_price:,.2f})"
        return {
            "title": "金价波动预警",
            "alert": {
                "time": now_str,
                "type": "volatility",
                "mode": "usd",
                "source": "volatility",
                "trigger_price": end_price,
                "alert_direction": "up" if end_price > start_price else "down",
                "message": message,
            },
        }, now
    return None, now
