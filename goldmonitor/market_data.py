import csv
import io
import json
import math
import os
import time
from datetime import datetime


def parse_iso_datetime(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _format_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return round(number, 4)


def extract_quoted_payload(text):
    raw = str(text or "")
    try:
        return raw.split('"', 2)[1]
    except IndexError:
        return ""


def parse_stooq_ohlc_csv(text, source_label="数据源"):
    reader = csv.reader(io.StringIO(str(text or "")))
    rows = list(reader)
    if len(rows) < 1:
        return None, f"{source_label}返回为空"
    row = rows[0]
    if len(row) < 7:
        return None, f"{source_label}返回格式异常"
    try:
        return {
            "date": row[1],
            "time": row[2],
            "open": float(row[3]),
            "high": float(row[4]),
            "low": float(row[5]),
            "close": float(row[6]),
        }, ""
    except (ValueError, IndexError):
        return None, f"{source_label}返回格式异常"


def parse_sina_forex(text):
    try:
        quoted = extract_quoted_payload(text)
        parts = quoted.split(",")
        if len(parts) < 2:
            return None, "新浪汇率返回格式异常"
        rate = float(parts[1])
    except (IndexError, TypeError, ValueError):
        return None, "新浪汇率返回格式异常"
    return (rate, "") if rate > 0 else (None, "新浪汇率返回无效")


def parse_frankfurter_forex(payload):
    try:
        rate = float(payload["rates"]["CNY"])
    except (KeyError, TypeError, ValueError):
        return None, "Frankfurter 返回格式异常"
    return (rate, "") if rate > 0 else (None, "Frankfurter 返回无效汇率")


def parse_sina_gold(text, now=None):
    now = now or datetime.now()
    quoted = extract_quoted_payload(text)
    parts = [part.strip() for part in quoted.split(",") if part.strip()]
    numeric_values = []
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            continue
        if value > 0:
            numeric_values.append(value)

    if not numeric_values:
        return None, "新浪贵金属未返回金价"

    close = numeric_values[0]
    open_price = numeric_values[3] if len(numeric_values) > 3 else close
    high_price = max(numeric_values[:6]) if len(numeric_values) >= 2 else close
    low_price = min(numeric_values[:6]) if len(numeric_values) >= 2 else close
    time_text = next((part for part in parts if ":" in part), now.strftime("%H:%M:%S"))
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": time_text,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close,
    }, ""


def parse_eastmoney_gold(payload, now=None):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None, "东方财富返回格式异常"

    scale_power = data.get("f59", 2)
    try:
        scale = 10 ** int(scale_power)
    except (TypeError, ValueError):
        scale = 100

    def field_value(key):
        value = data.get(key)
        if value in (None, "-", ""):
            return None
        return round(float(value) / scale, 4)

    try:
        close = field_value("f43")
    except (TypeError, ValueError):
        return None, "东方财富返回格式异常"
    if close is None:
        return None, "东方财富未返回金价"

    now = now or datetime.now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "open": field_value("f46") or close,
        "high": field_value("f44") or close,
        "low": field_value("f45") or close,
        "close": close,
    }, ""


def parse_goldprice_rates(payload, now=None):
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return None, None, "GoldPrice 返回格式异常"

    rates = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        curr = str(item.get("curr") or "").upper()
        try:
            price = float(item.get("xauPrice"))
        except (TypeError, ValueError):
            continue
        if curr:
            rates[curr] = price

    usd_price = rates.get("USD")
    cny_price = rates.get("CNY")
    if usd_price is None:
        return None, None, "GoldPrice 未返回美元金价"

    cny_rate = round(cny_price / usd_price, 6) if cny_price and usd_price else None
    now = now or datetime.now()
    data = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "open": usd_price,
        "high": usd_price,
        "low": usd_price,
        "close": usd_price,
    }
    return data, cny_rate, ""


class MarketCacheStore:
    def __init__(self, cache_path, max_age_seconds, now_factory=None):
        self.cache_path = cache_path
        self.max_age_seconds = int(max_age_seconds)
        self.now_factory = now_factory or datetime.now

    @staticmethod
    def normalize_usdcny(raw):
        if not isinstance(raw, dict):
            return None
        try:
            value = float(raw.get("value"))
        except (TypeError, ValueError):
            return None
        if value <= 0:
            return None
        timestamp = str(raw.get("timestamp") or "").strip()
        if not timestamp:
            return None
        return {
            "value": value,
            "source": str(raw.get("source") or "缓存汇率").strip(),
            "timestamp": timestamp,
            "cached": True,
        }

    def normalize_xauusd(self, raw):
        if not isinstance(raw, dict):
            return None
        try:
            close = float(raw.get("close"))
        except (TypeError, ValueError):
            return None
        if close <= 0:
            return None
        timestamp = str(raw.get("timestamp") or "").strip()
        if not timestamp:
            return None

        def number_or_default(key, default):
            try:
                value = float(raw.get(key))
            except (TypeError, ValueError):
                return default
            return value if value > 0 else default

        now = self.now_factory()
        return {
            "date": str(raw.get("date") or now.strftime("%Y-%m-%d")),
            "time": str(raw.get("time") or now.strftime("%H:%M:%S")),
            "open": number_or_default("open", close),
            "high": number_or_default("high", close),
            "low": number_or_default("low", close),
            "close": close,
            "source": str(raw.get("source") or "缓存金价").strip(),
            "timestamp": timestamp,
            "cached": True,
        }

    def load_payload(self):
        if not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_section(self, section, data):
        os.makedirs(os.path.dirname(self.cache_path) or ".", exist_ok=True)
        payload = self.load_payload()
        payload[section] = data
        tmp_path = self.cache_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.cache_path)

    def load_usdcny(self):
        return self.normalize_usdcny(self.load_payload().get("usdcny"))

    def load_xauusd(self):
        return self.normalize_xauusd(self.load_payload().get("xauusd"))

    def is_fresh(self, cached, max_age_seconds=None):
        if not cached:
            return False
        parsed_time = parse_iso_datetime(cached.get("timestamp"))
        if not parsed_time:
            return False
        age = self.now_factory() - parsed_time
        max_age_seconds = self.max_age_seconds if max_age_seconds is None else int(max_age_seconds)
        return 0 <= age.total_seconds() <= max_age_seconds

    def load_valid_usdcny(self, max_age_seconds=None):
        cached = self.load_usdcny()
        return cached if self.is_fresh(cached, max_age_seconds=max_age_seconds) else None

    def load_valid_xauusd(self, max_age_seconds=None):
        cached = self.load_xauusd()
        return cached if self.is_fresh(cached, max_age_seconds=max_age_seconds) else None

    def save_usdcny(self, value, source, timestamp=None):
        rate = self.normalize_usdcny({
            "value": value,
            "source": source,
            "timestamp": timestamp or self.now_factory().isoformat(),
        })
        if not rate:
            raise ValueError("invalid USD/CNY rate cache")
        self.write_section("usdcny", {
            "value": rate["value"],
            "source": rate["source"],
            "timestamp": rate["timestamp"],
        })
        return {
            "value": rate["value"],
            "source": rate["source"],
            "timestamp": rate["timestamp"],
            "cached": False,
        }

    def save_xauusd(self, data, source, timestamp=None):
        if not isinstance(data, dict):
            raise ValueError("invalid XAU/USD cache")
        cache = self.normalize_xauusd({
            "date": data.get("date"),
            "time": data.get("time"),
            "open": data.get("open"),
            "high": data.get("high"),
            "low": data.get("low"),
            "close": data.get("close"),
            "source": source,
            "timestamp": timestamp or self.now_factory().isoformat(),
        })
        if not cache:
            raise ValueError("invalid XAU/USD cache")
        self.write_section("xauusd", {
            "date": cache["date"],
            "time": cache["time"],
            "open": cache["open"],
            "high": cache["high"],
            "low": cache["low"],
            "close": cache["close"],
            "source": cache["source"],
            "timestamp": cache["timestamp"],
        })
        return {
            "date": cache["date"],
            "time": cache["time"],
            "open": cache["open"],
            "high": cache["high"],
            "low": cache["low"],
            "close": cache["close"],
            "source": cache["source"],
            "timestamp": cache["timestamp"],
            "cached": False,
        }


def record_source_health(
    health_state,
    name,
    category,
    ok,
    error="",
    started_at=None,
    cached=False,
    now=None,
    now_monotonic=None,
    limit=None,
):
    if not name:
        return None
    elapsed_ms = None
    if started_at is not None:
        current_monotonic = time.monotonic() if now_monotonic is None else now_monotonic
        elapsed_ms = int(max(0, (current_monotonic - started_at) * 1000))
    now = now or datetime.now()
    current = health_state.get(name, {
        "name": name,
        "category": category,
        "ok_count": 0,
        "fail_count": 0,
    })
    current.update({
        "name": name,
        "category": category,
        "ok": bool(ok),
        "cached": bool(cached),
        "error": str(error or ""),
        "last_checked": now.isoformat(timespec="seconds"),
        "elapsed_ms": elapsed_ms,
    })
    if ok:
        current["ok_count"] = int(current.get("ok_count", 0)) + 1
    else:
        current["fail_count"] = int(current.get("fail_count", 0)) + 1
    health_state[name] = current
    if limit and len(health_state) > int(limit):
        oldest = sorted(health_state.values(), key=lambda item: item.get("last_checked", ""))[0]
        health_state.pop(oldest.get("name"), None)
    return dict(current)


def build_source_health_state(health_state, comparison=None, now=None):
    now = now or datetime.now()
    items = sorted(
        [dict(item) for item in health_state.values()],
        key=lambda item: (item.get("category", ""), item.get("name", "")),
    )
    summary = {
        "total": len(items),
        "ok": sum(1 for item in items if item.get("ok")),
        "failed": sum(1 for item in items if item.get("ok") is False),
        "cached": sum(1 for item in items if item.get("cached")),
    }
    return {
        "items": items,
        "summary": summary,
        "comparison": comparison,
        "updated_at": now.isoformat(timespec="seconds"),
    }


def build_source_comparison_state(samples=None, stale_seconds=300, anomaly_pct=0.5, now=None):
    samples = samples or []
    now = now or datetime.now()
    items = []
    for sample in samples:
        checked_at = parse_iso_datetime(sample.get("checked_at"))
        age_seconds = None
        if checked_at:
            age_seconds = max(0, int((now - checked_at).total_seconds()))
        stale = age_seconds is None or age_seconds > stale_seconds
        item = dict(sample)
        item["age_seconds"] = age_seconds
        item["stale"] = stale
        item["available"] = bool(item.get("usd")) and not item.get("cached") and not stale
        items.append(item)
    items.sort(key=lambda item: item.get("name", ""))
    comparable = [item for item in items if item.get("available")]
    state = {
        "items": items,
        "summary": {
            "total": len(items),
            "compared": len(comparable),
            "spread_usd": None,
            "spread_pct": None,
            "threshold_pct": anomaly_pct,
        },
        "status": "insufficient",
        "message": "可对比数据源不足",
        "updated_at": now.isoformat(timespec="seconds"),
    }
    if len(comparable) >= 2:
        low = min(comparable, key=lambda item: item.get("usd"))
        high = max(comparable, key=lambda item: item.get("usd"))
        spread_usd = round(float(high["usd"]) - float(low["usd"]), 4)
        midpoint = (float(high["usd"]) + float(low["usd"])) / 2
        spread_pct = round(spread_usd / midpoint * 100, 4) if midpoint else 0
        state["summary"].update({
            "spread_usd": spread_usd,
            "spread_pct": spread_pct,
            "low_source": low.get("name"),
            "high_source": high.get("name"),
        })
        if spread_pct >= anomaly_pct:
            state["status"] = "anomaly"
            state["message"] = f"数据源价差 {spread_pct:.2f}% ，建议核对行情源"
        else:
            state["status"] = "normal"
            state["message"] = f"数据源价差 {spread_pct:.2f}% ，处于正常范围"
    return state
