function clearRenderedRiskComparison() {
  const comparison = document.getElementById('riskComparison');
  if (!comparison) return;
  comparison.innerHTML = '';
  comparison.hidden = true;
}

function toggleRiskComparisonItem(index) {
  if (!Number.isInteger(index) || !riskAnalysisHistory[index]) return;
  const selectedIndex = riskComparisonSelection.indexOf(index);
  if (selectedIndex >= 0) {
    riskComparisonSelection.splice(selectedIndex, 1);
    clearRenderedRiskComparison();
    applyRiskStatus('已取消该条对比选择。', '');
    renderRiskHistory();
    return;
  }
  if (riskComparisonSelection.length >= 2) {
    applyRiskStatus('最多选择两条风险分析，请先取消一条已选记录。', 'error');
    return;
  }
  riskComparisonSelection.push(index);
  clearRenderedRiskComparison();
  applyRiskStatus(
    riskComparisonSelection.length === 2 ? '已选择两条风险分析，可以开始对比。' : '已选择一条风险分析，请再选择一条。',
    ''
  );
  renderRiskHistory();
}

function riskComparisonValue(value) {
  if (value === null || value === undefined || value === '') return '暂无';
  if (typeof value === 'number' && !Number.isFinite(value)) return '暂无';
  return String(value);
}

function riskComparisonNumber(value, suffix) {
  if (value === null || value === undefined || value === '') return '暂无';
  const number = Number(value);
  if (!Number.isFinite(number)) return '暂无';
  return number.toLocaleString('en-US', { maximumFractionDigits: 4 }) + (suffix || '');
}

function riskComparisonSource(snapshot, sourceKey, cachedKey) {
  const source = snapshot && snapshot[sourceKey];
  if (!source) return '暂无';
  const cached = snapshot[cachedKey];
  const state = cached === true ? '缓存' : cached === false ? '实时' : '状态暂无';
  return String(source) + ' · ' + state;
}

function riskComparisonQuality(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return '暂无';
  const marketQuality = snapshot.market_quality && Object.keys(snapshot.market_quality).length
    ? snapshot.market_quality
    : null;
  const quality = marketQuality || (snapshot.data_quality && Object.keys(snapshot.data_quality).length ? snapshot.data_quality : null);
  if (!quality) return '暂无';
  const score = riskComparisonValue(quality.score);
  const label = riskComparisonValue(quality.label || quality.level);
  if (score === '暂无' && label === '暂无') return '暂无';
  if (score === '暂无') return label;
  if (label === '暂无') return score + '分';
  return score + '分 · ' + label;
}

function riskComparisonSamples(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return '暂无';
  const values = [
    ['历史', snapshot.history_points, '点'],
    ['K线', snapshot.kline_points, '根'],
    ['资讯', snapshot.news_count, '条'],
  ].filter(item => item[1] !== null && item[1] !== undefined && item[1] !== '');
  if (!values.length) return '暂无';
  return values.map(item => item[0] + ' ' + riskComparisonNumber(item[1], item[2])).join(' · ');
}

function riskComparisonEntryTime(item) {
  if (!item || typeof item !== 'object') return '';
  return item.analysis_time || (item.snapshot && item.snapshot.analysis_time) || '';
}

function riskComparisonParsedTime(item) {
  const value = riskComparisonEntryTime(item);
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function riskComparisonRow(field, label, earlierValue, laterValue, sideLabels) {
  const earlierText = riskComparisonValue(earlierValue);
  const laterText = riskComparisonValue(laterValue);
  const changedClass = earlierText === laterText ? '' : ' changed';
  const labels = sideLabels || { earlier: '较早', later: '较新' };
  return [
    '<div class="risk-comparison-row' + changedClass + '" data-field="' + escapeHtml(field) + '">',
    '<div class="risk-comparison-label">' + escapeHtml(label) + '</div>',
    '<div class="risk-comparison-value" data-side="earlier" data-side-label="' + escapeHtml(labels.earlier) + '">' + escapeHtml(earlierText) + '</div>',
    '<div class="risk-comparison-value" data-side="later" data-side-label="' + escapeHtml(labels.later) + '">' + escapeHtml(laterText) + '</div>',
    '</div>',
  ].join('');
}

function renderRiskComparison(earlier, later, sideLabels) {
  const comparison = document.getElementById('riskComparison');
  if (!comparison) return;
  const labels = sideLabels || { earlier: '较早', later: '较新' };
  const earlierSnapshot = earlier && earlier.snapshot && typeof earlier.snapshot === 'object' ? earlier.snapshot : {};
  const laterSnapshot = later && later.snapshot && typeof later.snapshot === 'object' ? later.snapshot : {};
  const earlierStructured = earlier && earlier.structured && typeof earlier.structured === 'object' ? earlier.structured : {};
  const laterStructured = later && later.structured && typeof later.structured === 'object' ? later.structured : {};
  const earlierScorecard = earlierSnapshot.risk_scorecard && typeof earlierSnapshot.risk_scorecard === 'object' ? earlierSnapshot.risk_scorecard : {};
  const laterScorecard = laterSnapshot.risk_scorecard && typeof laterSnapshot.risk_scorecard === 'object' ? laterSnapshot.risk_scorecard : {};
  const structuredFields = [
    ['risk_level', '风险等级'],
    ['trend_direction', '趋势方向'],
    ['data_credibility', '数据可信度'],
    ['main_factors', '主要影响因素'],
    ['watch_range', '观察价格区间'],
    ['follow_up', '后续关注'],
  ];
  const scorecardFields = [
    ['overall_risk', '总体风险'],
    ['trend_strength', '趋势强度'],
    ['volatility_risk', '波动风险'],
    ['fx_impact', '汇率影响'],
    ['event_risk', '事件风险'],
    ['data_credibility', '数据可信度'],
  ];
  const snapshotFields = [
    ['price_rmb', '人民币克价', item => riskComparisonNumber(item.price_rmb, ' 元/克')],
    ['price_usd', '国际金价', item => riskComparisonNumber(item.price_usd, ' 美元/盎司')],
    ['usdcny_rate', '美元人民币汇率', item => riskComparisonNumber(item.usdcny_rate, '')],
    ['gold_source', '金价来源', item => riskComparisonSource(item, 'gold_source', 'gold_cached')],
    ['rate_source', '汇率来源', item => riskComparisonSource(item, 'rate_source', 'rate_cached')],
    ['quality', '行情质量', item => riskComparisonQuality(item)],
    ['samples', '样本规模', item => riskComparisonSamples(item)],
  ];
  const section = (title, rows) => [
    '<section class="risk-comparison-section">',
    '<div class="risk-comparison-title">' + escapeHtml(title) + '</div>',
    '<div class="risk-comparison-grid">' + rows.join('') + '</div>',
    '</section>',
  ].join('');
  const earlierProvider = [earlier.provider, earlier.model].filter(Boolean).join(' / ') || '暂无';
  const laterProvider = [later.provider, later.model].filter(Boolean).join(' / ') || '暂无';
  comparison.innerHTML = [
    '<div class="risk-comparison-head">',
    '<div class="risk-block-title">风险分析对比</div>',
    '<div class="risk-comparison-sides">',
    '<div class="risk-comparison-side" data-side="earlier"><strong>' + escapeHtml(labels.earlier) + '</strong><span>' + escapeHtml(riskComparisonValue(riskComparisonEntryTime(earlier))) + '</span><span>' + escapeHtml(earlierProvider) + '</span></div>',
    '<div class="risk-comparison-side" data-side="later"><strong>' + escapeHtml(labels.later) + '</strong><span>' + escapeHtml(riskComparisonValue(riskComparisonEntryTime(later))) + '</span><span>' + escapeHtml(laterProvider) + '</span></div>',
    '</div>',
    '</div>',
    section('结构化字段', structuredFields.map(item => riskComparisonRow(item[0], item[1], earlierStructured[item[0]], laterStructured[item[0]], labels))),
    section('风险评分卡', scorecardFields.map(item => riskComparisonRow(item[0], item[1], earlierScorecard[item[0]], laterScorecard[item[0]], labels))),
    section('行情快照', snapshotFields.map(item => riskComparisonRow(item[0], item[1], item[2](earlierSnapshot), item[2](laterSnapshot), labels))),
  ].join('');
  comparison.hidden = false;
}

function compareSelectedRiskHistory() {
  if (riskComparisonSelection.length !== 2) {
    applyRiskStatus('请选择两条风险分析后再对比。', 'error');
    return;
  }
  const selected = riskComparisonSelection.map(index => riskAnalysisHistory[index]);
  if (selected.some(item => !item)) {
    riskComparisonSelection = [];
    clearRenderedRiskComparison();
    renderRiskHistory();
    applyRiskStatus('所选历史记录已更新，请重新选择两条风险分析。', 'error');
    return;
  }
  let earlier = selected[0];
  let later = selected[1];
  const earlierTime = riskComparisonParsedTime(earlier);
  const laterTime = riskComparisonParsedTime(later);
  const timesAreComparable = earlierTime !== null && laterTime !== null;
  const sideLabels = timesAreComparable
    ? { earlier: '较早', later: '较新' }
    : { earlier: '记录一', later: '记录二' };
  if (timesAreComparable && earlierTime > laterTime) {
    earlier = selected[1];
    later = selected[0];
  }
  renderRiskComparison(earlier, later, sideLabels);
  applyRiskStatus('已生成本地风险分析对比，不会调用模型。', '');
}

function openRiskHistoryItem(index) {
  const item = riskAnalysisHistory[index];
  if (!item) return;
  renderRiskSnapshot(item.snapshot || null);
  renderRiskStructured(item.structured || null);
  document.getElementById('riskResult').textContent = item.content || '历史记录无内容。';
  const usageText = formatRiskUsage(item.usage || null);
  applyRiskStatus(usageText ? '已打开历史分析。' + usageText : '已打开历史分析。', '');
}

function openRiskTimelineFromHistory(index) {
  const item = riskAnalysisHistory[index];
  if (!item) return;
  openEventTimelineAround(item.analysis_time || (item.snapshot && item.snapshot.analysis_time), 'risk_analysis', item.id);
}

function handleRiskHistoryTimelineClick(event) {
  const button = event.target && event.target.closest ? event.target.closest('[data-risk-timeline-index]') : null;
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openRiskTimelineFromHistory(Number(button.getAttribute('data-risk-timeline-index')));
}

document.addEventListener('click', handleRiskHistoryTimelineClick, true);

window.openRiskTimelineFromHistory = openRiskTimelineFromHistory;
