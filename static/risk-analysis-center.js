let riskAnalysisRunning = false;
let riskAnalysisHistory = [];
let riskComparisonSelection = [];
let pendingRiskForceTrigger = null;

function registerRiskAnalysisSocketHandlers(socket) {
  socket.on('risk_analysis_status', data => {
    riskAnalysisRunning = !!(data && data.running);
    if (data && data.message) {
      applyRiskStatus(data.message, riskAnalysisRunning ? 'loading' : '');
    }
    updateRiskButtonState();
  });

  socket.on('risk_analysis_result', data => {
    riskAnalysisRunning = false;
    const usageText = formatRiskUsage(data && data.usage ? data.usage : null);
    renderRiskDiagnostic(null);
    applyRiskStatus(usageText ? '分析完成。' + usageText : '分析完成。', '');
    renderRiskSnapshot(data && data.snapshot ? data.snapshot : null);
    renderRiskStructured(data && data.structured ? data.structured : null);
    document.getElementById('riskResult').textContent = data && data.content ? data.content : '未返回分析内容。';
    pendingRiskForceTrigger = null;
    setRiskForceButtonVisible(false);
    if (data && data.snapshot) {
      addChartEvent({
        type: 'risk',
        level: 'analysis',
        timestamp: data.snapshot.analysis_time || '',
        label: data.structured && data.structured.risk_level ? '风险 ' + data.structured.risk_level : '风险分析',
        message: data.content || '',
      });
    }
    updateRiskButtonState();
  });

  socket.on('risk_analysis_error', data => {
    riskAnalysisRunning = false;
    applyRiskStatus(data && data.message ? data.message : '风险分析失败。', 'error');
    renderRiskDiagnostic(data && data.diagnostic ? data.diagnostic : null);
    if (data && data.snapshot) renderRiskSnapshot(data.snapshot);
    updateRiskButtonState();
  });

  socket.on('risk_analysis_cache_hit', data => {
    riskAnalysisRunning = false;
    renderRiskDiagnostic(null);
    const age = data && data.cache_age_seconds != null ? Math.max(0, Number(data.cache_age_seconds)) : 0;
    const ageText = age >= 60 ? Math.floor(age / 60) + ' 分钟前' : Math.max(1, age) + ' 秒前';
    applyRiskStatus((data && data.message ? data.message : '已复用最近同一行情分析。') + ' 生成于 ' + ageText + '。', '');
    renderRiskSnapshot(data && data.snapshot ? data.snapshot : null);
    renderRiskStructured(data && data.structured ? data.structured : null);
    document.getElementById('riskResult').textContent = data && data.content ? data.content : '暂无缓存分析内容。';
    pendingRiskForceTrigger = data && data.trigger ? data.trigger : null;
    setRiskForceButtonVisible(true);
    if (data && data.snapshot) {
      addChartEvent({
        type: 'risk',
        level: 'analysis',
        timestamp: data.snapshot.analysis_time || '',
        label: data.structured && data.structured.risk_level ? '风险 ' + data.structured.risk_level : '风险分析',
        message: data.content || '',
      });
    }
    updateRiskButtonState();
  });

  socket.on('risk_analysis_history_updated', data => {
    applyRiskHistory(data || {});
  });

  socket.on('risk_model_test_result', data => {
    const el = document.getElementById('riskModelTestStatus');
    if (!el) return;
    el.textContent = data && data.message ? data.message : '模型测试完成。';
    el.className = 'model-test-status ' + (data && data.ok ? 'ok' : 'fail');
  });

  socket.on('open_risk_analysis', data => {
    if (!openRiskAnalysis()) return;
    if (data && data.run) requestRiskAnalysis({ source: data.source || 'floating_price' });
  });

  socket.on('risk_model_options_updated', data => {
    if (!data || data.provider !== 'deepseek') return;
    deepseekModelOptions = Array.isArray(data.models) && data.models.length ? data.models : deepseekModelOptions;
    const currentModel = document.getElementById('setDeepseekModel').value || appSettings.deepseek_model || 'deepseek-v4-pro';
    renderDeepseekModelOptions(currentModel);
    const status = document.getElementById('deepseekModelStatus');
    if (status) {
      status.textContent = data.error
        ? data.error + ' 当前显示兜底模型。'
        : '模型列表已更新，来源：' + (data.source === 'api' ? '接口' : '兜底列表') + '。';
      status.dataset.state = data.error ? 'error' : 'ok';
    }
  });
}

// ========== 风险分析助手 ==========
function selectedRiskPrice(data) {
  const source = data || latestData || {};
  return currentMode === 'usd' ? source.usd : source.rmb;
}

function hasRiskAnalysisInput(data) {
  const price = Number(selectedRiskPrice(data));
  return Number.isFinite(price) && price > 0;
}

function riskAnalysisUnavailableMessage() {
  if (!hasRiskAnalysisInput()) return '当前没有可用于风险分析的行情价格，请先重新获取行情数据。';
  const retry = document.getElementById('priceRetry');
  if (retry && retry.classList.contains('show')) return '当前行情状态异常，请先重新获取行情数据后再分析。';
  return '';
}

function updateRiskEntryState() {
  const riskAnalyzeButton = document.getElementById('riskAnalyzeButton');
  const available = !riskAnalysisUnavailableMessage();
  if (riskAnalyzeButton) {
    riskAnalyzeButton.hidden = !available;
    riskAnalyzeButton.disabled = !available || !appSettings.risk_assistant_enabled;
    riskAnalyzeButton.setAttribute('aria-hidden', available ? 'false' : 'true');
  }
  document.querySelectorAll('.source-risk-action').forEach(button => {
    button.hidden = !available;
    button.disabled = !available || !appSettings.risk_assistant_enabled;
    button.setAttribute('aria-hidden', available ? 'false' : 'true');
  });
}

function openRiskAnalysis() {
  const riskUnavailable = riskAnalysisUnavailableMessage();
  if (riskUnavailable) {
    applyFetchStatus({ ok:false, message:riskUnavailable, retryable:true });
    return false;
  }
  document.getElementById('riskBackdrop').classList.add('show');
  socket.emit('get_risk_analysis_history');
  const providerMessage = riskProviderErrorMessage();
  if (!appSettings.risk_assistant_enabled) {
    applyRiskStatus('风险分析助手已关闭，请先在设置中启用。', 'error');
  } else if (providerMessage) {
    applyRiskStatus(providerMessage, 'error');
  } else if (!document.getElementById('riskResult').textContent || document.getElementById('riskResult').textContent === '暂无分析结果。') {
    applyRiskStatus('点击开始分析，助手会基于当前行情生成风险趋势判断。', '');
  }
  updateRiskButtonState();
  return true;
}

function closeRiskAnalysis() {
  document.getElementById('riskBackdrop').classList.remove('show');
}

function onRiskBackdrop(event) {
  if (event.target.id === 'riskBackdrop') closeRiskAnalysis();
}

function applyRiskStatus(message, type) {
  const statusEl = document.getElementById('riskStatus');
  statusEl.textContent = message || '';
  statusEl.className = 'risk-status' + (type ? ' ' + type : '');
}

function renderRiskDiagnostic(diagnostic) {
  const el = document.getElementById('riskDiagnostic');
  if (!el) return;
  if (!diagnostic) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const provider = [diagnostic.provider, diagnostic.model].filter(Boolean).join(' / ');
  const recovery = Array.isArray(diagnostic.recovery) ? diagnostic.recovery.filter(Boolean) : [];
  const recoveryHtml = recovery.length
    ? '<ul class="risk-diagnostic-list">' + recovery.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ul>'
    : '<div>' + escapeHtml('稍后重试；如果问题持续，请导出诊断报告核对配置和网络状态。') + '</div>';
  el.innerHTML = [
    '<div class="risk-diagnostic-title">失败原因 · ' + escapeHtml(diagnostic.title || '风险分析失败') + '</div>',
    provider ? '<div class="risk-diagnostic-meta">模型 ' + escapeHtml(provider) + '</div>' : '',
    '<div class="risk-diagnostic-section"><strong>原因</strong><div>' + escapeHtml(diagnostic.reason || '未知错误') + '</div></div>',
    '<div class="risk-diagnostic-section"><strong>影响</strong><div>' + escapeHtml(diagnostic.impact || '风险分析未生成，本次不会写入分析历史。') + '</div></div>',
    '<div class="risk-diagnostic-section"><strong>建议处理</strong>' + recoveryHtml + '</div>',
  ].join('');
  el.classList.add('show');
}

function updateRiskButtonState() {
  const runBtn = document.getElementById('riskRunButton');
  const forceBtn = document.getElementById('riskForceRunButton');
  const riskUnavailable = riskAnalysisUnavailableMessage();
  const disabled = riskAnalysisRunning || !appSettings.risk_assistant_enabled || !!riskProviderErrorMessage() || !!riskUnavailable;
  if (runBtn) {
    runBtn.disabled = disabled;
    runBtn.textContent = riskAnalysisRunning ? '分析中...' : '开始分析';
  }
  if (forceBtn) forceBtn.disabled = disabled;
  updateRiskEntryState();
}

function requestRiskAnalysis(trigger, force) {
  if (riskAnalysisRunning) return;
  const riskUnavailable = riskAnalysisUnavailableMessage();
  if (riskUnavailable) {
    applyRiskStatus(riskUnavailable, 'error');
    updateRiskButtonState();
    return;
  }
  if (!appSettings.risk_assistant_enabled) {
    applyRiskStatus('风险分析助手已关闭，请先在设置中启用。', 'error');
    return;
  }
  const providerMessage = riskProviderErrorMessage();
  if (providerMessage) {
    applyRiskStatus(providerMessage, 'error');
    return;
  }
  riskAnalysisRunning = true;
  document.getElementById('riskResult').textContent = '正在分析当前行情...';
  renderRiskDiagnostic(null);
  renderRiskSnapshot(null);
  renderRiskStructured(null);
  pendingRiskForceTrigger = null;
  setRiskForceButtonVisible(false);
  applyRiskStatus('正在生成风险分析...', 'loading');
  updateRiskButtonState();
  socket.emit('request_risk_analysis', Object.assign({}, trigger ? { trigger } : {}, force ? { force: true } : {}));
}

function setRiskForceButtonVisible(visible) {
  const btn = document.getElementById('riskForceRunButton');
  if (btn) btn.style.display = visible ? '' : 'none';
}

function rerunRiskAnalysis() {
  requestRiskAnalysis(pendingRiskForceTrigger || null, true);
}

function riskProviderErrorMessage() {
  const provider = appSettings.risk_assistant_provider || 'deepseek';
  if (provider === 'deepseek') {
    if (!appSettings.deepseek_api_key_configured) return '请先在设置中配置 DeepSeek API Key。';
    if (!appSettings.deepseek_model) return '请先选择 DeepSeek 模型。';
    return '';
  }
  if (provider === 'openai_compatible') {
    if (!appSettings.openai_compatible_base_url) return '请先配置兼容接口地址。';
    if (!appSettings.openai_compatible_model) return '请先配置兼容模型。';
    if (!appSettings.openai_compatible_api_key_configured) return '请先配置兼容 API Key。';
    return '';
  }
  return '当前模型提供商暂不支持。';
}

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

function clearRiskHistory() {
  if (riskAnalysisRunning) return;
  socket.emit('clear_risk_analysis_history');
}

function currentRiskReportMarkdown() {
  const result = document.getElementById('riskResult').textContent || '';
  const meta = Array.from(document.querySelectorAll('#riskMeta span')).map(item => item.textContent).join('\n');
  const evidence = document.getElementById('riskEvidence') ? document.getElementById('riskEvidence').innerText.trim() : '';
  const parts = ['# 风险分析报告'];
  if (meta) parts.push('', '## 数据快照', meta);
  if (evidence) parts.push('', '## 数据依据', evidence);
  parts.push('', '## 分析内容', result || '暂无分析结果。');
  return parts.join('\n');
}

function copyRiskReport() {
  const content = currentRiskReportMarkdown();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(content).then(() => applyRiskStatus('报告已复制。', '')).catch(() => applyRiskStatus('复制失败，请手动选择内容。', 'error'));
    return;
  }
  applyRiskStatus('当前环境不支持自动复制，请手动选择内容。', 'error');
}

function exportRiskReport() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  downloadText('GoldMonitor-risk-report-' + stamp + '.md', currentRiskReportMarkdown(), 'text/markdown;charset=utf-8');
  applyRiskStatus('报告已导出。', '');
}
