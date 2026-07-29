// ========== 持仓管理 ==========
function normalizePortfolioSummary(summary) {
  const base = {
    count: 0,
    valued: 0,
    cost: 0,
    cost_basis: 0,
    market_value: 0,
    pnl: 0,
    pnl_percent: 0,
    unrealized_pnl: 0,
    unrealized_pnl_percent: 0,
    realized_pnl: 0,
    total_pnl: 0,
    fees: 0,
    quantity: 0,
  };
  const source = summary && typeof summary === 'object' ? summary : {};
  return Object.keys(base).reduce((acc, key) => {
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
}

function normalizePortfolioReviewPoint(point) {
  const base = {
    trade_count: 0,
    buy_amount: 0,
    sell_amount: 0,
    fee: 0,
    realized_pnl: 0,
    cumulative_buy_amount: 0,
    cumulative_sell_amount: 0,
    cumulative_fee: 0,
    cumulative_realized_pnl: 0,
    net_invested: 0,
    quantity: 0,
    cost_basis: 0,
  };
  const source = point && typeof point === 'object' ? point : {};
  const normalized = Object.keys(base).reduce((acc, key) => {
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
  normalized.date = source.date || '';
  return normalized;
}

function normalizePortfolioReviewSummary(summary, mode) {
  const base = {
    mode,
    trade_count: 0,
    buy_count: 0,
    sell_count: 0,
    buy_amount: 0,
    sell_amount: 0,
    fee_total: 0,
    realized_pnl: 0,
    net_invested: 0,
    current_quantity: 0,
    cost_basis: 0,
    average_cost: null,
  };
  const source = summary && typeof summary === 'object' ? summary : {};
  const normalized = Object.keys(base).reduce((acc, key) => {
    if (key === 'mode') {
      acc.mode = source.mode === 'usd' ? 'usd' : mode;
      return acc;
    }
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
  normalized.first_trade_date = source.first_trade_date || '';
  normalized.last_trade_date = source.last_trade_date || '';
  normalized.points = Array.isArray(source.points) ? source.points.map(normalizePortfolioReviewPoint) : [];
  return normalized;
}

function normalizePortfolioReview(review) {
  const source = review && typeof review === 'object' && !Array.isArray(review) ? review : {};
  return {
    rmb: normalizePortfolioReviewSummary(source.rmb, 'rmb'),
    usd: normalizePortfolioReviewSummary(source.usd, 'usd'),
  };
}

function normalizePortfolioAlert(alert) {
  const source = alert && typeof alert === 'object' && !Array.isArray(alert) ? alert : {};
  const triggered = source.triggered && typeof source.triggered === 'object' && !Array.isArray(source.triggered) ? source.triggered : {};
  return {
    id: source.id || '',
    position_id: source.position_id || '',
    enabled: source.enabled !== false,
    take_profit_price: source.take_profit_price == null ? '' : String(source.take_profit_price),
    stop_loss_price: source.stop_loss_price == null ? '' : String(source.stop_loss_price),
    profit_percent: source.profit_percent == null ? '' : String(source.profit_percent),
    loss_percent: source.loss_percent == null ? '' : String(source.loss_percent),
    near_cost_percent: source.near_cost_percent == null ? '' : String(source.near_cost_percent),
    note: source.note || '',
    status: source.status || '',
    triggered: {
      take_profit: !!triggered.take_profit,
      stop_loss: !!triggered.stop_loss,
      profit_percent: !!triggered.profit_percent,
      loss_percent: !!triggered.loss_percent,
      near_cost: !!triggered.near_cost,
    },
    last_triggered_at: source.last_triggered_at || '',
    last_trigger_price: source.last_trigger_price == null ? '' : String(source.last_trigger_price),
    last_trigger_condition: source.last_trigger_condition || '',
  };
}

function normalizePortfolioAlertsState(alerts) {
  const source = alerts && typeof alerts === 'object' && !Array.isArray(alerts) ? alerts : {};
  const items = Array.isArray(source.items) ? source.items.map(normalizePortfolioAlert).filter(item => item.position_id) : [];
  return {
    items,
    total: Number.isFinite(Number(source.total)) ? Number(source.total) : items.length,
    enabled: Number.isFinite(Number(source.enabled)) ? Number(source.enabled) : 0,
    triggered: Number.isFinite(Number(source.triggered)) ? Number(source.triggered) : 0,
  };
}

function normalizePortfolioImportBackup(data) {
  const source = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  return {
    available: source.available === true,
    kind: source.kind || 'transactions',
    batch_id: source.batch_id || '',
    imported_at: source.imported_at || '',
    count: Number.isFinite(Number(source.count)) ? Number(source.count) : 0,
    create: Number.isFinite(Number(source.create)) ? Number(source.create) : 0,
    overwrite: Number.isFinite(Number(source.overwrite)) ? Number(source.overwrite) : 0,
  };
}

function normalizePortfolioState(data) {
  const source = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  const items = Array.isArray(source.items)
    ? source.items.map(item => (item && typeof item === 'object') ? Object.assign({}, item) : null).filter(Boolean)
    : [];
  const transactions = Array.isArray(source.transactions)
    ? source.transactions.map(item => (item && typeof item === 'object') ? Object.assign({}, item) : null).filter(Boolean)
    : [];
  return {
    items,
    transactions,
    total: Number.isFinite(Number(source.total)) ? Number(source.total) : items.length,
    rmb_summary: normalizePortfolioSummary(source.rmb_summary),
    usd_summary: normalizePortfolioSummary(source.usd_summary),
    prices: source.prices && typeof source.prices === 'object' && !Array.isArray(source.prices) ? Object.assign({}, source.prices) : {},
    review: normalizePortfolioReview(source.review),
    alerts: normalizePortfolioAlertsState(source.alerts),
    import_backup: normalizePortfolioImportBackup(source.import_backup),
  };
}

function applyPortfolio(data) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  captureActivePortfolioAlertDraft();
  portfolioState = normalizePortfolioState(data);
  if (activePortfolioPositionId && activePortfolioPositionId !== 'new' && !portfolioState.items.some(item => item.id === activePortfolioPositionId)) {
    clearPortfolioDraft(activePortfolioPositionId);
    activePortfolioPositionId = null;
  }
  if (activePortfolioDetailId && !portfolioState.items.some(item => item.id === activePortfolioDetailId)) {
    activePortfolioDetailId = null;
  }
  if (activePortfolioAlertEditorId && !portfolioState.items.some(item => item.id === activePortfolioAlertEditorId)) {
    activePortfolioAlertEditorId = null;
  }
  if (activePortfolioTransactionId && activePortfolioTransactionId !== 'new' && !portfolioState.transactions.some(item => item.id === activePortfolioTransactionId)) {
    clearPortfolioTransactionDraft(activePortfolioTransactionId);
    activePortfolioTransactionId = null;
  }
  if (pendingPortfolioSave) {
    if (pendingPortfolioSave.kind === 'transaction') {
      clearPortfolioTransactionDraft(pendingPortfolioSave.id);
      if (activePortfolioTransactionId === pendingPortfolioSave.id) activePortfolioTransactionId = null;
    } else if (pendingPortfolioSave.kind === 'alert') {
      clearPortfolioAlertDraft(pendingPortfolioSave.id);
    } else if (pendingPortfolioSave.kind === 'position') {
      clearPortfolioDraft(pendingPortfolioSave.id);
      if (activePortfolioPositionId === pendingPortfolioSave.id) activePortfolioPositionId = null;
    }
    pendingPortfolioSave = null;
  }
  renderPortfolio();
  if (activeUnifiedAlertRuleId && alertRuleDraft && alertRuleDraft.kind === 'portfolio') {
    renderAlertRuleCenter();
  }
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
  const places = Number.isFinite(Number(digits)) ? Math.max(0, Number(digits)) : 2;
  return number.toLocaleString('en-US', { minimumFractionDigits: places, maximumFractionDigits: places });
}

function formatPortfolioMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return portfolioCurrency(mode) + formatPortfolioNumber(number, 2);
}

function formatPortfolioSignedMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const prefix = number > 0 ? '+' : number < 0 ? '-' : '';
  return prefix + portfolioCurrency(mode) + formatPortfolioNumber(Math.abs(number), 2);
}

function formatPortfolioPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const prefix = number > 0 ? '+' : '';
  return prefix + formatPortfolioNumber(number, 2) + '%';
}

function portfolioPnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return '';
  return number > 0 ? 'up' : 'down';
}

function portfolioStatusLabel(status) {
  return ({
    profit: '盈利',
    loss: '亏损',
    near_cost: '接近成本',
    target_hit: '触发预警',
    waiting_price: '等待行情',
    closed: '清仓',
    invalid_position: '需修正',
    valued: '已估值',
  })[status] || '未分类';
}

function portfolioStatusClass(status) {
  if (status === 'profit') return 'on';
  if (status === 'loss' || status === 'target_hit') return 'warn';
  return 'off';
}

function portfolioValuationLabel(item) {
  if (!item || item.valuation_status === 'invalid_position' || item.quantity == null) {
    return '持仓数据需修正';
  }
  if (item.valuation_status === 'closed') {
    return '已清仓';
  }
  if (item.valuation_status === 'waiting_price' || item.current_price == null) {
    return '等待行情';
  }
  const mode = item.mode || currentMode;
  return formatPortfolioMoney(item.market_value, mode);
}

function requestPortfolioRefresh() {
  if (!socket.connected) return;
  socket.emit('get_portfolio');
}

function portfolioDraftKey(id) {
  return String(id || 'new');
}

function portfolioBaseDraft(item) {
  const isNew = !item || item.id === 'new';
  const source = item || {};
  return {
    id: isNew ? 'new' : source.id,
    name: source.name || '',
    mode: source.mode || currentMode,
    entry_price: source.entry_price == null ? '' : String(source.entry_price),
    quantity: source.quantity == null ? '' : String(source.quantity),
    entry_date: source.entry_date || '',
    note: source.note || '',
  };
}

function portfolioDraftFor(item) {
  const base = portfolioBaseDraft(item);
  const draft = portfolioDrafts[portfolioDraftKey(base.id)] || {};
  return Object.assign({}, base, draft, { id: base.id });
}

function capturePortfolioDraft(id) {
  const key = portfolioDraftKey(id);
  if (!document.getElementById('portfolioName_' + key)) return;
  portfolioDrafts[key] = {
    name: portfolioInputValue(key, 'Name'),
    mode: portfolioInputValue(key, 'Mode') || currentMode,
    entry_price: portfolioInputValue(key, 'EntryPrice'),
    quantity: portfolioInputValue(key, 'Quantity'),
    entry_date: portfolioInputValue(key, 'EntryDate'),
    note: portfolioInputValue(key, 'Note'),
  };
}

function captureActivePortfolioDraft() {
  if (!activePortfolioPositionId) return;
  capturePortfolioDraft(activePortfolioPositionId);
}

function clearPortfolioDraft(id) {
  delete portfolioDrafts[portfolioDraftKey(id)];
}

function portfolioTransactionDraftKey(id) {
  return String(id || 'new');
}

function portfolioTransactionToday(now) {
  const date = now instanceof Date ? now : new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

function defaultPortfolioTransactionPrice(mode) {
  const raw = latestData && mode === 'usd' ? latestData.usd : latestData && latestData.rmb;
  const number = Number(raw);
  return Number.isFinite(number) && number > 0 ? number.toFixed(2) : '';
}

function portfolioTransactionBaseDraft(item) {
  const isNew = !item || item.id === 'new';
  const source = item || {};
  const mode = source.mode || currentMode;
  const defaultPrice = isNew ? defaultPortfolioTransactionPrice(mode) : '';
  return {
    id: isNew ? 'new' : source.id,
    position_id: source.position_id || '',
    name: source.name || '',
    type: source.type || 'buy',
    mode: mode,
    price: source.price == null || (isNew && source.price === '') ? defaultPrice : String(source.price),
    quantity: source.quantity == null ? '' : String(source.quantity),
    fee: source.fee == null ? '0' : String(source.fee),
    trade_date: source.trade_date || (isNew ? portfolioTransactionToday() : ''),
    note: source.note || '',
  };
}

function portfolioTransactionDraftFor(item) {
  const base = portfolioTransactionBaseDraft(item);
  const draft = portfolioTransactionDrafts[portfolioTransactionDraftKey(base.id)] || {};
  return Object.assign({}, base, draft, { id: base.id });
}

function portfolioTransactionInputValue(id, field) {
  const el = document.getElementById('portfolioTransaction' + field + '_' + id);
  return el ? el.value : '';
}

function capturePortfolioTransactionDraft(id) {
  const key = portfolioTransactionDraftKey(id);
  if (!document.getElementById('portfolioTransactionName_' + key)) return;
  portfolioTransactionDrafts[key] = {
    position_id: portfolioTransactionInputValue(key, 'PositionId'),
    name: portfolioTransactionInputValue(key, 'Name'),
    type: portfolioTransactionInputValue(key, 'Type') || 'buy',
    mode: portfolioTransactionInputValue(key, 'Mode') || currentMode,
    price: portfolioTransactionInputValue(key, 'Price'),
    quantity: portfolioTransactionInputValue(key, 'Quantity'),
    fee: portfolioTransactionInputValue(key, 'Fee'),
    trade_date: portfolioTransactionInputValue(key, 'TradeDate'),
    note: portfolioTransactionInputValue(key, 'Note'),
  };
}

function captureActivePortfolioTransactionDraft() {
  if (!activePortfolioTransactionId) return;
  capturePortfolioTransactionDraft(activePortfolioTransactionId);
}

function clearPortfolioTransactionDraft(id) {
  delete portfolioTransactionDrafts[portfolioTransactionDraftKey(id)];
}

function portfolioAlertForPosition(positionId) {
  const alerts = portfolioState.alerts && Array.isArray(portfolioState.alerts.items) ? portfolioState.alerts.items : [];
  return alerts.find(item => item.position_id === positionId) || null;
}

function portfolioAlertDraftKey(positionId) {
  return String(positionId || '');
}

function portfolioAlertBaseDraft(position, alert) {
  const source = alert || {};
  return {
    id: source.id || '',
    position_id: position && position.id ? position.id : source.position_id || '',
    enabled: source.enabled !== false,
    take_profit_price: source.take_profit_price == null ? '' : String(source.take_profit_price || ''),
    stop_loss_price: source.stop_loss_price == null ? '' : String(source.stop_loss_price || ''),
    profit_percent: source.profit_percent == null ? '' : String(source.profit_percent || ''),
    loss_percent: source.loss_percent == null ? '' : String(source.loss_percent || ''),
    near_cost_percent: source.near_cost_percent == null ? '' : String(source.near_cost_percent || ''),
    note: source.note || '',
    status: source.status || 'empty',
  };
}

function portfolioAlertDraftFor(position, alert) {
  const base = portfolioAlertBaseDraft(position, alert);
  const draft = portfolioAlertDrafts[portfolioAlertDraftKey(base.position_id)] || {};
  return Object.assign({}, base, draft, { id: base.id, position_id: base.position_id, status: alert ? alert.status : base.status });
}

function portfolioAlertInputValue(positionId, field) {
  const el = document.getElementById('portfolioAlert' + field + '_' + positionId);
  return el ? el.value : '';
}

function capturePortfolioAlertDraft(positionId) {
  const key = portfolioAlertDraftKey(positionId);
  if (!key || !document.getElementById('portfolioAlertTakeProfit_' + key)) return;
  const existing = portfolioAlertForPosition(key);
  portfolioAlertDrafts[key] = {
    id: existing ? existing.id : '',
    position_id: key,
    enabled: portfolioAlertInputValue(key, 'Enabled') !== 'false',
    take_profit_price: portfolioAlertInputValue(key, 'TakeProfit'),
    stop_loss_price: portfolioAlertInputValue(key, 'StopLoss'),
    profit_percent: portfolioAlertInputValue(key, 'ProfitPercent'),
    loss_percent: portfolioAlertInputValue(key, 'LossPercent'),
    near_cost_percent: portfolioAlertInputValue(key, 'NearCostPercent'),
    note: portfolioAlertInputValue(key, 'Note'),
  };
}

function captureActivePortfolioAlertDraft() {
  if (!activePortfolioDetailId) return;
  capturePortfolioAlertDraft(activePortfolioDetailId);
}

function clearPortfolioAlertDraft(positionId) {
  delete portfolioAlertDrafts[portfolioAlertDraftKey(positionId)];
}
