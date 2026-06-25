# Portfolio Transactions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add portfolio transaction records, moving-average cost basis, realized PnL, migration from legacy positions, transaction UI, and CSV exports.

**Architecture:** Treat transaction records as the source of truth. Backend stores `portfolio_transactions.json`, derives current positions on every state build, and keeps legacy position functions as compatibility wrappers. Frontend adds a segmented portfolio/transaction view with separate drafts so live price refreshes do not clear active input.

**Tech Stack:** Python, Flask-SocketIO, local JSON stores, vanilla JavaScript, CSS, pytest.

---

### Task 1: Backend Transaction Model

**Files:**
- Modify: `goldmonitor/portfolio.py`
- Test: `tests/test_portfolio_module.py`

- [x] Add failing tests for transaction normalization, legacy migration, moving-average buy/sell calculation, invalid oversell, and both CSV exports.
- [x] Run `python -m pytest tests/test_portfolio_module.py -q` and confirm the new tests fail because transaction helpers do not exist.
- [x] Implement transaction helpers in `goldmonitor/portfolio.py`: `generate_portfolio_transaction_id`, `normalize_portfolio_transaction`, `normalize_portfolio_transactions`, `transactions_from_positions`, `build_portfolio_state_from_transactions`, `validate_portfolio_transactions`, `PortfolioTransactionStore`, `build_portfolio_positions_csv`, and `build_portfolio_transactions_csv`.
- [x] Keep existing position helpers available by making them use equivalent buy transactions internally where possible.
- [x] Run `python -m pytest tests/test_portfolio_module.py -q` and confirm backend portfolio tests pass.

### Task 2: App Integration And Socket Events

**Files:**
- Modify: `app.py`
- Test: `tests/test_portfolio_module.py`

- [x] Add failing tests for app wrappers using transaction state, save/delete transaction events, oversell error handling, export `positions`, and export `transactions`.
- [x] Run targeted pytest and confirm failures are due to missing app wrappers/events.
- [x] Add `PORTFOLIO_TRANSACTIONS_PATH`, `portfolio_transactions`, transaction store wrappers, save/delete transaction wrappers, migration on load, and transaction-aware CSV export.
- [x] Keep legacy `save_portfolio_position` and `delete_portfolio_position` events working by translating them to transaction operations.
- [x] Run `python -m pytest tests/test_portfolio_module.py -q`.

### Task 3: Frontend Transaction UI

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Test: `tests/frontend_asset_check.py`

- [x] Add failing frontend asset checks for segmented view anchors, transaction event names, transaction draft functions, and transaction export entry.
- [x] Run `python tests/frontend_asset_check.py` and confirm it fails for missing frontend contract.
- [x] Add portfolio view segmented controls, transaction editor/list rendering, separate transaction drafts, and export kind selection.
- [x] Update styles so all portfolio and transaction input fields have stable widths on desktop and full width on mobile.
- [x] Run `node --check static/app.js` and `python tests/frontend_asset_check.py`.

### Task 4: Final Verification And Commit

**Files:**
- Modify: implementation files above
- Add: this plan document

- [x] Run `python -m pytest tests/test_portfolio_module.py -q`.
- [x] Run `python tests/frontend_asset_check.py`.
- [x] Run `node --check static/app.js`.
- [x] Run `python -m py_compile app.py goldmonitor/portfolio.py`.
- [x] Inspect `git diff --check` and `git status --short`.
- [x] Commit with `feat: 增加持仓流水和已实现盈亏`.
