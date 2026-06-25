# Portfolio Review Trends Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a transaction-derived portfolio review view that summarizes buy/sell cash flow, fees, realized PnL, net invested capital, and dated trend points.

**Architecture:** Backend derives a `review` object from normalized transaction replay and attaches it to the existing portfolio state. Frontend adds a third segmented view that renders review cards and trend rows from `portfolioState.review`, without duplicating cost or PnL calculations in JavaScript.

**Tech Stack:** Python, Flask-SocketIO state payloads, vanilla JavaScript, CSS, pytest, frontend static asset checks.

---

### Task 1: Backend Review Aggregation

**Files:**
- Modify: `goldmonitor/portfolio.py`
- Modify: `tests/test_portfolio_module.py`

- [x] Add a failing pytest case that imports `build_portfolio_state_from_transactions`, builds RMB buy/sell transactions across two dates, and asserts `state["review"]["rmb"]` contains `trade_count`, `buy_amount`, `sell_amount`, `fee_total`, `realized_pnl`, `net_invested`, `current_quantity`, `cost_basis`, and two trend `points`.
- [x] Run `.venv/bin/python -m pytest tests/test_portfolio_module.py::test_portfolio_review_tracks_cash_flow_and_realized_pnl -q` and verify it fails because `review` is missing.
- [x] Add empty review helpers in `goldmonitor/portfolio.py`: `empty_portfolio_review_summary`, `empty_portfolio_review`, and `_portfolio_review_trade_date`.
- [x] Add `build_portfolio_review_from_transactions(items)` that normalizes transactions, replays them once, groups enriched transactions by mode and date, and returns stable `rmb` and `usd` summaries.
- [x] Attach `review` to the dict returned by `build_portfolio_state_from_transactions`.
- [x] Run `.venv/bin/python -m pytest tests/test_portfolio_module.py::test_portfolio_review_tracks_cash_flow_and_realized_pnl -q` and verify it passes.

### Task 2: Frontend Review Contract

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Modify: `tests/frontend_asset_check.py`

- [x] Add failing frontend asset checks for `onclick="setPortfolioView('review')"`, `function renderPortfolioReview`, `.portfolio-review`, `.portfolio-review-card`, and `.portfolio-review-track`.
- [x] Run `.venv/bin/python tests/frontend_asset_check.py` and verify it fails because the frontend review contract is missing.
- [x] Add a `复盘` tab to `templates/index.html`.
- [x] Update `static/app.js` so `portfolioState` and `normalizePortfolioState` carry `review`.
- [x] Update `setPortfolioView` to allow `review`.
- [x] Add `renderPortfolioReview(box)`, `renderPortfolioReviewCard(mode, summary)`, `renderPortfolioReviewPoint(mode, point, maxNetInvested)`, `formatPortfolioSignedMoney(value, mode)`, and `portfolioReviewDateLabel(value)`.
- [x] Update `renderPortfolio()` so `portfolioView === "review"` renders the new review view.
- [x] Add CSS for review cards, trend rows, labels, and track bars with responsive grid constraints.
- [x] Run `.venv/bin/python tests/frontend_asset_check.py` and verify it passes.

### Task 3: Verification And Commit

**Files:**
- Modify: files above
- Add: this plan and the design document

- [x] Run `.venv/bin/python -m pytest tests/test_portfolio_module.py -q`.
- [x] Run `.venv/bin/python tests/frontend_asset_check.py`.
- [x] Run `/Users/dev/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node --check static/app.js`.
- [x] Run `.venv/bin/python -m py_compile app.py goldmonitor/portfolio.py`.
- [x] Run `git diff --check`.
- [x] Run browser verification for the `复盘` tab at desktop and mobile viewport widths.
- [x] Commit with `feat: 增加持仓复盘趋势`.
