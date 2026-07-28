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

function renderPortfolioSummaryCard(title, mode, summary) {
  const state = normalizePortfolioSummary(summary);
  const valueClass = portfolioPnlClass(state.total_pnl || state.pnl);
  const titleText = title ? title + ' · ' + portfolioModeLabel(mode) : portfolioModeLabel(mode);
  const valueText = state.count === 0
    ? formatPortfolioMoney(0, mode)
    : formatPortfolioMoney(state.total_pnl || state.pnl, mode);
  const costMeta = state.count === 0
    ? '暂无持仓'
    : state.valued === 0
      ? '等待行情'
      : '市值 ' + formatPortfolioMoney(state.market_value, mode) + ' · 成本 ' + formatPortfolioMoney(state.cost_basis || state.cost, mode);
  const countMeta = '未实现 ' + formatPortfolioMoney(state.unrealized_pnl, mode) + ' · 已实现 ' + formatPortfolioMoney(state.realized_pnl, mode);
  return [
    '<div class="portfolio-summary-card">',
    '<div class="portfolio-summary-title">' + escapeHtml(titleText) + '</div>',
    '<div class="portfolio-summary-value ' + valueClass + '">' + escapeHtml(valueText) + '</div>',
    '<div class="portfolio-summary-meta">' + escapeHtml(costMeta) + '</div>',
    '<div class="portfolio-summary-meta ' + valueClass + '">' + escapeHtml(countMeta) + '</div>',
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

function renderPortfolioTabs() {
  const box = document.getElementById('portfolioViewTabs');
  if (!box) return;
  Array.from(box.querySelectorAll('.portfolio-tab')).forEach(button => {
    const target = button.getAttribute('onclick') || '';
    const isActive = target.indexOf("'" + portfolioView + "'") >= 0;
    button.classList.toggle('active', isActive);
  });
}

function rightPanelMenuForButton(button) {
  if (!button || !button.closest) return null;
  if (button.id === 'portfolioToolsMoreButton') return document.getElementById('portfolioToolsMenu');
  if (button.id === 'alertLogMoreButton') return document.getElementById('alertLogMenu');
  const portfolioSelect = button.closest('.portfolio-select-wrap');
  if (portfolioSelect) return portfolioSelect.querySelector('.portfolio-select-menu');
  const sourceActions = button.closest('.source-health-actions');
  if (sourceActions) return sourceActions.querySelector('#sourceHealthMenu');
  const logActions = button.closest('.log-actions');
  if (logActions) return logActions.querySelector('.log-entry-menu');
  const portfolioDetailActions = button.closest('.portfolio-detail-actions');
  if (portfolioDetailActions) return portfolioDetailActions.querySelector('.portfolio-detail-action-menu');
  return null;
}

function closeRightPanelMenus(exceptMenu) {
  const menus = [
    document.getElementById('portfolioToolsMenu'),
    document.getElementById('sourceHealthMenu'),
    document.getElementById('alertLogMenu'),
    ...document.querySelectorAll('.portfolio-select-menu'),
    ...document.querySelectorAll('.log-entry-menu'),
    ...document.querySelectorAll('.portfolio-detail-action-menu'),
  ].filter(Boolean);
  menus.forEach(menu => {
    if (menu !== exceptMenu) menu.hidden = true;
  });
  document.querySelectorAll('#portfolioToolsMoreButton, #alertLogMoreButton, .portfolio-select-trigger, .source-health-action-trigger, .log-action-trigger, .portfolio-detail-action-trigger').forEach(button => {
    const controlledMenu = rightPanelMenuForButton(button);
    if (controlledMenu !== exceptMenu) button.setAttribute('aria-expanded', 'false');
  });
}

function isRightPanelMenuEventTarget(target) {
  return !!(target && target.closest && target.closest([
    '#portfolioToolsMoreButton',
    '#portfolioToolsMenu',
    '#alertLogMoreButton',
    '#alertLogMenu',
    '.portfolio-select-wrap',
    '.source-health-actions',
    '#sourceHealthMenu',
    '.log-actions',
    '.portfolio-detail-actions',
  ].join(', ')));
}

function closeRightPanelMenusOnOutsideClick(event) {
  if (isRightPanelMenuEventTarget(event.target)) return;
  closeRightPanelMenus();
}

document.addEventListener('click', closeRightPanelMenusOnOutsideClick);

function togglePortfolioToolsMenu() {
  const menu = document.getElementById('portfolioToolsMenu');
  const button = document.getElementById('portfolioToolsMoreButton');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}

function togglePortfolioDetailActionMenu(button) {
  const actions = button && button.closest ? button.closest('.portfolio-detail-actions') : null;
  const menu = actions ? actions.querySelector('.portfolio-detail-action-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function setPortfolioSearch(value) {
  portfolioSearch = String(value || '').trim();
  renderPortfolio();
}

const PORTFOLIO_POSITION_FILTER_OPTIONS = [
  { value: 'all', label: '全部持仓' },
  { value: 'rmb', label: '人民币' },
  { value: 'usd', label: '美元' },
  { value: 'profit', label: '盈利' },
  { value: 'loss', label: '亏损' },
  { value: 'near_cost', label: '接近成本' },
  { value: 'target_hit', label: '触发预警' },
  { value: 'valued', label: '已估值' },
  { value: 'waiting_price', label: '等待行情' },
  { value: 'closed', label: '清仓' },
];
const PORTFOLIO_POSITION_SORT_OPTIONS = [
  { value: 'recent', label: '最近交易' },
  { value: 'market_value', label: '市值' },
  { value: 'total_pnl', label: '总盈亏' },
  { value: 'unrealized_pnl', label: '未实现盈亏' },
  { value: 'quantity', label: '数量' },
  { value: 'name', label: '名称' },
];
const PORTFOLIO_TRANSACTION_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
];
const PORTFOLIO_TRANSACTION_MODE_OPTIONS = [
  { value: 'all', label: '全部单位' },
  { value: 'rmb', label: 'RMB/克' },
  { value: 'usd', label: 'USD/oz' },
];
const PORTFOLIO_TRANSACTION_SORT_OPTIONS = [
  { value: 'date_desc', label: '交易日期倒序' },
  { value: 'date_asc', label: '交易日期正序' },
  { value: 'amount_desc', label: '成交金额优先' },
  { value: 'realized_desc', label: '已实现优先' },
  { value: 'name', label: '名称' },
];

function portfolioOptionValue(options, value, fallback) {
  return options.some(option => option.value === value) ? value : fallback;
}

function setPortfolioPositionFilter(value) {
  portfolioPositionFilter = portfolioOptionValue(PORTFOLIO_POSITION_FILTER_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioPositionSort(value) {
  portfolioPositionSort = portfolioOptionValue(PORTFOLIO_POSITION_SORT_OPTIONS, value, 'recent');
  renderPortfolio();
}

function setPortfolioTransactionTypeFilter(value) {
  portfolioTransactionTypeFilter = portfolioOptionValue(PORTFOLIO_TRANSACTION_TYPE_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioTransactionModeFilter(value) {
  portfolioTransactionModeFilter = portfolioOptionValue(PORTFOLIO_TRANSACTION_MODE_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioTransactionSort(value) {
  portfolioTransactionSort = portfolioOptionValue(PORTFOLIO_TRANSACTION_SORT_OPTIONS, value, 'date_desc');
  renderPortfolio();
}

function escapeJsString(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\r/g, '\\r').replace(/\n/g, '\\n');
}

function togglePortfolioControlMenu(button) {
  const wrap = button && button.closest ? button.closest('.portfolio-select-wrap') : null;
  const menu = wrap ? wrap.querySelector('.portfolio-select-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function setPortfolioControlSelection(action, value) {
  closeRightPanelMenus();
  const handlers = {
    positionFilter: setPortfolioPositionFilter,
    positionSort: setPortfolioPositionSort,
    transactionType: setPortfolioTransactionTypeFilter,
    transactionMode: setPortfolioTransactionModeFilter,
    transactionSort: setPortfolioTransactionSort,
  };
  if (handlers[action]) handlers[action](value);
}

function renderPortfolioDropdownControl(className, label, current, options, action) {
  const selected = options.find(option => option.value === current) || options[0];
  const optionButtons = options.map(option => {
    const active = option.value === current;
    return [
      '<button class="portfolio-select-option' + (active ? ' active' : '') + '" type="button" data-value="' + escapeHtml(option.value) + '" aria-pressed="' + String(active) + '" onclick="setPortfolioControlSelection(\'' + escapeJsString(action) + '\', \'' + escapeJsString(option.value) + '\')">',
      escapeHtml(option.label),
      '</button>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-control ' + escapeHtml(className) + ' portfolio-select-control">',
    '<span>' + escapeHtml(label) + '</span>',
    '<div class="portfolio-select-wrap">',
    '<button class="portfolio-select-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="togglePortfolioControlMenu(this)">',
    '<span class="portfolio-select-value">' + escapeHtml(selected.label) + '</span>',
    '<span class="portfolio-select-arrow" aria-hidden="true"></span>',
    '</button>',
    '<div class="portfolio-select-menu" hidden>',
    optionButtons,
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioControls() {
  const box = document.getElementById('portfolioControls');
  if (!box) return;
  if (portfolioView === 'review') {
    box.innerHTML = [
      '<div class="portfolio-controls-note">交易复盘基于全部流水；持仓总收益按所选历史行情重估</div>',
      '<div class="portfolio-analytics-ranges">',
      [30, 90, 365].map(days => '<button class="btn-clear-sm' + (portfolioAnalyticsRange === days ? ' active' : '') + '" type="button" onclick="setPortfolioAnalyticsRange(' + days + ')">' + days + ' 日</button>').join(''),
      '<button class="btn-clear-sm" type="button" onclick="requestPortfolioAnalytics(true)">刷新</button>',
      '</div>',
    ].join('');
    return;
  }
  const search = [
    '<label class="portfolio-control portfolio-search">',
    '<span>搜索</span>',
    '<input type="search" value="' + escapeHtml(portfolioSearch) + '" placeholder="名称、备注、日期" oninput="setPortfolioSearch(this.value)">',
    '</label>',
  ].join('');
  if (portfolioView === 'transactions') {
    box.innerHTML = [
      search,
      renderPortfolioDropdownControl('portfolio-filter', '类型', portfolioTransactionTypeFilter, PORTFOLIO_TRANSACTION_TYPE_OPTIONS, 'transactionType'),
      renderPortfolioDropdownControl('portfolio-filter', '单位', portfolioTransactionModeFilter, PORTFOLIO_TRANSACTION_MODE_OPTIONS, 'transactionMode'),
      renderPortfolioDropdownControl('portfolio-sort', '排序', portfolioTransactionSort, PORTFOLIO_TRANSACTION_SORT_OPTIONS, 'transactionSort'),
    ].join('');
    return;
  }
  box.innerHTML = [
    search,
    renderPortfolioDropdownControl('portfolio-filter', '筛选', portfolioPositionFilter, PORTFOLIO_POSITION_FILTER_OPTIONS, 'positionFilter'),
    renderPortfolioDropdownControl('portfolio-sort', '排序', portfolioPositionSort, PORTFOLIO_POSITION_SORT_OPTIONS, 'positionSort'),
  ].join('');
}

function requestPortfolioAnalytics(force) {
  if (portfolioAnalyticsLoading) return;
  if (!force && portfolioAnalyticsState && Number(portfolioAnalyticsState.range_days) === portfolioAnalyticsRange) return;
  portfolioAnalyticsLoading = true;
  socket.emit('get_portfolio_analytics', { days: portfolioAnalyticsRange });
  if (portfolioView === 'review') renderPortfolio();
}

function setPortfolioAnalyticsRange(days) {
  const next = [30, 90, 365].includes(Number(days)) ? Number(days) : 90;
  if (portfolioAnalyticsRange === next && portfolioAnalyticsState) return;
  portfolioAnalyticsRange = next;
  portfolioAnalyticsState = null;
  renderPortfolio();
  requestPortfolioAnalytics(true);
}

function portfolioSearchMatches(textParts) {
  const query = portfolioSearch.trim().toLowerCase();
  if (!query) return true;
  return textParts.filter(Boolean).join(' ').toLowerCase().includes(query);
}

function portfolioSortableNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NEGATIVE_INFINITY;
}

function portfolioSortableDate(value) {
  return String(value || '');
}

function filteredPortfolioPositions() {
  const items = Array.isArray(portfolioState.items) ? portfolioState.items.slice() : [];
  const filtered = items.filter(item => {
    const mode = item.mode || 'rmb';
    const pnl = Number(item.total_pnl != null ? item.total_pnl : item.pnl);
    const portfolioStatus = item.portfolio_status || item.valuation_status || '';
    const valuationStatus = item.valuation_status || '';
    const matchesFilter = portfolioPositionFilter === 'all'
      || portfolioPositionFilter === mode
      || portfolioPositionFilter === portfolioStatus
      || portfolioPositionFilter === valuationStatus
      || (portfolioPositionFilter === 'profit' && Number.isFinite(pnl) && pnl > 0)
      || (portfolioPositionFilter === 'loss' && Number.isFinite(pnl) && pnl < 0);
    if (!matchesFilter) return false;
    return portfolioSearchMatches([
      item.id,
      item.name,
      item.note,
      portfolioModeLabel(mode),
      portfolioStatusLabel(portfolioStatus),
      portfolioValuationLabel(item),
      item.last_trade_date,
      item.entry_date,
    ]);
  });
  filtered.sort((left, right) => {
    if (portfolioPositionSort === 'name') return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
    if (portfolioPositionSort === 'market_value') return portfolioSortableNumber(right.market_value) - portfolioSortableNumber(left.market_value);
    if (portfolioPositionSort === 'total_pnl') {
      const rightPnl = right.total_pnl != null ? right.total_pnl : right.pnl;
      const leftPnl = left.total_pnl != null ? left.total_pnl : left.pnl;
      return portfolioSortableNumber(rightPnl) - portfolioSortableNumber(leftPnl);
    }
    if (portfolioPositionSort === 'unrealized_pnl') return portfolioSortableNumber(right.unrealized_pnl) - portfolioSortableNumber(left.unrealized_pnl);
    if (portfolioPositionSort === 'quantity') return portfolioSortableNumber(right.quantity) - portfolioSortableNumber(left.quantity);
    const dateCompare = portfolioSortableDate(right.last_trade_date || right.entry_date).localeCompare(portfolioSortableDate(left.last_trade_date || left.entry_date));
    return dateCompare || String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
  });
  return filtered;
}

function filteredPortfolioTransactions() {
  const transactions = Array.isArray(portfolioState.transactions) ? portfolioState.transactions.slice() : [];
  const filtered = transactions.filter(item => {
    const type = item.type === 'sell' ? 'sell' : 'buy';
    const mode = item.mode || 'rmb';
    if (portfolioTransactionTypeFilter !== 'all' && portfolioTransactionTypeFilter !== type) return false;
    if (portfolioTransactionModeFilter !== 'all' && portfolioTransactionModeFilter !== mode) return false;
    return portfolioSearchMatches([
      item.id,
      item.position_id,
      item.name,
      item.note,
      item.trade_date,
      type === 'sell' ? '卖出' : '买入',
      portfolioModeLabel(mode),
    ]);
  });
  filtered.sort((left, right) => {
    if (portfolioTransactionSort === 'name') return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
    if (portfolioTransactionSort === 'date_asc') {
      return portfolioSortableDate(left.trade_date).localeCompare(portfolioSortableDate(right.trade_date)) || String(left.id || '').localeCompare(String(right.id || ''));
    }
    if (portfolioTransactionSort === 'amount_desc') {
      const rightAmount = (Number(right.price) || 0) * (Number(right.quantity) || 0) + (Number(right.fee) || 0);
      const leftAmount = (Number(left.price) || 0) * (Number(left.quantity) || 0) + (Number(left.fee) || 0);
      return rightAmount - leftAmount;
    }
    if (portfolioTransactionSort === 'realized_desc') return portfolioSortableNumber(right.realized_pnl) - portfolioSortableNumber(left.realized_pnl);
    return portfolioSortableDate(right.trade_date).localeCompare(portfolioSortableDate(left.trade_date)) || String(right.id || '').localeCompare(String(left.id || ''));
  });
  return filtered;
}

function buildPortfolioEditor(item) {
  const target = portfolioDraftFor(item);
  const id = target.id;
  const escapedId = escapeHtml(id);
  const draftInputAttr = ' oninput="capturePortfolioDraft(\'' + escapedId + '\')"';
  const draftChangeAttr = ' onchange="capturePortfolioDraft(\'' + escapedId + '\')"';
  const modeChangeAttr = ' onchange="capturePortfolioDraft(\'' + escapedId + '\'); renderPortfolio()"';
  const mode = target.mode || currentMode;
  const name = target.name || '';
  const entryPrice = target.entry_price == null ? '' : String(target.entry_price);
  const quantity = target.quantity == null ? '' : String(target.quantity);
  const entryDate = target.entry_date || '';
  const note = target.note || '';
  return [
    '<div class="portfolio-editor">',
    '<div class="portfolio-fields">',
    '<div class="portfolio-field portfolio-name">',
    '<label for="portfolioName_' + escapedId + '">名称</label>',
    '<input id="portfolioName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(name) + '" placeholder="例如 金条"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioMode_' + escapedId + '">单位</label>',
    '<select id="portfolioMode_' + escapedId + '"' + modeChangeAttr + '>',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryPrice_' + escapedId + '">买入价</label>',
    '<input id="portfolioEntryPrice_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(entryPrice) + '" placeholder="输入价格"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioQuantity_' + escapedId + '">数量（' + escapeHtml(portfolioQuantityUnit(mode)) + '）</label>',
    '<input id="portfolioQuantity_' + escapedId + '" type="number" step="0.0001" value="' + escapeHtml(quantity) + '" placeholder="输入数量"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryDate_' + escapedId + '">买入日期</label>',
    '<input id="portfolioEntryDate_' + escapedId + '" type="date" value="' + escapeHtml(entryDate) + '"' + draftChangeAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioNote_' + escapedId + '">备注</label>',
    '<textarea id="portfolioNote_' + escapedId + '" maxlength="200" rows="2" placeholder="例如 账户或来源"' + draftInputAttr + '>' + escapeHtml(note) + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-editor-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioPosition(\'' + escapedId + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActivePortfolioPosition(\'' + escapedId + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolio() {
  const detailItem = activePortfolioDetailItem();
  renderPortfolioHeaderChrome(detailItem);
  renderPortfolioSummary();
  renderPortfolioTabs();
  renderPortfolioControls();
  renderPortfolioImportBackup();
  const box = document.getElementById('portfolioList');
  if (!box) return;
  if (detailItem) {
    box.innerHTML = renderPortfolioPositionDetail(detailItem);
    return;
  }
  if (portfolioView === 'review') {
    renderPortfolioReview(box);
    return;
  }
  if (portfolioView === 'transactions') {
    renderPortfolioTransactions(box);
    return;
  }
  renderPortfolioPositions(box);
}

function activePortfolioDetailItem() {
  if (!activePortfolioDetailId) return null;
  return (portfolioState.items || []).find(item => item && item.id === activePortfolioDetailId) || null;
}

function closePortfolioDetail() {
  captureActivePortfolioAlertDraft();
  activePortfolioDetailId = null;
  activePortfolioAlertEditorId = null;
  portfolioDetailView = 'review';
  renderPortfolio();
}

function renderPortfolioHeaderChrome(detailItem) {
  const card = document.querySelector('.portfolio-card');
  if (!card) return;
  card.classList.toggle('portfolio-detail-mode', !!detailItem);
  const title = card.querySelector('.portfolio-head h3');
  if (title) title.textContent = detailItem ? '持仓详情 · 复盘' : '持仓';
  const primary = card.querySelector('.portfolio-primary-action');
  if (!primary) return;
  if (detailItem) {
    primary.textContent = '返回列表';
    primary.onclick = closePortfolioDetail;
  } else {
    primary.textContent = '新增流水';
    primary.onclick = () => setActivePortfolioTransaction('new');
  }
}

function portfolioReviewDateLabel(value) {
  return value && value !== '未标日期' ? value : '未标日期';
}

function renderPortfolioReviewMetric(label, value, extraClass) {
  return [
    '<div class="portfolio-review-metric">',
    '<div class="portfolio-review-metric-label">' + escapeHtml(label) + '</div>',
    '<div class="portfolio-review-metric-value ' + (extraClass || '') + '">' + escapeHtml(value) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewCard(mode, summary) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  const pnlClass = portfolioPnlClass(state.realized_pnl);
  const title = mode === 'usd' ? '美元复盘' : '人民币复盘';
  const dateText = state.trade_count ? '最近 ' + portfolioReviewDateLabel(state.last_trade_date) : '暂无交易';
  const quantityText = formatPortfolioNumber(state.current_quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode);
  const meta = state.trade_count
    ? state.trade_count + ' 笔 · 买入 ' + formatPortfolioMoney(state.buy_amount, mode) + ' · 卖出 ' + formatPortfolioMoney(state.sell_amount, mode)
    : '暂无流水';
  return [
    '<div class="portfolio-review-card">',
    '<div class="portfolio-review-title">' + escapeHtml(title + ' · ' + portfolioModeLabel(mode)) + '</div>',
    '<div class="portfolio-review-value">' + escapeHtml(formatPortfolioMoney(state.net_invested, mode)) + '</div>',
    '<div class="portfolio-review-meta">' + escapeHtml(meta) + '</div>',
    '<div class="portfolio-review-meta">' + escapeHtml(dateText) + '</div>',
    '<div class="portfolio-review-metrics">',
    renderPortfolioReviewMetric('已实现', formatPortfolioSignedMoney(state.realized_pnl, mode), pnlClass),
    renderPortfolioReviewMetric('手续费', formatPortfolioMoney(state.fee_total, mode), ''),
    renderPortfolioReviewMetric('持有数量', quantityText, ''),
    renderPortfolioReviewMetric('剩余成本', formatPortfolioMoney(state.cost_basis, mode), ''),
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewPoint(mode, point, maxNetInvested) {
  const item = normalizePortfolioReviewPoint(point);
  const ratio = maxNetInvested > 0 ? Math.min(100, Math.max(0, Math.abs(item.net_invested) / maxNetInvested * 100)) : 0;
  const pnlClass = portfolioPnlClass(item.cumulative_realized_pnl);
  return [
    '<div class="portfolio-review-point">',
    '<div class="portfolio-review-point-main">',
    '<div class="portfolio-review-point-date">' + escapeHtml(portfolioReviewDateLabel(item.date)) + '</div>',
    '<div class="portfolio-review-point-meta">' + escapeHtml(item.trade_count + ' 笔 · 当日买入 ' + formatPortfolioMoney(item.buy_amount, mode) + ' · 当日卖出 ' + formatPortfolioMoney(item.sell_amount, mode)) + '</div>',
    '</div>',
    '<div class="portfolio-review-point-side">',
    '<div class="portfolio-review-track"><span style="width:' + ratio.toFixed(2) + '%"></span></div>',
    '<div class="portfolio-review-point-meta">净投入 ' + escapeHtml(formatPortfolioMoney(item.net_invested, mode)) + ' · 已实现 <span class="' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(item.cumulative_realized_pnl, mode)) + '</span></div>',
    '<div class="portfolio-review-point-meta">持有 ' + escapeHtml(formatPortfolioNumber(item.quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode)) + ' · 成本 ' + escapeHtml(formatPortfolioMoney(item.cost_basis, mode)) + '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewCurve(mode, summary) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  const points = state.points.map(normalizePortfolioReviewPoint).filter(point => point.date);
  if (!points.length) return '';
  const values = points.map(point => Number(point.cumulative_realized_pnl) || 0);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const width = 240;
  const height = 88;
  const padding = 12;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const xy = values.map((value, index) => {
    const x = points.length === 1 ? width / 2 : padding + innerWidth * (index / (points.length - 1));
    const y = padding + innerHeight * (1 - ((value - minValue) / range));
    return {
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
      value,
      point: points[index],
    };
  });
  const zeroY = padding + innerHeight * (1 - ((0 - minValue) / range));
  const linePoints = xy.map(item => item.x + ',' + item.y).join(' ');
  const last = xy[xy.length - 1];
  const pnlClass = portfolioPnlClass(last.value);
  return [
    '<div class="portfolio-review-curve">',
    '<div class="portfolio-review-curve-head">',
    '<div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '已实现收益曲线') + '</div>',
    '<div class="portfolio-review-curve-value ' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(last.value, mode)) + '</div>',
    '</div>',
    '<svg class="portfolio-curve-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" aria-hidden="true">',
    '<line class="portfolio-curve-axis" x1="' + padding + '" y1="' + zeroY.toFixed(2) + '" x2="' + (width - padding) + '" y2="' + zeroY.toFixed(2) + '"></line>',
    '<polyline class="portfolio-curve-line" points="' + linePoints + '"></polyline>',
    xy.map(item => '<circle class="portfolio-curve-point" cx="' + item.x + '" cy="' + item.y + '" r="2.8"></circle>').join(''),
    '</svg>',
    '<div class="portfolio-review-curve-meta">' + escapeHtml(points[0].date + ' 至 ' + last.point.date + ' · ' + points.length + ' 个交易日') + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewSection(mode, summary, maxNetInvested) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  if (!state.points.length) return '';
  return [
    '<div class="portfolio-review-section">',
    '<div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '趋势') + '</div>',
    renderPortfolioReviewCurve(mode, state),
    '<div class="portfolio-review-points">',
    state.points.map(point => renderPortfolioReviewPoint(mode, point, maxNetInvested)).join(''),
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioPerformanceCurve(mode, performance) {
  const state = performance && typeof performance === 'object' ? performance : {};
  const points = Array.isArray(state.points) ? state.points.filter(point => point && Number.isFinite(Number(point.total_pnl))) : [];
  if (!points.length) {
    return '<div class="portfolio-review-section"><div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '持仓总收益曲线') + '</div><div class="portfolio-review-analytics-empty">当前区间没有可用于历史重估的行情与流水交集。</div></div>';
  }
  const values = points.map(point => Number(point.total_pnl) || 0);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const width = 360;
  const height = 118;
  const padding = 14;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const xy = values.map((value, index) => {
    const x = points.length === 1 ? width / 2 : padding + innerWidth * (index / (points.length - 1));
    const y = padding + innerHeight * (1 - ((value - minValue) / range));
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), value, point: points[index] };
  });
  const zeroY = padding + innerHeight * (1 - ((0 - minValue) / range));
  const last = points[points.length - 1];
  const summary = state.summary && typeof state.summary === 'object' ? state.summary : {};
  const pnlClass = portfolioPnlClass(last.total_pnl);
  const meta = [
    points[0].date + ' 至 ' + last.date,
    points.length + ' 个估值点',
    '最大回撤 ' + formatPortfolioSignedMoney(summary.max_drawdown, mode),
  ].join(' · ');
  return [
    '<div class="portfolio-review-section portfolio-performance-section">',
    '<div class="portfolio-review-curve-head">',
    '<div><div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '持仓总收益曲线') + '</div><div class="portfolio-review-curve-meta">总收益 = 已实现收益 + 按历史市价计算的未实现收益</div></div>',
    '<div class="portfolio-review-curve-value ' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(last.total_pnl, mode)) + '</div>',
    '</div>',
    '<svg class="portfolio-curve-svg portfolio-performance-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" aria-label="持仓总收益曲线">',
    '<line class="portfolio-curve-axis" x1="' + padding + '" y1="' + zeroY.toFixed(2) + '" x2="' + (width - padding) + '" y2="' + zeroY.toFixed(2) + '"></line>',
    '<polyline class="portfolio-curve-line" points="' + xy.map(item => item.x + ',' + item.y).join(' ') + '"></polyline>',
    '</svg>',
    '<div class="portfolio-performance-metrics">',
    renderPortfolioReviewMetric('未实现', formatPortfolioSignedMoney(last.unrealized_pnl, mode), portfolioPnlClass(last.unrealized_pnl)),
    renderPortfolioReviewMetric('已实现', formatPortfolioSignedMoney(last.realized_pnl, mode), portfolioPnlClass(last.realized_pnl)),
    renderPortfolioReviewMetric('市值', formatPortfolioMoney(last.market_value, mode), ''),
    renderPortfolioReviewMetric('收益率', formatPortfolioPercent(last.total_pnl_percent), pnlClass),
    '</div>',
    '<div class="portfolio-review-curve-meta">' + escapeHtml(meta) + '</div>',
    state.unknown_date_count ? '<div class="portfolio-review-analytics-note">有 ' + escapeHtml(String(state.unknown_date_count)) + ' 笔流水缺少可识别日期，未计入历史曲线。</div>' : '',
    '</div>',
  ].join('');
}

function portfolioAnalyticsRate(value) {
  return value == null || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(1) + '%';
}

function renderAlertEffectiveness(effectiveness) {
  const state = effectiveness && typeof effectiveness === 'object' ? effectiveness : {};
  const total = Number(state.period_alerts || 0);
  const delivery = state.delivery && typeof state.delivery === 'object' ? state.delivery : {};
  const response = state.response && typeof state.response === 'object' ? state.response : {};
  const market = state.market_follow_through && typeof state.market_follow_through === 'object' ? state.market_follow_through : {};
  const items = Array.isArray(state.items) ? state.items.slice(0, 6) : [];
  if (!total) {
    return '<div class="portfolio-alert-effectiveness"><div class="portfolio-review-section-title">预警有效性</div><div class="portfolio-review-analytics-empty">最近 ' + escapeHtml(String(state.period_days || 30)) + ' 日没有可分析的预警记录。</div></div>';
  }
  const rows = items.map(item => {
    const direction = item.direction === 'down' ? '下行' : '上行';
    const outcome = item.follow_through ? '延续' : '未延续';
    const className = portfolioPnlClass(item.follow_through ? 1 : -1);
    return [
      '<div class="portfolio-effectiveness-row">',
      '<div><strong>' + escapeHtml(item.title || '预警') + '</strong><span>' + escapeHtml(String(item.timestamp || '').replace('T', ' ').slice(0, 16)) + ' · ' + direction + '</span></div>',
      '<div class="' + className + '">' + escapeHtml(outcome + ' ' + portfolioAnalyticsRate(item.final_signed_change_pct)) + '</div>',
      '</div>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-alert-effectiveness">',
    '<div class="portfolio-review-curve-head"><div><div class="portfolio-review-section-title">预警有效性</div><div class="portfolio-review-curve-meta">最近 ' + escapeHtml(String(state.period_days || 30)) + ' 日；行情延续按触发方向的 24 小时后变化统计</div></div></div>',
    '<div class="portfolio-effectiveness-grid">',
    renderPortfolioReviewMetric('预警数量', String(total), ''),
    renderPortfolioReviewMetric('通知送达率', portfolioAnalyticsRate(delivery.sent_rate), ''),
    renderPortfolioReviewMetric('已处理率', portfolioAnalyticsRate(response.handled_rate), ''),
    renderPortfolioReviewMetric('行情延续率', portfolioAnalyticsRate(market.rate), ''),
    '</div>',
    '<div class="portfolio-review-analytics-note">行情延续率仅描述预警触发后的价格路径，不代表预测准确率或投资建议。已评估 ' + escapeHtml(String(market.evaluated || 0)) + ' 条方向性预警。</div>',
    rows ? '<div class="portfolio-effectiveness-list">' + rows + '</div>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioAnalytics() {
  if (portfolioAnalyticsLoading && !portfolioAnalyticsState) {
    return '<div class="portfolio-review-analytics-loading">正在计算历史持仓收益与预警效果...</div>';
  }
  if (!portfolioAnalyticsState || Number(portfolioAnalyticsState.range_days) !== portfolioAnalyticsRange) {
    return '<div class="portfolio-review-analytics-empty">选择区间后可查看按历史市价重估的持仓总收益与预警效果。</div>';
  }
  const performance = portfolioAnalyticsState.performance && typeof portfolioAnalyticsState.performance === 'object' ? portfolioAnalyticsState.performance : {};
  return [
    '<div class="portfolio-performance-grid">',
    renderPortfolioPerformanceCurve('rmb', performance.rmb),
    renderPortfolioPerformanceCurve('usd', performance.usd),
    '</div>',
    renderAlertEffectiveness(portfolioAnalyticsState.alert_effectiveness),
  ].join('');
}

function renderPortfolioReview(box) {
  const review = normalizePortfolioReview(portfolioState.review);
  const totalTrades = review.rmb.trade_count + review.usd.trade_count;
  if (!totalTrades) {
    box.innerHTML = '<div class="portfolio-review">' + renderPortfolioAnalytics() + '<div class="portfolio-empty">暂无流水复盘数据</div></div>';
    return;
  }
  const maxNetInvested = Math.max(
    1,
    ...review.rmb.points.concat(review.usd.points).map(point => Math.abs(Number(point.net_invested) || 0))
  );
  box.innerHTML = [
    '<div class="portfolio-review">',
    '<div class="portfolio-review-grid">',
    renderPortfolioReviewCard('rmb', review.rmb),
    renderPortfolioReviewCard('usd', review.usd),
    '</div>',
    renderPortfolioAnalytics(),
    renderPortfolioReviewSection('rmb', review.rmb, maxNetInvested),
    renderPortfolioReviewSection('usd', review.usd, maxNetInvested),
    '</div>',
  ].join('');
}

function portfolioTransactionsForPosition(positionId) {
  return (Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [])
    .filter(item => item && item.position_id === positionId)
    .sort((left, right) => (
      portfolioReviewTimestampValue(right.trade_date || right.updated_at || right.created_at)
      - portfolioReviewTimestampValue(left.trade_date || left.updated_at || left.created_at)
    ));
}

function renderPortfolioDetailMetric(label, value, extraClass) {
  return [
    '<div class="portfolio-detail-metric">',
    '<div class="portfolio-detail-label">' + escapeHtml(label) + '</div>',
    '<div class="portfolio-detail-value ' + (extraClass || '') + '">' + escapeHtml(value) + '</div>',
    '</div>',
  ].join('');
}

function portfolioAlertStatusLabel(alert) {
  const status = alert && alert.status ? alert.status : 'empty';
  if (status === 'triggered') return '已触发';
  if (status === 'watching') return '监控中';
  if (status === 'disabled') return '已停用';
  return '未设置';
}

function portfolioAlertStatusClass(alert) {
  const status = alert && alert.status ? alert.status : 'empty';
  if (status === 'triggered') return 'on';
  if (status === 'watching') return 'on';
  return 'off';
}

function buildPortfolioAlertEditor(item) {
  const alert = portfolioAlertForPosition(item.id);
  const target = portfolioAlertDraftFor(item, alert);
  const positionId = escapeHtml(target.position_id);
  const inputAttr = ' oninput="capturePortfolioAlertDraft(\'' + positionId + '\')"';
  const changeAttr = ' onchange="capturePortfolioAlertDraft(\'' + positionId + '\')"';
  const resetButton = alert && alert.id
    ? '<button class="btn-clear-sm" type="button" onclick="resetPortfolioAlert(\'' + escapeHtml(alert.id) + '\')">重置</button>'
    : '';
  const deleteButton = alert && alert.id
    ? '<button class="btn-clear-sm" type="button" onclick="deletePortfolioAlert(\'' + escapeHtml(alert.id) + '\', \'' + positionId + '\')">清空</button>'
    : '';
  return [
    '<div class="portfolio-alert-editor">',
    '<div class="portfolio-alert-head">',
    '<div class="portfolio-detail-section-title">提醒设置</div>',
    '<span class="portfolio-alert-state ' + portfolioAlertStatusClass(alert) + '">' + escapeHtml(portfolioAlertStatusLabel(alert)) + '</span>',
    '</div>',
    '<div class="portfolio-alert-fields">',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertEnabled_' + positionId + '">状态</label>',
    '<select id="portfolioAlertEnabled_' + positionId + '"' + changeAttr + '>',
    '<option value="true"' + (target.enabled !== false ? ' selected' : '') + '>监控</option>',
    '<option value="false"' + (target.enabled === false ? ' selected' : '') + '>停用</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertTakeProfit_' + positionId + '">止盈价</label>',
    '<input id="portfolioAlertTakeProfit_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.take_profit_price) + '" placeholder="例如 760"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertStopLoss_' + positionId + '">止损价</label>',
    '<input id="portfolioAlertStopLoss_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.stop_loss_price) + '" placeholder="例如 680"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertProfitPercent_' + positionId + '">浮盈比例（%）</label>',
    '<input id="portfolioAlertProfitPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.profit_percent) + '" placeholder="例如 8"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertLossPercent_' + positionId + '">浮亏比例（%）</label>',
    '<input id="portfolioAlertLossPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.loss_percent) + '" placeholder="例如 3"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertNearCostPercent_' + positionId + '">近成本（%）</label>',
    '<input id="portfolioAlertNearCostPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.near_cost_percent) + '" placeholder="例如 1"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioAlertNote_' + positionId + '">备注</label>',
    '<textarea id="portfolioAlertNote_' + positionId + '" maxlength="120" rows="2" placeholder="例如 止盈后分批卖出"' + inputAttr + '>' + escapeHtml(target.note) + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-alert-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioAlert(\'' + positionId + '\')">保存提醒</button>',
    resetButton,
    deleteButton,
    '</div>',
    '</div>',
  ].join('');
}

function portfolioAlertThresholdText(label, value, mode, suffix) {
  if (value === null || value === undefined || value === '') return '';
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  const text = suffix ? formatPortfolioNumber(number, 2) + suffix : formatPortfolioMoney(number, mode);
  return label + ' ' + text;
}

function renderPortfolioAlertSummary(item, alert) {
  const mode = item.mode || 'rmb';
  const positionId = escapeHtml(item.id);
  const parts = [
    portfolioAlertThresholdText('止盈', alert && alert.take_profit_price, mode, ''),
    portfolioAlertThresholdText('止损', alert && alert.stop_loss_price, mode, ''),
    portfolioAlertThresholdText('浮盈', alert && alert.profit_percent, mode, '%'),
    portfolioAlertThresholdText('浮亏', alert && alert.loss_percent, mode, '%'),
    portfolioAlertThresholdText('近成本', alert && alert.near_cost_percent, mode, '%'),
  ].filter(Boolean);
  const stateText = portfolioAlertStatusLabel(alert);
  const summaryText = parts.length ? stateText + ' · ' + parts.join(' · ') : stateText + ' · 未设置价格条件';
  const buttonText = activePortfolioAlertEditorId === item.id ? '收起编辑' : '编辑提醒';
  return [
    '<div class="portfolio-alert-summary">',
    '<div class="portfolio-alert-summary-main">',
    '<span class="portfolio-alert-state ' + portfolioAlertStatusClass(alert) + '">' + escapeHtml(stateText) + '</span>',
    '<span class="portfolio-alert-summary-text">' + escapeHtml(summaryText) + '</span>',
    '</div>',
    '<div class="portfolio-alert-summary-actions">',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="togglePortfolioAlertEditor(\'' + positionId + '\')">' + buttonText + '</button>',
    '</div>',
    '</div>',
  ].join('');
}

function portfolioTransactionDisplay(transaction, fallbackMode) {
  const mode = transaction.mode || fallbackMode || 'rmb';
  const quantityDigits = mode === 'usd' ? 4 : 2;
  const typeText = transaction.type === 'sell' ? '卖出' : '买入';
  const typeClass = transaction.type === 'sell' ? 'sell' : 'buy';
  const amount = Number(transaction.price) * Number(transaction.quantity);
  const valueText = transaction.type === 'sell'
    ? '已实现 ' + formatPortfolioSignedMoney(transaction.realized_pnl, mode)
    : '成交 ' + formatPortfolioMoney(amount, mode);
  return {
    mode,
    quantityDigits,
    typeText,
    typeClass,
    valueText,
    quantityText: formatPortfolioNumber(transaction.quantity, quantityDigits) + ' ' + portfolioQuantityUnit(mode),
  };
}

function renderPortfolioDetailTransactionItem(item, transaction) {
  const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
  const metaParts = [
    transaction.trade_date || '未标日期',
    formatPortfolioMoney(transaction.price, display.mode),
    display.quantityText,
    Number(transaction.fee) > 0 ? '手续费 ' + formatPortfolioMoney(transaction.fee, display.mode) : '',
    transaction.note || '',
  ].filter(Boolean);
  return [
    '<div class="portfolio-detail-transaction">',
    '<div class="portfolio-detail-transaction-main">',
    '<div class="portfolio-detail-transaction-title"><span class="portfolio-transaction-type ' + display.typeClass + '">' + escapeHtml(display.typeText) + '</span>' + escapeHtml(transaction.name || item.name || '未命名流水') + '</div>',
    '<div class="portfolio-detail-transaction-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
    '</div>',
    '<div class="portfolio-detail-transaction-value ' + portfolioPnlClass(transaction.realized_pnl) + '">' + escapeHtml(display.valueText) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailTransactionsList(item, transactions, limit) {
  const visibleTransactions = Number.isFinite(Number(limit)) ? transactions.slice(0, Number(limit)) : transactions;
  if (!transactions.length) return '<div class="portfolio-detail-empty">暂无关联流水</div>';
  return visibleTransactions.map(transaction => renderPortfolioDetailTransactionItem(item, transaction)).join('')
    + (transactions.length > visibleTransactions.length ? '<div class="portfolio-detail-more">还有 ' + escapeHtml(String(transactions.length - visibleTransactions.length)) + ' 条流水，可切换到流水页查看</div>' : '');
}

function renderPortfolioDetailActions(item) {
  const positionId = escapeHtml(item.id);
  return [
    '<span class="portfolio-detail-actions">',
    '<button class="btn-clear-sm btn-muted-sm portfolio-detail-action-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="togglePortfolioDetailActionMenu(this)">操作</button>',
    '<span class="portfolio-detail-action-menu" hidden>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'buy\')">新增买入</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'sell\')">新增卖出</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioPosition(\'' + positionId + '\')">编辑持仓</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="openPortfolioAlertEditor(\'' + positionId + '\')">设置提醒</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setPortfolioView(\'transactions\')">查看全部流水</button>',
    '</span>',
    '</span>',
  ].join('');
}

function renderPortfolioDetailTabs(activeView) {
  const tabs = [
    ['overview', '概览'],
    ['transactions', '流水'],
    ['alert', '预警'],
    ['review', '复盘'],
  ];
  return '<div class="portfolio-detail-tabs">' + tabs.map(tab => (
    '<button class="portfolio-detail-tab' + (activeView === tab[0] ? ' active' : '') + '" type="button" onclick="setPortfolioDetailView(\'' + tab[0] + '\')">' + escapeHtml(tab[1]) + '</button>'
  )).join('') + '</div>';
}

function renderPortfolioDetailMetricGrid(item) {
  const mode = item.mode || 'rmb';
  const unrealizedPnl = item.unrealized_pnl != null ? item.unrealized_pnl : item.pnl;
  return [
    '<div class="portfolio-detail-grid">',
    renderPortfolioDetailMetric('平均成本', formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode), ''),
    renderPortfolioDetailMetric('市值', formatPortfolioMoney(item.market_value, mode), ''),
    renderPortfolioDetailMetric('未实现', formatPortfolioSignedMoney(unrealizedPnl, mode), portfolioPnlClass(unrealizedPnl)),
    renderPortfolioDetailMetric('已实现', formatPortfolioSignedMoney(item.realized_pnl, mode), portfolioPnlClass(item.realized_pnl)),
    '</div>',
  ].join('');
}

function renderPortfolioDetailOverview(item, alert, transactions) {
  return [
    '<div class="portfolio-detail-panel">',
    renderPortfolioDetailMetricGrid(item),
    renderPortfolioAlertSummary(item, alert),
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-transactions-head">',
    '<div class="portfolio-detail-section-title">最近流水</div>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setPortfolioDetailView(\'transactions\')">查看全部</button>',
    '</div>',
    '<div class="portfolio-detail-transactions-list">',
    renderPortfolioDetailTransactionsList(item, transactions, 3),
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailTransactions(item, transactions) {
  return [
    '<div class="portfolio-detail-panel">',
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-transactions-head">',
    '<div class="portfolio-detail-section-title">关联流水</div>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">新增流水</button>',
    '</div>',
    '<div class="portfolio-detail-transactions-list">',
    renderPortfolioDetailTransactionsList(item, transactions),
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailAlert(item, alert) {
  return [
    '<div class="portfolio-detail-panel">',
    renderPortfolioAlertSummary(item, alert),
    activePortfolioAlertEditorId === item.id ? buildPortfolioAlertEditor(item) : '',
    '</div>',
  ].join('');
}

function portfolioParseDate(value) {
  if (!value) return null;
  const parsed = new Date(String(value).replace(' ', 'T'));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function portfolioReviewTimestampValue(value) {
  const parsed = portfolioParseDate(value);
  return parsed ? parsed.getTime() : 0;
}

function portfolioAlertEntriesForPosition(item) {
  const tokens = [item && item.id, item && item.name]
    .map(value => String(value || '').trim().toLowerCase())
    .filter(Boolean);
  return alertEntries.filter(entry => {
    if (!entry || typeof entry !== 'object') return false;
    if (item && entry.position_id && entry.position_id === item.id) return true;
    const text = [
      entry.message,
      entry.title,
      entry.type,
      entry.mode,
      entry.handling_note,
      entry.watch_target_id,
      entry.source,
    ].join(' ').toLowerCase();
    return tokens.some(token => text.includes(token));
  });
}

function latestPortfolioRiskAnalysis() {
  const items = Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory.slice() : [];
  if (!items.length) return null;
  return items.sort((left, right) => portfolioReviewTimestampValue(left.analysis_time) - portfolioReviewTimestampValue(right.analysis_time))[items.length - 1];
}

function buildPortfolioReviewSummary(item, alert, transactions) {
  const now = Date.now();
  const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
  const recentTransactions = transactions.filter(transaction => {
    const date = portfolioParseDate(transaction.trade_date || transaction.updated_at || transaction.created_at);
    return date && date.getTime() >= sevenDaysAgo;
  });
  const matchedAlerts = portfolioAlertEntriesForPosition(item);
  const triggeredConditions = alert && alert.triggered && typeof alert.triggered === 'object'
    ? Object.keys(alert.triggered).filter(key => alert.triggered[key])
    : [];
  const triggeredCount = matchedAlerts.length + (alert && alert.status === 'triggered' && !matchedAlerts.length ? 1 : 0);
  const riskItems = Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory : [];
  const latestRisk = latestPortfolioRiskAnalysis();
  const riskLevel = latestRisk && latestRisk.structured ? (latestRisk.structured.risk_level || latestRisk.structured.overall_risk || '') : '';
  const quality = latestSourceHealthState && latestSourceHealthState.quality ? latestSourceHealthState.quality : null;
  return [
    {
      label: '近7日',
      value: recentTransactions.length + ' 笔',
      meta: transactions.length ? '共 ' + transactions.length + ' 笔流水' : '暂无流水',
    },
    {
      label: '触发预警',
      value: triggeredCount ? triggeredCount + ' 条' : '无触发',
      meta: triggeredConditions.length ? triggeredConditions.length + ' 个条件命中' : portfolioAlertStatusLabel(alert),
      className: triggeredCount ? 'up' : '',
    },
    {
      label: '风险分析',
      value: riskItems.length ? riskItems.length + ' 条' : '暂无分析',
      meta: riskLevel || (latestRisk ? '最近 ' + (latestRisk.analysis_time || '--') : '可从风险分析入口生成'),
    },
    {
      label: '数据质量',
      value: quality && quality.score != null ? quality.score + ' 分' : '--',
      meta: sourceQualityText(quality) || '等待数据源检查',
    },
  ];
}

function portfolioReviewTimelineEventLabel(type) {
  if (type === 'transaction') return '流水';
  if (type === 'alert') return '预警';
  if (type === 'risk') return '风险';
  if (type === 'quality') return '数据';
  return '线索';
}

function buildPortfolioReviewTimeline(item, alert, transactions) {
  const events = [];
  transactions.forEach(transaction => {
    const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
    events.push({
      type: 'transaction',
      time: transaction.trade_date || transaction.updated_at || transaction.created_at || '未标日期',
      sortTime: portfolioReviewTimestampValue(transaction.trade_date || transaction.updated_at || transaction.created_at),
      title: display.typeText + ' · ' + (transaction.name || item.name || '未命名流水'),
      text: [
        formatPortfolioMoney(transaction.price, display.mode),
        display.quantityText,
        display.valueText,
        Number(transaction.fee) > 0 ? '手续费 ' + formatPortfolioMoney(transaction.fee, display.mode) : '',
        transaction.note || '',
      ].filter(Boolean).join(' · '),
    });
  });
  if (alert) {
    const thresholds = [
      portfolioAlertThresholdText('止盈', alert.take_profit_price, item.mode || 'rmb', ''),
      portfolioAlertThresholdText('止损', alert.stop_loss_price, item.mode || 'rmb', ''),
      portfolioAlertThresholdText('浮盈', alert.profit_percent, item.mode || 'rmb', '%'),
      portfolioAlertThresholdText('浮亏', alert.loss_percent, item.mode || 'rmb', '%'),
      portfolioAlertThresholdText('近成本', alert.near_cost_percent, item.mode || 'rmb', '%'),
    ].filter(Boolean);
    events.push({
      type: 'alert',
      time: alert.last_triggered_at || '当前设置',
      sortTime: portfolioReviewTimestampValue(alert.last_triggered_at),
      title: portfolioAlertStatusLabel(alert) + ' · 持仓提醒',
      text: thresholds.length ? thresholds.join(' · ') : '未设置价格条件',
    });
  }
  portfolioAlertEntriesForPosition(item).slice(-5).forEach(entry => {
    events.push({
      type: 'alert',
      time: entry.timestamp || entry.time || '--',
      sortTime: portfolioReviewTimestampValue(entry.timestamp),
      title: alertLevelLabel(entry.type) + ' · 告警记录',
      text: entry.message || '达到预警条件',
    });
  });
  (Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory.slice(-2) : []).forEach(entry => {
    const structured = entry.structured || {};
    const firstLine = String(entry.content || '').split('\n').find(Boolean) || '风险分析记录';
    events.push({
      type: 'risk',
      time: entry.analysis_time || '--',
      sortTime: portfolioReviewTimestampValue(entry.analysis_time),
      title: '风险分析' + (structured.risk_level ? ' · ' + structured.risk_level : ''),
      text: firstLine,
    });
  });
  const quality = latestSourceHealthState && latestSourceHealthState.quality ? latestSourceHealthState.quality : null;
  if (quality) {
    const reasons = Array.isArray(quality.reasons) ? quality.reasons.filter(Boolean).join('；') : '';
    events.push({
      type: 'quality',
      time: latestData && latestData.time ? latestData.time : '当前',
      sortTime: Date.now(),
      title: '行情质量 · ' + (quality.label || quality.level || '--'),
      text: quality.summary || reasons || sourceQualityText(quality),
    });
  }
  return events.sort((left, right) => right.sortTime - left.sortTime);
}

function renderPortfolioReviewSummaryStrip(summary) {
  return '<div class="portfolio-detail-review-summary">' + summary.map(item => [
    '<div class="portfolio-detail-review-stat">',
    '<div class="portfolio-detail-review-stat-label">' + escapeHtml(item.label) + '</div>',
    '<div class="portfolio-detail-review-stat-value ' + (item.className || '') + '">' + escapeHtml(item.value) + '</div>',
    '<div class="portfolio-detail-review-stat-meta">' + escapeHtml(item.meta) + '</div>',
    '</div>',
  ].join('')).join('') + '</div>';
}

function renderPortfolioReviewTimeline(events) {
  if (!events.length) return '<div class="portfolio-detail-empty">暂无复盘线索</div>';
  return [
    '<div class="portfolio-review-timeline">',
    events.map(event => [
      '<div class="portfolio-review-event">',
      '<div class="portfolio-review-event-time">' + escapeHtml(String(event.time || '--').replace('T', ' ').slice(0, 16)) + '</div>',
      '<div class="portfolio-review-event-main">',
      '<div class="portfolio-review-event-title"><span class="portfolio-review-event-type">' + escapeHtml(portfolioReviewTimelineEventLabel(event.type)) + '</span>' + escapeHtml(event.title || '复盘线索') + '</div>',
      '<div class="portfolio-review-event-text">' + escapeHtml(event.text || '暂无详情') + '</div>',
      '</div>',
      '</div>',
    ].join('')).join(''),
    '</div>',
  ].join('');
}

function renderPortfolioRelatedTransactionsTable(item, transactions) {
  if (!transactions.length) return '<div class="portfolio-detail-empty">暂无关联流水</div>';
  const rows = transactions.slice(0, 5).map(transaction => {
    const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
    return [
      '<div class="portfolio-related-row">',
      '<span>' + escapeHtml(transaction.trade_date || '未标日期') + '</span>',
      '<span><span class="portfolio-transaction-type ' + display.typeClass + '">' + escapeHtml(display.typeText) + '</span></span>',
      '<span>' + escapeHtml(formatPortfolioMoney(transaction.price, display.mode)) + '</span>',
      '<span>' + escapeHtml(display.quantityText) + '</span>',
      '<span class="' + portfolioPnlClass(transaction.realized_pnl) + '">' + escapeHtml(display.valueText) + '</span>',
      '</div>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-related-table">',
    '<div class="portfolio-related-row head"><span>日期</span><span>类型</span><span>成交价</span><span>数量</span><span>结果</span></div>',
    rows,
    transactions.length > 5 ? '<div class="portfolio-detail-more">还有 ' + escapeHtml(String(transactions.length - 5)) + ' 条流水</div>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioPositionReview(item, alert, transactions) {
  const summary = buildPortfolioReviewSummary(item, alert, transactions);
  const events = buildPortfolioReviewTimeline(item, alert, transactions);
  const positionId = escapeHtml(item.id);
  return [
    '<div class="portfolio-detail-panel portfolio-detail-review-panel">',
    renderPortfolioReviewSummaryStrip(summary),
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-section-title">复盘线索</div>',
    renderPortfolioReviewTimeline(events),
    '</div>',
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-section-title">关联流水</div>',
    renderPortfolioRelatedTransactionsTable(item, transactions),
    '</div>',
    '<div class="portfolio-detail-action-row">',
    '<button class="btn-set" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'buy\')">新增流水</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="openPortfolioAlertEditor(\'' + positionId + '\')">设置提醒</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="exportPortfolioPositionReview(\'' + positionId + '\')">导出复盘</button>',
    '</div>',
    '</div>',
  ].join('');
}

function portfolioReviewSafeFilename(value) {
  return String(value || 'position').trim().replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'position';
}

function portfolioPositionReviewMarkdown(item, alert, transactions) {
  const mode = item.mode || 'rmb';
  const summary = buildPortfolioReviewSummary(item, alert, transactions);
  const events = buildPortfolioReviewTimeline(item, alert, transactions);
  const totalPnl = item.total_pnl != null ? item.total_pnl : item.pnl;
  const lines = [
    '# 持仓复盘',
    '',
    '## 持仓',
    '- 名称：' + (item.name || '未命名持仓'),
    '- 单位：' + portfolioModeLabel(mode),
    '- 数量：' + formatPortfolioNumber(item.quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode),
    '- 当前价：' + (item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode)),
    '- 平均成本：' + formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode),
    '- 合计盈亏：' + formatPortfolioSignedMoney(totalPnl, mode),
    '',
    '## 摘要',
    ...summary.map(item => '- ' + item.label + '：' + item.value + '（' + item.meta + '）'),
    '',
    '## 复盘线索',
    ...(events.length ? events.map(event => '- ' + String(event.time || '--') + ' [' + portfolioReviewTimelineEventLabel(event.type) + '] ' + (event.title || '') + '：' + (event.text || '')) : ['- 暂无复盘线索']),
    '',
    '## 关联流水',
    ...(transactions.length ? transactions.map(transaction => {
      const display = portfolioTransactionDisplay(transaction, mode);
      return '- ' + (transaction.trade_date || '未标日期') + ' ' + display.typeText + ' ' + formatPortfolioMoney(transaction.price, display.mode) + ' × ' + display.quantityText + '，' + display.valueText;
    }) : ['- 暂无关联流水']),
  ];
  return lines.join('\n');
}

function exportPortfolioPositionReview(positionId) {
  const item = (portfolioState.items || []).find(entry => entry.id === positionId);
  if (!item) {
    setPortfolioStatus('未找到持仓，无法导出复盘。', 'fail');
    return;
  }
  const alert = portfolioAlertForPosition(item.id);
  const transactions = portfolioTransactionsForPosition(item.id);
  const filename = 'GoldMonitor-' + portfolioReviewSafeFilename(item.name || item.id) + '-review.md';
  downloadText(filename, portfolioPositionReviewMarkdown(item, alert, transactions), 'text/markdown;charset=utf-8');
  setPortfolioStatus('已导出当前持仓复盘。', 'ok');
}

function renderPortfolioPositionDetail(item) {
  const mode = item.mode || 'rmb';
  const quantityDigits = mode === 'usd' ? 4 : 2;
  const quantityText = formatPortfolioNumber(item.quantity, quantityDigits) + ' ' + portfolioQuantityUnit(mode);
  const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode);
  const totalPnl = item.total_pnl != null ? item.total_pnl : item.pnl;
  const pnlClass = portfolioPnlClass(totalPnl);
  const status = item.portfolio_status || item.valuation_status || '';
  const alert = portfolioAlertForPosition(item.id);
  const transactions = portfolioTransactionsForPosition(item.id);
  const activeView = ['overview', 'transactions', 'alert', 'review'].includes(portfolioDetailView) ? portfolioDetailView : 'review';
  const bodyHtml = activeView === 'overview'
    ? renderPortfolioDetailOverview(item, alert, transactions)
    : activeView === 'transactions'
      ? renderPortfolioDetailTransactions(item, transactions)
      : activeView === 'alert'
        ? renderPortfolioDetailAlert(item, alert)
        : renderPortfolioPositionReview(item, alert, transactions);
  return [
    '<div class="portfolio-detail">',
    '<div class="portfolio-detail-focus">',
    '<div class="portfolio-detail-focus-main">',
    '<div class="portfolio-detail-focus-head">',
    '<div class="portfolio-detail-focus-title">' + escapeHtml(item.name || '未命名持仓') + '</div>',
    '<span class="alert-rule-state ' + portfolioStatusClass(status) + '">' + escapeHtml(portfolioStatusLabel(status)) + '</span>',
    renderPortfolioDetailActions(item),
    '</div>',
    '<div class="portfolio-detail-focus-meta">' + escapeHtml([portfolioModeLabel(mode), quantityText, '当前价 ' + currentPrice, item.last_trade_date ? '最近 ' + item.last_trade_date : ''].filter(Boolean).join(' · ')) + '</div>',
    '</div>',
    '<div class="portfolio-detail-focus-value ' + pnlClass + '">',
    '<strong>' + escapeHtml(formatPortfolioSignedMoney(totalPnl, mode)) + '</strong>',
    '<span>合计盈亏</span>',
    '</div>',
    '</div>',
    renderPortfolioDetailTabs(activeView),
    bodyHtml,
    '</div>',
  ].join('');
}

function renderPortfolioPositions(box) {
  const sourceItems = Array.isArray(portfolioState.items) ? portfolioState.items : [];
  const items = filteredPortfolioPositions();
  const parts = [];
  if (activePortfolioPositionId === 'new') {
    parts.push([
      '<div class="portfolio-item expanded">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">新增持仓</div>',
      '<div class="portfolio-meta">保存后按当前行情估值</div>',
      '</div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioEditor({ id: 'new', name: '', mode: currentMode, entry_price: '', quantity: '', entry_date: '', note: '' }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activePortfolioPositionId !== 'new') {
    parts.push('<div class="portfolio-empty">' + (sourceItems.length ? '没有匹配的持仓' : '暂无持仓') + '</div>');
  }
  parts.push(...items.map(item => {
    const cls = [
      'portfolio-item',
      activePortfolioPositionId === item.id || activePortfolioDetailId === item.id ? 'expanded' : '',
    ].filter(Boolean).join(' ');
    const mode = item.mode || 'rmb';
    const quantity = formatPortfolioNumber(item.quantity, 2);
    const unit = portfolioQuantityUnit(mode);
    const averageCost = formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode);
    const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode);
    const valuationLabel = portfolioValuationLabel(item);
    const portfolioStatus = item.portfolio_status || item.valuation_status || '';
    const pnlClass = portfolioPnlClass(item.total_pnl != null ? item.total_pnl : item.pnl);
    const metaParts = [
      portfolioModeLabel(mode),
      quantity === '--' ? '' : quantity + ' ' + unit,
      averageCost === '--' ? '' : '均价 ' + averageCost,
      '当前价 ' + currentPrice,
      item.last_trade_date ? '最近 ' + item.last_trade_date : '',
      item.note || '',
    ].filter(Boolean);
    return [
      '<div class="' + cls + '">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">' + escapeHtml((item.name || '未命名持仓') + ' · ' + valuationLabel) + '</div>',
      '<div class="portfolio-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
      '<div class="portfolio-meta portfolio-pnl ' + pnlClass + '">未实现 ' + escapeHtml(formatPortfolioMoney(item.unrealized_pnl != null ? item.unrealized_pnl : item.pnl, mode)) + ' · 已实现 ' + escapeHtml(formatPortfolioMoney(item.realized_pnl, mode)) + ' · 合计 ' + escapeHtml(formatPortfolioMoney(item.total_pnl, mode)) + '</div>',
      '</div>',
      '<div class="portfolio-actions">',
      '<span class="alert-rule-state ' + portfolioStatusClass(portfolioStatus) + '">' + escapeHtml(portfolioStatusLabel(portfolioStatus)) + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActivePortfolioDetail(\'' + escapeHtml(item.id) + '\')">' + (activePortfolioDetailId === item.id ? '收起' : '详情') + '</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">买入</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'sell\')">卖出</button>',
      '</div>',
      activePortfolioDetailId === item.id ? renderPortfolioPositionDetail(item) : '',
      activePortfolioPositionId === item.id ? buildPortfolioEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function renderPortfolioTransactions(box) {
  const sourceTransactions = Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [];
  const transactions = filteredPortfolioTransactions();
  const parts = [];
  if (activePortfolioTransactionId === 'new') {
    parts.push([
      '<div class="portfolio-item expanded">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">新增流水</div>',
      '<div class="portfolio-meta">买入会更新平均成本，卖出会计算已实现盈亏</div>',
      '</div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioTransactionEditor({ id: 'new', type: 'buy', mode: currentMode, fee: '0' }),
      '</div>',
    ].join(''));
  }
  if (!transactions.length && activePortfolioTransactionId !== 'new') {
    parts.push('<div class="portfolio-empty">' + (sourceTransactions.length ? '没有匹配的流水' : '暂无流水') + '</div>');
  }
  parts.push(...transactions.map(item => {
    const cls = [
      'portfolio-item',
      activePortfolioTransactionId === item.id ? 'expanded' : '',
    ].filter(Boolean).join(' ');
    const mode = item.mode || 'rmb';
    const typeText = item.type === 'sell' ? '卖出' : '买入';
    const typeClass = item.type === 'sell' ? 'sell' : 'buy';
    const realizedText = item.type === 'sell' ? ' · 已实现 ' + formatPortfolioMoney(item.realized_pnl, mode) : '';
    const metaParts = [
      portfolioModeLabel(mode),
      formatPortfolioMoney(item.price, mode),
      formatPortfolioNumber(item.quantity, 4) + ' ' + portfolioQuantityUnit(mode),
      Number(item.fee) > 0 ? '手续费 ' + formatPortfolioMoney(item.fee, mode) : '',
      item.trade_date || '',
      item.note || '',
    ].filter(Boolean);
    return [
      '<div class="' + cls + '">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line"><span class="portfolio-transaction-type ' + typeClass + '">' + escapeHtml(typeText) + '</span> ' + escapeHtml(item.name || '未命名流水') + escapeHtml(realizedText) + '</div>',
      '<div class="portfolio-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
      '</div>',
      '<div class="portfolio-actions">',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActivePortfolioTransaction(\'' + escapeHtml(item.id) + '\')">编辑</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="deletePortfolioTransaction(\'' + escapeHtml(item.id) + '\')">删除</button>',
      '</div>',
      activePortfolioTransactionId === item.id ? buildPortfolioTransactionEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function buildPortfolioTransactionEditor(item) {
  const target = portfolioTransactionDraftFor(item);
  const id = target.id;
  const escapedId = escapeHtml(id);
  const draftInputAttr = ' oninput="capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const draftChangeAttr = ' onchange="capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const modeChangeAttr = ' onchange="capturePortfolioTransactionDraft(\'' + escapedId + '\'); renderPortfolio()"';
  const positionChangeAttr = ' onchange="syncPortfolioTransactionPosition(\'' + escapedId + '\'); capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const type = target.type || 'buy';
  const mode = target.mode || currentMode;
  const positionOptions = buildPortfolioPositionOptions(target.position_id);
  return [
    '<div class="portfolio-editor portfolio-transaction-editor">',
    '<div class="portfolio-fields portfolio-transaction-fields">',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionType_' + escapedId + '">类型</label>',
    '<select id="portfolioTransactionType_' + escapedId + '"' + draftChangeAttr + '>',
    '<option value="buy"' + (type === 'buy' ? ' selected' : '') + '>买入</option>',
    '<option value="sell"' + (type === 'sell' ? ' selected' : '') + '>卖出</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionPositionId_' + escapedId + '">关联持仓</label>',
    '<select id="portfolioTransactionPositionId_' + escapedId + '"' + positionChangeAttr + '>',
    '<option value="">新持仓</option>',
    positionOptions,
    '</select>',
    '</div>',
    '<div class="portfolio-field portfolio-name">',
    '<label for="portfolioTransactionName_' + escapedId + '">名称</label>',
    '<input id="portfolioTransactionName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.name || '') + '" placeholder="例如 金条"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionMode_' + escapedId + '">单位</label>',
    '<select id="portfolioTransactionMode_' + escapedId + '"' + modeChangeAttr + '>',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionPrice_' + escapedId + '">成交价</label>',
    '<input id="portfolioTransactionPrice_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(target.price || '') + '" placeholder="输入价格"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionQuantity_' + escapedId + '">数量（' + escapeHtml(portfolioQuantityUnit(mode)) + '）</label>',
    '<input id="portfolioTransactionQuantity_' + escapedId + '" type="number" step="0.0001" value="' + escapeHtml(target.quantity || '') + '" placeholder="输入数量"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionFee_' + escapedId + '">手续费</label>',
    '<input id="portfolioTransactionFee_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(target.fee == null ? '0' : target.fee) + '" placeholder="0"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionTradeDate_' + escapedId + '">交易日期</label>',
    '<input id="portfolioTransactionTradeDate_' + escapedId + '" type="date" value="' + escapeHtml(target.trade_date || '') + '"' + draftChangeAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioTransactionNote_' + escapedId + '">备注</label>',
    '<textarea id="portfolioTransactionNote_' + escapedId + '" maxlength="200" rows="2" placeholder="例如 账户或来源"' + draftInputAttr + '>' + escapeHtml(target.note || '') + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-editor-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioTransaction(\'' + escapedId + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActivePortfolioTransaction(\'' + escapedId + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function buildPortfolioPositionOptions(selectedId) {
  const items = Array.isArray(portfolioState.items) ? portfolioState.items : [];
  return items.map(item => {
    const selected = item.id === selectedId ? ' selected' : '';
    return '<option value="' + escapeHtml(item.id) + '"' + selected + '>' + escapeHtml((item.name || '未命名持仓') + ' · ' + portfolioModeLabel(item.mode)) + '</option>';
  }).join('');
}

function syncPortfolioTransactionPosition(id) {
  const key = portfolioTransactionDraftKey(id);
  const selectedId = portfolioTransactionInputValue(key, 'PositionId');
  const item = (portfolioState.items || []).find(entry => entry.id === selectedId);
  if (!item) {
    capturePortfolioTransactionDraft(id);
    return;
  }
  const nameInput = document.getElementById('portfolioTransactionName_' + key);
  const modeInput = document.getElementById('portfolioTransactionMode_' + key);
  const priceInput = document.getElementById('portfolioTransactionPrice_' + key);
  const previousMode = modeInput ? modeInput.value || currentMode : currentMode;
  const previousDefaultPrice = defaultPortfolioTransactionPrice(previousMode);
  const nextMode = item.mode || currentMode;
  if (nameInput && !nameInput.value) nameInput.value = item.name || '';
  if (priceInput && (!priceInput.value || priceInput.value === previousDefaultPrice)) priceInput.value = defaultPortfolioTransactionPrice(nextMode);
  if (modeInput) modeInput.value = nextMode;
  capturePortfolioTransactionDraft(id);
}

function setPortfolioView(view) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  portfolioView = ['positions', 'transactions', 'review'].includes(view) ? view : 'positions';
  if (portfolioView !== 'positions') {
    activePortfolioDetailId = null;
    activePortfolioAlertEditorId = null;
    portfolioDetailView = 'review';
  }
  renderPortfolio();
  if (portfolioView === 'review') requestPortfolioAnalytics(false);
}

function setActivePortfolioDetail(id) {
  captureActivePortfolioAlertDraft();
  const nextId = activePortfolioDetailId === id ? null : id;
  activePortfolioDetailId = nextId;
  if (activePortfolioDetailId) {
    portfolioView = 'positions';
    portfolioDetailView = 'review';
  }
  if (activePortfolioDetailId !== id) activePortfolioAlertEditorId = null;
  if (activePortfolioDetailId && activePortfolioAlertEditorId && activePortfolioAlertEditorId !== activePortfolioDetailId) {
    activePortfolioAlertEditorId = null;
  }
  renderPortfolio();
}

function setPortfolioDetailView(view) {
  captureActivePortfolioAlertDraft();
  portfolioDetailView = ['overview', 'transactions', 'alert', 'review'].includes(view) ? view : 'review';
  renderPortfolio();
}

function togglePortfolioAlertEditor(positionId) {
  captureActivePortfolioAlertDraft();
  activePortfolioAlertEditorId = activePortfolioAlertEditorId === positionId ? null : positionId;
  activePortfolioDetailId = positionId;
  portfolioDetailView = 'alert';
  renderPortfolio();
}

function openPortfolioAlertEditor(positionId) {
  captureActivePortfolioAlertDraft();
  activePortfolioDetailId = positionId;
  portfolioDetailView = 'alert';
  activePortfolioAlertEditorId = positionId;
  renderPortfolio();
}

function setActivePortfolioPosition(id) {
  captureActivePortfolioDraft();
  if (activePortfolioPositionId === id) {
    clearPortfolioDraft(id);
    activePortfolioPositionId = null;
  } else {
    activePortfolioPositionId = id;
  }
  renderPortfolio();
}

function setActivePortfolioTransaction(id, defaults) {
  captureActivePortfolioTransactionDraft();
  if (activePortfolioTransactionId === id && !defaults) {
    clearPortfolioTransactionDraft(id);
    activePortfolioTransactionId = null;
  } else {
    activePortfolioTransactionId = id;
    if (defaults && typeof defaults === 'object') {
      portfolioTransactionDrafts[portfolioTransactionDraftKey(id)] = Object.assign({}, defaults);
    }
  }
  portfolioView = 'transactions';
  renderPortfolio();
}

function startPortfolioTransactionForPosition(positionId, type) {
  const item = (portfolioState.items || []).find(entry => entry.id === positionId);
  let defaults;
  if (item) {
    const mode = item.mode || currentMode;
    defaults = {
      position_id: item.id,
      name: item.name || '',
      type: type === 'sell' ? 'sell' : 'buy',
      mode: mode,
      price: defaultPortfolioTransactionPrice(mode),
      quantity: '',
      fee: '0',
      trade_date: portfolioTransactionToday(),
      note: '',
    };
  } else {
    defaults = {
      type: type === 'sell' ? 'sell' : 'buy',
      mode: currentMode,
      fee: '0',
      price: defaultPortfolioTransactionPrice(currentMode),
      trade_date: portfolioTransactionToday(),
    };
  }
  setActivePortfolioTransaction('new', defaults);
}

function portfolioInputValue(id, field) {
  const el = document.getElementById('portfolio' + field + '_' + id);
  return el ? el.value : '';
}

function savePortfolioPosition(id) {
  const isNew = id === 'new';
  const payload = {
    name: portfolioInputValue(id, 'Name').trim(),
    mode: portfolioInputValue(id, 'Mode').trim(),
    entry_price: portfolioInputValue(id, 'EntryPrice').trim(),
    quantity: portfolioInputValue(id, 'Quantity').trim(),
    entry_date: portfolioInputValue(id, 'EntryDate').trim(),
    note: portfolioInputValue(id, 'Note').trim(),
  };
  if (!payload.name) {
    setPortfolioStatus('请输入持仓名称。', 'fail');
    return;
  }
  const entryPrice = Number(payload.entry_price);
  if (!Number.isFinite(entryPrice) || entryPrice <= 0) {
    setPortfolioStatus('请输入有效的持仓价格。', 'fail');
    return;
  }
  const quantity = Number(payload.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    setPortfolioStatus('请输入有效的持仓数量。', 'fail');
    return;
  }
  if (payload.mode !== 'rmb' && payload.mode !== 'usd') {
    setPortfolioStatus('持仓单位无效。', 'fail');
    return;
  }
  if (!isNew) payload.id = id;
  payload.entry_price = entryPrice;
  payload.quantity = quantity;
  setPortfolioStatus('正在保存持仓...', '');
  pendingPortfolioSave = { kind: 'position', id };
  socket.emit('save_portfolio_position', payload);
}

function deletePortfolioPosition(id) {
  setPortfolioStatus('正在删除持仓...', '');
  socket.emit('delete_portfolio_position', { id });
  clearPortfolioDraft(id);
  clearPortfolioAlertDraft(id);
  if (activePortfolioPositionId === id) activePortfolioPositionId = null;
  if (activePortfolioDetailId === id) activePortfolioDetailId = null;
  if (activePortfolioAlertEditorId === id) activePortfolioAlertEditorId = null;
}

function savePortfolioAlert(positionId) {
  capturePortfolioAlertDraft(positionId);
  const draft = portfolioAlertDrafts[portfolioAlertDraftKey(positionId)] || {};
  const payload = {
    position_id: positionId,
    enabled: draft.enabled !== false,
    take_profit_price: draft.take_profit_price,
    stop_loss_price: draft.stop_loss_price,
    profit_percent: draft.profit_percent,
    loss_percent: draft.loss_percent,
    near_cost_percent: draft.near_cost_percent,
    note: draft.note,
  };
  const existing = portfolioAlertForPosition(positionId);
  if (existing && existing.id) payload.id = existing.id;
  setPortfolioStatus('正在保存持仓提醒...', '');
  pendingPortfolioSave = { kind: 'alert', id: positionId };
  socket.emit('save_portfolio_alert', payload);
}

function resetPortfolioAlert(alertId) {
  setPortfolioStatus('正在重置持仓提醒...', '');
  socket.emit('reset_portfolio_alert', { id: alertId });
}

function deletePortfolioAlert(alertId, positionId) {
  setPortfolioStatus('正在清空持仓提醒...', '');
  socket.emit('delete_portfolio_alert', { id: alertId });
  clearPortfolioAlertDraft(positionId);
  if (activePortfolioAlertEditorId === positionId) activePortfolioAlertEditorId = null;
}

function savePortfolioTransaction(id) {
  const isNew = id === 'new';
  const payload = {
    position_id: portfolioTransactionInputValue(id, 'PositionId').trim(),
    name: portfolioTransactionInputValue(id, 'Name').trim(),
    type: portfolioTransactionInputValue(id, 'Type').trim(),
    mode: portfolioTransactionInputValue(id, 'Mode').trim(),
    price: portfolioTransactionInputValue(id, 'Price').trim(),
    quantity: portfolioTransactionInputValue(id, 'Quantity').trim(),
    fee: portfolioTransactionInputValue(id, 'Fee').trim() || '0',
    trade_date: portfolioTransactionInputValue(id, 'TradeDate').trim(),
    note: portfolioTransactionInputValue(id, 'Note').trim(),
  };
  if (!payload.name) {
    setPortfolioStatus('请输入流水名称。', 'fail');
    return;
  }
  if (payload.type !== 'buy' && payload.type !== 'sell') {
    setPortfolioStatus('流水类型无效。', 'fail');
    return;
  }
  if (payload.type === 'sell' && !payload.position_id) {
    setPortfolioStatus('请选择要卖出的持仓。', 'fail');
    return;
  }
  if (payload.mode !== 'rmb' && payload.mode !== 'usd') {
    setPortfolioStatus('持仓单位无效。', 'fail');
    return;
  }
  const price = Number(payload.price);
  if (!Number.isFinite(price) || price <= 0) {
    setPortfolioStatus('请输入有效的成交价格。', 'fail');
    return;
  }
  const quantity = Number(payload.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    setPortfolioStatus('请输入有效的成交数量。', 'fail');
    return;
  }
  const fee = Number(payload.fee);
  if (!Number.isFinite(fee) || fee < 0) {
    setPortfolioStatus('请输入有效的手续费。', 'fail');
    return;
  }
  if (!isNew) payload.id = id;
  if (!payload.position_id) delete payload.position_id;
  payload.price = price;
  payload.quantity = quantity;
  payload.fee = fee;
  setPortfolioStatus('正在保存流水...', '');
  pendingPortfolioSave = { kind: 'transaction', id };
  socket.emit('save_portfolio_transaction', payload);
}

function deletePortfolioTransaction(id) {
  setPortfolioStatus('正在删除流水...', '');
  socket.emit('delete_portfolio_transaction', { id });
  clearPortfolioTransactionDraft(id);
  if (activePortfolioTransactionId === id) activePortfolioTransactionId = null;
}

function exportPortfolio(kind) {
  const exportKind = ['transactions', 'review'].includes(kind) ? kind : 'positions';
  const statusText = exportKind === 'review'
    ? '正在导出复盘...'
    : exportKind === 'transactions' ? '正在导出流水...' : '正在导出持仓...';
  setPortfolioStatus(statusText, '');
  socket.emit('export_portfolio', { kind: exportKind });
}

function buildPortfolioTransactionTemplateCsv() {
  const lines = [
    PORTFOLIO_TRANSACTION_IMPORT_FIELDS.join(','),
    'transaction-demo-1,position-demo,buy,示例金条,rmb,580,10,0,2026-06-01,模板示例',
    'transaction-demo-2,position-demo,sell,示例金条,rmb,620,2,0,2026-06-15,可删除示例行',
  ];
  return lines.join('\n') + '\n';
}

function downloadPortfolioTransactionTemplate() {
  const blob = new Blob([buildPortfolioTransactionTemplateCsv()], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'goldmonitor_portfolio_transactions_template.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setPortfolioStatus('CSV 模板已生成。', 'ok');
}

function parsePortfolioCsvRows(csvText) {
  const text = String(csvText || '').replace(/^\ufeff/, '');
  if (!text.trim()) return { fields: [], rows: [], error: 'CSV 内容不能为空。' };
  const parsed = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"') {
      if (inQuotes && next === '"') {
        cell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      row.push(cell);
      cell = '';
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      row.push(cell);
      if (row.some(value => String(value || '').trim())) parsed.push(row);
      row = [];
      cell = '';
      if (char === '\r' && next === '\n') index += 1;
    } else {
      cell += char;
    }
  }
  if (inQuotes) return { fields: [], rows: [], error: 'CSV 引号未闭合。' };
  row.push(cell);
  if (row.some(value => String(value || '').trim())) parsed.push(row);
  if (!parsed.length) return { fields: [], rows: [], error: 'CSV 缺少表头。' };
  const fields = parsed[0].map(field => String(field || '').trim().replace(/^\ufeff/, ''));
  if (!fields.some(Boolean)) return { fields: [], rows: [], error: 'CSV 缺少表头。' };
  const rows = parsed.slice(1).map((values, index) => {
    const item = {};
    fields.forEach((field, fieldIndex) => {
      if (field) item[field] = values[fieldIndex] == null ? '' : String(values[fieldIndex]).trim();
    });
    return { rowNumber: index + 2, values: item };
  }).filter(item => Object.values(item.values).some(value => String(value || '').trim()));
  return { fields, rows, error: '' };
}

function portfolioImportSummary(rows) {
  const existingIds = new Set((Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [])
    .map(item => String(item.id || '').trim())
    .filter(Boolean));
  let overwrite = 0;
  rows.forEach(item => {
    const id = String(item.values.id || '').trim();
    if (id && existingIds.has(id)) overwrite += 1;
  });
  return {
    total: rows.length,
    overwrite,
    create: rows.length - overwrite,
    previewCount: Math.min(rows.length, 5),
  };
}

function portfolioImportRowErrors(rows) {
  const errors = [];
  rows.forEach(item => {
    const values = item.values || {};
    const rowNumber = item.rowNumber || '';
    const missing = PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS.filter(field => !String(values[field] || '').trim());
    if (missing.length) errors.push('第 ' + rowNumber + ' 行缺少字段: ' + missing.join(', '));
    if (values.type && !['buy', 'sell'].includes(values.type)) errors.push('第 ' + rowNumber + ' 行 type 必须为 buy 或 sell。');
    if (values.mode && !['rmb', 'usd'].includes(values.mode)) errors.push('第 ' + rowNumber + ' 行 mode 必须为 rmb 或 usd。');
    const price = Number(values.price);
    if (values.price && (!Number.isFinite(price) || price <= 0)) errors.push('第 ' + rowNumber + ' 行 price 必须大于 0。');
    const quantity = Number(values.quantity);
    if (values.quantity && (!Number.isFinite(quantity) || quantity <= 0)) errors.push('第 ' + rowNumber + ' 行 quantity 必须大于 0。');
    const fee = values.fee === '' || values.fee == null ? 0 : Number(values.fee);
    if (!Number.isFinite(fee) || fee < 0) errors.push('第 ' + rowNumber + ' 行 fee 不能小于 0。');
    if (values.trade_date && !/^\d{4}-\d{2}-\d{2}$/.test(values.trade_date)) errors.push('第 ' + rowNumber + ' 行 trade_date 必须为 YYYY-MM-DD。');
  });
  return errors.slice(0, 8);
}

function previewPortfolioImport(fileName, content) {
  const parsed = parsePortfolioCsvRows(content);
  const missingFields = PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS.filter(field => !parsed.fields.includes(field));
  const errors = [];
  if (parsed.error) errors.push(parsed.error);
  if (missingFields.length) errors.push('CSV 缺少必要字段: ' + missingFields.join(', '));
  if (!parsed.error && !parsed.rows.length) errors.push('CSV 没有可导入流水。');
  if (!parsed.error && !missingFields.length) errors.push(...portfolioImportRowErrors(parsed.rows));
  portfolioImportPreview = {
    fileName: fileName || '未命名 CSV',
    content: String(content || ''),
    fields: parsed.fields,
    rows: parsed.rows,
    summary: portfolioImportSummary(parsed.rows),
    errors,
    backendStatus: errors.length ? 'skip' : 'pending',
    backendMessage: errors.length ? '' : '正在复核完整持仓约束...',
    requestId: '',
  };
  renderPortfolioImportPreview();
  setPortfolioStatus(errors.length ? errors[0] : 'CSV 已读取，确认后导入。', errors.length ? 'fail' : 'ok');
  if (!errors.length) requestPortfolioImportBackendPreview();
}

function requestPortfolioImportBackendPreview() {
  if (!portfolioImportPreview || portfolioImportPreview.errors.length) return;
  portfolioImportPreviewRequestSeq += 1;
  const requestId = 'portfolio-import-preview-' + portfolioImportPreviewRequestSeq;
  portfolioImportPreview.requestId = requestId;
  portfolioImportPreview.backendStatus = 'pending';
  portfolioImportPreview.backendMessage = '正在复核完整持仓约束...';
  renderPortfolioImportPreview();
  socket.emit('preview_import_portfolio_transactions', {
    content: portfolioImportPreview.content,
    request_id: requestId,
  });
}

function applyPortfolioImportBackendPreview(data) {
  if (!portfolioImportPreview) return;
  const requestId = data && data.request_id ? String(data.request_id) : '';
  if (requestId && portfolioImportPreview.requestId && requestId !== portfolioImportPreview.requestId) return;
  if (data && data.ok) {
    portfolioImportPreview.backendStatus = 'ok';
    portfolioImportPreview.backendMessage = '后端复核通过。';
    portfolioImportPreview.summary = {
      total: Number(data.count) || 0,
      row_count: Number(data.row_count) || 0,
      valid_count: Number(data.valid_count) || 0,
      create: Number(data.create) || 0,
      overwrite: Number(data.overwrite) || 0,
      previewCount: portfolioImportPreview.summary ? portfolioImportPreview.summary.previewCount : 0,
    };
    portfolioImportPreview.errors = Array.isArray(data.errors) ? data.errors : [];
    portfolioImportPreview.warnings = Array.isArray(data.warnings) ? data.warnings : [];
    renderPortfolioImportPreview();
    setPortfolioStatus('CSV 复核通过，确认后导入。', 'ok');
    return;
  }
  const message = (data && data.message) || 'CSV 后端复核失败。';
  portfolioImportPreview.backendStatus = 'fail';
  portfolioImportPreview.backendMessage = message;
  portfolioImportPreview.errors = Array.isArray(data && data.errors) && data.errors.length ? data.errors : [message];
  portfolioImportPreview.warnings = Array.isArray(data && data.warnings) ? data.warnings : [];
  renderPortfolioImportPreview();
  setPortfolioStatus(message, 'fail');
}

function renderPortfolioImportPreview() {
  const box = document.getElementById('portfolioImportPreview');
  if (!box) return;
  if (!portfolioImportPreview) {
    box.innerHTML = '';
    box.classList.remove('show', 'fail');
    return;
  }
  const preview = portfolioImportPreview;
  const summary = preview.summary || { total: 0, row_count: 0, valid_count: 0, create: 0, overwrite: 0, previewCount: 0 };
  const rows = (preview.rows || []).slice(0, summary.previewCount || 0);
  const hasError = !!(preview.errors && preview.errors.length);
  const backendPending = preview.backendStatus === 'pending';
  const backendOk = preview.backendStatus === 'ok';
  const warnings = Array.isArray(preview.warnings) ? preview.warnings : [];
  box.classList.toggle('show', true);
  box.classList.toggle('fail', hasError);
  const errorHtml = hasError
    ? '<div class="portfolio-import-error">' + preview.errors.map(error => '<div>' + escapeHtml(error) + '</div>').join('') + '</div>'
    : '';
  const warningHtml = warnings.length
    ? '<div class="portfolio-import-preview-state">' + warnings.map(warning => escapeHtml(warning)).join('；') + '</div>'
    : '';
  const stateHtml = preview.backendMessage
    ? '<div class="portfolio-import-preview-state ' + escapeHtml(preview.backendStatus || '') + '">' + escapeHtml(preview.backendMessage) + '</div>'
    : '';
  const rowHtml = rows.map(item => {
    const values = item.values || {};
    const typeText = values.type === 'sell' ? '卖出' : values.type === 'buy' ? '买入' : values.type || '--';
    return [
      '<div class="portfolio-import-preview-row">',
      '<span>' + escapeHtml(values.trade_date || '--') + '</span>',
      '<span>' + escapeHtml(typeText) + '</span>',
      '<span>' + escapeHtml(values.name || '--') + '</span>',
      '<span>' + escapeHtml((values.quantity || '--') + ' / ' + (values.price || '--')) + '</span>',
      '</div>',
    ].join('');
  }).join('');
  box.innerHTML = [
    '<div class="portfolio-import-preview-head">',
    '<div><strong>CSV 导入预览</strong><span>' + escapeHtml(preview.fileName) + '</span></div>',
    '<button class="btn-clear-sm" type="button" onclick="cancelPortfolioImport()">取消</button>',
    '</div>',
    '<div class="portfolio-import-preview-grid">',
    '<div><span>总行数</span><strong>' + escapeHtml(String(summary.row_count || summary.total)) + '</strong></div>',
    '<div><span>有效</span><strong>' + escapeHtml(String(summary.valid_count || summary.total)) + '</strong></div>',
    '<div><span>新增</span><strong>' + escapeHtml(String(summary.create)) + '</strong></div>',
    '<div><span>覆盖</span><strong>' + escapeHtml(String(summary.overwrite)) + '</strong></div>',
    '</div>',
    stateHtml,
    warningHtml,
    errorHtml,
    '<div class="portfolio-import-preview-table">',
    '<div class="portfolio-import-preview-row head"><span>日期</span><span>类型</span><span>名称</span><span>数量/价格</span></div>',
    rowHtml || '<div class="portfolio-import-preview-empty">无可预览流水</div>',
    '</div>',
    '<div class="portfolio-import-actions">',
    '<button class="btn-clear-sm" type="button" onclick="downloadPortfolioTransactionTemplate()">下载模板</button>',
    !hasError && backendOk ? '<button class="btn-set" type="button" onclick="confirmPortfolioImport()">确认导入</button>' : '',
    backendPending ? '<button class="btn-clear-sm" type="button" disabled>复核中</button>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioImportBackup() {
  const box = document.getElementById('portfolioImportBackup');
  if (!box) return;
  const backup = normalizePortfolioImportBackup(portfolioState.import_backup);
  if (!backup.available) {
    box.innerHTML = '';
    box.classList.remove('show');
    return;
  }
  box.classList.add('show');
  const timeText = backup.imported_at ? backup.imported_at.replace('T', ' ') : '未知时间';
  box.innerHTML = [
    '<div class="portfolio-import-backup-head">',
    '<div><strong>最近 CSV 导入</strong><span>' + escapeHtml(timeText) + '</span></div>',
    '<button class="btn-clear-sm" type="button" onclick="undoPortfolioImport()">撤销导入</button>',
    '</div>',
    '<div class="portfolio-import-preview-grid">',
    '<div><span>导入</span><strong>' + escapeHtml(String(backup.count)) + '</strong></div>',
    '<div><span>新增</span><strong>' + escapeHtml(String(backup.create)) + '</strong></div>',
    '<div><span>覆盖</span><strong>' + escapeHtml(String(backup.overwrite)) + '</strong></div>',
    '</div>',
  ].join('');
}

function confirmPortfolioImport() {
  if (!portfolioImportPreview || portfolioImportPreview.errors.length || portfolioImportPreview.backendStatus !== 'ok') {
    setPortfolioStatus('请先选择并复核有效的 CSV 文件。', 'fail');
    return;
  }
  const content = portfolioImportPreview.content;
  setPortfolioStatus('正在导入流水...', '');
  portfolioImportPreview = null;
  renderPortfolioImportPreview();
  socket.emit('import_portfolio_transactions', { content });
}

function cancelPortfolioImport() {
  portfolioImportPreview = null;
  renderPortfolioImportPreview();
  const input = document.getElementById('portfolioImportFile');
  if (input) input.value = '';
  setPortfolioStatus('已取消 CSV 导入。', '');
}

function importPortfolioTransactions() {
  const input = document.getElementById('portfolioImportFile');
  if (!input) {
    setPortfolioStatus('未找到导入入口。', 'fail');
    return;
  }
  input.click();
}

function undoPortfolioImport() {
  setPortfolioStatus('正在撤销最近一次导入...', '');
  socket.emit('undo_portfolio_import');
}

function onPortfolioImportFile(input) {
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) return;
  if (file.size > 1024 * 1024) {
    setPortfolioStatus('CSV 文件不能超过 1MB。', 'fail');
    input.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const content = String(reader.result || '');
    if (!content.trim()) {
      setPortfolioStatus('CSV 内容不能为空。', 'fail');
      input.value = '';
      return;
    }
    previewPortfolioImport(file.name, content);
    input.value = '';
  };
  reader.onerror = () => {
    setPortfolioStatus('CSV 读取失败。', 'fail');
    input.value = '';
  };
  reader.readAsText(file, 'utf-8');
}
