// ========== 定投历史模拟 ==========
const PORTFOLIO_INVESTMENT_SIMULATION_WINDOWS = [7, 30, 90];

function portfolioInvestmentSimulationState(planId) {
  const id = String(planId || '');
  const current = portfolioInvestmentSimulations[id];
  if (current && typeof current === 'object') return current;
  return { days: 30, request_id: '', loading: false, result: null, message: '' };
}

function setPortfolioInvestmentSimulationDays(planId, days) {
  const id = String(planId || '');
  const selected = PORTFOLIO_INVESTMENT_SIMULATION_WINDOWS.includes(Number(days)) ? Number(days) : 30;
  const current = portfolioInvestmentSimulationState(id);
  portfolioInvestmentSimulations[id] = {
    ...current,
    days: selected,
    result: current.days === selected
      ? current.result
      : null,
    message: '',
  };
  renderPortfolio();
}

function requestPortfolioInvestmentSimulation(planId) {
  const id = String(planId || '');
  const current = portfolioInvestmentSimulationState(id);
  const requestId = String(++portfolioInvestmentSimulationSeq);
  portfolioInvestmentSimulations[id] = {
    ...current,
    request_id: requestId,
    loading: true,
    message: '',
  };
  renderPortfolio();
  socket.emit('simulate_portfolio_investment_plan', {
    id,
    days: current.days,
    request_id: requestId,
  });
}

function applyPortfolioInvestmentSimulation(data) {
  const id = String((data && data.id) || '');
  const current = portfolioInvestmentSimulations[id];
  if (!current || String(data.request_id || '') !== current.request_id) return;
  portfolioInvestmentSimulations[id] = {
    ...current,
    loading: false,
    result: data && data.result && typeof data.result === 'object' ? data.result : null,
    message: '',
  };
  if (activePortfolioInvestmentPlanId === id) renderPortfolio();
}

function applyPortfolioInvestmentSimulationError(data) {
  const id = String((data && data.id) || '');
  const current = portfolioInvestmentSimulations[id];
  if (!current || String(data.request_id || '') !== current.request_id) return;
  portfolioInvestmentSimulations[id] = {
    ...current,
    loading: false,
    result: null,
    message: String((data && data.message) || '历史模拟失败。'),
  };
  if (activePortfolioInvestmentPlanId === id) renderPortfolio();
}

function portfolioInvestmentSimulationCoverageLabel(result) {
  const scheduled = Math.max(0, Number(result && result.scheduled_count) || 0);
  const covered = Math.max(0, Number(result && result.covered_count) || 0);
  if (!scheduled) return { text: '窗口内无期次', tone: 'empty' };
  if (!covered) return { text: '无可用行情', tone: 'missing' };
  if (covered < scheduled) return { text: '部分覆盖', tone: 'partial' };
  return { text: '完整覆盖', tone: 'complete' };
}

function portfolioInvestmentSimulationDuration(seconds) {
  const value = Math.max(0, Number(seconds) || 0);
  if (!value) return '无明显缺口';
  if (value < 3600) return Math.max(1, Math.round(value / 60)) + ' 分钟';
  if (value < 86400) return Math.max(1, Math.round(value / 3600)) + ' 小时';
  return Math.max(1, Math.round(value / 86400)) + ' 天';
}

function portfolioInvestmentSimulationConfidenceMarkup(result) {
  const confidence = result && result.confidence && typeof result.confidence === 'object'
    ? result.confidence
    : {};
  const quality = result && result.coverage && result.coverage.data_quality && typeof result.coverage.data_quality === 'object'
    ? result.coverage.data_quality
    : {};
  const granularity = quality.granularity && typeof quality.granularity === 'object'
    ? quality.granularity
    : {};
  const reasons = Array.isArray(confidence.reasons) ? confidence.reasons : [];
  const score = Number.isFinite(Number(confidence.score)) ? Math.max(0, Math.min(100, Number(confidence.score))) : null;
  const density = Number.isFinite(Number(quality.density_percent)) ? Number(quality.density_percent).toFixed(0) + '%' : '--';
  const range = Number.isFinite(Number(quality.range_coverage_percent)) ? Number(quality.range_coverage_percent).toFixed(0) + '%' : '--';
  const level = ['high', 'medium', 'low', 'unavailable'].includes(confidence.level) ? confidence.level : 'unavailable';
  return [
    '<section class="portfolio-investment-simulation-confidence ' + level + '">',
    '<div class="portfolio-investment-simulation-confidence-score"><span>结果可信度</span><strong>' + escapeHtml(confidence.label || '无法评估') + '</strong><small>' + escapeHtml(score == null ? '暂无评分' : score.toFixed(0) + ' / 100') + '</small></div>',
    '<div class="portfolio-investment-simulation-confidence-body"><strong>' + escapeHtml(confidence.summary || '历史数据质量信息不足。') + '</strong><div class="portfolio-investment-simulation-quality-facts">',
    '<span>范围 ' + escapeHtml(range) + '</span>',
    '<span>完整度 ' + escapeHtml(density) + '</span>',
    '<span>' + escapeHtml(granularity.label || '无法判断粒度') + '</span>',
    '<span>' + escapeHtml(String(Math.max(0, Number(quality.gap_count) || 0)) + ' 个缺口') + '</span>',
    '</div>',
    reasons.length ? '<ul>' + reasons.map(reason => '<li>' + escapeHtml(reason) + '</li>').join('') + '</ul>' : '',
    '</div>',
    '</section>',
  ].join('');
}

function portfolioInvestmentSimulationGapMarkup(result) {
  const quality = result && result.coverage && result.coverage.data_quality && typeof result.coverage.data_quality === 'object'
    ? result.coverage.data_quality
    : {};
  const gaps = Array.isArray(quality.gaps) ? quality.gaps : [];
  if (!gaps.length) return '';
  const positionLabel = { leading: '窗口开头', internal: '窗口中段', trailing: '窗口末端' };
  return [
    '<details class="portfolio-investment-simulation-gaps">',
    '<summary>查看 ' + escapeHtml(String(gaps.length)) + ' 个主要行情缺口</summary>',
    '<div>',
    gaps.map(item => [
      '<div>',
      '<span><strong>' + escapeHtml(positionLabel[item.position] || '时间区间') + '</strong><small>' + escapeHtml(portfolioInvestmentDateTime(item.start_timestamp) + ' 至 ' + portfolioInvestmentDateTime(item.end_timestamp)) + '</small></span>',
      '<span><strong>' + escapeHtml(portfolioInvestmentSimulationDuration(item.duration_seconds)) + '</strong><small>估算缺失 ' + escapeHtml(String(Math.max(0, Number(item.estimated_missing_points) || 0))) + ' 个样本</small></span>',
      '</div>',
    ].join('')).join(''),
    '</div>',
    '</details>',
  ].join('');
}

function portfolioInvestmentSimulationExecutionMarkup(result) {
  const executions = Array.isArray(result && result.executions) ? result.executions : [];
  if (!executions.length) return '<div class="portfolio-investment-simulation-empty">所选范围内没有计划期次。</div>';
  return [
    '<details class="portfolio-investment-simulation-runs">',
    '<summary>查看 ' + escapeHtml(String(executions.length)) + ' 个模拟期次</summary>',
    '<div>',
    executions.map(item => {
      const estimated = item.status === 'estimated';
      const detail = estimated
        ? formatPortfolioMoney(item.price, result.mode) + ' · ' + formatPortfolioNumber(item.quantity, 8) + ' ' + portfolioQuantityUnit(result.mode)
        : '附近没有可用行情样本';
      const sample = estimated
        ? '样本 ' + portfolioInvestmentDateTime(item.sample_timestamp)
        : '未参与汇总';
      return '<div class="' + (estimated ? 'covered' : 'missing') + '"><span><strong>' + escapeHtml(portfolioInvestmentDateTime(item.scheduled_at)) + '</strong><small>' + escapeHtml(sample) + '</small></span><span><strong>' + escapeHtml(estimated ? formatPortfolioMoney(item.total_cost, result.mode) : '--') + '</strong><small>' + escapeHtml(detail) + '</small></span></div>';
    }).join(''),
    '</div>',
    '</details>',
  ].join('');
}

function portfolioInvestmentSimulationResultMarkup(result) {
  if (!result || typeof result !== 'object') return '';
  const coverage = portfolioInvestmentSimulationCoverageLabel(result);
  const coverageData = result.coverage && typeof result.coverage === 'object' ? result.coverage : {};
  const scheduled = Math.max(0, Number(result.scheduled_count) || 0);
  const covered = Math.max(0, Number(result.covered_count) || 0);
  const coveredPercent = scheduled ? covered / scheduled * 100 : null;
  const pnlText = result.pnl == null
    ? '--'
    : formatPortfolioSignedMoney(result.pnl, result.mode) + ' · ' + formatPortfolioPercent(result.pnl_percent);
  const valuationText = result.latest_price == null
    ? '范围末端无邻近行情，未估算市值'
    : '末端样本 ' + portfolioInvestmentDateTime(result.latest_price_timestamp);
  const qualityData = coverageData.data_quality && typeof coverageData.data_quality === 'object' ? coverageData.data_quality : {};
  const qualityRangeText = qualityData.requested_start_timestamp
    ? portfolioInvestmentDateTime(qualityData.requested_start_timestamp)
    : '--';
  const qualityRangeEndText = qualityData.requested_end_timestamp
    ? '至 ' + portfolioInvestmentDateTime(qualityData.requested_end_timestamp)
    : '没有请求范围';
  return [
    '<div class="portfolio-investment-simulation-result">',
    portfolioInvestmentSimulationConfidenceMarkup(result),
    '<div class="portfolio-investment-simulation-coverage">',
    '<div><span>行情覆盖</span><strong class="' + coverage.tone + '">' + escapeHtml(coverage.text) + '</strong><small>' + escapeHtml(scheduled ? covered + '/' + scheduled + ' 期 · ' + (coveredPercent == null ? '--' : coveredPercent.toFixed(0) + '%') : '当前计划在窗口内未产生期次') + '</small></div>',
    '<div><span>本地样本</span><strong>' + escapeHtml(String(Number(coverageData.point_count) || 0) + ' 个') + '</strong><small>' + escapeHtml(coverageData.interval_label || '样本不足') + '</small></div>',
    '<div><span>数据区间</span><strong>' + escapeHtml(coverageData.first_timestamp ? portfolioInvestmentDateTime(coverageData.first_timestamp) : '--') + '</strong><small>' + escapeHtml(coverageData.last_timestamp ? '至 ' + portfolioInvestmentDateTime(coverageData.last_timestamp) : '没有可用历史行情') + '</small></div>',
    '<div><span>请求范围</span><strong>' + escapeHtml(qualityRangeText) + '</strong><small>' + escapeHtml(qualityRangeEndText) + '</small></div>',
    '<div><span>最大缺口</span><strong>' + escapeHtml(portfolioInvestmentSimulationDuration(qualityData.largest_gap_seconds)) + '</strong><small>' + escapeHtml((Number(qualityData.gap_count) || 0) ? String(Number(qualityData.gap_count) || 0) + ' 个明显缺口' : '当前粒度下未发现明显缺口') + '</small></div>',
    '</div>',
    portfolioInvestmentSimulationGapMarkup(result),
    result.usable ? [
      '<div class="portfolio-investment-simulation-metrics">',
      '<div><span>计划买入</span><strong>' + escapeHtml(formatPortfolioMoney(result.planned_amount, result.mode)) + '</strong><small>已覆盖支出 ' + escapeHtml(formatPortfolioMoney(result.actual_cost, result.mode)) + '</small></div>',
      '<div><span>估算均价</span><strong>' + escapeHtml(formatPortfolioMoney(result.average_price, result.mode)) + '</strong><small>累计 ' + escapeHtml(formatPortfolioNumber(result.quantity, 8) + ' ' + portfolioQuantityUnit(result.mode)) + '</small></div>',
      '<div><span>估算市值</span><strong>' + escapeHtml(result.market_value == null ? '--' : formatPortfolioMoney(result.market_value, result.mode)) + '</strong><small>' + escapeHtml(valuationText) + '</small></div>',
      '<div><span>估算盈亏</span><strong class="' + portfolioPnlClass(result.pnl) + '">' + escapeHtml(pnlText) + '</strong><small>仅对已覆盖期次计算</small></div>',
      '</div>',
    ].join('') : '<div class="portfolio-investment-simulation-empty">当前本地历史行情不足，无法对所选期次进行估算。</div>',
    portfolioInvestmentSimulationExecutionMarkup(result),
    '</div>',
  ].join('');
}

function portfolioInvestmentSimulationMarkup(plan) {
  const state = portfolioInvestmentSimulationState(plan && plan.id);
  return [
    '<section class="portfolio-investment-simulation">',
    '<div class="portfolio-investment-simulation-head"><div><span>历史模拟</span><small>按当前计划回看本地行情覆盖情况</small></div><div class="portfolio-investment-simulation-controls">',
    '<label><span class="sr-only">模拟范围</span><select onchange="setPortfolioInvestmentSimulationDays(\'' + escapeHtml(plan.id) + '\', this.value)"' + (state.loading ? ' disabled' : '') + '>',
    PORTFOLIO_INVESTMENT_SIMULATION_WINDOWS.map(days => '<option value="' + days + '"' + (state.days === days ? ' selected' : '') + '>近 ' + days + ' 天</option>').join(''),
    '</select></label>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="requestPortfolioInvestmentSimulation(\'' + escapeHtml(plan.id) + '\')"' + (state.loading ? ' disabled' : '') + '>' + (state.loading ? '计算中' : '运行模拟') + '</button>',
    '</div></div>',
    state.loading ? '<div class="portfolio-investment-simulation-loading">正在读取本地历史行情并匹配计划期次...</div>' : '',
    state.message ? '<div class="portfolio-investment-simulation-error">' + escapeHtml(state.message) + '</div>' : '',
    !state.loading && !state.message ? portfolioInvestmentSimulationResultMarkup(state.result) : '',
    '<small class="portfolio-investment-simulation-notice">基于本地历史样本估算，不代表真实成交、滑点或历史真实收益；模拟不会写入持仓和流水。</small>',
    '</section>',
  ].join('');
}
