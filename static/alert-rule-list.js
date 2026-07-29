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
