from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app


sina_rate, sina_error = app.parse_sina_forex('var hq_str_fx_susdcny="美元人民币,7.1234,7.1200";')
if sina_error or sina_rate != 7.1234:
    raise SystemExit(f"sina forex parser failed: rate={sina_rate}, error={sina_error}")

frankfurter_rate, frankfurter_error = app.parse_frankfurter_forex({"rates": {"CNY": 7.2345}})
if frankfurter_error or frankfurter_rate != 7.2345:
    raise SystemExit(f"frankfurter forex parser failed: rate={frankfurter_rate}, error={frankfurter_error}")

with tempfile.TemporaryDirectory() as tmp_dir:
    original_path = app.MARKET_CACHE_PATH
    original_source_metrics_path = app.SOURCE_METRICS_PATH
    try:
        app.MARKET_CACHE_PATH = str(Path(tmp_dir) / "market_cache.json")
        app.SOURCE_METRICS_PATH = str(Path(tmp_dir) / "source_metrics.json")
        cached = {
            "value": 7.1111,
            "source": "测试缓存",
            "timestamp": datetime.now().isoformat(),
        }
        saved = app.save_usdcny_cache(cached["value"], cached["source"], cached["timestamp"])
        if saved["cached"]:
            raise SystemExit("freshly saved forex rate must be marked as realtime, not cached")
        loaded = app.load_usdcny_cache()
        if loaded["value"] != cached["value"] or loaded["source"] != cached["source"]:
            raise SystemExit(f"cached forex did not round-trip: {loaded}")
        if not loaded["cached"]:
            raise SystemExit("loaded forex cache must be marked as cached")

        stale_timestamp = (datetime.now() - timedelta(days=8)).isoformat()
        app.save_usdcny_cache(7.2222, "过期缓存", stale_timestamp)
        stale = app.load_valid_usdcny_cache()
        if stale is not None:
            raise SystemExit("stale forex cache must not be used")

        fresh_timestamp = (datetime.now() - timedelta(hours=2)).isoformat()
        app.save_usdcny_cache(7.3333, "新鲜缓存", fresh_timestamp)
        app.usdcny_rate = None
        app.usdcny_rate_source = ""
        app.usdcny_rate_time = None
        app.usdcny_rate_cached = False
        app.usdcny_rate_error = ""
        app.initialize_market_cache()
        if app.usdcny_rate != 7.3333 or not app.usdcny_rate_cached:
            raise SystemExit("startup must initialize USD/CNY from fresh cache")

        original_sina_gold = app.fetch_sina_gold_result
        original_eastmoney = app.fetch_eastmoney_gold_result
        original_goldprice = app.fetch_goldprice_data_result
        original_stooq_gold = app.fetch_gold_data_result
        original_sina = app.fetch_sina_forex_result
        original_frankfurter = app.fetch_frankfurter_forex_result
        original_stooq = app.fetch_csv_price_result
        try:
            def failing_sina_gold():
                return None, "新浪贵金属请求超时"

            def working_gold():
                return {
                    "date": "2026-06-01",
                    "time": "11:30:00",
                    "open": 2300.0,
                    "high": 2310.0,
                    "low": 2290.0,
                    "close": 2300.0,
                }, ""

            def failing_sina():
                return None, "新浪汇率请求超时"

            def failing_frankfurter():
                return None, "Frankfurter 请求超时"

            def failing_stooq(*args, **kwargs):
                return None, "Stooq 汇率源请求超时"

            def failing_goldprice():
                return None, None, "GoldPrice 请求超时"

            def failing_stooq_gold(*args, **kwargs):
                return None, "Stooq 金价源请求超时"

            app.fetch_sina_gold_result = failing_sina_gold
            app.fetch_eastmoney_gold_result = working_gold
            app.fetch_goldprice_data_result = failing_goldprice
            app.fetch_gold_data_result = failing_stooq_gold
            app.fetch_sina_forex_result = failing_sina
            app.fetch_frankfurter_forex_result = failing_frankfurter
            app.fetch_csv_price_result = failing_stooq

            data, rate_info, source, gold_error, forex_error = app.fetch_market_data_result()
        finally:
            app.fetch_sina_gold_result = original_sina_gold
            app.fetch_eastmoney_gold_result = original_eastmoney
            app.fetch_goldprice_data_result = original_goldprice
            app.fetch_gold_data_result = original_stooq_gold
            app.fetch_sina_forex_result = original_sina
            app.fetch_frankfurter_forex_result = original_frankfurter
            app.fetch_csv_price_result = original_stooq

        if data["close"] != 2300.0:
            raise SystemExit("market fetch must preserve gold data when forex falls back to cache")

        if rate_info["value"] != 7.3333 or not rate_info["cached"]:
            raise SystemExit(f"market fetch must use fresh forex cache, got: {rate_info}")

        if source != "东方财富":
            raise SystemExit(f"market fetch must preserve gold source, got: {source}")

        if "Stooq" not in forex_error:
            raise SystemExit(f"forex error should explain failed live sources, got: {forex_error}")
    finally:
        app.MARKET_CACHE_PATH = original_path
        app.SOURCE_METRICS_PATH = original_source_metrics_path

print("forex cache checks passed.")
