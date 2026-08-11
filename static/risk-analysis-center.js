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
