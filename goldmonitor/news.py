import json
import os
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


NEWS_KEYWORDS = (
    "gold", "xau", "xauusd", "bullion", "precious metal", "fed", "fomc",
    "interest rate", "inflation", "cpi", "jobs", "nonfarm", "payroll",
    "dollar", "yield", "central bank", "黄金", "金价", "通胀", "美元",
)


def is_relevant_news(text, keywords=NEWS_KEYWORDS):
    lowered = str(text or "").lower()
    return any(keyword in lowered for keyword in keywords)


def classify_news_topic(text, source_kind=""):
    lowered = str(text or "").lower()
    if any(word in lowered for word in ("fomc", "federal reserve", "fed", "interest rate", "rate decision", "利率")):
        return "利率"
    if any(word in lowered for word in ("cpi", "inflation", "通胀")):
        return "通胀"
    if any(word in lowered for word in ("dollar", "usd", "yield", "美元", "美债")):
        return "美元"
    if any(word in lowered for word in ("central bank", "reserve", "央行")):
        return "央行"
    if any(word in lowered for word in ("gold", "xau", "bullion", "黄金", "金价")):
        return "黄金"
    if source_kind in {"fed", "macro"}:
        return "宏观"
    return "市场"


def parse_gdelt_time(value, now_factory=None):
    raw = str(value or "").strip()
    if len(raw) >= 15 and raw[8] == "T":
        try:
            return datetime.strptime(raw[:15], "%Y%m%dT%H%M%S").isoformat()
        except ValueError:
            pass
    now_factory = now_factory or datetime.now
    return now_factory().isoformat()


def parse_rss_time(value, now_factory=None):
    try:
        return parsedate_to_datetime(value).isoformat()
    except Exception:
        now_factory = now_factory or datetime.now
        return now_factory().isoformat()


def news_key(item):
    url = str(item.get("url") or "").strip().lower()
    if url:
        return url
    return str(item.get("title") or "").strip().lower()


def normalize_news_items(items, limit=20, now_factory=None):
    now_factory = now_factory or datetime.now
    seen = set()
    normalized = []
    for item in items:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        key = news_key(item)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({
            "title": title[:180],
            "url": url,
            "source": str(item.get("source") or "Public Source").strip(),
            "time": str(item.get("time") or now_factory().isoformat()),
            "topic": str(item.get("topic") or classify_news_topic(title)),
            "summary": str(item.get("summary") or "").strip()[:260],
        })

    def sort_key(item):
        try:
            parsed = datetime.fromisoformat(item["time"].replace("Z", "+00:00"))
            if parsed.tzinfo:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except ValueError:
            return datetime.min

    normalized.sort(key=sort_key, reverse=True)
    return normalized[:limit]


def parse_gdelt_articles(payload, limit=20, now_factory=None):
    articles = payload.get("articles", []) if isinstance(payload, dict) else []
    items = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        url = str(article.get("url") or "").strip()
        source = str(article.get("domain") or article.get("sourceCountry") or "GDELT").strip()
        text = f"{title} {source}"
        if not is_relevant_news(text):
            continue
        items.append({
            "title": title,
            "url": url,
            "source": source,
            "time": parse_gdelt_time(article.get("seendate"), now_factory=now_factory),
            "topic": classify_news_topic(text),
            "summary": "",
        })
    return normalize_news_items(items, limit=limit, now_factory=now_factory)


def parse_rss_items(xml_text, source_name, source_kind, limit=20, now_factory=None):
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        description = (item.findtext("description") or "").strip()
        text = f"{title} {description}"
        if not is_relevant_news(text):
            continue
        items.append({
            "title": title,
            "url": link,
            "source": source_name,
            "time": parse_rss_time(item.findtext("pubDate"), now_factory=now_factory),
            "topic": classify_news_topic(text, source_kind),
            "summary": description,
        })
    return normalize_news_items(items, limit=limit, now_factory=now_factory)


def select_related_news(title, items, limit=3):
    title_text = str(title or "")
    preferred = []
    fallback = []
    for item in list(items or []):
        topic = item.get("topic", "")
        haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
        if "利率" in title_text and topic == "利率":
            preferred.append(item)
        elif "波动" in title_text and topic in {"美元", "通胀", "利率"}:
            preferred.append(item)
        elif any(keyword in haystack for keyword in ("gold", "xau", "黄金", "金价")):
            preferred.append(item)
        else:
            fallback.append(item)
    return (preferred + fallback)[:limit]


class NewsCacheStore:
    def __init__(self, json_path, limit=20, now_factory=None):
        self.json_path = json_path
        self.limit = int(limit)
        self.now_factory = now_factory or datetime.now

    def normalize(self, items):
        return normalize_news_items(items, limit=self.limit, now_factory=self.now_factory)

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
        payload = wrap_item_payload(normalized, updated_at=self.now_factory().isoformat())
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized
