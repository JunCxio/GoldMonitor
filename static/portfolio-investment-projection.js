// ========== 定投预算投影 ==========
function portfolioInvestmentProjection(value) {
  const source = value && typeof value === 'object' && !Array.isArray(value) ? value : null;
  const targetCount = Number(source && source.target_count);
  if (!source || !Number.isFinite(targetCount) || targetCount <= 0) return null;
  return {
    mode: source.mode === 'usd' ? 'usd' : 'rmb',
    target_count: targetCount,
    completed_count: Math.max(0, Number(source.completed_count) || 0),
    remaining_count: Math.max(0, Number(source.remaining_count) || 0),
    planned_cost_per_run: Number(source.planned_cost_per_run),
    projected_total_cost: Number(source.projected_total_cost),
    projected_remaining_cost: Number(source.projected_remaining_cost),
    projected_completion_at: String(source.projected_completion_at || ''),
    completion_limited_by_window: source.completion_limited_by_window === true,
    completion_out_of_range: source.completion_out_of_range === true,
  };
}

function portfolioInvestmentProjectionDateTime(value) {
  const text = String(value || '').trim();
  if (!text) return '--';
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text.replace('T', ' ').slice(0, 16);
  return parsed.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

function portfolioInvestmentProjectionMarkup(value) {
  const projection = portfolioInvestmentProjection(value);
  if (!projection) return '';
  const completion = projection.remaining_count === 0
    ? '目标已完成'
    : projection.completion_limited_by_window
      ? '结束日期不足'
      : projection.completion_out_of_range
        ? '超出可计算范围'
        : portfolioInvestmentProjectionDateTime(projection.projected_completion_at);
  const notice = projection.completion_limited_by_window
    ? '<small class="portfolio-investment-projection-notice">当前结束日期不足以完成目标期数，请延长执行区间或减少目标期数。</small>'
    : '<small class="portfolio-investment-projection-notice">按每期固定金额与手续费估算，不改变实际执行金额。</small>';
  return [
    '<div class="portfolio-investment-projection">',
    '<div><span>预计总投入</span><strong>' + escapeHtml(formatPortfolioMoney(projection.projected_total_cost, projection.mode)) + '</strong><small>' + escapeHtml(String(projection.target_count) + ' 期计划预算') + '</small></div>',
    '<div><span>剩余投入</span><strong>' + escapeHtml(formatPortfolioMoney(projection.projected_remaining_cost, projection.mode)) + '</strong><small>' + escapeHtml('剩余 ' + String(projection.remaining_count) + ' 期') + '</small></div>',
    '<div><span>预计完成</span><strong>' + escapeHtml(completion) + '</strong><small>' + escapeHtml('每期 ' + formatPortfolioMoney(projection.planned_cost_per_run, projection.mode)) + '</small></div>',
    '</div>',
    notice,
  ].join('');
}

function portfolioInvestmentProjectionSummary(plan) {
  const projection = portfolioInvestmentProjection(plan && plan.projection);
  if (!projection) return '';
  if (projection.remaining_count === 0) return '目标预算已完成';
  const remaining = '剩余投入 ' + formatPortfolioMoney(projection.projected_remaining_cost, projection.mode);
  if (projection.completion_limited_by_window) return remaining + ' · 结束日期不足以完成目标';
  if (projection.completion_out_of_range) return remaining + ' · 完成日期超出可计算范围';
  return remaining + ' · 预计完成 ' + portfolioInvestmentProjectionDateTime(projection.projected_completion_at);
}

function portfolioInvestmentActualTrendMarkup(items, months) {
  const source = Array.isArray(items) ? items : [];
  if (!source.length) return '';
  const maxRmb = Math.max(...source.map(item => Math.max(0, Number(item.rmb_invested) || 0)), 0);
  const maxUsd = Math.max(...source.map(item => Math.max(0, Number(item.usd_invested) || 0)), 0);
  const barWidth = (value, maximum) => {
    const amount = Math.max(0, Number(value) || 0);
    if (!amount || !maximum) return 0;
    return Math.max(4, Math.min(100, amount / maximum * 100));
  };
  return [
    '<div class="portfolio-investment-actual-trend">',
    '<div class="portfolio-investment-actual-trend-head"><div><span>近' + escapeHtml(String(Number(months) || source.length)) + '个月投入趋势</span><small>只统计定投买入流水，人民币与美元分别按各自峰值缩放</small></div><div class="portfolio-investment-actual-trend-legend"><span class="rmb">人民币</span><span class="usd">美元</span></div></div>',
    '<div class="portfolio-investment-actual-trend-scroll"><div class="portfolio-investment-actual-trend-grid">',
    source.map(item => {
      const month = String(item.month || '');
      const monthLabel = month.length === 7 ? month.slice(2, 4) + '/' + month.slice(5, 7) : month;
      const rmb = Math.max(0, Number(item.rmb_invested) || 0);
      const usd = Math.max(0, Number(item.usd_invested) || 0);
      return [
        '<div class="portfolio-investment-actual-trend-item" title="' + escapeHtml(month + ' · 实际执行 ' + String(Number(item.execution_count) || 0) + ' 次') + '">',
        '<strong>' + escapeHtml(monthLabel) + '</strong>',
        '<div class="portfolio-investment-actual-trend-row rmb"><i style="width:' + escapeHtml(String(barWidth(rmb, maxRmb))) + '%"></i></div>',
        '<small>' + escapeHtml(formatPortfolioMoney(rmb, 'rmb')) + '</small>',
        '<div class="portfolio-investment-actual-trend-row usd"><i style="width:' + escapeHtml(String(barWidth(usd, maxUsd))) + '%"></i></div>',
        '<small>' + escapeHtml(formatPortfolioMoney(usd, 'usd')) + '</small>',
        '</div>',
      ].join('');
    }).join(''),
    '</div></div>',
    '</div>',
  ].join('');
}

function portfolioInvestmentReliabilityMarkup(summary, titlePrefix) {
  const source = summary && typeof summary === 'object' ? summary : {};
  const windowDays = Number(source.days || source.reliability_days) || 90;
  const automaticCount = Math.max(0, Number(source.automatic_execution_count) || 0);
  const onTimeCount = Math.max(0, Number(source.on_time_execution_count) || 0);
  const catchUpCount = Math.max(0, Number(source.catch_up_execution_count) || 0);
  const manualCount = Math.max(0, Number(source.manual_execution_count) || 0);
  const unclassifiedCount = Math.max(0, Number(source.unclassified_execution_count) || 0);
  const rate = source.on_time_rate == null || !Number.isFinite(Number(source.on_time_rate))
    ? null
    : Math.max(0, Math.min(100, Number(source.on_time_rate)));
  const notice = unclassifiedCount
    ? '<small class="portfolio-investment-reliability-notice">另有 ' + escapeHtml(String(unclassifiedCount)) + ' 条旧流水未记录执行类型，未计入按时率。</small>'
    : '';
  return [
    '<div class="portfolio-investment-reliability">',
    '<div class="portfolio-investment-reliability-head"><div><span>' + escapeHtml((titlePrefix ? String(titlePrefix) + ' · ' : '') + '近' + String(windowDays) + '天执行稳定性') + '</span><small>按时率只计算计划执行与补执行，手动执行单独列出</small></div></div>',
    '<div class="portfolio-investment-reliability-grid">',
    '<div class="on-time"><span>按时率</span><strong>' + escapeHtml(rate == null ? '--' : rate.toFixed(1) + '%') + '</strong><small>' + escapeHtml(automaticCount ? onTimeCount + '/' + automaticCount + ' 次自动执行' : '暂无自动执行记录') + '</small></div>',
    '<div class="catch-up"><span>补执行</span><strong>' + escapeHtml(String(catchUpCount)) + '</strong><small>应用恢复后执行</small></div>',
    '<div class="manual"><span>手动执行</span><strong>' + escapeHtml(String(manualCount)) + '</strong><small>不计入按时率</small></div>',
    '</div>',
    notice,
    '</div>',
  ].join('');
}

function portfolioInvestmentCommitmentRange(item) {
  const first = portfolioInvestmentProjectionDateTime(item && item.first_run_at);
  const last = portfolioInvestmentProjectionDateTime(item && item.last_run_at);
  return first === last ? first : first + ' 至 ' + last;
}

function portfolioInvestmentCommitmentItemsMarkup(items) {
  const source = Array.isArray(items) ? items : [];
  if (!source.length) {
    return '<div class="portfolio-investment-commitment-empty">未来 30 天暂无计划投入。</div>';
  }
  return '<div class="portfolio-investment-commitment-list">' + source.map(item => {
    const mode = item.mode === 'usd' ? 'usd' : 'rmb';
    return [
      '<div class="portfolio-investment-commitment-item">',
      '<div><strong>' + escapeHtml(item.name || '未命名计划') + '</strong><small>' + escapeHtml(portfolioInvestmentCommitmentRange(item)) + '</small></div>',
      '<div><strong>' + escapeHtml(formatPortfolioMoney(item.projected_cost, mode)) + '</strong><small>' + escapeHtml(String(Number(item.run_count) || 0) + ' 期 · 每期 ' + formatPortfolioMoney(item.planned_cost_per_run, mode)) + '</small></div>',
      '</div>',
    ].join('');
  }).join('') + '</div>';
}
