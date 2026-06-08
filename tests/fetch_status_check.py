from pathlib import Path
import tempfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app
import requests


with tempfile.TemporaryDirectory() as tmp_dir:
    original_market_cache_path = app.MARKET_CACHE_PATH
    app.MARKET_CACHE_PATH = str(Path(tmp_dir) / "market_cache.json")
    try:
        status = app.build_fetch_status(
            ok=False,
            message="无法获取金价数据",
            gold_ok=False,
            forex_ok=True,
            error="金价源请求超时",
        )

        if status["ok"] is not False:
            raise SystemExit("fetch status must preserve ok=false")

        if "金价源" not in status["message"]:
            raise SystemExit("fetch status must include the failed source")

        if "retryable" not in status:
            raise SystemExit("fetch status must tell the frontend whether retry is available")

        original_get = app.requests.get
        try:
            def timeout_get(*args, **kwargs):
                raise requests.Timeout()

            app.requests.get = timeout_get
            data, error = app.fetch_gold_data_result(app.GOLD_URL, "金价源")
        finally:
            app.requests.get = original_get

        if data is not None:
            raise SystemExit("timed out gold fetch must not return data")

        if error != "金价源请求超时":
            raise SystemExit(f"timed out gold fetch must explain the reason, got: {error}")

        sample_goldprice = {
            "date": "2026-06-01",
            "items": [
                {"curr": "USD", "xauPrice": 2350.5},
                {"curr": "CNY", "xauPrice": 17000.0},
            ],
        }
        data, cny_rate, parse_error = app.parse_goldprice_rates(sample_goldprice)

        if parse_error:
            raise SystemExit(f"goldprice sample should parse, got: {parse_error}")

        if data["close"] != 2350.5:
            raise SystemExit("goldprice parser must return XAU/USD price")

        if round(cny_rate, 6) != round(17000.0 / 2350.5, 6):
            raise SystemExit("goldprice parser must derive USD/CNY from CNY and USD XAU prices")

        eastmoney_payload = {
            "rc": 0,
            "data": {
                "f43": 235050,
                "f46": 234000,
                "f44": 236000,
                "f45": 233000,
                "f59": 2,
            },
        }
        eastmoney_data, eastmoney_error = app.parse_eastmoney_gold(eastmoney_payload)

        if eastmoney_error:
            raise SystemExit(f"eastmoney sample should parse, got: {eastmoney_error}")

        if eastmoney_data["close"] != 2350.5:
            raise SystemExit("eastmoney parser must scale f43 by f59")

        if eastmoney_data["open"] != 2340.0 or eastmoney_data["high"] != 2360.0 or eastmoney_data["low"] != 2330.0:
            raise SystemExit("eastmoney parser must parse OHLC fields")

        sina_gold_text = 'var hq_str_hf_XAU="2300.50,2301.20,2290.10,2295.00,2310.00,2288.00,11:30:00";'
        sina_gold_data, sina_gold_error = app.parse_sina_gold(sina_gold_text)

        if sina_gold_error:
            raise SystemExit(f"sina gold sample should parse, got: {sina_gold_error}")

        if sina_gold_data["close"] != 2300.5:
            raise SystemExit("sina gold parser must parse the current XAU/USD price")

        original_goldprice = app.fetch_goldprice_data_result
        original_gold_data = app.fetch_gold_data_result
        original_eastmoney = app.fetch_eastmoney_gold_result
        original_sina_gold = app.fetch_sina_gold_result
        original_csv_price = app.fetch_csv_price_result
        try:
            def working_eastmoney():
                raise SystemExit("eastmoney should not be called when sina gold source works")

            def working_sina_gold():
                return sina_gold_data, ""

            def working_goldprice():
                raise SystemExit("goldprice should not be called when sina gold source works")

            def failing_stooq(*args, **kwargs):
                raise SystemExit("stooq should not be called when sina gold source works")

            def no_forex(*args, **kwargs):
                return None, "汇率源测试跳过"

            app.fetch_sina_gold_result = working_sina_gold
            app.fetch_eastmoney_gold_result = working_eastmoney
            app.fetch_goldprice_data_result = working_goldprice
            app.fetch_gold_data_result = failing_stooq
            app.fetch_csv_price_result = no_forex
            market_data, market_rate_info, market_source, market_error, forex_error = app.fetch_market_data_result()
        finally:
            app.fetch_eastmoney_gold_result = original_eastmoney
            app.fetch_sina_gold_result = original_sina_gold
            app.fetch_goldprice_data_result = original_goldprice
            app.fetch_gold_data_result = original_gold_data
            app.fetch_csv_price_result = original_csv_price

        if market_data["close"] != 2300.5:
            raise SystemExit("market fetch must use the working sina gold source")

        if market_rate_info is not None:
            raise SystemExit(f"market fetch should not invent rate info when forex is unavailable, got: {market_rate_info}")

        if market_source != "新浪贵金属":
            raise SystemExit(f"market fetch must report the fallback source, got: {market_source}")

        if market_error:
            raise SystemExit("working sina gold source must not report gold fetch errors")

        captured_headers = {}
        original_get = app.requests.get
        try:
            class FakeGoldPriceResponse:
                def raise_for_status(self):
                    return None

                def json(self):
                    return sample_goldprice

            def capture_get(*args, **kwargs):
                captured_headers.update(kwargs.get("headers") or {})
                return FakeGoldPriceResponse()

            app.requests.get = capture_get
            app.fetch_goldprice_data_result()
        finally:
            app.requests.get = original_get

        user_agent = captured_headers.get("User-Agent", "")
        try:
            user_agent.encode("ascii")
        except UnicodeEncodeError:
            raise SystemExit("GoldPrice User-Agent must be ASCII so requests can send it")
    finally:
        app.MARKET_CACHE_PATH = original_market_cache_path

print("fetch status checks passed.")
