import tempfile
from datetime import datetime
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 5, 29, 14, 0, 0)


def test_news_parsers_filter_dedupe_and_classify_market_items():
    from goldmonitor.news import parse_gdelt_articles, parse_rss_items

    gdelt_payload = {
        "articles": [
            {
                "title": "Gold rises as dollar weakens before Fed decision",
                "url": "https://example.com/gold-fed",
                "sourceCountry": "US",
                "domain": "example.com",
                "seendate": "20260529T120000Z",
            },
            {
                "title": "Gold rises as dollar weakens before Fed decision",
                "url": "https://example.com/gold-fed",
                "domain": "example.com",
                "seendate": "20260529T120000Z",
            },
            {
                "title": "Unrelated sports headline",
                "url": "https://example.com/sports",
                "domain": "example.com",
                "seendate": "20260529T120000Z",
            },
        ]
    }

    gdelt_items = parse_gdelt_articles(gdelt_payload, now_factory=fixed_now)
    assert len(gdelt_items) == 1
    assert gdelt_items[0]["url"] == "https://example.com/gold-fed"
    assert gdelt_items[0]["time"] == "2026-05-29T12:00:00"
    assert gdelt_items[0]["topic"] in {"黄金", "美元", "利率"}

    rss_payload = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <item>
      <title>Federal Reserve issues FOMC statement on inflation</title>
      <link>https://example.com/fomc</link>
      <pubDate>Fri, 29 May 2026 13:00:00 GMT</pubDate>
      <description>Policy statement references inflation and interest rates.</description>
    </item>
  </channel>
</rss>
"""
    rss_items = parse_rss_items(rss_payload, "Federal Reserve", "fed", now_factory=fixed_now)
    assert len(rss_items) == 1
    assert rss_items[0]["topic"] == "利率"
    assert rss_items[0]["source"] == "Federal Reserve"


def test_news_normalization_cache_and_related_selection_are_stable():
    from goldmonitor.news import NewsCacheStore, normalize_news_items, select_related_news

    items = normalize_news_items([
        {
            "title": "黄金价格上涨",
            "url": "https://example.com/gold",
            "source": "",
            "time": "2026-05-29T12:00:00",
            "summary": "金价受到美元回落支撑。",
        },
        {
            "title": "Fed rate decision",
            "url": "https://example.com/fed",
            "source": "Fed",
            "time": "2026-05-29T13:00:00+00:00",
            "summary": "Interest rate decision references inflation.",
        },
        {
            "title": "duplicate",
            "url": "https://example.com/gold",
            "source": "Other",
            "time": "2026-05-29T14:00:00",
        },
        {"title": "", "url": "https://example.com/empty"},
    ], now_factory=fixed_now)

    assert [item["url"] for item in items] == ["https://example.com/fed", "https://example.com/gold"]
    assert items[1]["source"] == "Public Source"
    assert items[1]["summary"] == "金价受到美元回落支撑。"

    related = select_related_news("金价预警 - 上涨关注", items)
    assert related[0]["url"] == "https://example.com/gold"

    with tempfile.TemporaryDirectory() as tmp_dir:
        store = NewsCacheStore(str(Path(tmp_dir) / "news.json"), now_factory=fixed_now)
        store.save(items)
        cached = store.load()
    assert cached == items


if __name__ == "__main__":
    failures = []
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            try:
                value()
            except Exception as exc:
                failures.append((name, exc))
    if failures:
        for name, exc in failures:
            print(f"{name}: {type(exc).__name__}: {exc}")
        raise SystemExit(1)
    print("news module checks passed.")
