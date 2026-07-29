import threading
from datetime import datetime
from types import SimpleNamespace


def test_news_runtime_refreshes_cache_state_and_emits_snapshot():
    from goldmonitor.news import NewsRuntime

    state = SimpleNamespace(
        lock=threading.RLock(),
        news_items=[],
        news_last_updated=None,
        news_last_error="",
    )
    saved = []
    emitted = []
    runtime = NewsRuntime(
        state,
        fetch_news=lambda: [{"title": "Gold update"}],
        save_cache=lambda items: saved.extend(items),
        emit=lambda event, payload: emitted.append((event, payload)),
        limit=20,
        now_factory=lambda: datetime(2026, 7, 28, 12, 30),
    )

    assert runtime.refresh() is True
    assert state.news_last_updated == "2026-07-28T12:30:00"
    assert saved == [{"title": "Gold update"}]
    assert emitted == [(
        "news_updated",
        {
            "items": [{"title": "Gold update"}],
            "updated_at": "2026-07-28T12:30:00",
            "error": "",
        },
    )]


def test_news_runtime_preserves_existing_items_when_refresh_fails():
    from goldmonitor.news import NewsRuntime

    state = SimpleNamespace(
        lock=threading.RLock(),
        news_items=[{"title": "Cached"}],
        news_last_updated="2026-07-28T10:00:00",
        news_last_error="",
    )
    emitted = []

    def fail_fetch():
        raise OSError("network unavailable")

    runtime = NewsRuntime(
        state,
        fetch_news=fail_fetch,
        save_cache=lambda items: None,
        emit=lambda event, payload: emitted.append((event, payload)),
    )

    assert runtime.refresh() is False
    assert state.news_items == [{"title": "Cached"}]
    assert state.news_last_error == "资讯获取失败，请稍后重试。"
    assert emitted[-1][0] == "news_updated"


def test_news_runtime_loop_refreshes_then_waits():
    from goldmonitor.news import NewsRuntime

    state = SimpleNamespace(
        lock=threading.RLock(),
        news_items=[],
        news_last_updated=None,
        news_last_error="",
    )
    calls = []
    runtime = NewsRuntime(
        state,
        fetch_news=lambda: calls.append("refresh") or [],
        save_cache=lambda items: None,
        emit=lambda event, payload: None,
    )

    def stop_after_first_wait(seconds):
        calls.append(("sleep", seconds))
        raise StopIteration

    try:
        runtime.run_loop(interval=900, sleep=stop_after_first_wait)
    except StopIteration:
        pass

    assert calls == ["refresh", ("sleep", 900)]
