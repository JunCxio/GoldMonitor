function resetAlertRuleSimulation() {
  alertRuleSimulation = null;
  alertRuleSimulationLoading = false;
  alertRuleSimulationRequestId = '';
}

function invalidateAlertRuleSimulation() {
  const hadResult = alertRuleSimulationLoading || !!alertRuleSimulation;
  resetAlertRuleSimulation();
  if (!hadResult) return;
  const result = document.getElementById('alertRuleSimulationResult');
  if (result) result.innerHTML = '<div class="alert-center-simulation-empty">规则已修改，请重新运行历史模拟。</div>';
  setAlertRuleCenterStatus('规则已修改，请重新运行历史模拟。', '');
}

function openNewAlertRule(kind) {
  activeUnifiedAlertRuleId = 'new';
  activeAlertRuleDetailId = null;
  alertRuleDraft = cloneAlertRuleDraft(null);
  resetAlertRuleSimulation();
  if (kind && ['price_threshold', 'volatility', 'watch_target', 'portfolio'].includes(kind)) {
    alertRuleDraft.kind = kind;
  }
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
  requestAnimationFrame(() => document.getElementById('alertRuleName')?.focus());
}

function editUnifiedAlertRule(id) {
  const rule = findUnifiedAlertRule(id);
  if (!rule) {
    setAlertRuleCenterStatus('该规则已不存在，可从历史警报复制规则快照。', 'fail');
    return;
  }
  activeUnifiedAlertRuleId = id;
  activeAlertRuleDetailId = null;
  alertRuleDraft = cloneAlertRuleDraft(rule);
  resetAlertRuleSimulation();
  alertRuleFilter = 'all';
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
  requestAnimationFrame(() => document.getElementById('alertRuleName')?.focus());
}

function cancelUnifiedAlertRuleEdit() {
  activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  resetAlertRuleSimulation();
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
}

function refreshAlertRuleInsight(id) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  alertRuleInsightLoading[ruleId] = true;
  socket.emit('get_alert_rule_insight', { id: ruleId, days: 30 });
  renderAlertRuleCenter();
}

function toggleAlertRuleDetail(id) {
  const ruleId = String(id || '');
  activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  activeAlertRuleDetailId = activeAlertRuleDetailId === ruleId ? null : ruleId;
  if (activeAlertRuleDetailId && !alertRuleInsights[ruleId] && !alertRuleInsightLoading[ruleId]) {
    refreshAlertRuleInsight(ruleId);
    return;
  }
  renderAlertRuleCenter();
}

function alertRuleDiagnosticValue(value, rule, valueKind) {
  if (value == null || value === '') return '--';
  if (valueKind === 'percent') return alertRuleValueText(value, (rule.scope || {}).mode, '%');
  return alertRuleValueText(value, (rule.scope || {}).mode, '');
}

function alertRuleInspectionReason(reason) {
  return {
    watching: '条件尚未满足，规则持续监控。',
    condition_met: '当前条件已满足，等待本轮评估写入触发结果。',
    triggered_condition_met: '规则已触发，当前条件仍然满足。',
    triggered_latched: '规则已触发并保持锁定，重置后才会重新观察。',
    price_missing: '当前行情不可用，暂不执行判断。',
    history_insufficient: '价格历史样本不足，暂不能计算窗口波动。',
    position_missing: '关联持仓已不存在，需要修改或删除规则。',
    position_data_missing: '持仓存在，但当前估值数据不足。',
    disabled: '规则已停用，不参与评估。',
    scheduled: '尚未到开始时间。',
    expired: '规则已超过有效期。',
    orphaned: '关联对象不存在。',
    waiting_data: '正在等待可用数据。',
  }[reason] || '等待下一轮评估。';
}

function alertRuleRateText(value) {
  if (value == null || value === '') return '--';
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) + '%' : '--';
}

function buildAlertRuleDetail(rule) {
  const inspection = rule.inspection || {};
  const valueKind = inspection.value_kind || 'price';
  const distanceText = inspection.distance_to_trigger == null
    ? '--'
    : (Number(inspection.distance_to_trigger) <= 0 ? '已满足' : alertRuleDiagnosticValue(inspection.distance_to_trigger, rule, valueKind));
  const sampleText = inspection.required_samples
    ? '<span>窗口样本 ' + (inspection.sample_count || 0) + ' / ' + inspection.required_samples + '</span>'
    : '';
  const insight = alertRuleInsights[rule.id];
  let insightHtml = '<div class="alert-center-insight-loading">正在读取最近 30 天触发复盘...</div>';
  if (!alertRuleInsightLoading[rule.id] && insight) {
    const effectiveness = insight.effectiveness || {};
    const delivery = effectiveness.delivery || {};
    const response = effectiveness.response || {};
    const followThrough = effectiveness.market_follow_through || {};
    const deliveryState = insight.delivery || {};
    const channelText = deliveryState.record_only
      ? '仅记录'
      : (deliveryState.channels || []).map(channel => channel.label + (channel.ready ? '' : '（' + (channel.reason || '不可用') + '）')).join('、');
    const latest = Array.isArray(insight.recent_alerts) && insight.recent_alerts.length ? insight.recent_alerts[0] : null;
    insightHtml = [
      '<div class="alert-center-insight-grid">',
      '<div><span>30 天触发</span><strong>' + (Number(effectiveness.period_alerts) || 0) + '</strong></div>',
      '<div><span>通知送达率</span><strong>' + alertRuleRateText(delivery.sent_rate) + '</strong></div>',
      '<div><span>已处理率</span><strong>' + alertRuleRateText(response.handled_rate) + '</strong></div>',
      '<div><span>24 小时延续率</span><strong>' + alertRuleRateText(followThrough.rate) + '</strong></div>',
      '</div>',
      '<div class="alert-center-detail-line"><span>实际通知</span><strong>' + escapeHtml(channelText || '无可用渠道') + '</strong></div>',
      '<div class="alert-center-detail-line"><span>实际冷却</span><strong>' + escapeHtml(String(deliveryState.cooldown_minutes || 0)) + ' 分钟' + (deliveryState.cooldown_inherited ? '（继承）' : '') + '</strong></div>',
      latest ? '<div class="alert-center-detail-line"><span>最近记录</span><strong>' + escapeHtml(String(latest.timestamp || '').replace('T', ' ').slice(0, 16)) + (latest.handled ? ' · 已处理' : ' · 未处理') + '</strong></div>' : '',
    ].join('');
  }
  return [
    '<div class="alert-center-detail">',
    '<div class="alert-center-detail-head"><strong>运行诊断</strong><span>' + escapeHtml(alertRuleInspectionReason(inspection.reason)) + '</span></div>',
    '<div class="alert-center-inspection-grid">',
    '<div><span>当前值</span><strong>' + escapeHtml(alertRuleDiagnosticValue(inspection.current_value, rule, valueKind)) + '</strong></div>',
    '<div><span>目标值</span><strong>' + escapeHtml(alertRuleDiagnosticValue(inspection.target_value, rule, valueKind)) + '</strong></div>',
    '<div><span>距触发</span><strong>' + escapeHtml(distanceText) + '</strong></div>',
    '<div><span>最近评估</span><strong>' + escapeHtml(inspection.last_evaluated_at ? String(inspection.last_evaluated_at).replace('T', ' ').slice(0, 16) : '实时行情') + '</strong></div>',
    '</div>',
    sampleText ? '<div class="alert-center-detail-samples">' + sampleText + '</div>' : '',
    '<div class="alert-center-detail-head alert-center-insight-head"><strong>触发复盘</strong><span>行情延续率仅用于复盘，不代表预测准确率。</span></div>',
    insightHtml,
    '<div class="alert-center-detail-actions"><button class="btn-clear-sm" type="button" onclick="filterAlertLogByRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">查看记录</button><button class="btn-clear-sm" type="button" onclick="refreshAlertRuleInsight(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">刷新复盘</button></div>',
    '</div>',
  ].join('');
}
