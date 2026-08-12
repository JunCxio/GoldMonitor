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
