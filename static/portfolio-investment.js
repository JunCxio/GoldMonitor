// ========== 持仓定投 ==========
function portfolioInvestmentItems() {
  const state = portfolioState.investment_plans || {};
  return Array.isArray(state.items) ? state.items : [];
}

function portfolioInvestmentDraftKey(id) {
  return String(id || 'new');
}

function portfolioInvestmentBaseDraft(item) {
  const source = item && typeof item === 'object' ? item : {};
  const isNew = !source.id || source.id === 'new';
  return {
    id: isNew ? 'new' : source.id,
    name: source.name || '',
    position_id: source.position_id || '',
    position_name: source.position_name || '',
    mode: source.mode === 'usd' ? 'usd' : source.mode === 'rmb' ? 'rmb' : currentMode,
    amount: source.amount == null || isNew ? '' : String(source.amount),
    fee: source.fee == null ? '0' : String(source.fee),
    frequency: ['daily', 'monthly', 'yearly'].includes(source.frequency) ? source.frequency : 'monthly',
    time: source.time || '09:00',
    month: source.month == null ? '1' : String(source.month),
    day: source.day == null ? '1' : String(source.day),
    enabled: source.enabled !== false,
  };
}

function portfolioInvestmentDraftFor(item) {
  const base = portfolioInvestmentBaseDraft(item);
  const draft = portfolioInvestmentDrafts[portfolioInvestmentDraftKey(base.id)] || {};
  return Object.assign({}, base, draft, { id: base.id });
}

function portfolioInvestmentInputValue(id, field) {
  const el = document.getElementById('portfolioInvestment' + field + '_' + id);
  if (!el) return '';
  return el.type === 'checkbox' ? el.checked : el.value;
}

function capturePortfolioInvestmentDraft(id) {
  const key = portfolioInvestmentDraftKey(id);
  if (!document.getElementById('portfolioInvestmentName_' + key)) return;
  portfolioInvestmentDrafts[key] = {
    name: portfolioInvestmentInputValue(key, 'Name'),
    position_id: portfolioInvestmentInputValue(key, 'PositionId'),
    position_name: portfolioInvestmentInputValue(key, 'PositionName'),
    mode: portfolioInvestmentInputValue(key, 'Mode') || currentMode,
    amount: portfolioInvestmentInputValue(key, 'Amount'),
    fee: portfolioInvestmentInputValue(key, 'Fee'),
    frequency: portfolioInvestmentInputValue(key, 'Frequency') || 'monthly',
    time: portfolioInvestmentInputValue(key, 'Time') || '09:00',
    month: portfolioInvestmentInputValue(key, 'Month') || '1',
    day: portfolioInvestmentInputValue(key, 'Day') || '1',
    enabled: portfolioInvestmentInputValue(key, 'Enabled') !== false,
  };
}

function captureActivePortfolioInvestmentDraft() {
  if (!activePortfolioInvestmentPlanId) return;
  capturePortfolioInvestmentDraft(activePortfolioInvestmentPlanId);
}

function clearPortfolioInvestmentDraft(id) {
  delete portfolioInvestmentDrafts[portfolioInvestmentDraftKey(id)];
}

function setActivePortfolioInvestmentPlan(id) {
  captureActivePortfolioInvestmentDraft();
  if (activePortfolioInvestmentPlanId === id) {
    clearPortfolioInvestmentDraft(id);
    activePortfolioInvestmentPlanId = null;
  } else {
    activePortfolioInvestmentPlanId = id;
  }
  portfolioView = 'investment';
  renderPortfolio();
}

function refreshPortfolioInvestmentEditor(id) {
  capturePortfolioInvestmentDraft(id);
  renderPortfolio();
}

function portfolioInvestmentFrequencyLabel(plan) {
  const time = plan.time || '09:00';
  if (plan.frequency === 'daily') return '每天 ' + time;
  if (plan.frequency === 'yearly') return '每年 ' + Number(plan.month || 1) + ' 月 ' + Number(plan.day || 1) + ' 日 ' + time;
  return '每月 ' + Number(plan.day || 1) + ' 日 ' + time;
}

function portfolioInvestmentDateTime(value) {
  const text = String(value || '').trim();
  if (!text) return '--';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text.replace('T', ' ').slice(0, 16);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function portfolioInvestmentResultLabel(result) {
  return ({
    ok: '执行成功',
    waiting: '等待首次执行',
    waiting_price: '等待行情',
    orphaned: '关联失效',
    error: '执行失败',
  })[result] || '等待执行';
}

function portfolioInvestmentStateLabel(plan) {
  if (!plan.enabled) return '已暂停';
  if (plan.status === 'due') return '待执行';
  if (plan.last_result === 'waiting_price') return '等待行情';
  if (plan.last_result === 'orphaned') return '关联失效';
  return '运行中';
}

function portfolioInvestmentStateClass(plan) {
  if (plan.last_result === 'orphaned' || plan.last_result === 'error') return 'warn';
  if (plan.status === 'due' || plan.last_result === 'waiting_price') return 'attention';
  return plan.enabled ? 'on' : 'off';
}

function portfolioInvestmentExecutionKindLabel(kind) {
  return ({
    scheduled: '计划执行',
    catch_up: '补执行',
    manual: '手动执行',
  })[kind] || '定投执行';
}

function portfolioInvestmentPerformance(plan) {
  return plan.performance && typeof plan.performance === 'object' ? plan.performance : {};
}

function renderPortfolioInvestmentPerformance(plan) {
  const performance = portfolioInvestmentPerformance(plan);
  const mode = plan.mode || 'rmb';
  const count = Number(performance.execution_count || 0);
  if (count <= 0) {
    return '<div class="portfolio-investment-performance-empty">首次执行后显示累计投入、定投均价和盈亏。</div>';
  }
  const pnl = performance.pnl;
  const pnlText = pnl == null
    ? '等待行情估值'
    : formatPortfolioSignedMoney(pnl, mode) + ' · ' + formatPortfolioPercent(performance.pnl_percent);
  const recentExecutions = Array.isArray(performance.recent_executions) ? performance.recent_executions : [];
  return [
    '<div class="portfolio-investment-performance">',
    '<div class="portfolio-investment-performance-grid">',
    '<div><span>累计投入</span><strong>' + escapeHtml(formatPortfolioMoney(performance.total_invested, mode)) + '</strong><small>含手续费 ' + escapeHtml(formatPortfolioMoney(performance.total_fees, mode)) + '</small></div>',
    '<div><span>执行次数</span><strong>' + escapeHtml(String(count)) + ' 次</strong><small>累计 ' + escapeHtml(formatPortfolioNumber(performance.total_quantity, mode === 'usd' ? 6 : 4) + ' ' + portfolioQuantityUnit(mode)) + '</small></div>',
    '<div><span>定投均价</span><strong>' + escapeHtml(formatPortfolioMoney(performance.average_cost, mode)) + '</strong><small>成交均价 ' + escapeHtml(formatPortfolioMoney(performance.average_price, mode)) + '</small></div>',
    '<div><span>当前市值</span><strong>' + escapeHtml(performance.market_value == null ? '--' : formatPortfolioMoney(performance.market_value, mode)) + '</strong><small class="' + portfolioPnlClass(pnl) + '">' + escapeHtml(pnlText) + '</small></div>',
    '</div>',
    '<div class="portfolio-investment-execution-history">',
    '<div class="portfolio-investment-execution-history-head"><div><span>最近执行</span><small>页面最多显示 10 条</small></div><button class="btn-clear-sm btn-muted-sm" type="button" onclick="exportPortfolioInvestmentExecutions(\'' + escapeHtml(plan.id) + '\')">导出全部记录</button></div>',
    recentExecutions.map(item => [
      '<div class="portfolio-investment-execution-item">',
      '<div><strong>' + escapeHtml(portfolioInvestmentExecutionKindLabel(item.execution_kind)) + '</strong><span>' + escapeHtml(portfolioInvestmentDateTime(item.timestamp || item.scheduled_at || item.trade_date)) + '</span></div>',
      '<div><strong>' + escapeHtml(formatPortfolioMoney(item.total_cost, mode)) + '</strong><span>' + escapeHtml(formatPortfolioMoney(item.price, mode) + ' · ' + formatPortfolioNumber(item.quantity, mode === 'usd' ? 6 : 4) + ' ' + portfolioQuantityUnit(mode)) + '</span></div>',
      '</div>',
    ].join('')).join(''),
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioInvestmentSummary(box) {
  const state = portfolioState.investment_plans || {};
  const summary = state.summary || {};
  const nextPlan = portfolioInvestmentItems()
    .filter(item => item.enabled && item.next_run_at)
    .sort((left, right) => String(left.next_run_at).localeCompare(String(right.next_run_at)))[0];
  box.classList.add('portfolio-investment-summary');
  box.innerHTML = [
    '<div class="portfolio-investment-overview">',
    '<div class="portfolio-investment-overview-count"><span>运行中的计划</span><strong>' + escapeHtml(String(summary.enabled || 0)) + '</strong><small>共 ' + escapeHtml(String(summary.total || 0)) + ' 个计划</small></div>',
    '<div class="portfolio-investment-next">',
    '<span>下一次执行</span>',
    '<strong>' + escapeHtml(nextPlan ? portfolioInvestmentDateTime(nextPlan.next_run_at) : '暂无安排') + '</strong>',
    '<small>' + escapeHtml(nextPlan ? nextPlan.name + ' · ' + portfolioInvestmentFrequencyLabel(nextPlan) : '新增并启用计划后显示') + '</small>',
    '</div>',
    '<div class="portfolio-investment-overview-flags">',
    '<div><span>待执行</span><strong>' + escapeHtml(String(summary.due || 0)) + '</strong></div>',
    '<div><span>需处理</span><strong>' + escapeHtml(String(summary.attention || 0)) + '</strong></div>',
    '</div>',
    '<div class="portfolio-investment-overview-performance"><span>累计执行 ' + escapeHtml(String(summary.execution_count || 0)) + ' 次</span><strong>' + escapeHtml(formatPortfolioMoney(summary.rmb_invested || 0, 'rmb')) + ' · ' + escapeHtml(formatPortfolioMoney(summary.usd_invested || 0, 'usd')) + '</strong></div>',
    '</div>',
  ].join('');
}

function filteredPortfolioInvestments() {
  return portfolioInvestmentItems()
    .filter(item => portfolioSearchMatches([
      item.name,
      item.position_name,
      item.mode,
      portfolioInvestmentFrequencyLabel(item),
      item.last_message,
    ]))
    .sort((left, right) => {
      if (left.enabled !== right.enabled) return left.enabled ? -1 : 1;
      const leftRun = left.next_run_at || '9999';
      const rightRun = right.next_run_at || '9999';
      return leftRun.localeCompare(rightRun) || String(left.name).localeCompare(String(right.name), 'zh-CN');
    });
}

function buildPortfolioInvestmentEditor(item) {
  const target = portfolioInvestmentDraftFor(item);
  const id = target.id;
  const escapedId = escapeHtml(id);
  const existingPosition = (portfolioState.items || []).find(position => position.id === target.position_id);
  const selectedMode = existingPosition ? existingPosition.mode : target.mode;
  const positionOptions = [
    '<option value=""' + (!target.position_id ? ' selected' : '') + '>首次执行时创建新持仓</option>',
  ];
  if (target.position_id && !existingPosition) {
    positionOptions.push('<option value="' + escapeHtml(target.position_id) + '" selected disabled>原关联持仓已删除</option>');
  }
  (portfolioState.items || []).forEach(position => {
    positionOptions.push('<option value="' + escapeHtml(position.id) + '"' + (position.id === target.position_id ? ' selected' : '') + '>' + escapeHtml(position.name + ' · ' + portfolioModeLabel(position.mode)) + '</option>');
  });
  const fieldInput = ' oninput="capturePortfolioInvestmentDraft(\'' + escapedId + '\')"';
  const fieldChange = ' onchange="capturePortfolioInvestmentDraft(\'' + escapedId + '\')"';
  const rerenderChange = ' onchange="refreshPortfolioInvestmentEditor(\'' + escapedId + '\')"';
  return [
    '<div class="portfolio-editor portfolio-investment-editor">',
    '<div class="portfolio-fields portfolio-investment-fields">',
    '<div class="portfolio-field portfolio-name"><label for="portfolioInvestmentName_' + escapedId + '">计划名称</label><input id="portfolioInvestmentName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.name) + '" placeholder="例如 每月工资日定投"' + fieldInput + '></div>',
    '<div class="portfolio-field portfolio-investment-position"><label for="portfolioInvestmentPositionId_' + escapedId + '">关联持仓</label><select id="portfolioInvestmentPositionId_' + escapedId + '"' + rerenderChange + '>' + positionOptions.join('') + '</select></div>',
    !target.position_id ? '<div class="portfolio-field"><label for="portfolioInvestmentPositionName_' + escapedId + '">新持仓名称</label><input id="portfolioInvestmentPositionName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.position_name) + '" placeholder="例如 积存金"' + fieldInput + '></div>' : '<input id="portfolioInvestmentPositionName_' + escapedId + '" type="hidden" value="' + escapeHtml(existingPosition ? existingPosition.name : target.position_name) + '">',
    '<div class="portfolio-field"><label for="portfolioInvestmentMode_' + escapedId + '">单位</label><select id="portfolioInvestmentMode_' + escapedId + '"' + (existingPosition ? ' disabled' : fieldChange) + '><option value="rmb"' + (selectedMode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + (selectedMode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentAmount_' + escapedId + '">每次金额</label><input id="portfolioInvestmentAmount_' + escapedId + '" type="number" min="0.01" step="0.01" value="' + escapeHtml(target.amount) + '" placeholder="输入固定金额"' + fieldInput + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentFee_' + escapedId + '">固定手续费</label><input id="portfolioInvestmentFee_' + escapedId + '" type="number" min="0" step="0.01" value="' + escapeHtml(target.fee) + '"' + fieldInput + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentFrequency_' + escapedId + '">周期</label><select id="portfolioInvestmentFrequency_' + escapedId + '"' + rerenderChange + '><option value="daily"' + (target.frequency === 'daily' ? ' selected' : '') + '>每天</option><option value="monthly"' + (target.frequency === 'monthly' ? ' selected' : '') + '>每月</option><option value="yearly"' + (target.frequency === 'yearly' ? ' selected' : '') + '>每年</option></select></div>',
    target.frequency === 'yearly' ? '<div class="portfolio-field"><label for="portfolioInvestmentMonth_' + escapedId + '">月份</label><input id="portfolioInvestmentMonth_' + escapedId + '" type="number" min="1" max="12" value="' + escapeHtml(target.month) + '"' + fieldInput + '></div>' : '<input id="portfolioInvestmentMonth_' + escapedId + '" type="hidden" value="' + escapeHtml(target.month) + '">',
    target.frequency !== 'daily' ? '<div class="portfolio-field"><label for="portfolioInvestmentDay_' + escapedId + '">日期</label><input id="portfolioInvestmentDay_' + escapedId + '" type="number" min="1" max="31" value="' + escapeHtml(target.day) + '"' + fieldInput + '></div>' : '<input id="portfolioInvestmentDay_' + escapedId + '" type="hidden" value="' + escapeHtml(target.day) + '">',
    '<div class="portfolio-field"><label for="portfolioInvestmentTime_' + escapedId + '">执行时间</label><input id="portfolioInvestmentTime_' + escapedId + '" type="time" value="' + escapeHtml(target.time) + '"' + fieldChange + '></div>',
    '<label class="portfolio-investment-enabled"><input id="portfolioInvestmentEnabled_' + escapedId + '" type="checkbox"' + (target.enabled ? ' checked' : '') + fieldChange + '><span>保存后启用计划</span></label>',
    '</div>',
    '<div class="portfolio-editor-actions"><button class="btn-set" type="button" onclick="savePortfolioInvestmentPlan(\'' + escapedId + '\')">保存计划</button><button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioInvestmentPlan(\'' + escapedId + '\')">取消</button></div>',
    '</div>',
  ].join('');
}

function renderPortfolioInvestments(box) {
  const sourceItems = portfolioInvestmentItems();
  const items = filteredPortfolioInvestments();
  const parts = [];
  if (activePortfolioInvestmentPlanId === 'new') {
    parts.push([
      '<div class="portfolio-investment-card expanded">',
      '<div class="portfolio-investment-card-main"><div class="portfolio-line">新增定投计划</div><div class="portfolio-meta">固定金额按执行时最新行情生成买入流水</div></div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioInvestmentEditor({ id: 'new', frequency: 'monthly', time: '09:00', day: 1, month: 1, fee: 0, enabled: true }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activePortfolioInvestmentPlanId !== 'new') {
    parts.push('<div class="portfolio-empty">' + (sourceItems.length ? '没有匹配的定投计划' : '暂无定投计划，可从右上角新增') + '</div>');
  }
  parts.push(...items.map(plan => {
    const expanded = activePortfolioInvestmentPlanId === plan.id;
    const mode = plan.mode || 'rmb';
    const lastDetail = plan.last_executed_at
      ? portfolioInvestmentResultLabel(plan.last_result) + ' · ' + portfolioInvestmentDateTime(plan.last_executed_at)
      : plan.last_message || '等待首次执行';
    const resultMetrics = plan.last_price != null && plan.last_quantity != null && Number.isFinite(Number(plan.last_price)) && Number.isFinite(Number(plan.last_quantity))
      ? formatPortfolioMoney(plan.last_price, mode) + ' · ' + formatPortfolioNumber(plan.last_quantity, 6) + ' ' + portfolioQuantityUnit(mode)
      : plan.last_message || '尚无执行结果';
    return [
      '<div class="portfolio-investment-card' + (expanded ? ' expanded' : '') + '">',
      '<div class="portfolio-investment-card-main">',
      '<div class="portfolio-investment-card-head"><div><div class="portfolio-line">' + escapeHtml(plan.name || '未命名计划') + '</div><div class="portfolio-meta">' + escapeHtml(portfolioInvestmentFrequencyLabel(plan) + ' · ' + formatPortfolioMoney(plan.amount, mode) + (Number(plan.fee) > 0 ? ' · 手续费 ' + formatPortfolioMoney(plan.fee, mode) : '')) + '</div></div><span class="portfolio-investment-state ' + portfolioInvestmentStateClass(plan) + '">' + escapeHtml(portfolioInvestmentStateLabel(plan)) + '</span></div>',
      '<div class="portfolio-investment-timeline">',
      '<div class="portfolio-investment-timeline-marker"></div>',
      '<div><span>下一次执行</span><strong>' + escapeHtml(plan.enabled ? portfolioInvestmentDateTime(plan.next_run_at) : '计划已暂停') + '</strong><small>' + escapeHtml(plan.position_name + ' · ' + portfolioModeLabel(mode)) + '</small></div>',
      '<div><span>最近结果</span><strong>' + escapeHtml(lastDetail) + '</strong><small>' + escapeHtml(resultMetrics) + '</small></div>',
      '</div>',
      '</div>',
      '<div class="portfolio-investment-actions">',
      '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="executePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">立即执行</button>',
      '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="togglePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\', ' + String(!plan.enabled) + ')">' + (plan.enabled ? '暂停' : '启用') + '</button>',
      '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">' + (expanded ? '收起' : '编辑') + '</button>',
      '<button class="btn-clear-sm" type="button" onclick="deletePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">删除</button>',
      '</div>',
      expanded ? renderPortfolioInvestmentPerformance(plan) : '',
      expanded ? buildPortfolioInvestmentEditor(plan) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function savePortfolioInvestmentPlan(id) {
  const payload = {
    name: String(portfolioInvestmentInputValue(id, 'Name') || '').trim(),
    position_id: String(portfolioInvestmentInputValue(id, 'PositionId') || '').trim(),
    position_name: String(portfolioInvestmentInputValue(id, 'PositionName') || '').trim(),
    mode: portfolioInvestmentInputValue(id, 'Mode') || currentMode,
    amount: Number(portfolioInvestmentInputValue(id, 'Amount')),
    fee: Number(portfolioInvestmentInputValue(id, 'Fee') || 0),
    frequency: portfolioInvestmentInputValue(id, 'Frequency') || 'monthly',
    time: portfolioInvestmentInputValue(id, 'Time') || '09:00',
    month: Number(portfolioInvestmentInputValue(id, 'Month') || 1),
    day: Number(portfolioInvestmentInputValue(id, 'Day') || 1),
    enabled: portfolioInvestmentInputValue(id, 'Enabled') !== false,
  };
  const position = (portfolioState.items || []).find(item => item.id === payload.position_id);
  if (position) {
    payload.position_name = position.name;
    payload.mode = position.mode;
  }
  if (!payload.name) return setPortfolioStatus('请输入计划名称。', 'fail');
  if (!payload.position_name) return setPortfolioStatus('请输入或选择定投持仓。', 'fail');
  if (!Number.isFinite(payload.amount) || payload.amount <= 0) return setPortfolioStatus('请输入有效的定投金额。', 'fail');
  if (!Number.isFinite(payload.fee) || payload.fee < 0) return setPortfolioStatus('手续费不能为负数。', 'fail');
  if (id !== 'new') payload.id = id;
  pendingPortfolioSave = { kind: 'investment', id };
  setPortfolioStatus('正在保存定投计划...', '');
  socket.emit('save_portfolio_investment_plan', payload);
}

function togglePortfolioInvestmentPlan(id, enabled) {
  setPortfolioStatus(enabled ? '正在启用定投计划...' : '正在暂停定投计划...', '');
  socket.emit('toggle_portfolio_investment_plan', { id, enabled: enabled === true });
}

function executePortfolioInvestmentPlan(id) {
  setPortfolioStatus('正在按最新行情生成买入流水...', '');
  socket.emit('execute_portfolio_investment_plan', { id });
}

function exportPortfolioInvestmentExecutions(id) {
  setPortfolioStatus('正在导出定投执行记录...', '');
  socket.emit('export_portfolio_investment_executions', { id });
}

function deletePortfolioInvestmentPlan(id) {
  if (!window.confirm('确定删除这个定投计划？已生成的持仓流水不会删除。')) return;
  setPortfolioStatus('正在删除定投计划...', '');
  socket.emit('delete_portfolio_investment_plan', { id });
}
