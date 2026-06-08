import json
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


gdelt_payload = {
    "articles": [
        {
            "title": "Gold rises as dollar weakens before Fed decision",
            "url": "https://example.com/gold-fed",
            "sourceCountry": "US",
            "domain": "example.com",
            "seendate": "20260529T120000Z",
            "socialimage": "",
        },
        {
            "title": "Gold rises as dollar weakens before Fed decision",
            "url": "https://example.com/gold-fed",
            "sourceCountry": "US",
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

rss_payload = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>Federal Reserve</title>
    <item>
      <title>Federal Reserve issues FOMC statement on inflation</title>
      <link>https://example.com/fomc</link>
      <pubDate>Fri, 29 May 2026 13:00:00 GMT</pubDate>
      <description>Policy statement references inflation and interest rates.</description>
    </item>
  </channel>
</rss>
"""

gdelt_items = app.parse_gdelt_articles(gdelt_payload)
if len(gdelt_items) != 1:
    raise SystemExit(f"expected one deduplicated relevant GDELT item, got {len(gdelt_items)}")

if gdelt_items[0]["topic"] not in {"黄金", "美元", "利率"}:
    raise SystemExit("GDELT item topic should be classified")

rss_items = app.parse_rss_items(rss_payload, "Federal Reserve", "fed")
if len(rss_items) != 1:
    raise SystemExit("expected one parsed RSS item")

if rss_items[0]["topic"] != "利率":
    raise SystemExit("RSS FOMC item should be classified as interest-rate related")

merged = app.normalize_news_items(gdelt_items + rss_items + gdelt_items)
if len(merged) != 2:
    raise SystemExit("news normalization must deduplicate items")

with tempfile.TemporaryDirectory() as tmp_dir:
    cache_path = Path(tmp_dir) / "news.json"
    original_path = app.NEWS_CACHE_PATH
    try:
        app.NEWS_CACHE_PATH = str(cache_path)
        app.save_news_cache(merged)
        cached = app.load_news_cache()
    finally:
        app.NEWS_CACHE_PATH = original_path

if len(cached) != 2:
    raise SystemExit("news cache roundtrip failed")

related = app.select_related_news("金价预警 - 上涨关注", merged)
if not related:
    raise SystemExit("alerts should be able to select related news")

print("news logic checks passed.")
