# 持仓 / 成本价 / 盈亏看板 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加本地持仓看板，让用户维护人民币克价和国际金价持仓，并按当前行情查看成本、市值、浮动盈亏和 CSV 导出。

**Architecture:** 新增 `goldmonitor/portfolio.py` 承担持仓规范化、估值、汇总、JSON 存储和 CSV 导出；`app.py` 只负责读取当前行情、维护内存状态和 Socket.IO 事件编排。前端在现有右侧卡片区增加紧凑持仓面板，复用现有按钮、表单、状态提示和 Socket 状态更新模式。

**Tech Stack:** Python 3.12、Flask-SocketIO、版本化 JSON 契约、标准库 `csv`、原生 HTML/CSS/JavaScript、现有静态资源检查和发布工作流。

---

## 文件职责

- Create: `goldmonitor/portfolio.py`
  - 纯业务模块，提供 `normalize_portfolio_position`、`normalize_portfolio_positions`、`value_portfolio_position`、`build_portfolio_state`、`PortfolioPositionStore`、`build_portfolio_csv`。
- Create: `tests/test_portfolio_module.py`
  - 覆盖规范化、估值、分币种汇总、JSON 持久化、CSV 导出和异常输入。
- Modify: `app.py`
  - 引入 `portfolio_core`，增加 `PORTFOLIO_POSITIONS_PATH`、`portfolio_positions`、持仓读写编排函数、`init_state` 字段和 Socket.IO 事件。
- Modify: `templates/index.html`
  - 在右侧面板新增 `portfolioStatus`、`portfolioSummary`、`portfolioList` 挂载点，以及新增和导出按钮。
- Modify: `static/app.css`
  - 增加 `.portfolio-*` 样式，保持 8px 圆角、紧凑密度、移动端一列布局。
- Modify: `static/app.js`
  - 增加持仓前端状态、Socket 监听、渲染、表单采集、保存、删除和导出函数。
- Modify: `tests/frontend_asset_check.py`
  - 检查新增 DOM 挂载点、JS 函数和 Socket 事件名存在。
- Modify: `README.md`
  - 增加功能说明、本地数据文件和本地检查命令中的新增测试。
- Modify: `.github/workflows/release.yml`
  - 将 `tests/test_portfolio_module.py` 加入 Windows 和 macOS 发布检查。
- Modify: `CHANGELOG.md`
  - 在当前版本下增加持仓看板发布说明。

## Task 1: 持仓模块测试

**Files:**
- Create: `tests/test_portfolio_module.py`
- Create: `goldmonitor/portfolio.py`

- [ ] **Step 1: 写失败测试**

Create `tests/test_portfolio_module.py` with:

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m pytest tests/test_portfolio_module.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'goldmonitor.portfolio'`.

- [ ] **Step 3: 新增最小业务模块**

Create `goldmonitor/portfolio.py` with:

```python
import csv
import io
import json
import math
import os
import secrets
from datetime import datetime

from goldmonitor.data_contracts import unwrap_item_payload, wrap_item_payload


PORTFOLIO_MODES = ("rmb", "usd")
PORTFOLIO_NAME_LIMIT = 60
PORTFOLIO_NOTE_LIMIT = 200
CSV_FIELDS = [
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


def generate_portfolio_position_id():
    return "position-" + secrets.token_hex(8)


def _now_iso(now_factory):
    return now_factory().isoformat(timespec="seconds")


def _safe_id(value, id_factory):
    text = str(value or "").strip()
    allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    if text and all(ch in allowed for ch in text):
        return text
    return id_factory()


def _limited_text(value, limit):
    return str(value or "").strip()[:limit]


def _coerce_positive_number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


def _normalize_entry_date(value):
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def _round_number(value):
    if value is None:
        return None
    return round(float(value), 4)


def normalize_portfolio_position(item, existing=None, now_factory=None, id_factory=None):
    if not isinstance(item, dict):
        raise ValueError("持仓格式无效")
    existing = existing if isinstance(existing, dict) else {}
    now_factory = now_factory or datetime.now
    id_factory = id_factory or generate_portfolio_position_id
    now = _now_iso(now_factory)

    name = _limited_text(item.get("name", existing.get("name", "")), PORTFOLIO_NAME_LIMIT)
    if not name:
        raise ValueError("请输入持仓名称")

    mode = str(item.get("mode", existing.get("mode", "rmb")) or "").strip().lower()
    if mode not in PORTFOLIO_MODES:
        raise ValueError("持仓单位无效")

    return {
        "id": _safe_id(item.get("id") or existing.get("id"), id_factory),
        "name": name,
        "mode": mode,
        "entry_price": _coerce_positive_number(item.get("entry_price", existing.get("entry_price"))),
        "quantity": _coerce_positive_number(item.get("quantity", existing.get("quantity"))),
        "entry_date": _normalize_entry_date(item.get("entry_date", existing.get("entry_date", ""))),
        "note": _limited_text(item.get("note", existing.get("note", "")), PORTFOLIO_NOTE_LIMIT),
        "created_at": str(existing.get("created_at") or item.get("created_at") or now),
        "updated_at": now,
    }


def normalize_portfolio_positions(items, now_factory=None, id_factory=None):
    normalized = []
    seen = set()
    for item in list(items or []):
        try:
            position = normalize_portfolio_position(item, now_factory=now_factory, id_factory=id_factory)
        except ValueError:
            continue
        if position["id"] in seen:
            continue
        seen.add(position["id"])
        normalized.append(position)
    return normalized


def find_portfolio_position_index(items, position_id):
    target = str(position_id or "").strip()
    for index, item in enumerate(items or []):
        if str(item.get("id") or "") == target:
            return index
    return -1


def empty_portfolio_summary():
    return {"count": 0, "valued": 0, "cost": 0.0, "market_value": 0.0, "pnl": 0.0, "pnl_percent": 0.0}


def value_portfolio_position(position, prices):
    item = dict(position or {})
    mode = item.get("mode")
    entry_price = item.get("entry_price")
    quantity = item.get("quantity")
    cost = entry_price * quantity if entry_price and quantity else None
    current_price = (prices or {}).get(mode)

    item.update({
        "current_price": current_price,
        "cost": _round_number(cost),
        "market_value": None,
        "pnl": None,
        "pnl_percent": None,
        "valuation_status": "invalid_position",
    })

    if not cost or cost <= 0 or not quantity or quantity <= 0:
        return item
    if current_price is None:
        item["valuation_status"] = "waiting_price"
        return item

    market_value = current_price * quantity
    pnl = market_value - cost
    item.update({
        "current_price": _round_number(current_price),
        "market_value": _round_number(market_value),
        "pnl": _round_number(pnl),
        "pnl_percent": _round_number(pnl / cost * 100),
        "valuation_status": "valued",
    })
    return item


def _add_to_summary(summary, item):
    summary["count"] += 1
    if item.get("valuation_status") != "valued":
        return
    summary["valued"] += 1
    summary["cost"] += item["cost"]
    summary["market_value"] += item["market_value"]
    summary["pnl"] += item["pnl"]


def _finalize_summary(summary):
    cost = summary["cost"]
    summary["cost"] = _round_number(summary["cost"]) or 0.0
    summary["market_value"] = _round_number(summary["market_value"]) or 0.0
    summary["pnl"] = _round_number(summary["pnl"]) or 0.0
    summary["pnl_percent"] = _round_number(summary["pnl"] / cost * 100) if cost else 0.0
    return summary


def build_portfolio_state(items, prices):
    valued_items = [value_portfolio_position(item, prices) for item in list(items or [])]
    rmb_summary = empty_portfolio_summary()
    usd_summary = empty_portfolio_summary()
    for item in valued_items:
        if item.get("mode") == "usd":
            _add_to_summary(usd_summary, item)
        else:
            _add_to_summary(rmb_summary, item)
    return {
        "items": valued_items,
        "total": len(valued_items),
        "rmb_summary": _finalize_summary(rmb_summary),
        "usd_summary": _finalize_summary(usd_summary),
        "prices": {
            "rmb": prices.get("rmb") if isinstance(prices, dict) else None,
            "usd": prices.get("usd") if isinstance(prices, dict) else None,
        },
    }


class PortfolioPositionStore:
    def __init__(self, json_path, now_factory=None, id_factory=None):
        self.json_path = json_path
        self.now_factory = now_factory or datetime.now
        self.id_factory = id_factory or generate_portfolio_position_id

    def normalize(self, items):
        return normalize_portfolio_positions(items, now_factory=self.now_factory, id_factory=self.id_factory)

    def load(self):
        if not os.path.exists(self.json_path):
            return []
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return self.normalize(unwrap_item_payload(payload))
        except (OSError, json.JSONDecodeError):
            return []

    def save(self, items):
        normalized = self.normalize(items)
        os.makedirs(os.path.dirname(self.json_path) or ".", exist_ok=True)
        tmp_path = self.json_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(wrap_item_payload(normalized), f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.json_path)
        return normalized


def build_portfolio_csv(items, prices):
    state = build_portfolio_state(items, prices)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for item in state["items"]:
        writer.writerow({field: item.get(field, "") for field in CSV_FIELDS})
    return output.getvalue(), len(state["items"])
```

- [ ] **Step 4: 运行模块测试确认通过**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m pytest tests/test_portfolio_module.py -v
```

Expected: PASS for 3 tests.

- [ ] **Step 5: 提交后端纯模块**

Run:

```bash
git add goldmonitor/portfolio.py tests/test_portfolio_module.py
git commit -m "feat: 增加持仓估值模块"
```

Expected: commit succeeds and does not include attribution footers.

## Task 2: 接入 app.py 状态和 Socket 事件

**Files:**
- Modify: `app.py`

- [ ] **Step 1: 写 app 编排测试**

Append this test to `tests/test_portfolio_module.py`:

```python
def test_app_portfolio_wrappers_upsert_delete_and_export(monkeypatch):
    import app

    saved_positions = []
    monkeypatch.setattr(app, "portfolio_positions", [])
    monkeypatch.setattr(app, "price_rmb", 700.0)
    monkeypatch.setattr(app, "price_usd", 2350.0)
    monkeypatch.setattr(app, "save_portfolio_positions", lambda items=None: list(items or saved_positions))

    def fake_save(items=None):
        saved_positions[:] = list(items or app.portfolio_positions)
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
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m pytest tests/test_portfolio_module.py::test_app_portfolio_wrappers_upsert_delete_and_export -v
```

Expected: FAIL with `AttributeError` for missing `upsert_portfolio_position`.

- [ ] **Step 3: 修改 app.py 引入模块、常量和全局状态**

Apply these edits in `app.py`:

```python
from goldmonitor import portfolio as portfolio_core
```

Add near existing app data paths:

```python
PORTFOLIO_POSITIONS_PATH = os.path.join(APPDATA_DIR, "portfolio_positions.json")
```

Add near `watch_targets = []`:

```python
portfolio_positions = []
```

- [ ] **Step 4: 增加 app.py 持仓编排函数**

Insert after the watch target helper block:

```python
def _portfolio_store():
    return portfolio_core.PortfolioPositionStore(
        PORTFOLIO_POSITIONS_PATH,
        now_factory=datetime.now,
        id_factory=portfolio_core.generate_portfolio_position_id,
    )


def load_portfolio_positions():
    return _portfolio_store().load()


def save_portfolio_positions(items=None):
    items = portfolio_positions if items is None else items
    return _portfolio_store().save(items)


def _current_portfolio_prices():
    return {"rmb": price_rmb, "usd": price_usd}


def build_portfolio_state():
    with lock:
        items = [dict(item) for item in portfolio_positions]
        prices = _current_portfolio_prices()
    return portfolio_core.build_portfolio_state(items, prices)


def _find_portfolio_position_index(position_id):
    return portfolio_core.find_portfolio_position_index(portfolio_positions, position_id)


def upsert_portfolio_position(data):
    global portfolio_positions
    position_id = str((data or {}).get("id") or "").strip() if isinstance(data, dict) else ""
    with lock:
        index = _find_portfolio_position_index(position_id)
        existing = portfolio_positions[index] if index >= 0 else None
        position = portfolio_core.normalize_portfolio_position(data, existing=existing, now_factory=datetime.now)
        if index >= 0:
            portfolio_positions[index] = position
        else:
            portfolio_positions.append(position)
        portfolio_positions = save_portfolio_positions(portfolio_positions)
    return build_portfolio_state()


def delete_portfolio_position(position_id):
    global portfolio_positions
    with lock:
        index = _find_portfolio_position_index(position_id)
        if index < 0:
            return False, build_portfolio_state()
        portfolio_positions.pop(index)
        portfolio_positions = save_portfolio_positions(portfolio_positions)
    return True, build_portfolio_state()


def build_portfolio_csv():
    with lock:
        items = [dict(item) for item in portfolio_positions]
        prices = _current_portfolio_prices()
    return portfolio_core.build_portfolio_csv(items, prices)
```

- [ ] **Step 5: 启动加载持仓并加入 init_state**

After `watch_targets = load_watch_targets()` add:

```python
portfolio_positions = load_portfolio_positions()
```

Inside the `on_connect` state dict add:

```python
"portfolio": build_portfolio_state(),
```

- [ ] **Step 6: 增加 Socket.IO 事件**

Insert near watch target events:

```python
@socketio.on("get_portfolio")
def on_get_portfolio():
    emit("portfolio_updated", build_portfolio_state())


@socketio.on("save_portfolio_position")
def on_save_portfolio_position(data):
    try:
        state = upsert_portfolio_position(data)
    except ValueError as exc:
        emit("portfolio_error", {"message": str(exc)})
        return
    except OSError:
        emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("delete_portfolio_position")
def on_delete_portfolio_position(data=None):
    position_id = data.get("id") if isinstance(data, dict) else None
    try:
        ok, state = delete_portfolio_position(position_id)
    except OSError:
        emit("portfolio_error", {"message": "持仓保存失败，请检查配置目录权限。"})
        return
    if not ok:
        emit("portfolio_error", {"message": "未找到持仓记录"})
        emit("portfolio_updated", state)
        return
    socketio.emit("portfolio_updated", state)


@socketio.on("export_portfolio")
def on_export_portfolio():
    filename = f"GoldMonitor-portfolio-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    try:
        content, count = build_portfolio_csv()
        saved_path = save_export_file(filename, content)
        emit("portfolio_exported", {
            "ok": True,
            "filename": filename,
            "saved_path": saved_path,
            "count": count,
        })
    except OSError as exc:
        emit("portfolio_export_error", {"message": f"持仓导出失败: {exc}"})
```

- [ ] **Step 7: 运行 app 编排测试**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m pytest tests/test_portfolio_module.py -v
```

Expected: PASS for 4 tests.

- [ ] **Step 8: 提交 app 接入**

Run:

```bash
git add app.py tests/test_portfolio_module.py
git commit -m "feat: 接入持仓 Socket 事件"
```

Expected: commit succeeds.

## Task 3: 前端挂载点、样式和静态检查

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.css`
- Modify: `tests/frontend_asset_check.py`

- [ ] **Step 1: 更新前端静态检查**

Modify `tests/frontend_asset_check.py` by adding these checks:

```python
for required in ('id="portfolioStatus"', 'id="portfolioSummary"', 'id="portfolioList"', 'onclick="setActivePortfolioPosition(\'new\')"', 'onclick="exportPortfolio()"'):
    if required not in template:
        raise SystemExit(f"template missing portfolio anchor: {required}")

for required in (".portfolio-card", ".portfolio-summary", ".portfolio-item", ".portfolio-editor"):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio selector: {required}")

for required in (
    "function applyPortfolio",
    "function renderPortfolio",
    "function savePortfolioPosition",
    "function deletePortfolioPosition",
    "function exportPortfolio",
    "save_portfolio_position",
    "delete_portfolio_position",
    "export_portfolio",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio frontend contract: {required}")
```

- [ ] **Step 2: 运行静态检查确认失败**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python tests/frontend_asset_check.py
```

Expected: FAIL with `template missing portfolio anchor`.

- [ ] **Step 3: 新增 HTML 挂载点**

In `templates/index.html`, insert this card after the threshold card and before the data status card:

```html
        <div class="card-outer portfolio-card">
          <div class="card-inner">
            <div class="portfolio-head">
              <h3>持仓</h3>
              <div class="portfolio-tools">
                <button class="btn-clear-sm" type="button" onclick="setActivePortfolioPosition('new')">新增</button>
                <button class="btn-clear-sm" type="button" onclick="exportPortfolio()">导出</button>
              </div>
            </div>
            <div class="portfolio-status" id="portfolioStatus"></div>
            <div class="portfolio-summary" id="portfolioSummary"></div>
            <div class="portfolio-list" id="portfolioList"></div>
          </div>
        </div>
```

- [ ] **Step 4: 新增 CSS 样式**

Append near watch target styles in `static/app.css`:

```css
  .portfolio-head { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
  .portfolio-tools { display:flex; align-items:center; justify-content:flex-end; gap:6px; flex-wrap:wrap; }
  .portfolio-status { min-height:16px; color:var(--text-dim); font-size:0.68rem; line-height:1.4; margin-bottom:6px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .portfolio-status.ok { color:var(--down); }
  .portfolio-status.fail { color:var(--up); }
  .portfolio-summary { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:6px; margin-bottom:8px; }
  .portfolio-summary-card { padding:8px; border:1px solid rgba(255,255,255,0.055); border-radius:8px; background:rgba(255,255,255,0.022); }
  .portfolio-summary-title { color:var(--text-dim); font-size:0.66rem; font-weight:800; margin-bottom:5px; }
  .portfolio-summary-value { color:#f0f0f4; font-size:0.86rem; font-weight:800; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .portfolio-summary-meta { margin-top:3px; color:var(--text-dim); font-size:0.64rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .portfolio-summary-value.up, .portfolio-pnl.up { color:var(--up); }
  .portfolio-summary-value.down, .portfolio-pnl.down { color:var(--down); }
  .portfolio-list { display:grid; gap:6px; }
  .portfolio-empty { color:var(--text-dim); font-size:0.76rem; text-align:center; padding:16px 8px; border:1px dashed rgba(255,255,255,0.08); border-radius:8px; background:rgba(255,255,255,0.018); }
  .portfolio-item { display:grid; grid-template-columns:minmax(0, 1fr) auto; gap:8px; align-items:center; padding:9px; border:1px solid rgba(255,255,255,0.055); border-radius:8px; background:rgba(255,255,255,0.022); }
  .portfolio-item.expanded { border-color:rgba(232,184,48,0.24); background:rgba(232,184,48,0.045); }
  .portfolio-main { min-width:0; }
  .portfolio-line { color:#f0f0f4; font-size:0.76rem; font-weight:800; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .portfolio-meta { margin-top:3px; color:var(--text-dim); font-size:0.68rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .portfolio-actions { display:flex; gap:5px; align-items:center; justify-content:flex-end; flex-wrap:wrap; }
  .portfolio-editor { grid-column:1 / -1; display:grid; gap:8px; padding-top:8px; border-top:1px solid var(--hairline); }
  .portfolio-fields { display:grid; grid-template-columns:1fr 0.78fr 1fr 1fr; gap:8px; }
  .portfolio-field { min-width:0; }
  .portfolio-field label { display:block; color:var(--text-dim); font-size:0.68rem; margin-bottom:4px; }
  .portfolio-field input, .portfolio-field select { width:100%; min-height:34px; padding:7px 9px; border-radius:8px; border:1px solid var(--control-border); background:rgba(255,255,255,0.035); color:var(--text); font-size:0.8rem; outline:none; font-variant-numeric:tabular-nums; }
  .portfolio-field input:focus, .portfolio-field select:focus { border-color:var(--control-border-strong); background:#121225; box-shadow:var(--focus-ring); }
  .portfolio-note { grid-column:1 / -1; }
  .portfolio-editor-actions { display:flex; justify-content:flex-end; gap:6px; flex-wrap:wrap; }
  .portfolio-editor-actions button { min-height:32px; padding:6px 10px; font-size:0.7rem; }
```

Inside the mobile media query add:

```css
    .portfolio-summary { grid-template-columns:1fr; }
    .portfolio-item { grid-template-columns:1fr; }
    .portfolio-actions { justify-content:flex-start; }
    .portfolio-fields { grid-template-columns:1fr; }
```

- [ ] **Step 5: 运行静态检查确认只剩 JS 合同失败**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python tests/frontend_asset_check.py
```

Expected: FAIL with `static/app.js missing portfolio frontend contract`.

- [ ] **Step 6: 提交前端挂载点和检查**

Run:

```bash
git add templates/index.html static/app.css tests/frontend_asset_check.py
git commit -m "feat: 增加持仓看板结构"
```

Expected: commit succeeds.

## Task 4: 前端持仓状态、渲染和交互

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 新增前端全局状态**

Near `let watchTargets = [];` add:

```javascript
let portfolioState = { items: [], total: 0, rmb_summary: {}, usd_summary: {}, prices: {} };
let activePortfolioPositionId = null;
```

- [ ] **Step 2: 监听后端持仓事件**

Inside the existing `socket.on('init_state', data => {` listener, after the line `applyWatchTargets(data.watch_targets || []);` add:

```javascript
  applyPortfolio(data.portfolio || {});
```

Inside the existing `socket.on('price_update', data => {` listener, after the line `updateDailyStats(data);` add:

```javascript
  requestPortfolioRefresh();
```

Near watch target socket listeners add:

```javascript
socket.on('portfolio_updated', data => {
  applyPortfolio(data || {});
  setPortfolioStatus('持仓已更新。', 'ok');
});

socket.on('portfolio_error', data => {
  setPortfolioStatus((data && data.message) || '持仓更新失败。', 'fail');
});

socket.on('portfolio_exported', data => {
  const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
  setPortfolioStatus(data && data.saved_path ? '已导出 ' + count + ' 条，保存至 ' + data.saved_path : '持仓已导出。', 'ok');
});

socket.on('portfolio_export_error', data => {
  setPortfolioStatus((data && data.message) || '持仓导出失败。', 'fail');
});
```

- [ ] **Step 3: 新增格式化和状态函数**

Insert before watch target helpers:

```javascript
function normalizePortfolioState(data) {
  const state = data && typeof data === 'object' ? data : {};
  return {
    items: Array.isArray(state.items) ? state.items : [],
    total: Number.isFinite(Number(state.total)) ? Number(state.total) : 0,
    rmb_summary: state.rmb_summary || {},
    usd_summary: state.usd_summary || {},
    prices: state.prices || {},
  };
}

function applyPortfolio(data) {
  portfolioState = normalizePortfolioState(data);
  renderPortfolio();
}

function setPortfolioStatus(message, type) {
  const status = document.getElementById('portfolioStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'portfolio-status' + (type ? ' ' + type : '');
}

function portfolioModeLabel(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function portfolioCurrency(mode) {
  return mode === 'usd' ? '$' : '¥';
}

function portfolioQuantityUnit(mode) {
  return mode === 'usd' ? 'oz' : '克';
}

function formatPortfolioNumber(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return number.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function formatPortfolioMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return portfolioCurrency(mode) + formatPortfolioNumber(number, 2);
}

function formatPortfolioPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return (number >= 0 ? '+' : '') + number.toFixed(2) + '%';
}

function portfolioPnlClass(value) {
  const number = Number(value);
  if (number > 0) return 'up';
  if (number < 0) return 'down';
  return '';
}

function portfolioValuationLabel(item) {
  if (item.valuation_status === 'valued') return formatPortfolioMoney(item.market_value, item.mode);
  if (item.valuation_status === 'waiting_price') return '等待行情';
  return '持仓数据需修正';
}

function requestPortfolioRefresh() {
  if (!socket.connected) return;
  socket.emit('get_portfolio');
}
```

- [ ] **Step 4: 新增汇总和列表渲染**

Add these functions:

```javascript
function renderPortfolioSummaryCard(title, mode, summary) {
  const item = summary || {};
  const pnlClass = portfolioPnlClass(item.pnl);
  return [
    '<div class="portfolio-summary-card">',
    '<div class="portfolio-summary-title">' + escapeHtml(title) + '</div>',
    '<div class="portfolio-summary-value ' + pnlClass + '">' + escapeHtml(formatPortfolioMoney(item.pnl, mode)) + '</div>',
    '<div class="portfolio-summary-meta">市值 ' + escapeHtml(formatPortfolioMoney(item.market_value, mode)) + ' · 成本 ' + escapeHtml(formatPortfolioMoney(item.cost, mode)) + '</div>',
    '<div class="portfolio-summary-meta">' + escapeHtml(String(item.valued || 0)) + '/' + escapeHtml(String(item.count || 0)) + ' 已估值 · ' + escapeHtml(formatPortfolioPercent(item.pnl_percent)) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioSummary() {
  const box = document.getElementById('portfolioSummary');
  if (!box) return;
  box.innerHTML = [
    renderPortfolioSummaryCard('人民币持仓', 'rmb', portfolioState.rmb_summary),
    renderPortfolioSummaryCard('美元持仓', 'usd', portfolioState.usd_summary),
  ].join('');
}

function buildPortfolioEditor(item) {
  const isNew = !item || item.id === 'new';
  const position = item || { id: 'new', name: '', mode: currentMode, entry_price: '', quantity: '', entry_date: '', note: '' };
  const id = isNew ? 'new' : position.id;
  const mode = position.mode || currentMode;
  const name = position.name || '';
  const entryPrice = position.entry_price == null ? '' : String(position.entry_price);
  const quantity = position.quantity == null ? '' : String(position.quantity);
  const entryDate = position.entry_date || '';
  const note = position.note || '';
  return [
    '<div class="portfolio-editor">',
    '<div class="portfolio-fields">',
    '<div class="portfolio-field">',
    '<label for="portfolioName_' + escapeHtml(id) + '">名称</label>',
    '<input id="portfolioName_' + escapeHtml(id) + '" type="text" maxlength="60" value="' + escapeHtml(name) + '" placeholder="例如 实物金条">',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioMode_' + escapeHtml(id) + '">单位</label>',
    '<select id="portfolioMode_' + escapeHtml(id) + '">',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryPrice_' + escapeHtml(id) + '">买入价</label>',
    '<input id="portfolioEntryPrice_' + escapeHtml(id) + '" type="number" step="0.01" value="' + escapeHtml(entryPrice) + '" placeholder="输入买入价">',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioQuantity_' + escapeHtml(id) + '">数量</label>',
    '<input id="portfolioQuantity_' + escapeHtml(id) + '" type="number" step="0.0001" value="' + escapeHtml(quantity) + '" placeholder="输入数量">',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryDate_' + escapeHtml(id) + '">买入日期</label>',
    '<input id="portfolioEntryDate_' + escapeHtml(id) + '" type="date" value="' + escapeHtml(entryDate) + '">',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioNote_' + escapeHtml(id) + '">备注</label>',
    '<input id="portfolioNote_' + escapeHtml(id) + '" type="text" maxlength="200" value="' + escapeHtml(note) + '" placeholder="例如 账户或来源">',
    '</div>',
    '</div>',
    '<div class="portfolio-editor-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioPosition(\'' + escapeHtml(id) + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActivePortfolioPosition(\'' + escapeHtml(id) + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolio() {
  renderPortfolioSummary();
  const box = document.getElementById('portfolioList');
  if (!box) return;
  const items = [...portfolioState.items];
  const parts = [];
  if (activePortfolioPositionId === 'new') {
    parts.push([
      '<div class="portfolio-item expanded">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">新增持仓</div>',
      '<div class="portfolio-meta">保存后按当前行情估值</div>',
      '</div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioEditor({ id: 'new', mode: currentMode, name: '', entry_price: '', quantity: '', entry_date: '', note: '' }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activePortfolioPositionId !== 'new') {
    parts.push('<div class="portfolio-empty">暂无持仓</div>');
  }
  parts.push(...items.map(item => {
    const cls = ['portfolio-item', activePortfolioPositionId === item.id ? 'expanded' : ''].filter(Boolean).join(' ');
    const pnlClass = portfolioPnlClass(item.pnl);
    const quantity = formatPortfolioNumber(item.quantity, item.mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(item.mode);
    const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, item.mode);
    const dateText = item.entry_date ? ' · ' + item.entry_date : '';
    const noteText = item.note ? ' · ' + item.note : '';
    return [
      '<div class="' + cls + '">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">' + escapeHtml(item.name || '未命名持仓') + ' · ' + escapeHtml(portfolioValuationLabel(item)) + '</div>',
      '<div class="portfolio-meta">' + escapeHtml(portfolioModeLabel(item.mode) + ' · 数量 ' + quantity + ' · 当前价 ' + currentPrice + dateText + noteText) + '</div>',
      '<div class="portfolio-meta portfolio-pnl ' + pnlClass + '">浮动盈亏 ' + escapeHtml(formatPortfolioMoney(item.pnl, item.mode)) + ' · ' + escapeHtml(formatPortfolioPercent(item.pnl_percent)) + '</div>',
      '</div>',
      '<div class="portfolio-actions">',
      '<span class="alert-rule-state ' + (item.valuation_status === 'valued' ? 'on' : 'off') + '">' + escapeHtml(item.valuation_status === 'valued' ? '已估值' : '等待') + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActivePortfolioPosition(\'' + escapeHtml(item.id) + '\')">编辑</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="deletePortfolioPosition(\'' + escapeHtml(item.id) + '\')">删除</button>',
      '</div>',
      activePortfolioPositionId === item.id ? buildPortfolioEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}
```

- [ ] **Step 5: 新增表单采集、保存、删除和导出函数**

Add these functions:

```javascript
function setActivePortfolioPosition(id) {
  activePortfolioPositionId = activePortfolioPositionId === id ? null : id;
  renderPortfolio();
}

function portfolioInputValue(id, field) {
  const el = document.getElementById('portfolio' + field + '_' + id);
  return el ? el.value : '';
}

function savePortfolioPosition(id) {
  const isNew = id === 'new';
  const payload = {
    name: portfolioInputValue(id, 'Name'),
    mode: portfolioInputValue(id, 'Mode'),
    entry_price: portfolioInputValue(id, 'EntryPrice'),
    quantity: portfolioInputValue(id, 'Quantity'),
    entry_date: portfolioInputValue(id, 'EntryDate'),
    note: portfolioInputValue(id, 'Note'),
  };
  if (!isNew) payload.id = id;
  if (!payload.name.trim()) {
    setPortfolioStatus('请输入持仓名称。', 'fail');
    return;
  }
  const entryPrice = Number(payload.entry_price);
  const quantity = Number(payload.quantity);
  if (!Number.isFinite(entryPrice) || entryPrice <= 0 || !Number.isFinite(quantity) || quantity <= 0) {
    setPortfolioStatus('请输入有效的买入价和数量。', 'fail');
    return;
  }
  setPortfolioStatus('正在保存持仓...', '');
  socket.emit('save_portfolio_position', payload);
  activePortfolioPositionId = null;
}

function deletePortfolioPosition(id) {
  setPortfolioStatus('正在删除持仓...', '');
  socket.emit('delete_portfolio_position', { id });
  if (activePortfolioPositionId === id) activePortfolioPositionId = null;
}

function exportPortfolio() {
  setPortfolioStatus('正在导出持仓...', '');
  socket.emit('export_portfolio');
}
```

- [ ] **Step 6: 运行 JS 语法检查和静态检查**

Run:

```bash
/Users/dev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check static/app.js
/private/tmp/goldmonitor-venv/bin/python tests/frontend_asset_check.py
```

Expected: both commands pass.

- [ ] **Step 7: 提交前端交互**

Run:

```bash
git add static/app.js
git commit -m "feat: 增加持仓看板交互"
```

Expected: commit succeeds.

## Task 5: 文档、发布检查和变更记录

**Files:**
- Modify: `README.md`
- Modify: `.github/workflows/release.yml`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: 更新 README 功能和本地数据说明**

Add to main features:

```markdown
- 支持持仓看板，可维护人民币克价和国际金价持仓，展示成本、市值、浮动盈亏，并导出 CSV。
```

Add to local data list:

```markdown
- `portfolio_positions.json`：本地持仓记录。
```

- [ ] **Step 2: 更新 README 检查命令**

Add `tests\test_portfolio_module.py` to the Windows `py_compile` command and add this line to both Windows check blocks:

```powershell
.\.venv\Scripts\python.exe tests\test_portfolio_module.py
```

- [ ] **Step 3: 更新 Release workflow**

In both Windows and macOS `py_compile` commands, add:

```text
tests\test_portfolio_module.py
```

and

```text
tests/test_portfolio_module.py
```

In both Windows and macOS check command lists, add:

```text
python tests\test_portfolio_module.py
```

and

```text
python tests/test_portfolio_module.py
```

- [ ] **Step 4: 更新 CHANGELOG**

Under `## 1.4.3`, add:

```markdown
- 新增持仓看板，支持人民币克价和国际金价持仓的成本、市值、浮动盈亏计算与 CSV 导出。
```

- [ ] **Step 5: 运行文档相关检查**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m py_compile tests/frontend_asset_check.py tests/test_portfolio_module.py scripts/verify_release_assets.py
/private/tmp/goldmonitor-venv/bin/python tests/frontend_asset_check.py
```

Expected: both commands pass.

- [ ] **Step 6: 提交文档和发布检查**

Run:

```bash
git add README.md .github/workflows/release.yml CHANGELOG.md
git commit -m "docs: 补充持仓看板发布说明"
```

Expected: commit succeeds.

## Task 6: 全量验证和发布前检查

**Files:**
- Verify: `app.py`
- Verify: `goldmonitor/portfolio.py`
- Verify: `static/app.js`
- Verify: `static/app-shell.js`
- Verify: `tests/*.py`
- Verify: `scripts/verify_release_assets.py`

- [ ] **Step 1: Python 单元测试**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m pytest
```

Expected: all tests pass.

- [ ] **Step 2: Python 编译检查**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python -m py_compile app.py setup_gui.py goldmonitor/*.py tests/*.py scripts/verify_release_assets.py
```

Expected: exits 0.

- [ ] **Step 3: 前端语法检查**

Run:

```bash
/Users/dev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check static/app.js
/Users/dev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check static/app-shell.js
```

Expected: both commands exit 0.

- [ ] **Step 4: 脚本级回归检查**

Run:

```bash
/private/tmp/goldmonitor-venv/bin/python tests/frontend_asset_check.py
/private/tmp/goldmonitor-venv/bin/python tests/test_portfolio_module.py
/private/tmp/goldmonitor-venv/bin/python tests/test_targets_module.py
/private/tmp/goldmonitor-venv/bin/python tests/test_storage_modules.py
/private/tmp/goldmonitor-venv/bin/python tests/test_support_files_module.py
/private/tmp/goldmonitor-venv/bin/python -m pytest tests/test_verify_release_assets_script.py
```

Expected: all commands exit 0.

- [ ] **Step 5: 端口选择检查**

Run with approval because it binds local sockets:

```bash
/private/tmp/goldmonitor-venv/bin/python tests/port_selection_check.py
```

Expected: exits 0.

- [ ] **Step 6: 本地前端冒烟检查**

Start the app:

```bash
/private/tmp/goldmonitor-venv/bin/python app.py
```

Open `http://127.0.0.1:5000`, confirm the right panel shows `持仓`, then add one RMB holding and one USD holding. Expected: summaries update separately, CSV export writes a `GoldMonitor-portfolio-YYYYMMDD-HHMMSS.csv` file under the configured exports directory.

- [ ] **Step 7: 提交验证修正**

If verification required edits, run:

```bash
git add app.py goldmonitor/portfolio.py tests/test_portfolio_module.py templates/index.html static/app.css static/app.js tests/frontend_asset_check.py README.md .github/workflows/release.yml CHANGELOG.md
git commit -m "fix: 修正持仓看板验证问题"
```

Expected: no commit is created when verification produced no edits; any created commit uses Conventional Commits and contains no attribution footer.

## Self-Review

- Spec coverage: 设计中的本地多持仓维护、`rmb`/`usd` 两种模式、成本/市值/浮动盈亏/盈亏比例、分币种汇总、本地 JSON 持久化、CSV 导出、行情缺失状态、非法持仓状态均映射到 Task 1 至 Task 4。
- Non-goals: 计划未引入买卖流水、手续费、税费、汇率换算、收益曲线、云同步或持仓提醒；配置备份不合入持仓文件。
- Placeholder scan: 本计划没有使用占位词或空泛错误处理描述；每个新增函数和测试都有明确名称、输入和期望输出。
- Type consistency: 后端状态字段统一为 `items`、`total`、`rmb_summary`、`usd_summary`、`prices`；前端 Socket 事件统一为 `get_portfolio`、`save_portfolio_position`、`delete_portfolio_position`、`export_portfolio`。
- Test coverage: 纯模块测试覆盖核心计算与持久化，前端静态检查覆盖挂载点和事件合同，全量验证覆盖 Python、JS 和脚本级回归。
