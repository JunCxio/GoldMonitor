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
    target_count: Number(source.target_count) > 0 ? String(source.target_count) : '',
    frequency: ['daily', 'weekly', 'monthly', 'yearly'].includes(source.frequency) ? source.frequency : 'monthly',
    time: source.time || '09:00',
    month: source.month == null ? '1' : String(source.month),
    day: source.day == null ? '1' : String(source.day),
    weekday: source.weekday == null ? '1' : String(source.weekday),
    start_date: source.start_date || '',
    end_date: source.end_date || '',
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
    target_count: portfolioInvestmentInputValue(key, 'TargetCount'),
    frequency: portfolioInvestmentInputValue(key, 'Frequency') || 'monthly',
    time: portfolioInvestmentInputValue(key, 'Time') || '09:00',
    month: portfolioInvestmentInputValue(key, 'Month') || '1',
    day: portfolioInvestmentInputValue(key, 'Day') || '1',
    weekday: portfolioInvestmentInputValue(key, 'Weekday') || '1',
    start_date: portfolioInvestmentInputValue(key, 'StartDate'),
    end_date: portfolioInvestmentInputValue(key, 'EndDate'),
    enabled: portfolioInvestmentInputValue(key, 'Enabled') !== false,
  };
}

function captureActivePortfolioInvestmentDraft() {
  if (!activePortfolioInvestmentPlanId) return;
  capturePortfolioInvestmentDraft(activePortfolioInvestmentPlanId);
}

function clearPortfolioInvestmentDraft(id) {
  const key = portfolioInvestmentDraftKey(id);
  delete portfolioInvestmentDrafts[key];
  delete portfolioInvestmentSchedulePreviews[key];
}

function portfolioInvestmentSchedulePayload(item) {
  const source = item && typeof item === 'object' ? item : {};
  return {
    mode: source.mode === 'usd' ? 'usd' : 'rmb',
    amount: Number(source.amount || 0),
    fee: Number(source.fee || 0),
    frequency: source.frequency || 'monthly',
    time: source.time || '09:00',
    month: Number(source.month || 1),
    day: Number(source.day || 1),
    weekday: Number(source.weekday || 1),
    start_date: String(source.start_date || '').trim(),
    end_date: String(source.end_date || '').trim(),
    target_count: Number(source.target_count || 0),
  };
}

function requestPortfolioInvestmentSchedulePreview(id) {
  capturePortfolioInvestmentDraft(id);
  const key = portfolioInvestmentDraftKey(id);
  const target = portfolioInvestmentDraftFor({ id: key });
  const selectedPosition = (portfolioState.items || []).find(item => item.id === target.position_id);
  if (selectedPosition) target.mode = selectedPosition.mode;
  const requestId = String(++portfolioInvestmentSchedulePreviewSeq);
  portfolioInvestmentSchedulePreviews[key] = { request_id: requestId, loading: true, items: [], projection: null, message: '' };
  socket.emit('preview_portfolio_investment_schedule', Object.assign(
    { id: key === 'new' ? '' : key, request_id: requestId },
    portfolioInvestmentSchedulePayload(target),
  ));
  renderPortfolio();
}

function applyPortfolioInvestmentSchedulePreview(data) {
  const key = portfolioInvestmentDraftKey(data && data.id);
  const current = portfolioInvestmentSchedulePreviews[key];
  if (!current || String(current.request_id) !== String((data && data.request_id) || '')) return;
  portfolioInvestmentSchedulePreviews[key] = {
    request_id: current.request_id,
    loading: false,
    items: Array.isArray(data.items) ? data.items : [],
    projection: portfolioInvestmentProjection(data.projection),
    message: data.ok === false ? String(data.message || '无法生成期次预览。') : '',
  };
  renderPortfolio();
}

function portfolioInvestmentSchedulePreviewMarkup(id, fallbackItems, fallbackProjection) {
  const key = portfolioInvestmentDraftKey(id);
  const preview = portfolioInvestmentSchedulePreviews[key];
  const items = preview ? preview.items : Array.isArray(fallbackItems) ? fallbackItems : [];
  const projection = preview ? preview.projection : fallbackProjection;
  const stateClass = preview && preview.message ? ' error' : preview && preview.loading ? ' loading' : '';
  const content = preview && preview.loading
    ? '<span class="portfolio-investment-schedule-preview-empty">正在计算未来期次...</span>'
    : preview && preview.message
      ? '<span class="portfolio-investment-schedule-preview-empty">' + escapeHtml(preview.message) + '</span>'
      : items.length
        ? '<div class="portfolio-investment-schedule-preview-list">' + items.map((value, index) => '<span><b>' + String(index + 1).padStart(2, '0') + '</b>' + escapeHtml(portfolioInvestmentDateTime(value)) + '</span>').join('') + '</div>'
        : '<span class="portfolio-investment-schedule-preview-empty">当前设置范围内没有可执行期次。</span>';
  return [
    '<div class="portfolio-investment-schedule-preview' + stateClass + '">',
    '<div class="portfolio-investment-schedule-preview-head"><div><strong>未来 5 期</strong><small>按当前周期和执行区间计算</small></div><button class="btn-clear-sm btn-muted-sm" type="button" onclick="requestPortfolioInvestmentSchedulePreview(\'' + escapeHtml(key) + '\')">重新计算</button></div>',
    portfolioInvestmentProjectionMarkup(projection),
    content,
    '</div>',
  ].join('');
}

function duplicatePortfolioInvestmentPlan(id) {
  const plan = portfolioInvestmentItems().find(item => item.id === id);
  if (!plan) {
    setPortfolioStatus('未找到可复制的定投计划。', 'fail');
    return;
  }
  if (activePortfolioInvestmentPlanId === 'new' && portfolioInvestmentDrafts.new && !window.confirm('当前新计划草稿将被替换，是否继续复制？')) {
    return;
  }
  captureActivePortfolioInvestmentDraft();
  const draft = portfolioInvestmentBaseDraft(plan);
  portfolioInvestmentDrafts.new = Object.assign({}, draft, {
    id: 'new',
    name: String(plan.name || '定投计划').trim().slice(0, 57) + ' 副本',
    enabled: false,
  });
  activePortfolioInvestmentPlanId = 'new';
  portfolioView = 'investment';
  portfolioInvestmentDraftNotice = '已复制为新计划草稿，确认后再保存。';
  setPortfolioStatus(portfolioInvestmentDraftNotice, 'ok');
  renderPortfolio();
}

function setActivePortfolioInvestmentPlan(id) {
  captureActivePortfolioInvestmentDraft();
  const opening = activePortfolioInvestmentPlanId !== id;
  if (activePortfolioInvestmentPlanId === id) {
    clearPortfolioInvestmentDraft(id);
    activePortfolioInvestmentPlanId = null;
    if (id === 'new') portfolioInvestmentDraftNotice = '';
  } else {
    if (activePortfolioInvestmentPlanId === 'new' || id !== 'new') portfolioInvestmentDraftNotice = '';
    activePortfolioInvestmentPlanId = id;
  }
  if (id === 'new') portfolioInvestmentListMode = 'active';
  portfolioView = 'investment';
  renderPortfolio();
  if (opening) requestPortfolioInvestmentSchedulePreview(id);
}

function setPortfolioInvestmentListMode(mode) {
  captureActivePortfolioInvestmentDraft();
  activePortfolioInvestmentPlanId = null;
  portfolioInvestmentListMode = mode === 'archived' ? 'archived' : 'active';
  renderPortfolio();
}

function refreshPortfolioInvestmentEditor(id) {
  capturePortfolioInvestmentDraft(id);
  renderPortfolio();
  requestPortfolioInvestmentSchedulePreview(id);
}

function portfolioInvestmentFrequencyLabel(plan) {
  const time = plan.time || '09:00';
  if (plan.frequency === 'daily') return '每天 ' + time;
  if (plan.frequency === 'weekly') return '每周' + portfolioInvestmentWeekdayLabel(plan.weekday) + ' ' + time;
  if (plan.frequency === 'yearly') return '每年 ' + Number(plan.month || 1) + ' 月 ' + Number(plan.day || 1) + ' 日 ' + time;
  return '每月 ' + Number(plan.day || 1) + ' 日 ' + time;
}

function portfolioInvestmentWeekdayLabel(value) {
  return ['', '一', '二', '三', '四', '五', '六', '日'][Number(value) || 1] || '一';
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
    skipped: '已跳过一期',
    waiting: '等待首次执行',
    waiting_price: '等待行情',
    orphaned: '关联失效',
    error: '执行失败',
  })[result] || '等待执行';
}

function portfolioInvestmentStateLabel(plan) {
  if (plan.archived_at) return '已归档';
  if (plan.status === 'pending_start') return '待开始';
  if (plan.status === 'completed') return '已完成';
  if (!plan.enabled) return '已暂停';
  if (plan.status === 'due') return '待执行';
  if (plan.last_result === 'waiting_price') return '等待行情';
  if (plan.last_result === 'orphaned') return '关联失效';
  return '运行中';
}

function portfolioInvestmentStateClass(plan) {
  if (plan.archived_at) return 'off';
  if (plan.last_result === 'orphaned' || plan.last_result === 'error') return 'warn';
  if (plan.status === 'due' || plan.last_result === 'waiting_price') return 'attention';
  if (plan.status === 'completed') return 'off';
  return plan.enabled ? 'on' : 'off';
}

function portfolioInvestmentNextRunLabel(plan) {
  if (plan.archived_at) return '计划已归档';
  if (plan.status === 'completed') return '计划已完成';
  if (!plan.enabled) return '计划已暂停';
  return portfolioInvestmentDateTime(plan.next_run_at);
}

function portfolioInvestmentWindowLabel(plan) {
  const start = plan.start_date || '';
  const end = plan.end_date || '';
  const windowLabel = start && end ? start + ' 至 ' + end : start ? start + ' 起' : end ? end + ' 前' : '长期有效';
  const targetCount = Number(plan.target_count || 0);
  if (!targetCount) return windowLabel;
  return windowLabel + ' · 已完成 ' + Number(plan.completed_count || 0) + '/' + targetCount + ' 期';
}

function portfolioInvestmentCanExecute(plan) {
  return !['pending_start', 'completed'].includes(plan.status);
}

function portfolioInvestmentCanSkip(plan) {
  return Boolean(plan.enabled && plan.pending_run_at && plan.status !== 'completed');
}

function portfolioInvestmentLastDetail(plan) {
  if (plan.last_result === 'skipped' && plan.last_skipped_at) {
    return portfolioInvestmentResultLabel(plan.last_result) + ' · ' + portfolioInvestmentDateTime(plan.last_skipped_at);
  }
  if (plan.last_executed_at) {
    return portfolioInvestmentResultLabel(plan.last_result) + ' · ' + portfolioInvestmentDateTime(plan.last_executed_at);
  }
  return plan.last_message || '等待首次执行';
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
    const progress = Number(plan.target_count || 0) > 0 ? '当前进度 0/' + Number(plan.target_count) + ' 期。' : '';
    return '<div class="portfolio-investment-performance-empty">' + progress + '首次执行后显示累计投入、定投均价和盈亏。</div>';
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
    '<div><span>执行进度</span><strong>' + escapeHtml(Number(plan.target_count || 0) > 0 ? count + '/' + Number(plan.target_count) + ' 期' : count + ' 次') + '</strong><small>累计 ' + escapeHtml(formatPortfolioNumber(performance.total_quantity, mode === 'usd' ? 6 : 4) + ' ' + portfolioQuantityUnit(mode)) + '</small></div>',
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
    '<div class="portfolio-investment-overview-actual">',
    '<b>近' + escapeHtml(String(summary.actual_days || 30)) + '天</b>',
    '<div><span>实际投入</span><small>按已生成的定投买入流水统计</small></div>',
    '<div class="portfolio-investment-overview-actual-values"><strong>' + escapeHtml(formatPortfolioMoney(summary.rmb_actual_invested || 0, 'rmb')) + ' · ' + escapeHtml(formatPortfolioMoney(summary.usd_actual_invested || 0, 'usd')) + '</strong><small>实际执行 ' + escapeHtml(String(summary.actual_execution_count || 0)) + ' 次</small></div>',
    '</div>',
    portfolioInvestmentActualTrendMarkup(summary.actual_trend, summary.actual_trend_months),
    portfolioInvestmentReliabilityMarkup(summary),
    '<div class="portfolio-investment-overview-commitment">',
    '<b>未来' + escapeHtml(String(summary.commitment_days || 30)) + '天</b>',
    '<div><span>计划投入</span><small>含当前待执行期次，按固定金额估算</small></div>',
    '<div class="portfolio-investment-overview-commitment-values"><strong>' + escapeHtml(formatPortfolioMoney(summary.rmb_commitment || 0, 'rmb')) + ' · ' + escapeHtml(formatPortfolioMoney(summary.usd_commitment || 0, 'usd')) + '</strong><small>预计 ' + escapeHtml(String(summary.commitment_run_count || 0)) + ' 期 · 涉及 ' + escapeHtml(String(summary.commitment_plan_count || 0)) + ' 个计划</small></div>',
    '</div>',
    portfolioInvestmentCommitmentItemsMarkup(summary.commitment_items),
    '</div>',
  ].join('');
}

function filteredPortfolioInvestments() {
  return portfolioInvestmentItems()
    .filter(item => portfolioInvestmentListMode === 'archived' ? Boolean(item.archived_at) : !item.archived_at)
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
  const scheduleChange = ' onchange="requestPortfolioInvestmentSchedulePreview(\'' + escapedId + '\')"';
  const rerenderChange = ' onchange="refreshPortfolioInvestmentEditor(\'' + escapedId + '\')"';
  return [
    '<div class="portfolio-editor portfolio-investment-editor">',
    '<div class="portfolio-fields portfolio-investment-fields">',
    '<div class="portfolio-field portfolio-name"><label for="portfolioInvestmentName_' + escapedId + '">计划名称</label><input id="portfolioInvestmentName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.name) + '" placeholder="例如 每月工资日定投"' + fieldInput + '></div>',
    '<div class="portfolio-field portfolio-investment-position"><label for="portfolioInvestmentPositionId_' + escapedId + '">关联持仓</label><select id="portfolioInvestmentPositionId_' + escapedId + '"' + rerenderChange + '>' + positionOptions.join('') + '</select></div>',
    !target.position_id ? '<div class="portfolio-field"><label for="portfolioInvestmentPositionName_' + escapedId + '">新持仓名称</label><input id="portfolioInvestmentPositionName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.position_name) + '" placeholder="例如 积存金"' + fieldInput + '></div>' : '<input id="portfolioInvestmentPositionName_' + escapedId + '" type="hidden" value="' + escapeHtml(existingPosition ? existingPosition.name : target.position_name) + '">',
    '<div class="portfolio-field"><label for="portfolioInvestmentMode_' + escapedId + '">单位</label><select id="portfolioInvestmentMode_' + escapedId + '"' + (existingPosition ? ' disabled' : scheduleChange) + '><option value="rmb"' + (selectedMode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + (selectedMode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentAmount_' + escapedId + '">每次金额</label><input id="portfolioInvestmentAmount_' + escapedId + '" type="number" min="0.01" step="0.01" value="' + escapeHtml(target.amount) + '" placeholder="输入固定金额"' + scheduleChange + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentFee_' + escapedId + '">固定手续费</label><input id="portfolioInvestmentFee_' + escapedId + '" type="number" min="0" step="0.01" value="' + escapeHtml(target.fee) + '"' + scheduleChange + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentTargetCount_' + escapedId + '">目标期数（可选）</label><input id="portfolioInvestmentTargetCount_' + escapedId + '" type="number" min="1" max="10000" step="1" value="' + escapeHtml(target.target_count) + '" placeholder="留空则不限期数"' + scheduleChange + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentFrequency_' + escapedId + '">周期</label><select id="portfolioInvestmentFrequency_' + escapedId + '"' + rerenderChange + '><option value="daily"' + (target.frequency === 'daily' ? ' selected' : '') + '>每天</option><option value="weekly"' + (target.frequency === 'weekly' ? ' selected' : '') + '>每周</option><option value="monthly"' + (target.frequency === 'monthly' ? ' selected' : '') + '>每月</option><option value="yearly"' + (target.frequency === 'yearly' ? ' selected' : '') + '>每年</option></select></div>',
    target.frequency === 'weekly' ? '<div class="portfolio-field"><label for="portfolioInvestmentWeekday_' + escapedId + '">星期</label><select id="portfolioInvestmentWeekday_' + escapedId + '"' + scheduleChange + '><option value="1"' + (target.weekday === '1' ? ' selected' : '') + '>星期一</option><option value="2"' + (target.weekday === '2' ? ' selected' : '') + '>星期二</option><option value="3"' + (target.weekday === '3' ? ' selected' : '') + '>星期三</option><option value="4"' + (target.weekday === '4' ? ' selected' : '') + '>星期四</option><option value="5"' + (target.weekday === '5' ? ' selected' : '') + '>星期五</option><option value="6"' + (target.weekday === '6' ? ' selected' : '') + '>星期六</option><option value="7"' + (target.weekday === '7' ? ' selected' : '') + '>星期日</option></select></div>' : '<input id="portfolioInvestmentWeekday_' + escapedId + '" type="hidden" value="' + escapeHtml(target.weekday) + '">',
    target.frequency === 'yearly' ? '<div class="portfolio-field"><label for="portfolioInvestmentMonth_' + escapedId + '">月份</label><input id="portfolioInvestmentMonth_' + escapedId + '" type="number" min="1" max="12" value="' + escapeHtml(target.month) + '"' + scheduleChange + '></div>' : '<input id="portfolioInvestmentMonth_' + escapedId + '" type="hidden" value="' + escapeHtml(target.month) + '">',
    ['monthly', 'yearly'].includes(target.frequency) ? '<div class="portfolio-field"><label for="portfolioInvestmentDay_' + escapedId + '">日期</label><input id="portfolioInvestmentDay_' + escapedId + '" type="number" min="1" max="31" value="' + escapeHtml(target.day) + '"' + scheduleChange + '></div>' : '<input id="portfolioInvestmentDay_' + escapedId + '" type="hidden" value="' + escapeHtml(target.day) + '">',
    '<div class="portfolio-field"><label for="portfolioInvestmentTime_' + escapedId + '">执行时间</label><input id="portfolioInvestmentTime_' + escapedId + '" type="time" value="' + escapeHtml(target.time) + '"' + scheduleChange + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentStartDate_' + escapedId + '">开始日期（可选）</label><input id="portfolioInvestmentStartDate_' + escapedId + '" type="date" value="' + escapeHtml(target.start_date) + '"' + scheduleChange + '></div>',
    '<div class="portfolio-field"><label for="portfolioInvestmentEndDate_' + escapedId + '">结束日期（可选）</label><input id="portfolioInvestmentEndDate_' + escapedId + '" type="date" value="' + escapeHtml(target.end_date) + '"' + scheduleChange + '></div>',
    '<label class="portfolio-investment-enabled"><input id="portfolioInvestmentEnabled_' + escapedId + '" type="checkbox"' + (target.enabled ? ' checked' : '') + fieldChange + '><span>保存后启用计划</span></label>',
    '</div>',
    portfolioInvestmentSchedulePreviewMarkup(id, item && item.upcoming_run_ats, item && item.projection),
    '<div class="portfolio-editor-actions"><button class="btn-set" type="button" onclick="savePortfolioInvestmentPlan(\'' + escapedId + '\')">保存计划</button><button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioInvestmentPlan(\'' + escapedId + '\')">取消</button></div>',
    '</div>',
  ].join('');
}

function renderPortfolioInvestments(box) {
  const sourceItems = portfolioInvestmentItems();
  const items = filteredPortfolioInvestments();
  const parts = [];
  const activeCount = sourceItems.filter(item => !item.archived_at).length;
  const archivedCount = sourceItems.filter(item => item.archived_at).length;
  parts.push([
    '<div class="portfolio-investment-list-switch" role="tablist" aria-label="定投计划范围">',
    '<button type="button" role="tab" aria-selected="' + String(portfolioInvestmentListMode === 'active') + '" class="' + (portfolioInvestmentListMode === 'active' ? 'active' : '') + '" onclick="setPortfolioInvestmentListMode(\'active\')">进行中 <span>' + escapeHtml(String(activeCount)) + '</span></button>',
    '<button type="button" role="tab" aria-selected="' + String(portfolioInvestmentListMode === 'archived') + '" class="' + (portfolioInvestmentListMode === 'archived' ? 'active' : '') + '" onclick="setPortfolioInvestmentListMode(\'archived\')">已归档 <span>' + escapeHtml(String(archivedCount)) + '</span></button>',
    '</div>',
  ].join(''));
  if (activePortfolioInvestmentPlanId === 'new') {
    parts.push([
      '<div class="portfolio-investment-card expanded">',
      '<div class="portfolio-investment-card-main"><div class="portfolio-line">新增定投计划</div><div class="portfolio-meta">固定金额按执行时最新行情生成买入流水</div></div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioInvestmentEditor({ id: 'new', frequency: 'monthly', time: '09:00', day: 1, month: 1, weekday: 1, fee: 0, enabled: true }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activePortfolioInvestmentPlanId !== 'new') {
    const emptyText = portfolioInvestmentListMode === 'archived'
      ? '暂无归档计划'
      : sourceItems.length ? '没有匹配的定投计划' : '暂无定投计划，可从右上角新增';
    parts.push('<div class="portfolio-empty">' + emptyText + '</div>');
  }
  parts.push(...items.map(plan => {
    const expanded = activePortfolioInvestmentPlanId === plan.id;
    const mode = plan.mode || 'rmb';
    const lastDetail = portfolioInvestmentLastDetail(plan);
    const resultMetrics = plan.last_result === 'skipped'
      ? '跳过 ' + portfolioInvestmentDateTime(plan.last_skipped_scheduled_at) + ' · 累计 ' + Number(plan.skip_count || 0) + ' 次'
      : plan.last_price != null && plan.last_quantity != null && Number.isFinite(Number(plan.last_price)) && Number.isFinite(Number(plan.last_quantity))
      ? formatPortfolioMoney(plan.last_price, mode) + ' · ' + formatPortfolioNumber(plan.last_quantity, 6) + ' ' + portfolioQuantityUnit(mode)
      : plan.last_message || '尚无执行结果';
    return [
      '<div class="portfolio-investment-card' + (expanded ? ' expanded' : '') + '">',
      '<div class="portfolio-investment-card-main">',
      '<div class="portfolio-investment-card-head"><div><div class="portfolio-line">' + escapeHtml(plan.name || '未命名计划') + '</div><div class="portfolio-meta">' + escapeHtml(portfolioInvestmentFrequencyLabel(plan) + ' · ' + formatPortfolioMoney(plan.amount, mode) + (Number(plan.fee) > 0 ? ' · 手续费 ' + formatPortfolioMoney(plan.fee, mode) : '')) + '</div></div><span class="portfolio-investment-state ' + portfolioInvestmentStateClass(plan) + '">' + escapeHtml(portfolioInvestmentStateLabel(plan)) + '</span></div>',
      '<div class="portfolio-investment-timeline">',
      '<div class="portfolio-investment-timeline-marker"></div>',
      '<div><span>下一次执行</span><strong>' + escapeHtml(portfolioInvestmentNextRunLabel(plan)) + '</strong><small>' + escapeHtml(portfolioInvestmentWindowLabel(plan) + ' · ' + plan.position_name + ' · ' + portfolioModeLabel(mode)) + '</small></div>',
      '<div><span>最近结果</span><strong>' + escapeHtml(lastDetail) + '</strong><small>' + escapeHtml(resultMetrics) + '</small></div>',
      '<div class="portfolio-investment-upcoming"><span>' + (plan.archived_at ? '归档时间' : '后续安排') + '</span><strong>' + escapeHtml(plan.archived_at ? portfolioInvestmentDateTime(plan.archived_at) : (plan.upcoming_run_ats || []).slice(1, 4).map(portfolioInvestmentDateTime).join(' · ') || '暂无后续期次') + '</strong><small>' + escapeHtml(plan.archived_at ? '执行记录和绩效仍可查看及导出' : portfolioInvestmentProjectionSummary(plan) || '显示下一期之后的 3 个日期') + '</small></div>',
      '</div>',
      '</div>',
      '<div class="portfolio-investment-actions">',
      plan.archived_at ? [
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">' + (expanded ? '收起记录' : '查看记录') + '</button>',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="restorePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">恢复计划</button>',
        '<button class="btn-clear-sm" type="button" onclick="deletePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">永久删除</button>',
      ].join('') : [
      portfolioInvestmentCanExecute(plan)
        ? '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="executePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">立即执行</button>'
        : '<button class="btn-clear-sm btn-muted-sm" type="button" disabled>' + (plan.status === 'pending_start' ? '尚未开始' : '已结束') + '</button>',
      plan.status === 'completed'
        ? '<button class="btn-clear-sm btn-muted-sm" type="button" disabled>已结束</button>'
        : '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="togglePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\', ' + String(!plan.enabled) + ')">' + (plan.enabled ? '暂停' : '启用') + '</button>',
      portfolioInvestmentCanSkip(plan)
        ? '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="skipPortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\', \'' + escapeHtml(plan.pending_run_at) + '\')">跳过本期</button>'
        : '<button class="btn-clear-sm btn-muted-sm" type="button" disabled>不可跳过</button>',
      '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">' + (expanded ? '收起' : '编辑') + '</button>',
      '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="duplicatePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">复制</button>',
      '<button class="btn-clear-sm" type="button" onclick="archivePortfolioInvestmentPlan(\'' + escapeHtml(plan.id) + '\')">归档</button>',
      ].join(''),
      '</div>',
      expanded ? renderPortfolioInvestmentPerformance(plan) : '',
      expanded && !plan.archived_at ? buildPortfolioInvestmentEditor(plan) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}
