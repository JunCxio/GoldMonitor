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
