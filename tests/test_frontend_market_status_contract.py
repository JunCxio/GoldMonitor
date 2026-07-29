from pathlib import Path


def test_frontend_fetch_status_uses_degraded_status_contract():
    js = Path("static/market-dashboard.js").read_text(encoding="utf-8")
    start = js.index("function applyFetchStatus")
    end = js.index("function refreshPrice", start)
    body = js[start:end]

    assert "data.degraded" in body
    assert "data.status" in body
    assert "degraded" in body


def test_frontend_alert_log_uses_notification_summary_contract():
    js = Path("static/alert-log-center.js").read_text(encoding="utf-8")
    start = js.index("function alertNotificationIssues")
    end = js.index("function buildLogEntry", start)
    body = js[start:end]

    assert "notification_summary" in body
    assert "partial" in body
    assert "muted" in body
