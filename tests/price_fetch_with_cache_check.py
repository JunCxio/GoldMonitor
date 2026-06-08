from datetime import datetime
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


with tempfile.TemporaryDirectory() as tmp_dir:
    original_cache_path = app.MARKET_CACHE_PATH
    original_fetch_market = app.fetch_market_data_result
    original_emit = app.socketio.emit
    original_state = {
        "price_usd": app.price_usd,
        "price_rmb": app.price_rmb,
        "previous_usd": app.previous_usd,
        "previous_rmb": app.previous_rmb,
        "usdcny_rate": app.usdcny_rate,
        "usdcny_rate_source": app.usdcny_rate_source,
        "usdcny_rate_time": app.usdcny_rate_time,
        "usdcny_rate_cached": app.usdcny_rate_cached,
        "usdcny_rate_error": app.usdcny_rate_error,
        "price_history": list(app.price_history),
        "klines_5min": list(app.klines_5min),
    }
    emitted = []
    try:
        app.MARKET_CACHE_PATH = str(Path(tmp_dir) / "market_cache.json")
        app.save_usdcny_cache(7.25, "测试缓存", datetime.now().isoformat())

        def fake_market_data():
            return {
                "date": "2026-06-01",
                "time": "12:00:00",
                "open": 2300.0,
                "high": 2310.0,
                "low": 2290.0,
                "close": 2300.0,
            }, app.load_valid_usdcny_cache(), "新浪贵金属", "", "实时汇率测试失败"

        def capture_emit(name, data=None, *args, **kwargs):
            emitted.append((name, data))

        app.fetch_market_data_result = fake_market_data
        app.socketio.emit = capture_emit
        ok = app.fetch_price_once()
    finally:
        app.fetch_market_data_result = original_fetch_market
        app.socketio.emit = original_emit
        app.MARKET_CACHE_PATH = original_cache_path
        for key, value in original_state.items():
            setattr(app, key, value)

    if not ok:
        raise SystemExit("fetch_price_once should succeed with cached forex rate")

    price_updates = [data for name, data in emitted if name == "price_update"]
    if not price_updates:
        raise SystemExit("fetch_price_once must emit price_update")

    latest = price_updates[-1]
    expected_rmb = round(2300.0 * 7.25 / app.OZ_TO_GRAM, 2)
    if latest["rmb"] != expected_rmb:
        raise SystemExit(f"RMB price should use cached forex rate, got {latest['rmb']} expected {expected_rmb}")

    if not latest["rate_cached"] or latest["rate_source"] != "测试缓存":
        raise SystemExit(f"price_update must expose cached rate status, got {latest}")

    statuses = [data for name, data in emitted if name == "fetch_status"]
    if not any("使用缓存汇率" in status.get("message", "") for status in statuses):
        raise SystemExit(f"fetch_status must tell the user cached forex is used, got {statuses}")

print("price fetch with cache checks passed.")
