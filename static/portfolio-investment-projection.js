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
