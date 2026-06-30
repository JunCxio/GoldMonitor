# GoldMonitor Roadmap Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 GoldMonitor 五阶段演进目标：模块边界整理、本地数据能力完善、持仓预警复盘闭环、行情可信度增强、谨慎扩展产品边界。

**Architecture:** 先拆边界，不改变现有 Socket.IO 事件名、HTTP 路由、持久化路径和前端展示契约。后端逐步把纯业务逻辑从 `app.py` 移入 `goldmonitor/` 模块，前端逐步把状态、渲染和事件处理从 `static/app.js` 拆成专门模块。每个阶段必须有可运行测试和迁移/回归证据。

**Tech Stack:** Python 3、Flask、Flask-SocketIO、SQLite、JSON 本地存储、原生前端 JavaScript、pytest。

---

## Phase 1: 模块边界整理

### Task 1: 抽取后端状态组装模块

**Files:**
- Create: `goldmonitor/app_state.py`
- Create: `tests/test_app_state_module.py`
- Modify: `app.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_price_api_state_limits_klines_and_preserves_market_fields():
    from goldmonitor.app_state import build_price_api_state

    state = build_price_api_state(
        {
            "price_usd": 2350.12,
            "price_rmb": 544.21,
            "usdcny_rate": 7.21,
            "gold_price_source": "测试金价源",
            "gold_price_time": "2026-06-30T10:00:00",
            "gold_price_cached": False,
            "gold_price_error": "",
            "usdcny_rate_source": "测试汇率源",
            "usdcny_rate_time": "2026-06-30T10:00:01",
            "usdcny_rate_cached": True,
            "usdcny_rate_error": "启动时使用缓存汇率",
            "previous_usd": 2349.0,
            "previous_rmb": 543.9,
            "price_history": [{"time": "09:59:59"}],
            "last_fetch_ok": True,
            "klines_5min": [{"idx": idx} for idx in range(80)],
        }
    )

    assert state["usd"] == 2350.12
    assert state["rmb"] == 544.21
    assert state["rate"] == 7.21
    assert state["gold_source"] == "测试金价源"
    assert state["rate_cached"] is True
    assert state["time"] == "09:59:59"
    assert state["ok"] is True
    assert [item["idx"] for item in state["klines_5min"]] == list(range(8, 80))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_app_state_module.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'goldmonitor.app_state'`.

- [ ] **Step 3: Write minimal implementation**

Create `goldmonitor/app_state.py` with pure builders:

```python
def _recent_items(items, limit):
    if not isinstance(items, list):
        return []
    return list(items[-int(limit):])


def build_price_api_state(market):
    market = market if isinstance(market, dict) else {}
    history = market.get("price_history") if isinstance(market.get("price_history"), list) else []
    latest_time = history[-1].get("time") if history and isinstance(history[-1], dict) else None
    return {
        "usd": market.get("price_usd"),
        "rmb": market.get("price_rmb"),
        "rate": market.get("usdcny_rate"),
        "gold_source": market.get("gold_price_source"),
        "gold_time": market.get("gold_price_time"),
        "gold_cached": bool(market.get("gold_price_cached")),
        "gold_error": market.get("gold_price_error") or "",
        "rate_source": market.get("usdcny_rate_source"),
        "rate_time": market.get("usdcny_rate_time"),
        "rate_cached": bool(market.get("usdcny_rate_cached")),
        "rate_error": market.get("usdcny_rate_error") or "",
        "previous_usd": market.get("previous_usd"),
        "previous_rmb": market.get("previous_rmb"),
        "time": latest_time,
        "ok": bool(market.get("last_fetch_ok")),
        "klines_5min": _recent_items(market.get("klines_5min"), 72),
    }
```

- [ ] **Step 4: Add Socket init-state test and implementation**

Add a second test that calls `build_socket_init_state()` with injected watch target, portfolio, settings, alert log, fetch status, source health, comparison, history state, daily, news and risk history objects. Assert that `history` is limited to 60, `alert_log` is limited to 20, and injected state objects are preserved.

Implement `build_socket_init_state()` in `goldmonitor/app_state.py` by extending `build_price_api_state()` with the existing `on_connect` payload keys.

- [ ] **Step 5: Wire app.py to the new module**

Add `from goldmonitor import app_state as app_state_core`.

Add a small `_market_state_locked()` helper in `app.py` that returns the current market globals as a dictionary.

Replace `/api/price` payload assembly with `jsonify(app_state_core.build_price_api_state(_market_state_locked()))`.

Replace the `on_connect` inline state dictionary with `app_state_core.build_socket_init_state(...)`.

- [ ] **Step 6: Verify**

Run:

```bash
.venv/bin/python -m pytest tests/test_app_state_module.py tests/test_fetch_status_app.py tests/test_frontend_market_status_contract.py tests/socket_connect_check.py -q
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

## Phase 2: 本地数据能力完善

### Task 2: 数据清单与 schema 元数据统一

**Files:**
- Create: `goldmonitor/storage_manifest.py`
- Create: `tests/test_storage_manifest_module.py`
- Modify: `app.py`
- Modify: `goldmonitor/diagnostics.py`

- [ ] Define a `storage_manifest()` function listing settings, thresholds, watch targets, portfolio positions, portfolio transactions, portfolio alerts, market cache, news, risk history, price history JSON, price history SQLite, alert log SQLite and exports directory.
- [ ] Add tests asserting every current persisted path in `app.py` is represented in the manifest.
- [ ] Use the manifest in diagnostics so reports include path, format, expected schema version when applicable, and migration need.
- [ ] Run `.venv/bin/python -m pytest tests/test_storage_manifest_module.py tests/test_support_files_module.py tests/engineering_foundation_check.py -q`.

### Task 3: 导入前预检与恢复预览

**Files:**
- Modify: `goldmonitor/settings_store.py`
- Modify: `goldmonitor/support_files.py`
- Modify: `app.py`
- Modify: `static/app.js`
- Test: `tests/test_settings_store_module.py`, `tests/test_support_files_module.py`

- [ ] Add backend preview function for config import that reports affected sections, missing sections, ignored keys and secret-key handling.
- [ ] Add Socket event `preview_import_config` returning preview before `import_config`.
- [ ] Update front-end import flow to call preview first and show confirmation details.
- [ ] Preserve existing direct `import_config` behavior for existing clients.

## Phase 3: 持仓、预警、复盘闭环

### Task 4: 持仓状态分层

**Files:**
- Modify: `goldmonitor/portfolio.py`
- Modify: `static/app.js`
- Test: `tests/test_portfolio_module.py`

- [ ] Add portfolio status categories: `profit`, `loss`, `near_cost`, `target_hit`, `waiting_price`, `closed`.
- [ ] Compute category in pure portfolio state builders, not in front-end rendering.
- [ ] Display category in portfolio list and filters.

### Task 5: 预警处理记录

**Files:**
- Modify: `goldmonitor/alert_log.py`
- Modify: `app.py`
- Modify: `static/app.js`
- Test: `tests/test_alert_notification_summary_app.py`

- [ ] Add handled status, handled time and handling note to alert log payload.
- [ ] Add Socket event to update handling state.
- [ ] Show handled state in alert log and timeline.

## Phase 4: 行情可信度增强

### Task 6: 数据质量评分

**Files:**
- Modify: `goldmonitor/market_data.py`
- Modify: `goldmonitor/risk_analysis.py`
- Modify: `app.py`
- Modify: `static/app.js`
- Test: `tests/test_market_data_module.py`, `tests/test_risk_analysis_module.py`

- [ ] Add a pure `build_market_quality()` function based on cache status, source comparison, source health and stale age.
- [ ] Include quality state in fetch status, source health panel and risk analysis snapshot.
- [ ] Display quality level as normal, degraded, stale or anomaly.

## Phase 5: 谨慎扩展产品边界

### Task 7: 扩展入口约束

**Files:**
- Create: `docs/product-discovery/extension-readiness-checklist.md`
- Modify: `README.md`

- [ ] Document entry conditions for multi-asset support, extra notification channels, local read-only panel and cloud sync.
- [ ] Add a project rule: no boundary expansion starts until phases 1-4 are verified.
- [ ] Keep README focused on current product scope and mark boundary extensions as future options.

## Cross-Phase Verification

- [ ] Run `.venv/bin/python -m pytest -q`.
- [ ] Run release contract checks listed in `README.md` for the platform being changed.
- [ ] Inspect `git diff --stat` to ensure changes are scoped to the active phase.
- [ ] Update docs only after implementation behavior is verified.
