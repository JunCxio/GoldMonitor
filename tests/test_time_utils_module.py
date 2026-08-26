from datetime import datetime, timedelta, timezone


def test_time_utils_preserve_instant_when_offsets_differ():
    from goldmonitor.time_utils import iso_utc, parse_datetime, to_local_naive

    assert parse_datetime("2026-08-26T20:00:00+08:00") == datetime(
        2026,
        8,
        26,
        12,
        0,
        tzinfo=timezone.utc,
    )
    assert iso_utc("2026-08-26T20:00:00+08:00") == "2026-08-26T12:00:00Z"
    assert to_local_naive(
        "2026-08-26T12:00:00Z",
        target_timezone=timezone(timedelta(hours=8)),
    ) == datetime(2026, 8, 26, 20, 0)


def test_news_sorting_compares_real_instants_instead_of_wall_clock_text():
    from goldmonitor.news import normalize_news_items

    items = normalize_news_items([
        {
            "title": "较早",
            "url": "https://example.com/older",
            "time": "2026-08-26T20:00:00+08:00",
        },
        {
            "title": "较晚",
            "url": "https://example.com/newer",
            "time": "2026-08-26T13:00:00Z",
        },
    ])

    assert [item["title"] for item in items] == ["较晚", "较早"]


def test_market_cache_age_uses_timezone_offsets():
    from goldmonitor.market_data import MarketCacheStore

    store = MarketCacheStore(
        "unused.json",
        max_age_seconds=60,
        now_factory=lambda: datetime(2026, 8, 26, 12, 0, 30, tzinfo=timezone.utc),
    )

    assert store.is_fresh({
        "timestamp": "2026-08-26T20:00:00+08:00",
    }) is True
