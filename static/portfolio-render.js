// ========== 持仓渲染 ==========
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
  box.classList.remove('portfolio-investment-summary');
  if (portfolioView === 'investment') {
    renderPortfolioInvestmentSummary(box);
    return;
  }
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
  if (portfolioView === 'investment') {
    box.innerHTML = [
      '<label class="portfolio-control portfolio-search">',
      '<span>搜索</span>',
      '<input type="search" value="' + escapeHtml(portfolioSearch) + '" placeholder="计划或持仓名称" oninput="setPortfolioSearch(this.value)">',
      '</label>',
      '<div class="portfolio-controls-note portfolio-investment-note">应用关闭期间只补最近一期，并按恢复后的最新行情生成买入流水。</div>',
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
  if (portfolioView === 'investment') {
    renderPortfolioInvestments(box);
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
    primary.textContent = portfolioView === 'investment' ? '新增计划' : '新增流水';
    primary.onclick = portfolioView === 'investment'
      ? () => setActivePortfolioInvestmentPlan('new')
      : () => setActivePortfolioTransaction('new');
  }
}
