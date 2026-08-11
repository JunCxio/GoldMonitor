function formatRiskNumber(value, suffix) {
  if (value === null || value === undefined || value === '') return '--';
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString('en-US', { maximumFractionDigits: 2 }) + (suffix || '');
}

function formatRiskUsage(usage) {
  if (!usage || usage.total_tokens == null) return '';
  return '本次用量 ' + usage.total_tokens + ' tokens。';
}

function renderRiskEvidence(snapshot) {
  const el = document.getElementById('riskEvidence');
  if (!el) return;
  if (!snapshot) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const evidence = snapshot.evidence_summary || {};
  const goldCached = evidence.gold_cached ? '缓存' : '实时';
  const rateCached = evidence.rate_cached ? '缓存' : '实时';
  const qualityLabel = evidence.quality_label || '--';
  const qualityScore = evidence.quality_score == null ? '--' : evidence.quality_score + '分';
  const items = [
    ['当前金价', 'RMB ' + formatRiskNumber(evidence.price_rmb ?? snapshot.price_rmb, '/克') + ' · USD ' + formatRiskNumber(evidence.price_usd ?? snapshot.price_usd, '/oz')],
    ['行情源', (evidence.gold_source || snapshot.gold_source || '--') + ' · ' + goldCached + (evidence.gold_time ? ' · ' + evidence.gold_time : '')],
    ['汇率源', (evidence.rate_source || snapshot.rate_source || '--') + ' · ' + rateCached + (evidence.rate_time ? ' · ' + evidence.rate_time : '')],
    ['样本规模', '历史 ' + (evidence.history_points ?? snapshot.history_points ?? 0) + ' 点 · 5分钟K线 ' + (evidence.kline_points ?? snapshot.kline_points ?? 0) + ' 根'],
    ['近期资讯', (evidence.news_count ?? snapshot.news_count ?? 0) + ' 条'],
    ['数据质量', qualityScore + ' · ' + qualityLabel],
  ];
  const missing = Array.isArray(evidence.missing) ? evidence.missing.filter(Boolean) : [];
  const recovery = Array.isArray(evidence.recovery) ? evidence.recovery.filter(Boolean) : [];
  const warning = missing.length || recovery.length
    ? '<div class="risk-evidence-warning"><strong>缺失数据</strong>：' + escapeHtml(missing.join('、') || '暂无') + '<br><strong>恢复建议</strong>：' + escapeHtml(recovery.join('；') || '继续等待数据更新') + '</div>'
    : '';
  const qualitySummary = evidence.quality_summary ? '<div class="risk-evidence-warning">' + escapeHtml(evidence.quality_summary) + '</div>' : '';
  el.innerHTML = [
    '<div class="risk-block-title">数据依据</div>',
    '<div class="risk-evidence-grid">',
    items.map(item => '<div class="risk-evidence-item"><div class="risk-evidence-label">' + escapeHtml(item[0]) + '</div><div class="risk-evidence-value">' + escapeHtml(item[1]) + '</div></div>').join(''),
    '</div>',
    warning + qualitySummary,
  ].join('');
  el.classList.add('show');
}

function renderRiskSnapshot(snapshot) {
  const meta = document.getElementById('riskMeta');
  if (!snapshot) {
    meta.innerHTML = '';
    meta.classList.remove('show');
    renderRiskEvidence(null);
    renderRiskQuality(null);
    renderRiskTrends(null);
    renderRiskScorecard(null);
    renderRiskStructured(null);
    return;
  }
  const items = [
    '时间 ' + (snapshot.analysis_time || '--'),
    'RMB ' + formatRiskNumber(snapshot.price_rmb, '/克'),
    'USD ' + formatRiskNumber(snapshot.price_usd, '/oz'),
    '汇率 ' + formatRiskNumber(snapshot.usdcny_rate, ''),
    '历史点 ' + (snapshot.history_points || 0),
    'K线 ' + (snapshot.kline_points || 0),
    '资讯 ' + (snapshot.news_count || 0),
  ];
  const marketQuality = snapshot.market_quality && Object.keys(snapshot.market_quality).length ? snapshot.market_quality : null;
  const quality = marketQuality || snapshot.data_quality || null;
  if (quality) items.push('行情质量 ' + quality.score + '分/' + (quality.label || quality.level || '--'));
  if (snapshot.sample_warning) items.push(snapshot.sample_warning);
  meta.innerHTML = items.map(item => '<span>' + escapeHtml(item) + '</span>').join('');
  meta.classList.add('show');
  renderRiskEvidence(snapshot);
  renderRiskQuality(quality);
  renderRiskTrends(snapshot.multi_period_trends || []);
  renderRiskScorecard(snapshot.risk_scorecard || null);
}

function renderRiskQuality(quality) {
  const el = document.getElementById('riskQuality');
  if (!quality) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const reasons = Array.isArray(quality.reasons) ? quality.reasons.filter(Boolean).join('；') : '';
  const summary = quality.summary || reasons || quality.label || '暂无说明';
  el.innerHTML = [
    '<div class="risk-block-title">行情质量</div>',
    '<div class="risk-quality-score">' + escapeHtml(quality.score == null ? '--' : quality.score) + '</div>',
    '<div class="risk-quality-level">等级 ' + escapeHtml(quality.level || '--') + '</div>',
    '<div class="risk-quality-summary">' + escapeHtml(summary) + '</div>',
  ].join('');
  el.classList.add('show');
}

function riskTrendClass(direction) {
  if (direction === '上行') return 'up';
  if (direction === '下行') return 'down';
  if (direction === '震荡') return 'flat';
  return 'missing';
}

function renderRiskTrends(trends) {
  const el = document.getElementById('riskTrends');
  if (!Array.isArray(trends) || !trends.length) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const items = trends.map(item => {
    const direction = item.direction_rmb || item.direction_usd || '样本不足';
    const pct = item.rmb && item.rmb.change_pct != null ? item.rmb.change_pct : item.usd && item.usd.change_pct;
    return [
      '<div class="risk-trend-item">',
      '<div class="risk-trend-period">' + escapeHtml(item.minutes || '--') + '分钟 · ' + escapeHtml(item.points || 0) + '点</div>',
      '<div class="risk-trend-direction ' + riskTrendClass(direction) + '">' + escapeHtml(direction) + '</div>',
      '<div class="risk-trend-change">变动 ' + escapeHtml(pct == null ? '--' : Number(pct).toFixed(2) + '%') + '</div>',
      '</div>',
    ].join('');
  }).join('');
  el.innerHTML = '<div class="risk-block-title">多周期趋势</div><div class="risk-trend-list">' + items + '</div>';
  el.classList.add('show');
}

function renderRiskScorecard(scorecard) {
  const el = document.getElementById('riskScorecard');
  if (!scorecard) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const items = [
    ['总体风险', scorecard.overall_risk],
    ['趋势强度', scorecard.trend_strength],
    ['波动风险', scorecard.volatility_risk],
    ['汇率影响', scorecard.fx_impact],
    ['事件风险', scorecard.event_risk],
    ['数据可信度', scorecard.data_credibility],
  ];
  el.innerHTML = '<div class="risk-block-title">风险评分卡</div><div class="risk-score-grid">' + items.map(item => (
    '<div class="risk-score-item"><div class="risk-score-label">' + escapeHtml(item[0]) + '</div><div class="risk-score-value">' + escapeHtml(item[1] == null ? '--' : item[1]) + '</div></div>'
  )).join('') + '</div>';
  el.classList.add('show');
}

function renderRiskStructured(structured) {
  const el = document.getElementById('riskStructured');
  if (!el) return;
  const labels = [
    ['risk_level', '风险等级'],
    ['trend_direction', '趋势方向'],
    ['data_credibility', '数据可信度'],
    ['main_factors', '主要影响因素'],
    ['watch_range', '观察价格区间'],
    ['follow_up', '后续关注'],
  ];
  const items = labels
    .map(([key, label]) => [label, structured && structured[key]])
    .filter(([, value]) => value);
  if (!items.length) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  el.innerHTML = items.map(([label, value]) => (
    '<div class="risk-structured-item"><div class="risk-structured-label">' + escapeHtml(label) + '</div><div class="risk-structured-value">' + escapeHtml(value) + '</div></div>'
  )).join('');
  el.classList.add('show');
}

function applyRiskHistory(data) {
  riskAnalysisHistory = Array.isArray(data && data.items) ? data.items : [];
  riskComparisonSelection = [];
  const comparison = document.getElementById('riskComparison');
  if (comparison) {
    comparison.innerHTML = '';
    comparison.hidden = true;
  }
  renderRiskHistory();
}

function renderRiskHistory() {
  const list = document.getElementById('riskHistoryList');
  const clearBtn = document.getElementById('riskClearHistoryButton');
  const compareBtn = document.getElementById('riskCompareButton');
  if (clearBtn) clearBtn.disabled = riskAnalysisHistory.length === 0;
  if (compareBtn) {
    compareBtn.disabled = riskComparisonSelection.length !== 2;
    compareBtn.textContent = riskComparisonSelection.length
      ? '对比所选（' + riskComparisonSelection.length + '/2）'
      : '对比所选';
  }
  if (!riskAnalysisHistory.length) {
    list.innerHTML = '<div class="risk-history-empty">暂无历史记录</div>';
    return;
  }
  list.innerHTML = riskAnalysisHistory.map((item, index) => {
    const firstLine = String(item.content || '').split('\n').find(Boolean) || '历史分析';
    const qualitySource = item.snapshot ? (item.snapshot.market_quality || item.snapshot.data_quality) : null;
    const quality = qualitySource ? ' · 行情质量 ' + qualitySource.score + '分' : '';
    const evidence = item.evidence_summary || (item.snapshot && item.snapshot.evidence_summary) || {};
    const samples = evidence.history_points != null || evidence.kline_points != null
      ? ' · 历史' + (evidence.history_points ?? 0) + '/K线' + (evidence.kline_points ?? 0)
      : '';
    const selectedForComparison = riskComparisonSelection.includes(index);
    return [
      '<div class="risk-history-item' + (selectedForComparison ? ' selected' : '') + '">',
      '<button class="risk-history-main" type="button" onclick="openRiskHistoryItem(' + index + ')">',
      '<div class="risk-history-time">' + escapeHtml(item.analysis_time || '--') + escapeHtml(quality) + escapeHtml(samples) + '</div>',
      '<div class="risk-history-text">' + escapeHtml(firstLine) + '</div>',
      '</button>',
      '<button class="btn-clear-sm btn-muted-sm risk-history-compare" type="button" aria-pressed="' + String(selectedForComparison) + '" onclick="toggleRiskComparisonItem(' + index + ')">' + (selectedForComparison ? '已选' : '选择对比') + '</button>',
      '<button class="btn-clear-sm btn-muted-sm risk-history-review" type="button" data-risk-timeline-index="' + index + '" onclick="window.openRiskTimelineFromHistory(' + index + ')">查看复盘</button>',
      '</div>',
    ].join('');
  }).join('');
}
