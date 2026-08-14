let todayOverviewState = null;
let todayOverviewLoading = false;
let todayOverviewRefreshTimer = null;
let todayOverviewLastFocused = null;
let todayOverviewShouldMarkViewed = false;
let todayOverviewItemIndex = {};
let todayOverviewAttentionFilter = 'all';
let todayOverviewPendingAction = null;
let todayOverviewActionFeedback = null;
let todayOverviewFeedbackTimer = null;

const TODAY_OVERVIEW_REFRESH_EVENTS = [
  'alert',
  'alert_log_cleared',
  'alert_log_status_updated',
  'alert_log_handling_updated',
  'alert_notification_resent',
  'alert_rules_updated',
  'portfolio_updated',
  'portfolio_investment_plans_updated',
  'risk_analysis_result',
  'risk_analysis_history_updated',
  'review_notes_updated',
  'source_health_updated',
  'background_task_status',
  'fetch_status',
  'price_update',
];

function todayOverviewIsOpen() {
  const backdrop = document.getElementById('todayOverviewBackdrop');
  return !!(backdrop && backdrop.classList.contains('show'));
}

function todayOverviewNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function todayOverviewCountText(value, unit) {
  const number = Math.max(0, Math.trunc(todayOverviewNumber(value)));
  return number + ' ' + unit;
}

function todayOverviewDate(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function todayOverviewTimeText(value, includeDate) {
  const date = todayOverviewDate(value);
  if (!date) return '--';
  const time = date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  if (!includeDate) return time;
  return (date.getMonth() + 1) + '月' + date.getDate() + '日 ' + time;
}

function todayOverviewMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const prefix = mode === 'usd' ? '$' : '¥';
  return prefix + number.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function todayOverviewSignedMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const sign = number > 0 ? '+' : '';
  return sign + todayOverviewMoney(number, mode);
}

function todayOverviewPnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return 'neutral';
  return number > 0 ? 'profit' : 'loss';
}

function todayOverviewSeverityLabel(severity) {
  return ({
    critical: '紧急',
    high: '高优先',
    medium: '需关注',
    low: '可复核',
  })[severity] || '待检查';
}

function todayOverviewReasonLabel(reason) {
  return ({
    unhandled: '未处理',
    notification_issue: '通知异常',
    waiting_data: '等待数据',
    orphaned: '关联失效',
    expired: '已过期',
    market_anomaly: '行情异常',
    market_stale: '行情过期',
    market_degraded: '行情降级',
    waiting_price: '等待行情',
    investment_error: '执行失败',
    investment_due: '等待执行',
    task_failure: '任务异常',
    task_delayed: '调度延迟',
  })[reason] || String(reason || '');
}

function todayOverviewActivityLabel(kind) {
  return ({
    alert: '警报',
    portfolio_transaction: '持仓流水',
    portfolio_investment: '持仓定投',
    risk_analysis: '风险分析',
    review_note: '复盘笔记',
  })[kind] || '活动';
}

function todayOverviewActionLabel(action) {
  return ({
    open_alert: '查看详情',
    open_rule: '编辑规则',
    open_market_status: '查看详情',
    open_portfolio_transaction: '查看流水',
    open_portfolio_investment: '查看计划',
    open_operations_task: '查看任务',
    open_risk_analysis: '查看分析',
    open_review_note: '查看笔记',
  })[action && action.kind] || '查看';
}

function todayOverviewFilterLabel(filter) {
  return ({
    all: '全部',
    alert: '警报',
    notification: '通知异常',
    rule: '规则',
    market: '行情',
    portfolio: '持仓',
    operations: '运维',
  })[filter] || '全部';
}

function todayOverviewFilterMatches(item, filter) {
  if (filter === 'all') return true;
  if (filter === 'notification') {
    return Array.isArray(item.reason_codes) && item.reason_codes.includes('notification_issue');
  }
  if (filter === 'portfolio') return item.kind === 'portfolio_investment';
  if (filter === 'operations') return item.kind === 'background_task';
  return item.kind === filter;
}

function setTodayOverviewStatus(message, type) {
  const status = document.getElementById('todayOverviewStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'today-overview-status' + (type ? ' ' + type : '');
}

function setTodayOverviewActionFeedback(message, type, autoClear) {
  todayOverviewActionFeedback = message ? { message, type: type || '' } : null;
  if (todayOverviewFeedbackTimer) clearTimeout(todayOverviewFeedbackTimer);
  todayOverviewFeedbackTimer = null;
  setTodayOverviewStatus(message, type);
  if (message && autoClear) {
    todayOverviewFeedbackTimer = setTimeout(() => {
      todayOverviewFeedbackTimer = null;
      todayOverviewActionFeedback = null;
      if (!todayOverviewPendingAction) setTodayOverviewStatus('', '');
    }, 4000);
  }
}

function renderTodayOverviewFeedback() {
  if (todayOverviewPendingAction) {
    setTodayOverviewStatus(todayOverviewPendingAction.message, 'loading');
  } else if (todayOverviewActionFeedback) {
    setTodayOverviewStatus(todayOverviewActionFeedback.message, todayOverviewActionFeedback.type);
  } else {
    setTodayOverviewStatus('', '');
  }
}

function updateTodayOverviewButton(summary) {
  const button = document.getElementById('todayOverviewButton');
  const badge = document.getElementById('todayOverviewCount');
  if (!button || !badge) return;
  const total = Math.max(0, Math.trunc(todayOverviewNumber(summary && summary.attention_total)));
  badge.textContent = total > 99 ? '99+' : String(total);
  badge.hidden = total === 0;
  button.classList.toggle('has-attention', total > 0);
  button.setAttribute('aria-label', total ? '打开今日概览，' + total + ' 项待处理' : '打开今日概览，当前无待处理事项');
}

function renderTodayOverviewSummary(summary) {
  const box = document.getElementById('todayOverviewSummary');
  if (!box) return;
  const items = [
    ['待处理', summary.attention_total, summary.attention_total ? 'attention' : 'clear'],
    ['今日活动', summary.activity_total, ''],
    ['上次查看后新增', summary.new_since_last_view, summary.new_since_last_view ? 'new' : ''],
    ['今日警报', summary.alerts_today, ''],
  ];
  box.innerHTML = items.map(item => [
    '<div class="today-overview-summary-item ' + escapeHtml(item[2]) + '">',
    '<span>' + escapeHtml(item[0]) + '</span>',
    '<strong>' + escapeHtml(String(todayOverviewNumber(item[1]))) + '</strong>',
    '</div>',
  ].join('')).join('');
}

function todayOverviewAttentionMeta(item) {
  const parts = [];
  if (item.occurred_today === false) parts.push('跨日保留');
  if (item.timestamp) parts.push(todayOverviewTimeText(item.timestamp, item.occurred_today === false));
  return parts.join(' · ') || '当前状态';
}

function renderTodayOverviewFilters(attention) {
  const box = document.getElementById('todayOverviewFilters');
  if (!box) return;
  const counts = attention && attention.filter_counts && typeof attention.filter_counts === 'object'
    ? attention.filter_counts
    : {};
  const filters = ['all', 'alert', 'notification', 'rule', 'market', 'portfolio', 'operations'];
  if (!filters.includes(todayOverviewAttentionFilter)) todayOverviewAttentionFilter = 'all';
  box.innerHTML = filters.map(filter => {
    const count = Math.max(0, Math.trunc(todayOverviewNumber(counts[filter])));
    const active = filter === todayOverviewAttentionFilter;
    return [
      '<button class="today-overview-filter' + (active ? ' active' : '') + '" type="button"',
      ' onclick="setTodayOverviewAttentionFilter(\'' + filter + '\')"',
      ' aria-pressed="' + String(active) + '">',
      '<span>' + escapeHtml(todayOverviewFilterLabel(filter)) + '</span>',
      '<strong>' + escapeHtml(String(count)) + '</strong>',
      '</button>',
    ].join('');
  }).join('');
}

function setTodayOverviewAttentionFilter(filter) {
  todayOverviewAttentionFilter = ['all', 'alert', 'notification', 'rule', 'market', 'portfolio', 'operations'].includes(filter) ? filter : 'all';
  if (todayOverviewState) renderTodayOverview(todayOverviewState);
}

function todayOverviewQuickActionButtons(item, token) {
  const actions = Array.isArray(item.quick_actions) ? item.quick_actions : [];
  const pending = todayOverviewPendingAction && todayOverviewPendingAction.itemId === item.id;
  const quickButtons = actions.map((action, index) => {
    const actionPending = pending && todayOverviewPendingAction.kind === action.kind;
    const label = actionPending ? '处理中…' : (action.label || '处理');
    return [
      '<button class="today-overview-item-action primary' + (actionPending ? ' is-pending' : '') + '" type="button"',
      ' onclick="runTodayOverviewQuickAction(\'' + token + '\', ' + index + ')"',
      todayOverviewPendingAction ? ' disabled' : '',
      '>' + escapeHtml(label) + '</button>',
    ].join('');
  }).join('');
  const detailButton = [
    '<button class="today-overview-item-action secondary" type="button"',
    ' onclick="activateTodayOverviewItem(\'' + token + '\')">',
    escapeHtml(todayOverviewActionLabel(item.action)),
    '</button>',
  ].join('');
  return '<div class="today-overview-item-actions">' + quickButtons + detailButton + '</div>';
}

function renderTodayOverviewAttention(items, total, truncated) {
  const list = document.getElementById('todayOverviewAttentionList');
  const count = document.getElementById('todayOverviewAttentionCount');
  if (!list || !count) return;
  count.textContent = todayOverviewCountText(total, '项');
  if (!items.length) {
    const filtered = todayOverviewAttentionFilter !== 'all';
    list.innerHTML = [
      '<div class="today-overview-empty clear">',
      '<strong>' + (filtered ? '当前分类没有待处理事项' : '当前没有待处理事项') + '</strong>',
      '<span>' + (filtered ? '可切换到其他分类继续检查。' : '警报、规则、行情、持仓计划和后台任务均无需人工介入。') + '</span>',
      '</div>',
    ].join('');
    return;
  }
  list.innerHTML = items.map((item, index) => {
    const token = 'attention-' + index;
    todayOverviewItemIndex[token] = item;
    const reasons = Array.isArray(item.reason_codes) ? item.reason_codes : [];
    const tags = reasons.map(reason => (
      '<span>' + escapeHtml(todayOverviewReasonLabel(reason)) + '</span>'
    )).join('');
    return [
      '<article class="today-overview-attention-item severity-' + escapeHtml(item.severity || 'low') + '">',
      '<div class="today-overview-attention-copy">',
      '<div class="today-overview-item-meta">',
      '<span class="today-overview-priority">' + escapeHtml(todayOverviewSeverityLabel(item.severity)) + '</span>',
      '<span>' + escapeHtml(todayOverviewAttentionMeta(item)) + '</span>',
      '</div>',
      '<h4>' + escapeHtml(item.title || '待处理事项') + '</h4>',
      '<p>' + escapeHtml(item.summary || '请检查相关状态。') + '</p>',
      tags ? '<div class="today-overview-reasons">' + tags + '</div>' : '',
      '</div>',
      todayOverviewQuickActionButtons(item, token),
      '</article>',
    ].join('');
  }).join('') + (truncated
    ? '<div class="today-overview-truncated">仅展示优先级最高的 ' + items.length + ' 项。</div>'
    : '');
}

function todayOverviewTransactionSummary(item) {
  const parts = [item.summary || '持仓变动'];
  const quantity = Number(item.quantity);
  if (Number.isFinite(quantity)) parts.push(quantity.toLocaleString('zh-CN', { maximumFractionDigits: 4 }) + ' 单位');
  const price = Number(item.price);
  if (Number.isFinite(price)) parts.push('成交价 ' + todayOverviewMoney(price, item.mode));
  return parts.join(' · ');
}

function todayOverviewActivitySummary(item) {
  if (item.kind === 'portfolio_transaction') return todayOverviewTransactionSummary(item);
  if (item.kind === 'portfolio_investment') {
    const parts = [item.summary || '定投计划已执行'];
    if (item.position_name) parts.push(item.position_name);
    const amount = Number(item.amount);
    if (Number.isFinite(amount)) parts.push('计划金额 ' + todayOverviewMoney(amount, item.mode));
    const price = Number(item.price);
    if (Number.isFinite(price)) parts.push('成交价 ' + todayOverviewMoney(price, item.mode));
    return parts.join(' · ');
  }
  return item.summary || '已记录一项活动。';
}

function renderTodayOverviewActivity(items, total, truncated) {
  const list = document.getElementById('todayOverviewActivityList');
  const count = document.getElementById('todayOverviewActivityCount');
  if (!list || !count) return;
  count.textContent = todayOverviewCountText(total, '条');
  if (!items.length) {
    list.innerHTML = [
      '<div class="today-overview-empty">',
      '<strong>今日暂无活动</strong>',
      '<span>警报、持仓流水、定投执行、风险分析和复盘笔记会显示在这里。</span>',
      '</div>',
    ].join('');
    return;
  }
  list.innerHTML = items.map((item, index) => {
    const token = 'activity-' + index;
    todayOverviewItemIndex[token] = item;
    return [
      '<button class="today-overview-activity-item" type="button" onclick="activateTodayOverviewItem(\'' + token + '\')">',
      '<span class="today-overview-activity-time">' + escapeHtml(todayOverviewTimeText(item.timestamp, false)) + '</span>',
      '<span class="today-overview-activity-marker" aria-hidden="true"></span>',
      '<span class="today-overview-activity-copy">',
      '<span class="today-overview-activity-kind">' + escapeHtml(todayOverviewActivityLabel(item.kind)) + '</span>',
      '<strong>' + escapeHtml(item.title || todayOverviewActivityLabel(item.kind)) + '</strong>',
      '<span>' + escapeHtml(todayOverviewActivitySummary(item)) + '</span>',
      '</span>',
      '</button>',
    ].join('');
  }).join('') + (truncated
    ? '<div class="today-overview-truncated">仅展示最近的 ' + items.length + ' 条活动。</div>'
    : '');
}

function todayOverviewMarketState(market) {
  const quality = market && market.quality && typeof market.quality === 'object' ? market.quality : {};
  const fetchStatus = market && market.fetch_status && typeof market.fetch_status === 'object' ? market.fetch_status : {};
  const level = String(quality.level || (fetchStatus.ok === false ? 'degraded' : fetchStatus.ok === true ? 'normal' : 'waiting'));
  const stateClass = ['normal', 'anomaly', 'stale', 'degraded'].includes(level) ? level : 'waiting';
  const label = quality.label || (fetchStatus.ok === true ? '行情正常' : fetchStatus.ok === false ? '行情需检查' : '等待行情状态');
  const score = quality.score == null ? '' : Number(quality.score) + ' 分';
  const qualityReason = Array.isArray(quality.reasons) && quality.reasons.length ? quality.reasons[0] : '';
  const message = stateClass === 'normal'
    ? fetchStatus.message || qualityReason || '行情数据正常。'
    : qualityReason || fetchStatus.message || '请检查当前行情数据源。';
  return { stateClass, label, score, message };
}

function renderTodayOverviewPortfolioMode(mode, summary) {
  const source = summary && typeof summary === 'object' ? summary : {};
  const pnl = source.total_pnl != null ? source.total_pnl : source.pnl;
  const valued = todayOverviewNumber(source.valued);
  const count = todayOverviewNumber(source.count);
  return [
    '<div class="today-overview-portfolio-mode">',
    '<div class="today-overview-portfolio-mode-head">',
    '<span>' + (mode === 'usd' ? '美元持仓' : '人民币持仓') + '</span>',
    '<small>' + escapeHtml(valued + '/' + count + ' 已估值') + '</small>',
    '</div>',
    '<strong>' + escapeHtml(todayOverviewMoney(source.market_value, mode)) + '</strong>',
    '<span class="today-overview-pnl ' + todayOverviewPnlClass(pnl) + '">累计盈亏 ' + escapeHtml(todayOverviewSignedMoney(pnl, mode)) + '</span>',
    '</div>',
  ].join('');
}

function renderTodayOverviewContext(market, portfolio) {
  const box = document.getElementById('todayOverviewContext');
  if (!box) return;
  const marketState = todayOverviewMarketState(market);
  const current = portfolio && portfolio.current && typeof portfolio.current === 'object' ? portfolio.current : {};
  box.innerHTML = [
    '<button class="today-overview-market-state ' + escapeHtml(marketState.stateClass) + '" type="button" onclick="activateTodayOverviewAction(\'open_market_status\', \'market-quality\')">',
    '<span class="today-overview-market-dot" aria-hidden="true"></span>',
    '<span class="today-overview-market-copy">',
    '<span>行情状态</span>',
    '<strong>' + escapeHtml(marketState.label) + (marketState.score ? ' · ' + escapeHtml(marketState.score) : '') + '</strong>',
    '<small>' + escapeHtml(marketState.message) + '</small>',
    '</span>',
    '<span class="today-overview-market-link">详情</span>',
    '</button>',
    '<div class="today-overview-portfolio-summary">',
    renderTodayOverviewPortfolioMode('rmb', current.rmb),
    renderTodayOverviewPortfolioMode('usd', current.usd),
    '</div>',
  ].join('');
}

function renderTodayOverview(data) {
  const state = data && typeof data === 'object' ? data : {};
  const summary = state.summary && typeof state.summary === 'object' ? state.summary : {};
  const attention = state.attention && typeof state.attention === 'object' ? state.attention : {};
  const activity = state.activity && typeof state.activity === 'object' ? state.activity : {};
  const attentionItems = Array.isArray(attention.items) ? attention.items : [];
  const activityItems = Array.isArray(activity.items) ? activity.items : [];
  const filteredAttentionItems = attentionItems.filter(item => todayOverviewFilterMatches(item, todayOverviewAttentionFilter));
  const filterCounts = attention.filter_counts && typeof attention.filter_counts === 'object' ? attention.filter_counts : {};
  const filteredAttentionTotal = todayOverviewAttentionFilter === 'all'
    ? todayOverviewNumber(attention.total)
    : todayOverviewNumber(filterCounts[todayOverviewAttentionFilter]);
  todayOverviewItemIndex = {};
  todayOverviewFilteredAttentionItems = filteredAttentionItems;
  updateTodayOverviewButton(summary);
  renderTodayOverviewSummary(summary);
  renderTodayOverviewFilters(attention);
  renderTodayOverviewBatchTools(filteredAttentionItems);
  renderTodayOverviewAttention(
    filteredAttentionItems,
    filteredAttentionTotal,
    filteredAttentionTotal > filteredAttentionItems.length,
  );
  renderTodayOverviewContext(state.market, state.portfolio);
  renderTodayOverviewActivity(activityItems, activity.total, activity.truncated);
  const subtitle = document.getElementById('todayOverviewSubtitle');
  const dateText = state.range && state.range.date ? String(state.range.date) : '';
  const updatedText = state.generated_at ? todayOverviewTimeText(state.generated_at, false) : '';
  if (subtitle) {
    subtitle.textContent = [dateText, updatedText ? updatedText + ' 更新' : ''].filter(Boolean).join(' · ') || '汇总当前待处理事项和本机今日活动。';
  }
  renderTodayOverviewFeedback();
}

function requestTodayOverview(manual) {
  if (!socket.connected) {
    setTodayOverviewStatus('本地服务未连接，连接恢复后会自动刷新。', 'fail');
    return;
  }
  todayOverviewLoading = true;
  const refreshButton = document.getElementById('todayOverviewRefreshButton');
  if (refreshButton) refreshButton.disabled = true;
  if (manual) {
    setTodayOverviewActionFeedback('', '');
    setTodayOverviewStatus('正在更新今日概览…', 'loading');
  } else if (!todayOverviewState && !todayOverviewPendingAction) {
    setTodayOverviewStatus('正在更新今日概览…', 'loading');
  }
  socket.emit('get_today_overview');
}

function queueTodayOverviewRefresh() {
  if (todayOverviewRefreshTimer) clearTimeout(todayOverviewRefreshTimer);
  todayOverviewRefreshTimer = setTimeout(() => {
    todayOverviewRefreshTimer = null;
    requestTodayOverview(false);
  }, 450);
}

function registerTodayOverviewSocketHandlers(socketClient) {
  socketClient.on('today_overview_updated', data => {
    todayOverviewLoading = false;
    const refreshButton = document.getElementById('todayOverviewRefreshButton');
    if (refreshButton) refreshButton.disabled = false;
    todayOverviewState = data && typeof data === 'object' ? data : {};
    applyTodayOverviewBatchRefresh(todayOverviewState);
    renderTodayOverview(todayOverviewState);
    if (todayOverviewIsOpen()) todayOverviewShouldMarkViewed = true;
  });

  socketClient.on('today_overview_viewed', () => {
    todayOverviewShouldMarkViewed = false;
  });

  socketClient.on('today_overview_error', data => {
    todayOverviewLoading = false;
    const refreshButton = document.getElementById('todayOverviewRefreshButton');
    if (refreshButton) refreshButton.disabled = false;
    setTodayOverviewStatus((data && data.message) || '今日概览加载失败，请稍后重试。', 'fail');
  });

  socketClient.on('alert_log_handling_updated', data => {
    const pending = todayOverviewPendingAction;
    if (!pending || pending.kind !== 'handle_alert') return;
    const entryId = data && data.entry ? String(data.entry.id || '') : '';
    if (entryId && entryId !== pending.targetId) return;
    todayOverviewPendingAction = null;
    setTodayOverviewActionFeedback('警报已标记为已处理。', 'ok', true);
    if (todayOverviewState) renderTodayOverview(todayOverviewState);
  });

  socketClient.on('alert_log_handling_error', data => {
    if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== 'handle_alert') return;
    todayOverviewPendingAction = null;
    setTodayOverviewActionFeedback((data && data.message) || '警报处理失败。', 'fail', true);
    if (todayOverviewState) renderTodayOverview(todayOverviewState);
  });

  socketClient.on('alert_notification_resent', data => {
    const pending = todayOverviewPendingAction;
    if (!pending || pending.kind !== 'resend_notification') return;
    const entryId = data && data.entry ? String(data.entry.id || '') : '';
    if (entryId && entryId !== pending.targetId) return;
    todayOverviewPendingAction = null;
    setTodayOverviewActionFeedback('通知已重新提交，投递结果会自动更新。', 'ok', true);
    if (todayOverviewState) renderTodayOverview(todayOverviewState);
  });

  socketClient.on('alert_notification_resend_error', data => {
    if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== 'resend_notification') return;
    todayOverviewPendingAction = null;
    setTodayOverviewActionFeedback((data && data.message) || '通知重发失败。', 'fail', true);
    if (todayOverviewState) renderTodayOverview(todayOverviewState);
  });

  socketClient.on('fetch_status', data => {
    if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== 'refresh_market') return;
    if (data && data.retryable === false && data.ok !== true) return;
    todayOverviewPendingAction = null;
    if (data && data.ok === true) {
      setTodayOverviewActionFeedback('行情已更新。', 'ok', true);
    } else {
      setTodayOverviewActionFeedback((data && data.message) || '行情重新获取失败。', 'fail', true);
    }
    if (todayOverviewState) renderTodayOverview(todayOverviewState);
  });

  TODAY_OVERVIEW_REFRESH_EVENTS.forEach(eventName => {
    socketClient.on(eventName, queueTodayOverviewRefresh);
  });
  registerTodayOverviewBatchSocketHandlers(socketClient);
}

function openTodayOverview() {
  const backdrop = document.getElementById('todayOverviewBackdrop');
  const button = document.getElementById('todayOverviewButton');
  if (!backdrop) return;
  todayOverviewLastFocused = document.activeElement;
  todayOverviewShouldMarkViewed = false;
  backdrop.classList.add('show');
  if (button) button.setAttribute('aria-expanded', 'true');
  if (todayOverviewState) renderTodayOverview(todayOverviewState);
  requestTodayOverview(false);
  requestAnimationFrame(() => document.getElementById('todayOverviewCloseButton')?.focus());
}

function closeTodayOverview(options) {
  const settings = Object.assign({ markViewed: true, restoreFocus: true }, options || {});
  const backdrop = document.getElementById('todayOverviewBackdrop');
  const button = document.getElementById('todayOverviewButton');
  if (!backdrop || !backdrop.classList.contains('show')) return;
  backdrop.classList.remove('show');
  if (button) button.setAttribute('aria-expanded', 'false');
  if (settings.markViewed && todayOverviewShouldMarkViewed && socket.connected) {
    todayOverviewShouldMarkViewed = false;
    socket.emit('mark_today_overview_viewed');
  }
  if (settings.restoreFocus && todayOverviewLastFocused && typeof todayOverviewLastFocused.focus === 'function') {
    todayOverviewLastFocused.focus();
  }
  todayOverviewLastFocused = null;
}

function onTodayOverviewBackdrop(event) {
  if (event.target.id === 'todayOverviewBackdrop') closeTodayOverview();
}

function todayOverviewFocusableElements() {
  const modal = document.querySelector('.today-overview-modal');
  if (!modal) return [];
  return Array.from(modal.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
    .filter(element => !element.hidden && element.offsetParent !== null);
}

function handleTodayOverviewKeydown(event) {
  if (!todayOverviewIsOpen()) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeTodayOverview();
    return;
  }
  if (event.key !== 'Tab') return;
  const focusable = todayOverviewFocusableElements();
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function openTodayOverviewAlert(targetId, timestamp) {
  const entry = Array.isArray(alertEntries)
    ? alertEntries.find(item => String(item.id || '') === String(targetId || ''))
    : null;
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  if (entry) {
    showAlertModal(entry);
    return;
  }
  openEventTimelineAround(timestamp, 'alert', targetId);
}

function openTodayOverviewRule(targetId) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  const rule = findUnifiedAlertRule(targetId);
  if (rule) editUnifiedAlertRule(rule.id);
  else setAlertRuleCenterStatus('该规则已不存在，请检查当前规则列表。', 'fail');
  document.getElementById('alertRuleCenterList')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openTodayOverviewMarketStatus() {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  const details = document.getElementById('sourceHealthDetails');
  if (details) details.hidden = false;
  document.getElementById('sourceHealth')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function openTodayOverviewPortfolioTransaction(targetId) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  setActivePortfolioTransaction(targetId);
  document.querySelector('.portfolio-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openTodayOverviewPortfolioInvestment(targetId) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  activePortfolioInvestmentPlanId = targetId || null;
  setPortfolioView('investment');
  document.querySelector('.portfolio-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openTodayOverviewOperationsTask(targetId) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  openSettings();
  switchSettingsTab('ops');
  requestBackgroundTaskStatus();
  window.requestAnimationFrame(() => {
    const taskButton = Array.from(document.querySelectorAll('.ops-task-run')).find(
      element => String(element.dataset.taskName || '') === String(targetId || '')
    );
    const target = taskButton ? taskButton.closest('.ops-task-item') : document.querySelector('.ops-task-card');
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    if (taskButton) taskButton.focus();
  });
}

function openTodayOverviewRiskAnalysis(targetId) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  if (!openRiskAnalysis()) return;
  const index = Array.isArray(riskAnalysisHistory)
    ? riskAnalysisHistory.findIndex(item => String(item.id || item.analysis_time || '') === String(targetId || ''))
    : -1;
  if (index >= 0) openRiskHistoryItem(index);
}

function openTodayOverviewReviewNote(targetId, timestamp) {
  closeTodayOverview({ markViewed: true, restoreFocus: false });
  openEventTimelineAround(timestamp, 'review_note', targetId);
}

function activateTodayOverviewAction(kind, targetId, timestamp) {
  if (kind === 'open_alert') openTodayOverviewAlert(targetId, timestamp);
  else if (kind === 'open_rule') openTodayOverviewRule(targetId);
  else if (kind === 'open_market_status') openTodayOverviewMarketStatus();
  else if (kind === 'open_portfolio_transaction') openTodayOverviewPortfolioTransaction(targetId);
  else if (kind === 'open_portfolio_investment') openTodayOverviewPortfolioInvestment(targetId);
  else if (kind === 'open_operations_task') openTodayOverviewOperationsTask(targetId);
  else if (kind === 'open_risk_analysis') openTodayOverviewRiskAnalysis(targetId);
  else if (kind === 'open_review_note') openTodayOverviewReviewNote(targetId, timestamp);
}

function activateTodayOverviewItem(token) {
  const item = todayOverviewItemIndex[token];
  if (!item) return;
  const action = item.action && typeof item.action === 'object' ? item.action : {};
  activateTodayOverviewAction(action.kind, action.target_id, item.timestamp);
}

function runTodayOverviewQuickAction(token, actionIndex) {
  const item = todayOverviewItemIndex[token];
  const actions = item && Array.isArray(item.quick_actions) ? item.quick_actions : [];
  const action = actions[actionIndex];
  if (!item || !action || todayOverviewPendingAction) return;
  if (!socket.connected) {
    setTodayOverviewActionFeedback('本地服务未连接，暂时无法处理该事项。', 'fail', true);
    return;
  }
  const messages = {
    handle_alert: '正在更新警报处置状态…',
    resend_notification: '正在重新提交通知…',
    refresh_market: '正在重新获取行情数据…',
  };
  todayOverviewActionFeedback = null;
  todayOverviewPendingAction = {
    itemId: item.id,
    targetId: String(action.target_id || item.source_id || ''),
    kind: action.kind,
    message: messages[action.kind] || '正在处理…',
  };
  renderTodayOverview(todayOverviewState);
  if (action.kind === 'handle_alert') {
    socket.emit('update_alert_log_handling', {
      id: todayOverviewPendingAction.targetId,
      handled: true,
      note: '',
    });
  } else if (action.kind === 'resend_notification') {
    socket.emit('resend_alert_notification', { id: todayOverviewPendingAction.targetId });
  } else if (action.kind === 'refresh_market') {
    refreshPrice();
  } else {
    todayOverviewPendingAction = null;
    setTodayOverviewActionFeedback('该处理操作暂不可用。', 'fail', true);
    renderTodayOverview(todayOverviewState);
  }
}

document.addEventListener('keydown', handleTodayOverviewKeydown);
