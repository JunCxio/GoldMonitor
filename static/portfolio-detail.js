// ========== 持仓详情 ==========
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
  const transactionId = escapeHtml(transaction.id || '');
  const isEditing = activePortfolioTransactionId === transaction.id && activePortfolioTransactionDetailId === item.id;
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
    '<div class="portfolio-detail-transaction-side">',
    '<div class="portfolio-detail-transaction-value ' + portfolioPnlClass(transaction.realized_pnl) + '">' + escapeHtml(display.valueText) + '</div>',
    '<div class="portfolio-detail-transaction-actions">',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioTransaction(\'' + transactionId + '\')">' + (isEditing ? '取消编辑' : '编辑') + '</button>',
    '<button class="btn-clear-sm portfolio-detail-transaction-delete" type="button" onclick="deletePortfolioTransaction(\'' + transactionId + '\')">删除</button>',
    '</div>',
    '</div>',
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
  const activeTransaction = activePortfolioTransactionId === 'new'
    ? { id: 'new' }
    : transactions.find(transaction => transaction.id === activePortfolioTransactionId) || null;
  const transactionDraft = activeTransaction ? portfolioTransactionDraftFor(activeTransaction) : null;
  const transactionEditor = activePortfolioTransactionDetailId === item.id
    && transactionDraft
    ? buildPortfolioTransactionEditor(activeTransaction)
    : '';
  return [
    '<div class="portfolio-detail-panel">',
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-transactions-head">',
    '<div class="portfolio-detail-section-title">关联流水</div>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">新增流水</button>',
    '</div>',
    transactionEditor,
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
