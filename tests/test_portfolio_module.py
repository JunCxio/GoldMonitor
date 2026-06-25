import csv
import json
import sys
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 25, 10, 0, 0)


def test_portfolio_positions_normalize_value_and_summarize_by_currency():
    from goldmonitor.portfolio import build_portfolio_state, normalize_portfolio_position

    rmb_position = normalize_portfolio_position(
        {
            "name": "  实物金条  ",
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "10",
            "entry_date": "2026-06-01",
            "note": "长期持有" * 80,
        },
        now_factory=fixed_now,
        id_factory=lambda: "position-rmb",
    )
    usd_position = normalize_portfolio_position(
        {
            "name": "黄金 ETF",
            "mode": "usd",
            "entry_price": "2300",
            "quantity": "2",
            "entry_date": "2026-06-10",
        },
        now_factory=fixed_now,
        id_factory=lambda: "position-usd",
    )

    assert rmb_position["id"] == "position-rmb"
    assert rmb_position["name"] == "实物金条"
    assert rmb_position["entry_price"] == 680.0
    assert rmb_position["quantity"] == 10.0
    assert rmb_position["created_at"] == "2026-06-25T10:00:00"
    assert len(rmb_position["note"]) == 200

    state = build_portfolio_state([rmb_position, usd_position], {"rmb": 700.0, "usd": 2350.0})
    assert state["total"] == 2
    assert state["items"][0]["cost"] == 6800.0
    assert state["items"][0]["market_value"] == 7000.0
    assert state["items"][0]["pnl"] == 200.0
    assert state["items"][0]["pnl_percent"] == 2.9412
    assert state["items"][0]["valuation_status"] == "valued"
    assert state["items"][1]["cost"] == 4600.0
    assert state["items"][1]["market_value"] == 4700.0
    assert state["rmb_summary"] == {
        "count": 1,
        "valued": 1,
        "cost": 6800.0,
        "market_value": 7000.0,
        "pnl": 200.0,
        "pnl_percent": 2.9412,
    }
    assert state["usd_summary"] == {
        "count": 1,
        "valued": 1,
        "cost": 4600.0,
        "market_value": 4700.0,
        "pnl": 100.0,
        "pnl_percent": 2.1739,
    }


def test_portfolio_state_marks_waiting_price_and_invalid_position():
    from goldmonitor.portfolio import build_portfolio_state, normalize_portfolio_positions

    positions = normalize_portfolio_positions(
        [
            {"id": "valid-usd", "name": "美元持仓", "mode": "usd", "entry_price": "2300", "quantity": "1"},
            {"id": "bad-rmb", "name": "异常持仓", "mode": "rmb", "entry_price": "bad", "quantity": "5"},
            {"id": "skip", "name": "", "mode": "rmb", "entry_price": "680", "quantity": "1"},
        ],
        now_factory=fixed_now,
        id_factory=lambda: "position-generated",
    )

    assert [item["id"] for item in positions] == ["valid-usd", "bad-rmb"]
    state = build_portfolio_state(positions, {"rmb": 700.0, "usd": None})
    by_id = {item["id"]: item for item in state["items"]}
    assert by_id["valid-usd"]["valuation_status"] == "waiting_price"
    assert by_id["valid-usd"]["current_price"] is None
    assert by_id["bad-rmb"]["valuation_status"] == "invalid_position"
    assert by_id["bad-rmb"]["cost"] is None
    assert state["usd_summary"]["count"] == 1
    assert state["usd_summary"]["valued"] == 0
    assert state["rmb_summary"]["count"] == 1
    assert state["rmb_summary"]["valued"] == 0


def test_portfolio_store_persists_versioned_json_and_csv_export():
    from goldmonitor.portfolio import PortfolioPositionStore, build_portfolio_csv

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "portfolio_positions.json"
        store = PortfolioPositionStore(str(path), now_factory=fixed_now, id_factory=lambda: "position-store")
        saved = store.save([
            {"name": "金条", "mode": "rmb", "entry_price": "680", "quantity": "3", "entry_date": "2026-06-01"},
            {"name": "XAU", "mode": "usd", "entry_price": "2300", "quantity": "1.5", "note": "账户持仓"},
        ])

        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert len(payload["items"]) == 2
        assert store.load() == saved

        csv_text, count = build_portfolio_csv(saved, {"rmb": 700.0, "usd": 2350.0})
        assert count == 2
        rows = list(csv.DictReader(StringIO(csv_text)))
        assert rows[0]["name"] == "金条"
        assert rows[0]["current_price"] == "700.0"
        assert rows[0]["pnl"] == "60.0"
        assert rows[1]["mode"] == "usd"
        assert rows[1]["valuation_status"] == "valued"


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
    print("portfolio module checks passed.")
