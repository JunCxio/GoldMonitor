// ========== 统一预警中心 ==========
function normalizeAlertRulesState(data) {
  const items = Array.isArray(data && data.items) ? data.items : [];
  return {
    schema_version: Number(data && data.schema_version) || 1,
    items,
    total: Number.isFinite(Number(data && data.total)) ? Number(data.total) : items.length,
    summary: data && data.summary && typeof data.summary === 'object' ? data.summary : {},
    by_kind: data && data.by_kind && typeof data.by_kind === 'object' ? data.by_kind : {},
    migration: data && data.migration && typeof data.migration === 'object' ? data.migration : {},
    invalid_count: Number(data && data.invalid_count) || 0,
    load_error: data && data.load_error ? String(data.load_error) : '',
  };
}

function applyAlertRulesState(data) {
  alertRulesState = normalizeAlertRulesState(data);
  const existingIds = new Set((alertRulesState.items || []).map(rule => rule.id));
  selectedAlertRuleIds = selectedAlertRuleIds.filter(id => existingIds.has(id));
  if (activeAlertRuleDetailId && !existingIds.has(activeAlertRuleDetailId)) activeAlertRuleDetailId = null;
  if (alertRulesState.load_error) setAlertRuleCenterStatus(alertRulesState.load_error, 'fail');
  renderAlertRuleCenter();
}

function setAlertRuleCenterStatus(message, type) {
  const el = document.getElementById('alertRuleCenterStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'alert-center-status' + (type ? ' ' + type : '');
}

function alertRuleKindLabel(kind) {
  return {
    price_threshold: '价格',
    volatility: '波动',
    watch_target: '目标价',
    portfolio: '持仓',
  }[kind] || '规则';
}

function alertRuleStatusLabel(status) {
  return {
    watching: '监控中',
    triggered: '已触发',
    expired: '已过期',
    disabled: '已停用',
    waiting_data: '等待数据',
    orphaned: '关联失效',
    scheduled: '待生效',
  }[status] || '状态未知';
}

function alertRuleStatusClass(status) {
  if (status === 'watching') return 'watching';
  if (status === 'triggered') return 'triggered';
  if (status === 'expired' || status === 'orphaned') return 'problem';
  if (status === 'waiting_data' || status === 'scheduled') return 'waiting';
  return 'disabled';
}

function alertRuleUnit(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function alertRuleValueText(value, mode, suffix) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  if (suffix) return number.toLocaleString('en-US', { maximumFractionDigits: 2 }) + suffix;
  const unit = mode === 'usd' ? '$' : '¥';
  return unit + number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function alertRuleConditionText(rule) {
  const scope = rule && rule.scope ? rule.scope : {};
  const condition = rule && rule.condition ? rule.condition : {};
  const mode = scope.mode || 'rmb';
  if (rule.kind === 'volatility') {
    return (condition.window_minutes || 10) + ' 分钟内波动达到 ' + alertRuleValueText(condition.value, mode, '%');
  }
  if (rule.kind === 'portfolio') {
    const label = {
      take_profit: '止盈价达到',
      stop_loss: '止损价达到',
      profit_percent: '浮盈达到',
      loss_percent: '浮亏达到',
      near_cost: '距离成本不超过',
    }[condition.condition_key] || '持仓条件';
    const suffix = ['profit_percent', 'loss_percent', 'near_cost'].includes(condition.condition_key) ? '%' : '';
    return (rule.scope_label || scope.position_id || '未关联持仓') + ' · ' + label + ' ' + alertRuleValueText(condition.value, mode, suffix);
  }
  const operator = condition.operator === 'gte' ? '上涨至' : '下跌至';
  return alertRuleUnit(mode) + ' · ' + operator + ' ' + alertRuleValueText(condition.value, mode, '');
}

function alertRuleDeliveryText(rule) {
  const delivery = rule && rule.delivery ? rule.delivery : {};
  const channels = delivery.channels;
  const cooldown = delivery.cooldown_minutes;
  let channelText = '继承通知';
  if (Array.isArray(channels)) {
    const labels = channels.map(channel => ({ local: '本机', email: '邮件', webhook: 'Webhook' }[channel] || channel));
    channelText = labels.length ? labels.join('、') : '仅记录';
  }
  const cooldownText = cooldown === 'inherit' || cooldown == null ? '继承冷却' : '冷却 ' + cooldown + ' 分钟';
  return channelText + ' · ' + cooldownText;
}

function alertRuleValidityText(rule) {
  const validity = rule && rule.validity ? rule.validity : {};
  if (validity.expires_at) return '有效至 ' + String(validity.expires_at).replace('T', ' ').slice(0, 16);
  if (validity.starts_at) return String(validity.starts_at).replace('T', ' ').slice(0, 16) + ' 起生效';
  return '长期有效';
}

function setAlertRuleFilter(filter) {
  alertRuleFilter = ['all', 'price_threshold', 'volatility', 'watch_target', 'portfolio'].includes(filter) ? filter : 'all';
  renderAlertRuleCenter();
}

function setAlertRuleStatusFilter(status) {
  alertRuleStatusFilter = ['all', 'watching', 'triggered', 'waiting_data', 'scheduled', 'expired', 'orphaned', 'disabled'].includes(status) ? status : 'all';
  renderAlertRuleCenter();
}

function setAlertRuleSearch(value) {
  alertRuleSearch = String(value || '').trim().toLowerCase();
  renderAlertRuleCenter();
}

function filteredAlertRules() {
  return (alertRulesState.items || []).filter(rule => {
    const status = (rule.state || {}).status || (rule.enabled === false ? 'disabled' : 'watching');
    if (alertRuleFilter !== 'all' && rule.kind !== alertRuleFilter) return false;
    if (alertRuleStatusFilter !== 'all' && status !== alertRuleStatusFilter) return false;
    if (!alertRuleSearch) return true;
    const haystack = [
      rule.id,
      rule.name,
      alertRuleKindLabel(rule.kind),
      alertRuleStatusLabel(status),
      alertRuleConditionText(rule),
      alertRuleDeliveryText(rule),
      rule.note,
    ].join(' ').toLowerCase();
    return haystack.includes(alertRuleSearch);
  });
}

function toggleAlertRuleSelection(id, checked) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  if (checked && !selectedAlertRuleIds.includes(ruleId)) selectedAlertRuleIds.push(ruleId);
  if (!checked) selectedAlertRuleIds = selectedAlertRuleIds.filter(item => item !== ruleId);
  renderAlertRuleCenter();
}

function toggleVisibleAlertRuleSelection(checked) {
  const visibleIds = filteredAlertRules().map(rule => rule.id).filter(Boolean);
  if (checked) {
    selectedAlertRuleIds = Array.from(new Set(selectedAlertRuleIds.concat(visibleIds)));
  } else {
    const visibleSet = new Set(visibleIds);
    selectedAlertRuleIds = selectedAlertRuleIds.filter(id => !visibleSet.has(id));
  }
  renderAlertRuleCenter();
}

function batchUpdateSelectedAlertRules(action) {
  const ids = selectedAlertRuleIds.slice();
  if (!ids.length) {
    setAlertRuleCenterStatus('请先选择要操作的预警规则。', 'fail');
    return;
  }
  if (action === 'delete' && !window.confirm('删除已选的 ' + ids.length + ' 条预警规则？此操作不会删除历史警报记录。')) return;
  const actionLabel = { enable: '启用', disable: '停用', reset: '重置', delete: '删除' }[action] || '更新';
  setAlertRuleCenterStatus('正在批量' + actionLabel + '规则...', '');
  socket.emit('batch_update_alert_rules', { ids, action });
}

function renderAlertRuleBatchBar(visibleItems) {
  const bar = document.getElementById('alertRuleBatchBar');
  if (bar) {
    bar.innerHTML = selectedAlertRuleIds.length ? [
      '<span>已选 ' + selectedAlertRuleIds.length + ' 条</span>',
      '<div>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'enable\')">启用</button>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'disable\')">停用</button>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'reset\')">重置</button>',
      '<button class="btn-clear-sm alert-center-batch-delete" type="button" onclick="batchUpdateSelectedAlertRules(\'delete\')">删除</button>',
      '</div>',
    ].join('') : '';
    bar.className = 'alert-center-batch' + (selectedAlertRuleIds.length ? ' active' : '');
  }
  const selectVisible = document.getElementById('alertRuleSelectVisible');
  if (!selectVisible) return;
  const visibleIds = (visibleItems || []).map(rule => rule.id).filter(Boolean);
  const selectedVisibleCount = visibleIds.filter(id => selectedAlertRuleIds.includes(id)).length;
  selectVisible.checked = !!visibleIds.length && selectedVisibleCount === visibleIds.length;
  selectVisible.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length;
  selectVisible.disabled = !visibleIds.length;
}

function findUnifiedAlertRule(id) {
  return (alertRulesState.items || []).find(rule => rule.id === id) || null;
}

function cloneAlertRuleDraft(rule) {
  if (!rule) {
    return {
      kind: 'price_threshold',
      name: '',
      enabled: true,
      scope: { mode: currentMode, position_id: null },
      condition: { operator: 'gte', value: '', window_minutes: 10, condition_key: 'take_profit' },
      delivery: { channels: 'inherit', cooldown_minutes: 'inherit' },
      validity: { starts_at: '', expires_at: '' },
      note: '',
      alert_level: 'warning',
    };
  }
  return JSON.parse(JSON.stringify(rule));
}

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

function alertRuleEditorValue(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function alertRuleEditorChecked(id) {
  return !!document.getElementById(id)?.checked;
}

function captureAlertRuleDraft(preserveSimulation) {
  if (!activeUnifiedAlertRuleId || !document.getElementById('alertRuleKind')) return;
  const existing = activeUnifiedAlertRuleId === 'new' ? null : findUnifiedAlertRule(activeUnifiedAlertRuleId);
  const kind = alertRuleEditorValue('alertRuleKind');
  const mode = alertRuleEditorValue('alertRuleMode') || 'rmb';
  const deliveryMode = alertRuleEditorValue('alertRuleDeliveryMode') || 'inherit';
  const cooldownMode = alertRuleEditorValue('alertRuleCooldownMode') || 'inherit';
  let channels = 'inherit';
  if (deliveryMode === 'record') channels = [];
  if (deliveryMode === 'custom') {
    channels = ['local', 'email', 'webhook'].filter(channel => alertRuleEditorChecked('alertRuleChannel_' + channel));
  }
  const condition = { value: alertRuleEditorValue('alertRuleConditionValue') };
  if (kind === 'volatility') {
    condition.operator = 'abs_change_gte';
    condition.window_minutes = alertRuleEditorValue('alertRuleWindowMinutes');
  } else if (kind === 'portfolio') {
    condition.condition_key = alertRuleEditorValue('alertRulePortfolioCondition');
  } else {
    condition.operator = alertRuleEditorValue('alertRuleOperator') || 'gte';
  }
  alertRuleDraft = {
    id: existing ? existing.id : undefined,
    kind,
    name: alertRuleEditorValue('alertRuleName'),
    enabled: alertRuleEditorChecked('alertRuleEnabled'),
    scope: {
      mode,
      position_id: kind === 'portfolio' ? alertRuleEditorValue('alertRulePosition') : null,
    },
    condition,
    delivery: {
      channels,
      cooldown_minutes: cooldownMode === 'custom' ? alertRuleEditorValue('alertRuleCooldownMinutes') : 'inherit',
    },
    validity: {
      starts_at: alertRuleEditorValue('alertRuleStartsAt'),
      expires_at: alertRuleEditorValue('alertRuleExpiresAt'),
    },
    note: alertRuleEditorValue('alertRuleNote'),
    alert_level: kind === 'volatility' ? 'volatility' : alertRuleEditorValue('alertRuleLevel') || 'warning',
    legacy: existing && existing.kind === kind ? (existing.legacy || {}) : {},
  };
  if (!preserveSimulation) invalidateAlertRuleSimulation();
}

function changeAlertRuleKind(kind) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.kind = kind;
  alertRuleDraft.scope = Object.assign({ mode: currentMode, position_id: null }, alertRuleDraft.scope || {});
  alertRuleDraft.condition = {
    operator: kind === 'volatility' ? 'abs_change_gte' : 'gte',
    value: alertRuleDraft.condition && alertRuleDraft.condition.value ? alertRuleDraft.condition.value : '',
    window_minutes: 10,
    condition_key: 'take_profit',
  };
  alertRuleDraft.legacy = {};
  renderAlertRuleCenter();
}

function changeAlertRuleCooldownMode(mode) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.delivery = { ...(alertRuleDraft.delivery || {}) };
  alertRuleDraft.delivery.cooldown_minutes = mode === 'custom' ? 30 : 'inherit';
  renderAlertRuleCenter();
}

function changeAlertRuleDeliveryMode(mode) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.delivery = { ...(alertRuleDraft.delivery || {}) };
  if (mode === 'custom') alertRuleDraft.delivery.channels = ['local'];
  else if (mode === 'record') alertRuleDraft.delivery.channels = [];
  else alertRuleDraft.delivery.channels = 'inherit';
  renderAlertRuleCenter();
}

function validatedAlertRuleDraft() {
  captureAlertRuleDraft(true);
  const payload = alertRuleDraft ? JSON.parse(JSON.stringify(alertRuleDraft)) : null;
  const value = Number(payload && payload.condition && payload.condition.value);
  if (!payload || !Number.isFinite(value) || value <= 0) {
    setAlertRuleCenterStatus('请输入大于 0 的条件值。', 'fail');
    return null;
  }
  if (payload.kind === 'portfolio' && !(payload.scope && payload.scope.position_id)) {
    setAlertRuleCenterStatus('请选择要关联的持仓。', 'fail');
    return null;
  }
  if (payload.kind === 'volatility') {
    const minutes = Number(payload.condition.window_minutes);
    if (!Number.isInteger(minutes) || minutes < 1) {
      setAlertRuleCenterStatus('观察窗口必须是大于 0 的整数分钟。', 'fail');
      return null;
    }
  }
  return payload;
}

function setAlertRuleSimulationDays(value) {
  const days = Number(value);
  alertRuleSimulationDays = [7, 30, 90].includes(days) ? days : 30;
  resetAlertRuleSimulation();
  renderAlertRuleCenter();
}

function simulateUnifiedAlertRule() {
  const payload = validatedAlertRuleDraft();
  if (!payload) return;
  alertRuleSimulationRequestId = 'rule-simulation-' + Date.now().toString(36);
  alertRuleSimulation = null;
  alertRuleSimulationLoading = true;
  setAlertRuleCenterStatus(payload.kind === 'portfolio' ? '正在回放持仓流水与历史行情...' : '正在模拟历史行情...', '');
  socket.emit('simulate_alert_rule', {
    request_id: alertRuleSimulationRequestId,
    days: alertRuleSimulationDays,
    rule: payload,
  });
  renderAlertRuleCenter();
}

function alertRuleSimulationValueText(value, draft, mode) {
  const conditionKey = draft && draft.condition ? draft.condition.condition_key : '';
  if (draft && draft.kind === 'portfolio' && ['profit_percent', 'loss_percent', 'near_cost'].includes(conditionKey)) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(2) + '%' : '--';
  }
  const scope = draft && draft.scope ? draft.scope : {};
  return alertRuleValueText(value, mode || scope.mode || 'rmb', '');
}

function alertRuleSimulationPortfolioMeta(simulation) {
  const portfolio = simulation && simulation.portfolio ? simulation.portfolio : {};
  if (!portfolio.position_id && !portfolio.position_name) return '';
  const parts = [portfolio.position_name || portfolio.position_id || '关联持仓'];
  parts.push('流水 ' + (Number(portfolio.transaction_count) || 0) + ' 笔');
  if (Number(portfolio.unknown_date_count) > 0) parts.push('缺少日期 ' + Number(portfolio.unknown_date_count) + ' 笔');
  return parts.join(' · ');
}

function alertRuleSimulationEventText(event, draft) {
  if (!event) return '';
  const scope = draft && draft.scope ? draft.scope : {};
  const mode = event.mode || scope.mode || 'rmb';
  const value = alertRuleSimulationValueText(event.value, draft, mode);
  const change = event.change_percent == null ? '' : ' · 波动 ' + Number(event.change_percent).toFixed(2) + '%';
  const conditionKey = draft && draft.condition ? draft.condition.condition_key : '';
  const price = draft && draft.kind === 'portfolio'
    && ['profit_percent', 'loss_percent', 'near_cost'].includes(conditionKey)
    && event.current_price != null
    ? ' · 行情 ' + alertRuleValueText(event.current_price, mode, '')
    : '';
  return String(event.timestamp || '').replace('T', ' ').slice(0, 16) + ' · ' + value + price + change;
}

function buildAlertRuleSimulationPanel(draft) {
  const isPortfolio = draft.kind === 'portfolio';
  let resultHtml = '<div class="alert-center-simulation-empty">' + (isPortfolio
    ? '根据本地持仓流水与历史行情还原持仓估值，不修改真实持仓、规则或警报记录。'
    : '根据本地历史行情估算规则命中与冷却后的触发次数，不修改规则和历史数据。') + '</div>';
  if (alertRuleSimulationLoading) {
    resultHtml = '<div class="alert-center-insight-loading">' + (isPortfolio ? '正在回放持仓流水与历史行情...' : '正在读取并模拟历史行情...') + '</div>';
  } else if (alertRuleSimulation && alertRuleSimulation.error) {
    resultHtml = '<div class="alert-center-simulation-error">' + escapeHtml(alertRuleSimulation.error) + '</div>';
  } else if (alertRuleSimulation) {
    const simulation = alertRuleSimulation;
    const coverage = simulation.coverage || {};
    if (!simulation.supported || !simulation.usable) {
      resultHtml = [
        '<div class="alert-center-simulation-error">' + escapeHtml(simulation.message || '现有历史数据不足，无法完成模拟。') + '</div>',
        coverage.point_count ? '<div class="alert-center-simulation-meta">已读取 ' + Number(coverage.point_count) + ' 个价格点，采样间隔约 ' + escapeHtml(coverage.sampling_interval_label || '未知') + '。</div>' : '',
      ].join('');
    } else {
      const distribution = (simulation.time_distribution || []).map(item => '<span>' + escapeHtml(item.label || '') + '<strong>' + (Number(item.count) || 0) + '</strong></span>').join('');
      const recent = (simulation.recent_triggers || []).slice(0, 3).map(item => '<li>' + escapeHtml(alertRuleSimulationEventText(item, draft)) + '</li>').join('');
      const coverageText = coverage.from && coverage.to
        ? String(coverage.from).replace('T', ' ').slice(0, 16) + ' 至 ' + String(coverage.to).replace('T', ' ').slice(0, 16)
        : '无可用时间范围';
      const singleTrigger = simulation.trigger_policy === 'single';
      const portfolioMeta = alertRuleSimulationPortfolioMeta(simulation);
      resultHtml = [
        '<div class="alert-center-simulation-grid">',
        '<div><span>' + (isPortfolio ? '历史估值' : '历史样本') + '</span><strong>' + (Number(coverage.point_count) || 0) + '</strong></div>',
        '<div><span>规则命中</span><strong>' + (Number(simulation.match_count) || 0) + '</strong></div>',
        '<div><span>' + (singleTrigger ? '有效触发' : '冷却后触发') + '</span><strong>' + (Number(simulation.effective_trigger_count) || 0) + '</strong></div>',
        '<div><span>' + (singleTrigger ? '后续命中' : '被抑制') + '</span><strong>' + (Number(simulation.suppressed_count) || 0) + '</strong></div>',
        '</div>',
        portfolioMeta ? '<div class="alert-center-simulation-meta">' + escapeHtml(portfolioMeta) + '</div>' : '',
        '<div class="alert-center-simulation-meta">覆盖 ' + escapeHtml(coverageText) + ' · 采样间隔约 ' + escapeHtml(coverage.sampling_interval_label || '未知') + ' · ' + (singleTrigger ? '单次触发策略' : '冷却 ' + (Number(simulation.cooldown_minutes) || 0) + ' 分钟') + (coverage.partial ? ' · 覆盖不足' : '') + '</div>',
        '<div class="alert-center-simulation-distribution">' + distribution + '</div>',
        recent ? '<ul class="alert-center-simulation-events">' + recent + '</ul>' : '<div class="alert-center-simulation-empty">该范围内没有估算触发记录。</div>',
        '<div class="alert-center-simulation-note">' + escapeHtml(simulation.message || '') + ' 历史模拟仅用于配置评估，不代表预测准确率或投资建议。</div>',
      ].join('');
    }
  }
  return [
    '<div class="alert-center-simulation">',
    '<div class="alert-center-simulation-head"><div><strong>历史模拟</strong><span>忽略当前启停和有效期，仅按条件、触发策略与冷却设置计算。</span></div><div>',
    '<select id="alertRuleSimulationDays" aria-label="历史模拟范围" onchange="setAlertRuleSimulationDays(this.value)">',
    '<option value="7"' + (alertRuleSimulationDays === 7 ? ' selected' : '') + '>7 天</option>',
    '<option value="30"' + (alertRuleSimulationDays === 30 ? ' selected' : '') + '>30 天</option>',
    '<option value="90"' + (alertRuleSimulationDays === 90 ? ' selected' : '') + '>90 天</option>',
    '</select>',
    '<button class="btn-clear-sm" type="button" onclick="simulateUnifiedAlertRule()"' + (alertRuleSimulationLoading ? ' disabled' : '') + '>运行模拟</button>',
    '</div></div>',
    '<div id="alertRuleSimulationResult">' + resultHtml + '</div>',
    '</div>',
  ].join('');
}

function alertRuleEditorConditionFields(draft) {
  const condition = draft.condition || {};
  if (draft.kind === 'portfolio') {
    const positions = Array.isArray(portfolioState.items) ? portfolioState.items : [];
    const options = positions.map(item => '<option value="' + escapeHtml(item.id || '') + '"' + ((draft.scope || {}).position_id === item.id ? ' selected' : '') + '>' + escapeHtml(item.name || item.id || '未命名持仓') + '</option>').join('');
    return [
      '<label class="alert-center-field"><span>关联持仓</span><select id="alertRulePosition"><option value="">请选择持仓</option>' + options + '</select></label>',
      '<label class="alert-center-field"><span>提醒条件</span><select id="alertRulePortfolioCondition">',
      '<option value="take_profit"' + (condition.condition_key === 'take_profit' ? ' selected' : '') + '>止盈价</option>',
      '<option value="stop_loss"' + (condition.condition_key === 'stop_loss' ? ' selected' : '') + '>止损价</option>',
      '<option value="profit_percent"' + (condition.condition_key === 'profit_percent' ? ' selected' : '') + '>浮盈比例</option>',
      '<option value="loss_percent"' + (condition.condition_key === 'loss_percent' ? ' selected' : '') + '>浮亏比例</option>',
      '<option value="near_cost"' + (condition.condition_key === 'near_cost' ? ' selected' : '') + '>接近成本</option>',
      '</select></label>',
      '<label class="alert-center-field"><span>条件值</span><input id="alertRuleConditionValue" type="number" step="0.01" min="0" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="输入价格或比例"></label>',
    ].join('');
  }
  if (draft.kind === 'volatility') {
    return [
      '<label class="alert-center-field"><span>单位</span><select id="alertRuleMode"><option value="rmb"' + ((draft.scope || {}).mode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + ((draft.scope || {}).mode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></label>',
      '<label class="alert-center-field"><span>观察窗口</span><input id="alertRuleWindowMinutes" type="number" min="1" max="1440" step="1" value="' + escapeHtml(condition.window_minutes || 10) + '"></label>',
      '<label class="alert-center-field"><span>波动幅度（%）</span><input id="alertRuleConditionValue" type="number" min="0" step="0.1" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="例如 1.5"></label>',
    ].join('');
  }
  return [
    '<label class="alert-center-field"><span>单位</span><select id="alertRuleMode"><option value="rmb"' + ((draft.scope || {}).mode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + ((draft.scope || {}).mode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></label>',
    '<label class="alert-center-field"><span>方向</span><select id="alertRuleOperator"><option value="gte"' + (condition.operator === 'gte' ? ' selected' : '') + '>上涨至或高于</option><option value="lte"' + (condition.operator === 'lte' ? ' selected' : '') + '>下跌至或低于</option></select></label>',
    '<label class="alert-center-field"><span>目标价格</span><input id="alertRuleConditionValue" type="number" min="0" step="0.01" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="输入价格"></label>',
  ].join('');
}

function buildUnifiedAlertRuleEditor() {
  const draft = alertRuleDraft || cloneAlertRuleDraft(null);
  const delivery = draft.delivery || {};
  const channels = delivery.channels;
  const deliveryMode = channels === 'inherit' || channels == null ? 'inherit' : (Array.isArray(channels) && !channels.length ? 'record' : 'custom');
  const selectedChannels = Array.isArray(channels) ? channels : [];
  const cooldownMode = delivery.cooldown_minutes === 'inherit' || delivery.cooldown_minutes == null ? 'inherit' : 'custom';
  const validity = draft.validity || {};
  const editorTitle = activeUnifiedAlertRuleId === 'new' ? '新增预警规则' : '编辑预警规则';
  return [
    '<div class="alert-center-editor" oninput="captureAlertRuleDraft()">',
    '<div class="alert-center-editor-head"><strong>' + editorTitle + '</strong><span>保存失败时保留当前输入</span></div>',
    '<div class="alert-center-form-grid">',
    '<label class="alert-center-field"><span>类型</span><select id="alertRuleKind" onchange="changeAlertRuleKind(this.value)">',
    '<option value="price_threshold"' + (draft.kind === 'price_threshold' ? ' selected' : '') + '>价格阈值</option>',
    '<option value="volatility"' + (draft.kind === 'volatility' ? ' selected' : '') + '>波动规则</option>',
    '<option value="watch_target"' + (draft.kind === 'watch_target' ? ' selected' : '') + '>目标价观察</option>',
    '<option value="portfolio"' + (draft.kind === 'portfolio' ? ' selected' : '') + '>持仓提醒</option>',
    '</select></label>',
    '<label class="alert-center-field alert-center-field-wide"><span>名称</span><input id="alertRuleName" type="text" maxlength="80" value="' + escapeHtml(draft.name || '') + '" placeholder="留空时自动生成"></label>',
    alertRuleEditorConditionFields(draft),
    '<label class="alert-center-field"><span>级别</span><select id="alertRuleLevel"' + (draft.kind === 'volatility' ? ' disabled' : '') + '><option value="warning"' + (draft.alert_level !== 'critical' ? ' selected' : '') + '>关注</option><option value="critical"' + (draft.alert_level === 'critical' ? ' selected' : '') + '>警告</option></select></label>',
    '<label class="alert-center-field"><span>开始时间</span><input id="alertRuleStartsAt" type="datetime-local" value="' + escapeHtml(String(validity.starts_at || '').slice(0, 16)) + '"></label>',
    '<label class="alert-center-field"><span>失效时间</span><input id="alertRuleExpiresAt" type="datetime-local" value="' + escapeHtml(String(validity.expires_at || '').slice(0, 16)) + '"></label>',
    '<label class="alert-center-field"><span>冷却策略</span><select id="alertRuleCooldownMode" onchange="changeAlertRuleCooldownMode(this.value)"><option value="inherit"' + (cooldownMode === 'inherit' ? ' selected' : '') + '>继承全局</option><option value="custom"' + (cooldownMode === 'custom' ? ' selected' : '') + '>单独设置</option></select></label>',
    cooldownMode === 'custom' ? '<label class="alert-center-field"><span>冷却分钟</span><input id="alertRuleCooldownMinutes" type="number" min="0" max="1440" step="1" value="' + escapeHtml(delivery.cooldown_minutes == null ? 30 : delivery.cooldown_minutes) + '"></label>' : '<input id="alertRuleCooldownMinutes" type="hidden" value="inherit">',
    '<label class="alert-center-field"><span>通知策略</span><select id="alertRuleDeliveryMode" onchange="changeAlertRuleDeliveryMode(this.value)"><option value="inherit"' + (deliveryMode === 'inherit' ? ' selected' : '') + '>继承全局</option><option value="custom"' + (deliveryMode === 'custom' ? ' selected' : '') + '>指定渠道</option><option value="record"' + (deliveryMode === 'record' ? ' selected' : '') + '>仅记录</option></select></label>',
    deliveryMode === 'custom' ? '<div class="alert-center-channel-field"><span>通知渠道</span><label><input id="alertRuleChannel_local" type="checkbox"' + (selectedChannels.includes('local') ? ' checked' : '') + '>本机</label><label><input id="alertRuleChannel_email" type="checkbox"' + (selectedChannels.includes('email') ? ' checked' : '') + '>邮件</label><label><input id="alertRuleChannel_webhook" type="checkbox"' + (selectedChannels.includes('webhook') ? ' checked' : '') + '>Webhook</label></div>' : '<input id="alertRuleChannel_local" type="hidden"><input id="alertRuleChannel_email" type="hidden"><input id="alertRuleChannel_webhook" type="hidden">',
    '<label class="alert-center-field alert-center-field-wide"><span>备注</span><input id="alertRuleNote" type="text" maxlength="200" value="' + escapeHtml(draft.note || '') + '" placeholder="可选"></label>',
    '</div>',
    buildAlertRuleSimulationPanel(draft),
    '<div class="alert-center-editor-foot"><label class="alert-center-enabled"><input id="alertRuleEnabled" type="checkbox"' + (draft.enabled === false ? '' : ' checked') + '>保存后启用</label><div><button class="btn-clear-sm" type="button" onclick="cancelUnifiedAlertRuleEdit()">取消</button><button class="btn-set" type="button" onclick="saveUnifiedAlertRule()">保存规则</button></div></div>',
    '</div>',
  ].join('');
}

function saveUnifiedAlertRule() {
  const payload = validatedAlertRuleDraft();
  if (!payload) return;
  setAlertRuleCenterStatus('正在保存预警规则...', '');
  socket.emit('save_alert_rule', payload);
}

function toggleUnifiedAlertRule(id, enabled) {
  setAlertRuleCenterStatus(enabled ? '正在启用规则...' : '正在停用规则...', '');
  socket.emit('toggle_alert_rule', { id, enabled });
}

function duplicateUnifiedAlertRule(id) {
  setAlertRuleCenterStatus('正在复制规则...', '');
  socket.emit('duplicate_alert_rule', { id });
}

function resetUnifiedAlertRule(id) {
  setAlertRuleCenterStatus('正在重置触发状态...', '');
  socket.emit('reset_alert_rule_state', { id });
}

function deleteUnifiedAlertRule(id) {
  const rule = findUnifiedAlertRule(id);
  if (!rule || !window.confirm('删除预警规则“' + (rule.name || '未命名规则') + '”？')) return;
  setAlertRuleCenterStatus('正在删除规则...', '');
  socket.emit('delete_alert_rule', { id });
}

function renderAlertRuleSummary() {
  const box = document.getElementById('alertRuleSummary');
  if (!box) return;
  const summary = alertRulesState.summary || {};
  const items = [
    ['watching', '监控中'],
    ['triggered', '已触发'],
    ['expired', '已过期'],
    ['disabled', '已停用'],
  ];
  box.innerHTML = items.map(item => '<div class="alert-summary-item ' + item[0] + '"><span>' + escapeHtml(item[1]) + '</span><strong>' + (Number(summary[item[0]]) || 0) + '</strong></div>').join('');
}

function renderAlertRuleCenter() {
  const list = document.getElementById('alertRuleCenterList');
  if (!list) return;
  renderAlertRuleSummary();
  document.querySelectorAll('.alert-center-filter').forEach(button => {
    button.classList.toggle('active', button.dataset.filter === alertRuleFilter);
  });
  const items = filteredAlertRules();
  renderAlertRuleBatchBar(items);
  const parts = [];
  if (activeUnifiedAlertRuleId === 'new') parts.push(buildUnifiedAlertRuleEditor());
  if (!items.length && activeUnifiedAlertRuleId !== 'new') {
    parts.push('<div class="alert-center-empty">当前筛选下暂无规则。新增规则后会在这里统一展示状态和触发结果。</div>');
  }
  items.forEach(rule => {
    const state = rule.state || {};
    const status = state.status || (rule.enabled === false ? 'disabled' : 'watching');
    const detailExpanded = activeAlertRuleDetailId === rule.id;
    const expanded = activeUnifiedAlertRuleId === rule.id || detailExpanded;
    const selected = selectedAlertRuleIds.includes(rule.id);
    const lastTriggered = state.last_triggered_at ? ' · 最近触发 ' + String(state.last_triggered_at).replace('T', ' ').slice(0, 16) : '';
    parts.push([
      '<div class="alert-center-rule kind-' + escapeHtml(rule.kind || '') + ' status-' + escapeHtml(status) + (expanded ? ' expanded' : '') + (selected ? ' selected' : '') + '">',
      '<span class="alert-center-rail" aria-hidden="true"></span>',
      '<div class="alert-center-rule-main">',
      '<div class="alert-center-rule-title"><label class="alert-center-select"><input type="checkbox" aria-label="选择规则 ' + escapeHtml(rule.name || '未命名规则') + '" onchange="toggleAlertRuleSelection(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ', this.checked)"' + (selected ? ' checked' : '') + '></label><span class="alert-center-kind">' + escapeHtml(alertRuleKindLabel(rule.kind)) + '</span><strong>' + escapeHtml(rule.name || '未命名规则') + '</strong></div>',
      '<div class="alert-center-rule-condition">' + escapeHtml(alertRuleConditionText(rule)) + '</div>',
      '<div class="alert-center-rule-meta">' + escapeHtml(alertRuleDeliveryText(rule) + ' · ' + alertRuleValidityText(rule) + lastTriggered) + '</div>',
      '</div>',
      '<div class="alert-center-rule-actions">',
      '<span class="alert-center-state ' + alertRuleStatusClass(status) + '">' + escapeHtml(alertRuleStatusLabel(status)) + '</span>',
      '<button class="btn-clear-sm" type="button" onclick="toggleAlertRuleDetail(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">' + (detailExpanded ? '收起' : '详情') + '</button>',
      '<button class="btn-clear-sm" type="button" onclick="editUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">编辑</button>',
      '<button class="btn-clear-sm" type="button" onclick="toggleUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ', ' + (rule.enabled === false ? 'true' : 'false') + ')">' + (rule.enabled === false ? '启用' : '停用') + '</button>',
      '<button class="btn-clear-sm" type="button" onclick="duplicateUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">复制</button>',
      state.triggered ? '<button class="btn-clear-sm" type="button" onclick="resetUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">重置</button>' : '',
      '<button class="btn-clear-sm" type="button" onclick="deleteUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">删除</button>',
      '</div>',
      activeUnifiedAlertRuleId === rule.id ? buildUnifiedAlertRuleEditor() : '',
      detailExpanded ? buildAlertRuleDetail(rule) : '',
      '</div>',
    ].join(''));
  });
  list.innerHTML = parts.join('');
}

function formatAlertRuleValue(value, unit) {
  if (value == null || value === '') return '未设置';
  return unit + Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatAlertEmailState(emailKey) {
  return appSettings[emailKey] === false ? '邮件关闭' : '邮件开启';
}

function setActiveAlertRule(type) {
  activeAlertRule = activeAlertRule === type ? null : type;
  renderAlertRules();
}

function buildThresholdRuleEditor(rule, value) {
  const inputValue = value == null ? '' : String(value);
  const mailChecked = appSettings[rule.emailKey] !== false ? ' checked' : '';
  return [
    '<div class="alert-rule-editor">',
    '<div class="alert-rule-fields">',
    '<div class="alert-rule-field">',
    '<label for="alertRuleValue_' + escapeHtml(rule.type) + '">触发价位</label>',
    '<input id="alertRuleValue_' + escapeHtml(rule.type) + '" type="number" step="0.01" value="' + escapeHtml(inputValue) + '" placeholder="输入价位">',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>触发时发送邮件</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="alertRuleEmail_' + escapeHtml(rule.type) + '"' + mailChecked + '><span class="slider"></span></label>',
    '</div>',
    '</div>',
    '<div class="alert-rule-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveThresholdRule(\'' + rule.type + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="clearThreshold(\'' + rule.type + '\')">停用预警</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'' + rule.type + '\')">放弃编辑</button>',
    '</div>',
    '</div>',
  ].join('');
}

function buildVolatilityRuleEditor() {
  const pct = volConfig.percent == null ? '2.0' : String(volConfig.percent);
  const minutes = volConfig.minutes || 10;
  const mailChecked = appSettings.email_volatility_enabled !== false ? ' checked' : '';
  return [
    '<div class="alert-rule-editor">',
    '<div class="alert-rule-fields">',
    '<div class="alert-rule-field">',
    '<label for="alertRuleVolPct">波动幅度</label>',
    '<input id="alertRuleVolPct" type="number" step="0.1" value="' + escapeHtml(pct) + '" placeholder="2.0">',
    '</div>',
    '<div class="alert-rule-field">',
    '<label for="alertRuleVolMin">观察分钟</label>',
    '<input id="alertRuleVolMin" type="number" step="1" value="' + escapeHtml(minutes) + '" placeholder="10">',
    '</div>',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>触发时发送邮件</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="alertRuleEmail_volatility"' + mailChecked + '><span class="slider"></span></label>',
    '</div>',
    '<div class="alert-rule-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveVolatilityRule()">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="clearVolatility()">停用预警</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'volatility\')">放弃编辑</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderAlertRules() {
  const box = document.getElementById('alertRulesList');
  if (!box) return;
  const unit = currentMode === 'usd' ? '$' : '¥';
  const modeLabel = currentMode === 'usd' ? 'USD/oz' : 'RMB/克';
  const ruleItems = ALERT_RULE_DEFS.map(rule => {
    const key = rule.type + '_' + currentMode;
    const value = allThresholds[key];
    const enabled = value != null;
    return {
      badgeClass: rule.badgeClass,
      title: rule.title,
      meta: rule.direction + ' ' + formatAlertRuleValue(value, unit) + ' · ' + modeLabel + ' · ' + formatAlertEmailState(rule.emailKey),
      state: enabled ? '已启用' : '未设置',
      enabled,
      type: rule.type,
      editor: activeAlertRule === rule.type ? buildThresholdRuleEditor(rule, value) : '',
      edit: "setActiveAlertRule('" + rule.type + "')",
      clear: "clearThreshold('" + rule.type + "')",
    };
  });
  const volEnabled = !!(volConfig.enabled && volConfig.percent != null);
  ruleItems.push({
    badgeClass: 'vol',
    title: '波动预警',
    meta: (volEnabled ? volConfig.minutes + '分钟内波动达到 ' + volConfig.percent + '%' : '未启用') + ' · ' + formatAlertEmailState('email_volatility_enabled'),
    state: volEnabled ? '已启用' : '已关闭',
    enabled: volEnabled,
    type: 'volatility',
    editor: activeAlertRule === 'volatility' ? buildVolatilityRuleEditor() : '',
    edit: "setActiveAlertRule('volatility')",
    clear: "clearVolatility()",
  });
  box.innerHTML = ruleItems.map(rule => [
    '<div class="alert-rule-item' + (activeAlertRule === rule.type ? ' expanded' : '') + '">',
    '<div class="alert-rule-main">',
    '<div class="alert-rule-title"><span class="level-badge ' + escapeHtml(rule.badgeClass) + '">' + escapeHtml(rule.title.replace('上涨', '').replace('下跌', '').replace('预警', '')) + '</span> ' + escapeHtml(rule.title) + '</div>',
    '<div class="alert-rule-meta">' + escapeHtml(rule.meta) + '</div>',
    '</div>',
    '<div class="alert-rule-actions">',
    '<span class="alert-rule-state ' + (rule.enabled ? 'on' : 'off') + '">' + escapeHtml(rule.state) + '</span>',
    '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="' + rule.edit + '">编辑</button>',
    '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="' + rule.clear + '">停用</button>',
    '</div>',
    rule.editor,
    '</div>',
  ].join('')).join('');
}

function updateThresholdInputs() {
  renderAlertRules();
}

function setThreshold(type) {
  const input = document.getElementById('alertRuleValue_' + type);
  const val = input ? input.value.trim() : '';
  socket.emit('set_threshold', { mode: currentMode, type, value: val === '' ? null : val });
}

function saveThresholdRule(type) {
  const rule = ALERT_RULE_DEFS.find(item => item.type === type);
  if (!rule) return;
  const input = document.getElementById('alertRuleValue_' + type);
  const emailInput = document.getElementById('alertRuleEmail_' + type);
  const val = input ? input.value.trim() : '';
  if (emailInput) updateEmailSwitch(rule.emailKey, emailInput.checked);
  socket.emit('set_threshold', { mode: currentMode, type, value: val === '' ? null : val });
}

function clearThreshold(type) {
  socket.emit('clear_threshold', { mode: currentMode, type });
}

function updateEmailSwitch(key, value) {
  const update = {};
  update[key] = value;
  socket.emit('update_settings', update);
  appSettings[key] = value;
  renderAlertRules();
}
