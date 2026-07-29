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
