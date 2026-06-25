import csv
import json
import sys
import tempfile
from datetime import datetime
from io import StringIO
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def fixed_now():
    return datetime(2026, 6, 25, 10, 0, 0)


def later_now():
    return datetime(2026, 6, 26, 11, 30, 0)


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
    long_name_position = normalize_portfolio_position(
        {
            "name": "金" * 70,
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "1",
        },
        now_factory=fixed_now,
        id_factory=lambda: "position-long-name",
    )
    assert long_name_position["name"] == "金" * 60

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
            {"id": "valid-usd", "name": "重复美元持仓", "mode": "usd", "entry_price": "2400", "quantity": "2"},
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


def test_portfolio_normalization_dates_and_timestamps():
    from goldmonitor.portfolio import normalize_portfolio_position

    invalid_date_position = normalize_portfolio_position(
        {
            "name": "日期异常",
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "1",
            "entry_date": "2026-99-99",
            "updated_at": "2000-01-01T00:00:00",
        },
        now_factory=fixed_now,
        id_factory=lambda: "position-invalid-date",
    )
    valid_date_position = normalize_portfolio_position(
        {
            "name": "日期有效",
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "1",
            "entry_date": "2026-06-25 10:00:00",
        },
        now_factory=fixed_now,
        id_factory=lambda: "position-valid-date",
    )
    existing = normalize_portfolio_position(
        {
            "id": "position-existing",
            "name": "原始持仓",
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "1",
            "created_at": "2026-06-01T09:00:00",
            "updated_at": "2026-06-01T09:00:00",
        },
        now_factory=fixed_now,
        id_factory=lambda: "unused",
    )
    updated = normalize_portfolio_position(
        {
            "id": "position-existing",
            "name": "更新持仓",
            "mode": "rmb",
            "entry_price": "690",
            "quantity": "1",
            "created_at": "2026-06-20T09:00:00",
            "updated_at": "2026-06-20T09:00:00",
        },
        existing=existing,
        now_factory=later_now,
        id_factory=lambda: "unused",
    )

    assert invalid_date_position["entry_date"] == ""
    assert invalid_date_position["updated_at"] == "2026-06-25T10:00:00"
    assert valid_date_position["entry_date"] == "2026-06-25"
    assert updated["created_at"] == "2026-06-01T09:00:00"
    assert updated["updated_at"] == "2026-06-26T11:30:00"


def test_portfolio_public_helpers_contracts():
    from goldmonitor.portfolio import empty_portfolio_summary, find_portfolio_position_index

    items = [{"id": "position-a"}, {"id": "position-b"}]
    assert find_portfolio_position_index(items, "") == -1
    assert find_portfolio_position_index(items, "missing") == -1
    assert find_portfolio_position_index(items, "position-b") == 1
    assert empty_portfolio_summary() == {
        "count": 0,
        "valued": 0,
        "cost": 0.0,
        "market_value": 0.0,
        "pnl": 0.0,
        "pnl_percent": 0.0,
    }


def test_portfolio_store_persists_versioned_json_and_csv_export():
    from goldmonitor.portfolio import PortfolioPositionStore, build_portfolio_csv

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "portfolio_positions.json"
        generated_ids = iter(["position-store-rmb", "position-store-usd"])
        store = PortfolioPositionStore(
            str(path),
            now_factory=fixed_now,
            id_factory=lambda: next(generated_ids),
        )
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
        header = next(csv.reader(StringIO(csv_text)))
        assert header == [
            "id",
            "name",
            "mode",
            "entry_price",
            "quantity",
            "entry_date",
            "current_price",
            "cost",
            "market_value",
            "pnl",
            "pnl_percent",
            "valuation_status",
            "note",
        ]
        rows = list(csv.DictReader(StringIO(csv_text)))
        assert rows[0]["name"] == "金条"
        assert rows[0]["current_price"] == "700.0"
        assert rows[0]["pnl"] == "60.0"
        assert rows[1]["mode"] == "usd"
        assert rows[1]["valuation_status"] == "valued"


def test_portfolio_transactions_migrate_and_calculate_realized_pnl():
    from goldmonitor.portfolio import (
        build_portfolio_state_from_transactions,
        normalize_portfolio_transaction,
        transactions_from_positions,
        validate_portfolio_transactions,
    )

    migrated = transactions_from_positions(
        [{
            "id": "position-rmb",
            "name": "旧金条",
            "mode": "rmb",
            "entry_price": "680",
            "quantity": "10",
            "entry_date": "2026-06-01",
            "note": "旧持仓",
            "created_at": "2026-06-01T09:00:00",
            "updated_at": "2026-06-01T09:00:00",
        }],
        now_factory=fixed_now,
    )
    assert migrated == [{
        "id": "transaction-position-rmb",
        "position_id": "position-rmb",
        "name": "旧金条",
        "type": "buy",
        "mode": "rmb",
        "price": 680.0,
        "quantity": 10.0,
        "fee": 0.0,
        "trade_date": "2026-06-01",
        "note": "旧持仓",
        "created_at": "2026-06-01T09:00:00",
        "updated_at": "2026-06-01T09:00:00",
    }]

    second_buy = normalize_portfolio_transaction(
        {
            "position_id": "position-rmb",
            "name": "旧金条",
            "type": "buy",
            "mode": "rmb",
            "price": "700",
            "quantity": "10",
            "fee": "20",
            "trade_date": "2026-06-10",
        },
        now_factory=fixed_now,
        id_factory=lambda: "transaction-buy-2",
    )
    sell = normalize_portfolio_transaction(
        {
            "position_id": "position-rmb",
            "name": "旧金条",
            "type": "sell",
            "mode": "rmb",
            "price": "730",
            "quantity": "5",
            "fee": "5",
            "trade_date": "2026-06-20",
        },
        now_factory=fixed_now,
        id_factory=lambda: "transaction-sell-1",
    )
    transactions = migrated + [second_buy, sell]

    validate_portfolio_transactions(transactions)
    state = build_portfolio_state_from_transactions(transactions, {"rmb": 740.0, "usd": 2350.0})
    item = state["items"][0]
    assert state["total"] == 1
    assert len(state["transactions"]) == 3
    assert item["id"] == "position-rmb"
    assert item["quantity"] == 15.0
    assert item["average_cost"] == 691.0
    assert item["cost_basis"] == 10365.0
    assert item["market_value"] == 11100.0
    assert item["unrealized_pnl"] == 735.0
    assert item["realized_pnl"] == 190.0
    assert item["total_pnl"] == 925.0
    assert item["fees"] == 25.0
    assert item["pnl"] == 735.0
    assert state["transactions"][2]["realized_pnl"] == 190.0
    assert state["rmb_summary"]["cost"] == 10365.0
    assert state["rmb_summary"]["unrealized_pnl"] == 735.0
    assert state["rmb_summary"]["realized_pnl"] == 190.0
    assert state["rmb_summary"]["total_pnl"] == 925.0
    assert state["rmb_summary"]["pnl"] == 925.0


def test_portfolio_review_tracks_cash_flow_and_realized_pnl():
    from goldmonitor.portfolio import build_portfolio_state_from_transactions, normalize_portfolio_transaction

    transactions = [
        normalize_portfolio_transaction(
            {
                "position_id": "position-rmb",
                "name": "金条",
                "type": "buy",
                "mode": "rmb",
                "price": "680",
                "quantity": "10",
                "fee": "5",
                "trade_date": "2026-06-01",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-buy-rmb-1",
        ),
        normalize_portfolio_transaction(
            {
                "position_id": "position-usd",
                "name": "XAU",
                "type": "buy",
                "mode": "usd",
                "price": "2300",
                "quantity": "1",
                "fee": "2",
                "trade_date": "2026-06-03",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-buy-usd-1",
        ),
        normalize_portfolio_transaction(
            {
                "position_id": "position-rmb",
                "name": "金条",
                "type": "buy",
                "mode": "rmb",
                "price": "700",
                "quantity": "5",
                "fee": "10",
                "trade_date": "2026-06-10",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-buy-rmb-2",
        ),
        normalize_portfolio_transaction(
            {
                "position_id": "position-rmb",
                "name": "金条",
                "type": "sell",
                "mode": "rmb",
                "price": "740",
                "quantity": "6",
                "fee": "6",
                "trade_date": "2026-06-10",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-sell-rmb-1",
        ),
    ]

    state = build_portfolio_state_from_transactions(transactions, {"rmb": 750.0, "usd": 2350.0})

    assert state["review"]["rmb"] == {
        "mode": "rmb",
        "trade_count": 3,
        "buy_count": 2,
        "sell_count": 1,
        "buy_amount": 10315.0,
        "sell_amount": 4434.0,
        "fee_total": 21.0,
        "realized_pnl": 308.0,
        "net_invested": 5881.0,
        "current_quantity": 9.0,
        "cost_basis": 6189.0,
        "average_cost": 687.6667,
        "first_trade_date": "2026-06-01",
        "last_trade_date": "2026-06-10",
        "points": [
            {
                "date": "2026-06-01",
                "trade_count": 1,
                "buy_amount": 6805.0,
                "sell_amount": 0.0,
                "fee": 5.0,
                "realized_pnl": 0.0,
                "cumulative_buy_amount": 6805.0,
                "cumulative_sell_amount": 0.0,
                "cumulative_fee": 5.0,
                "cumulative_realized_pnl": 0.0,
                "net_invested": 6805.0,
                "quantity": 10.0,
                "cost_basis": 6805.0,
            },
            {
                "date": "2026-06-10",
                "trade_count": 2,
                "buy_amount": 3510.0,
                "sell_amount": 4434.0,
                "fee": 16.0,
                "realized_pnl": 308.0,
                "cumulative_buy_amount": 10315.0,
                "cumulative_sell_amount": 4434.0,
                "cumulative_fee": 21.0,
                "cumulative_realized_pnl": 308.0,
                "net_invested": 5881.0,
                "quantity": 9.0,
                "cost_basis": 6189.0,
            },
        ],
    }
    assert state["review"]["usd"]["trade_count"] == 1
    assert state["review"]["usd"]["buy_amount"] == 2302.0
    assert state["review"]["usd"]["sell_amount"] == 0.0
    assert state["review"]["usd"]["net_invested"] == 2302.0
    assert state["review"]["usd"]["current_quantity"] == 1.0

    empty_review = build_portfolio_state_from_transactions([], {})["review"]
    assert empty_review["rmb"]["points"] == []
    assert empty_review["usd"]["trade_count"] == 0


def test_portfolio_review_markdown_export_includes_summary_positions_and_transactions():
    from goldmonitor import portfolio as portfolio_core

    transactions = [
        portfolio_core.normalize_portfolio_transaction(
            {
                "position_id": "position-rmb",
                "name": "金条",
                "type": "buy",
                "mode": "rmb",
                "price": "680",
                "quantity": "10",
                "fee": "5",
                "trade_date": "2026-06-01",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-buy-rmb",
        ),
        portfolio_core.normalize_portfolio_transaction(
            {
                "position_id": "position-rmb",
                "name": "金条",
                "type": "sell",
                "mode": "rmb",
                "price": "730",
                "quantity": "2",
                "fee": "4",
                "trade_date": "2026-06-10",
            },
            now_factory=fixed_now,
            id_factory=lambda: "transaction-sell-rmb",
        ),
    ]

    markdown, count = portfolio_core.build_portfolio_review_markdown(
        transactions,
        {"rmb": 740.0, "usd": 2350.0},
        generated_at=fixed_now(),
    )

    assert count == 2
    assert "# 持仓复盘" in markdown
    assert "导出时间：2026-06-25 10:00:00" in markdown
    assert "人民币复盘" in markdown
    assert "金条" in markdown
    assert "已实现" in markdown
    assert "2026-06-10" in markdown
    assert "transaction-sell-rmb" in markdown


def test_portfolio_transactions_reject_invalid_oversell_and_mode_mismatch():
    from goldmonitor.portfolio import normalize_portfolio_transaction, validate_portfolio_transactions

    buy = normalize_portfolio_transaction(
        {"position_id": "position-rmb", "name": "金条", "type": "buy", "mode": "rmb", "price": "680", "quantity": "2"},
        now_factory=fixed_now,
        id_factory=lambda: "transaction-buy",
    )
    oversell = normalize_portfolio_transaction(
        {"position_id": "position-rmb", "name": "金条", "type": "sell", "mode": "rmb", "price": "700", "quantity": "3"},
        now_factory=fixed_now,
        id_factory=lambda: "transaction-sell",
    )
    usd_buy = normalize_portfolio_transaction(
        {"position_id": "position-rmb", "name": "金条", "type": "buy", "mode": "usd", "price": "2300", "quantity": "1"},
        now_factory=fixed_now,
        id_factory=lambda: "transaction-usd",
    )

    with pytest.raises(ValueError, match="卖出数量不能超过当前持仓"):
        validate_portfolio_transactions([buy, oversell])

    with pytest.raises(ValueError, match="同一持仓单位必须一致"):
        validate_portfolio_transactions([buy, usd_buy])


def test_portfolio_transaction_store_migrates_legacy_positions_and_exports_csv():
    from goldmonitor.portfolio import (
        PortfolioTransactionStore,
        build_portfolio_positions_csv,
        build_portfolio_transactions_csv,
    )

    with tempfile.TemporaryDirectory() as tmp_dir:
        legacy_path = Path(tmp_dir) / "portfolio_positions.json"
        transaction_path = Path(tmp_dir) / "portfolio_transactions.json"
        legacy_path.write_text(json.dumps({
            "schema_version": 1,
            "items": [{
                "id": "position-rmb",
                "name": "旧金条",
                "mode": "rmb",
                "entry_price": 680.0,
                "quantity": 2.0,
                "entry_date": "2026-06-01",
                "note": "迁移",
                "created_at": "2026-06-01T09:00:00",
                "updated_at": "2026-06-01T09:00:00",
            }],
        }, ensure_ascii=False), encoding="utf-8")
        transaction_path.write_text(json.dumps({"schema_version": 1, "items": []}), encoding="utf-8")

        store = PortfolioTransactionStore(
            str(transaction_path),
            legacy_positions_path=str(legacy_path),
            now_factory=fixed_now,
        )
        loaded = store.load()

        assert transaction_path.exists()
        assert loaded[0]["id"] == "transaction-position-rmb"
        assert loaded[0]["position_id"] == "position-rmb"
        assert store.load() == loaded

        positions_csv, position_count = build_portfolio_positions_csv(loaded, {"rmb": 700.0, "usd": 2350.0})
        transactions_csv, transaction_count = build_portfolio_transactions_csv(loaded)

        assert position_count == 1
        assert transaction_count == 1
        position_header = next(csv.reader(StringIO(positions_csv)))
        assert "average_cost" in position_header
        assert "realized_pnl" in position_header
        transaction_header = next(csv.reader(StringIO(transactions_csv)))
        assert transaction_header == [
            "id",
            "position_id",
            "name",
            "type",
            "mode",
            "price",
            "quantity",
            "fee",
            "trade_date",
            "realized_pnl",
            "note",
            "created_at",
            "updated_at",
        ]
        assert "旧金条" in positions_csv
        assert "transaction-position-rmb" in transactions_csv


def test_app_portfolio_wrappers_upsert_delete_and_export(monkeypatch):
    import app

    saved_positions = []
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    def fake_save(items=None):
        saved_positions[:] = list(app.portfolio_positions if items is None else items)
        return list(saved_positions)

    monkeypatch.setattr(app, "save_portfolio_positions", fake_save)

    state = app.upsert_portfolio_position({
        "name": "金条",
        "mode": "rmb",
        "entry_price": "680",
        "quantity": "2",
    })
    assert state["total"] == 1
    assert state["items"][0]["valuation_status"] == "valued"
    assert state["items"][0]["pnl"] == 40.0

    csv_text, count = app.build_portfolio_csv()
    assert count == 1
    assert "金条" in csv_text

    ok, deleted_state = app.delete_portfolio_position(state["items"][0]["id"])
    assert ok is True
    assert deleted_state["total"] == 0


def test_app_portfolio_transaction_wrappers_save_delete_and_validate(monkeypatch):
    import app

    saved_transactions = []
    monkeypatch.setattr(app, "portfolio_transactions", [])
    monkeypatch.setattr(app, "price_rmb", 740.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    def fake_save(items=None):
        saved_transactions[:] = list(app.portfolio_transactions if items is None else items)
        return list(saved_transactions)

    monkeypatch.setattr(app, "save_portfolio_transactions", fake_save)

    buy_state = app.upsert_portfolio_transaction({
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": "680",
        "quantity": "10",
        "fee": "0",
        "trade_date": "2026-06-01",
    })
    position_id = buy_state["items"][0]["id"]
    sell_state = app.upsert_portfolio_transaction({
        "position_id": position_id,
        "name": "金条",
        "type": "sell",
        "mode": "rmb",
        "price": "730",
        "quantity": "2",
        "fee": "4",
        "trade_date": "2026-06-20",
    })

    assert sell_state["items"][0]["quantity"] == 8.0
    assert sell_state["items"][0]["realized_pnl"] == 96.0
    assert len(sell_state["transactions"]) == 2

    with pytest.raises(ValueError, match="卖出数量不能超过当前持仓"):
        app.upsert_portfolio_transaction({
            "position_id": position_id,
            "name": "金条",
            "type": "sell",
            "mode": "rmb",
            "price": "720",
            "quantity": "20",
        })
    assert len(app.portfolio_transactions) == 2

    ok, deleted_state = app.delete_portfolio_transaction(sell_state["transactions"][1]["id"])
    assert ok is True
    assert deleted_state["items"][0]["quantity"] == 10.0


def test_app_portfolio_upsert_does_not_mutate_memory_when_save_fails(monkeypatch):
    import app

    existing = [{
        "id": "position-existing",
        "name": "原持仓",
        "mode": "rmb",
        "entry_price": 680.0,
        "quantity": 1.0,
        "entry_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }]
    monkeypatch.setattr(app, "portfolio_positions", [dict(item) for item in existing])
    monkeypatch.setattr(app, "save_portfolio_positions", lambda items=None: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        app.upsert_portfolio_position({
            "name": "新持仓",
            "mode": "rmb",
            "entry_price": "700",
            "quantity": "2",
        })

    assert app.portfolio_positions == existing


def test_app_portfolio_transaction_upsert_does_not_mutate_memory_when_save_fails(monkeypatch):
    import app

    existing = [{
        "id": "transaction-existing",
        "position_id": "position-existing",
        "name": "原流水",
        "type": "buy",
        "mode": "rmb",
        "price": 680.0,
        "quantity": 1.0,
        "fee": 0.0,
        "trade_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }]
    monkeypatch.setattr(app, "portfolio_transactions", [dict(item) for item in existing])
    monkeypatch.setattr(app, "save_portfolio_transactions", lambda items=None: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        app.upsert_portfolio_transaction({
            "position_id": "position-existing",
            "name": "新增流水",
            "type": "buy",
            "mode": "rmb",
            "price": "700",
            "quantity": "2",
        })

    assert app.portfolio_transactions == existing


def test_app_portfolio_delete_does_not_mutate_memory_when_save_fails(monkeypatch):
    import app

    existing = [{
        "id": "position-existing",
        "name": "原持仓",
        "mode": "rmb",
        "entry_price": 680.0,
        "quantity": 1.0,
        "entry_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }]
    monkeypatch.setattr(app, "portfolio_positions", [dict(item) for item in existing])
    monkeypatch.setattr(app, "save_portfolio_positions", lambda items=None: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        app.delete_portfolio_position("position-existing")

    assert app.portfolio_positions == existing


def test_app_portfolio_transaction_delete_does_not_mutate_memory_when_save_fails(monkeypatch):
    import app

    existing = [{
        "id": "transaction-existing",
        "position_id": "position-existing",
        "name": "原流水",
        "type": "buy",
        "mode": "rmb",
        "price": 680.0,
        "quantity": 1.0,
        "fee": 0.0,
        "trade_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }]
    monkeypatch.setattr(app, "portfolio_transactions", [dict(item) for item in existing])
    monkeypatch.setattr(app, "save_portfolio_transactions", lambda items=None: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(OSError):
        app.delete_portfolio_transaction("transaction-existing")

    assert app.portfolio_transactions == existing


def test_export_portfolio_socket_event_emits_saved_file_details(monkeypatch):
    import app

    saved = {}
    monkeypatch.setattr(app, "portfolio_positions", [{
        "id": "position-rmb",
        "name": "金条",
        "mode": "rmb",
        "entry_price": 680.0,
        "quantity": 2.0,
        "entry_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    def fake_save_export_file(filename, content):
        saved["filename"] = filename
        saved["content"] = content
        return f"/tmp/{filename}"

    monkeypatch.setattr(app, "save_export_file", fake_save_export_file)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("export_portfolio")
    events = client.get_received()

    exported = next(event for event in events if event["name"] == "portfolio_exported")
    payload = exported["args"][0]
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["filename"].startswith("GoldMonitor-portfolio-")
    assert payload["filename"].endswith(".csv")
    assert payload["saved_path"] == f"/tmp/{payload['filename']}"
    assert saved["filename"] == payload["filename"]
    assert "金条" in saved["content"]
    client.disconnect()


def test_export_portfolio_transactions_socket_event_emits_saved_file_details(monkeypatch):
    import app

    saved = {}
    monkeypatch.setattr(app, "portfolio_transactions", [{
        "id": "transaction-rmb",
        "position_id": "position-rmb",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 680.0,
        "quantity": 2.0,
        "fee": 0.0,
        "trade_date": "2026-06-01",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    def fake_save_export_file(filename, content):
        saved["filename"] = filename
        saved["content"] = content
        return f"/tmp/{filename}"

    monkeypatch.setattr(app, "save_export_file", fake_save_export_file)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("export_portfolio", {"kind": "transactions"})
    events = client.get_received()

    exported = next(event for event in events if event["name"] == "portfolio_exported")
    payload = exported["args"][0]
    assert payload["ok"] is True
    assert payload["kind"] == "transactions"
    assert payload["count"] == 1
    assert payload["filename"].startswith("GoldMonitor-portfolio-transactions-")
    assert payload["filename"].endswith(".csv")
    assert payload["saved_path"] == f"/tmp/{payload['filename']}"
    assert "transaction-rmb" in saved["content"]
    client.disconnect()


def test_export_portfolio_review_socket_event_emits_markdown_details(monkeypatch):
    import app

    saved = {}
    monkeypatch.setattr(app, "portfolio_transactions", [{
        "id": "transaction-rmb",
        "position_id": "position-rmb",
        "name": "金条",
        "type": "buy",
        "mode": "rmb",
        "price": 680.0,
        "quantity": 2.0,
        "fee": 0.0,
        "trade_date": "2026-06-01",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    def fake_save_export_file(filename, content):
        saved["filename"] = filename
        saved["content"] = content
        return f"/tmp/{filename}"

    monkeypatch.setattr(app, "save_export_file", fake_save_export_file)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("export_portfolio", {"kind": "review"})
    events = client.get_received()

    exported = next(event for event in events if event["name"] == "portfolio_exported")
    payload = exported["args"][0]
    assert payload["ok"] is True
    assert payload["kind"] == "review"
    assert payload["count"] == 1
    assert payload["filename"].startswith("GoldMonitor-portfolio-review-")
    assert payload["filename"].endswith(".md")
    assert payload["saved_path"] == f"/tmp/{payload['filename']}"
    assert "# 持仓复盘" in saved["content"]
    assert "金条" in saved["content"]
    client.disconnect()


def test_delete_missing_portfolio_socket_event_emits_error_and_current_state(monkeypatch):
    import app

    monkeypatch.setattr(app, "portfolio_positions", [{
        "id": "position-rmb",
        "name": "金条",
        "mode": "rmb",
        "entry_price": 680.0,
        "quantity": 2.0,
        "entry_date": "",
        "note": "",
        "created_at": "2026-06-25T10:00:00",
        "updated_at": "2026-06-25T10:00:00",
    }])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)

    client = app.socketio.test_client(app.app, auth={"token": app.SOCKET_ACCESS_TOKEN})
    client.get_received()
    client.emit("delete_portfolio_position", {"id": "missing"})
    events = client.get_received()

    event_names = [event["name"] for event in events]
    assert "portfolio_error" in event_names
    assert "portfolio_updated" in event_names
    error_payload = next(event["args"][0] for event in events if event["name"] == "portfolio_error")
    updated_payload = next(event["args"][0] for event in events if event["name"] == "portfolio_updated")
    assert error_payload == {"message": "未找到持仓记录"}
    assert updated_payload["total"] == 1
    assert updated_payload["items"][0]["id"] == "position-rmb"
    client.disconnect()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
