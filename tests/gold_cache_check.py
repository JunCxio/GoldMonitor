from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


def sample_gold(close=2300.0):
    return {
        "date": "2026-06-01",
        "time": "12:00:00",
        "open": close - 5,
        "high": close + 10,
        "low": close - 20,
        "close": close,
    }


with tempfile.TemporaryDirectory() as tmp_dir:
    original_cache_path = app.MARKET_CACHE_PATH
    original_source_metrics_path = app.SOURCE_METRICS_PATH
    original_fetchers = {
        "fetch_sina_gold_result": app.fetch_sina_gold_result,
        "fetch_eastmoney_gold_result": app.fetch_eastmoney_gold_result,
        "fetch_goldprice_data_result": app.fetch_goldprice_data_result,
        "fetch_gold_data_result": app.fetch_gold_data_result,
        "fetch_sina_forex_result": app.fetch_sina_forex_result,
        "fetch_frankfurter_forex_result": app.fetch_frankfurter_forex_result,
        "fetch_csv_price_result": app.fetch_csv_price_result,
        "fetch_market_data_result": app.fetch_market_data_result,
        "socketio_emit": app.socketio.emit,
    }
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
        "last_fetch_ok": app.last_fetch_ok,
        "last_fetch_error": app.last_fetch_error,
    }
    try:
        app.MARKET_CACHE_PATH = str(Path(tmp_dir) / "market_cache.json")
        app.SOURCE_METRICS_PATH = str(Path(tmp_dir) / "source_metrics.json")
        now = datetime.now().isoformat()
        app.save_usdcny_cache(7.25, "测试汇率", now)
        app.save_xauusd_cache(sample_gold(), "测试金价源", now)

        cached_rate = app.load_valid_usdcny_cache()
        if cached_rate["value"] != 7.25:
            raise SystemExit("saving XAU/USD cache must not overwrite USD/CNY cache")

        cached_gold = app.load_valid_xauusd_cache()
        if cached_gold["close"] != 2300.0 or cached_gold["source"] != "测试金价源":
            raise SystemExit(f"fresh XAU/USD cache must round-trip, got: {cached_gold}")

        stale = (datetime.now() - timedelta(days=8)).isoformat()
        app.save_xauusd_cache(sample_gold(2200.0), "过期金价源", stale)
        if app.load_valid_xauusd_cache() is not None:
            raise SystemExit("stale XAU/USD cache must not be used")

        app.save_xauusd_cache(sample_gold(), "测试金价源", now)

        def failing_sina_gold():
            return None, "新浪贵金属请求超时"

        def failing_eastmoney_gold():
            return None, "东方财富网络连接失败"

        def failing_goldprice():
            return None, None, "GoldPrice HTTP错误 403"

        def failing_stooq_gold(*args, **kwargs):
            return None, "Stooq 金价源请求超时"

        def failing_sina_forex():
            return None, "新浪汇率请求超时"

        def failing_frankfurter_forex():
            return None, "Frankfurter 请求超时"

        def failing_stooq_forex(*args, **kwargs):
            return None, "Stooq 汇率源请求超时"

        app.fetch_sina_gold_result = failing_sina_gold
        app.fetch_eastmoney_gold_result = failing_eastmoney_gold
        app.fetch_goldprice_data_result = failing_goldprice
        app.fetch_gold_data_result = failing_stooq_gold
        app.fetch_sina_forex_result = failing_sina_forex
        app.fetch_frankfurter_forex_result = failing_frankfurter_forex
        app.fetch_csv_price_result = failing_stooq_forex

        data, rate_info, source, gold_error, forex_error = app.fetch_market_data_result()
        if data["close"] != 2300.0 or not data.get("cached"):
            raise SystemExit(f"market fetch must fall back to fresh XAU/USD cache, got: {data}")

        if "缓存金价" not in source:
            raise SystemExit(f"cached market fetch must report cached gold source, got: {source}")

        if "GoldPrice HTTP错误 403" not in gold_error:
            raise SystemExit(f"cached market fetch must keep live failure reasons, got: {gold_error}")

        if rate_info["value"] != 7.25 or not rate_info["cached"]:
            raise SystemExit(f"cached market fetch must keep cached USD/CNY rate, got: {rate_info}")

        emitted = []

        def cached_market_data():
            return data, rate_info, source, gold_error, forex_error

        def capture_emit(name, payload=None, *args, **kwargs):
            emitted.append((name, payload))

        app.fetch_market_data_result = cached_market_data
        app.socketio.emit = capture_emit
        ok = app.fetch_price_once()
        if not ok:
            raise SystemExit("fetch_price_once should display cached market data")

        price_updates = [payload for name, payload in emitted if name == "price_update"]
        if not price_updates or not price_updates[-1].get("gold_cached"):
            raise SystemExit(f"price_update must expose cached gold status, got: {price_updates}")

        statuses = [payload for name, payload in emitted if name == "fetch_status"]
        if not any((status.get("ok") is False and "使用缓存金价" in status.get("message", "")) for status in statuses):
            raise SystemExit(f"fetch_status must tell the user cached gold is used, got: {statuses}")
    finally:
        app.MARKET_CACHE_PATH = original_cache_path
        app.SOURCE_METRICS_PATH = original_source_metrics_path
        app.fetch_sina_gold_result = original_fetchers["fetch_sina_gold_result"]
        app.fetch_eastmoney_gold_result = original_fetchers["fetch_eastmoney_gold_result"]
        app.fetch_goldprice_data_result = original_fetchers["fetch_goldprice_data_result"]
        app.fetch_gold_data_result = original_fetchers["fetch_gold_data_result"]
        app.fetch_sina_forex_result = original_fetchers["fetch_sina_forex_result"]
        app.fetch_frankfurter_forex_result = original_fetchers["fetch_frankfurter_forex_result"]
        app.fetch_csv_price_result = original_fetchers["fetch_csv_price_result"]
        app.fetch_market_data_result = original_fetchers["fetch_market_data_result"]
        app.socketio.emit = original_fetchers["socketio_emit"]
        for key, value in original_state.items():
            setattr(app, key, value)

print("gold cache checks passed.")
