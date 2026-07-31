function settingsFieldElements() {
  return SETTINGS_FIELD_IDS.map(id => document.getElementById(id)).filter(Boolean);
}

function captureSettingsSnapshot() {
  const snapshot = {};
  settingsFieldElements().forEach(element => {
    snapshot[element.id] = element.type === 'checkbox' ? !!element.checked : element.value;
  });
  return JSON.stringify(snapshot);
}

function showSettingsMessage(message, state) {
  const element = document.getElementById('settingsMessage');
  if (!element) return;
  element.textContent = message || '';
  if (state) element.dataset.state = state;
  else delete element.dataset.state;
}

function setSettingsSaving(saving) {
  const button = document.getElementById('settingsSaveButton');
  if (!button) return;
  button.textContent = saving ? '正在保存' : '保存更改';
  button.disabled = !!saving || !settingsDirty;
}

function setSettingsDirty(dirty) {
  settingsDirty = !!dirty;
  const state = document.getElementById('settingsDirtyState');
  if (state) {
    state.textContent = settingsDirty ? '有未保存的更改' : '所有更改已保存';
    state.classList.toggle('changed', settingsDirty);
  }
  setSettingsSaving(pendingSettingsSave);
}

function updateSettingsDirtyState() {
  if (!settingsInitialSnapshot) return;
  setSettingsDirty(captureSettingsSnapshot() !== settingsInitialSnapshot);
}

function resetSettingsDirtySnapshot() {
  settingsInitialSnapshot = captureSettingsSnapshot();
  setSettingsDirty(false);
  hideSettingsDiscardPrompt();
}

function readStoredSettingsTab() {
  try {
    const stored = window.localStorage.getItem(SETTINGS_TAB_STORAGE_KEY) || '';
    return SETTINGS_TABS.includes(stored) ? stored : 'general';
  } catch (_error) {
    return 'general';
  }
}

function storeSettingsTab(tab) {
  try {
    window.localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, tab);
  } catch (_error) {
    // 本机浏览器禁用存储时，仅在当前会话中保留分页。
  }
}

function settingsTabForElement(element) {
  const panel = element && element.closest ? element.closest('[data-settings-panel]') : null;
  return panel ? panel.dataset.settingsPanel : 'general';
}

function clearSettingsValidation() {
  const modal = document.querySelector('.settings-primary-modal');
  if (!modal) return;
  modal.querySelectorAll('.invalid').forEach(element => element.classList.remove('invalid'));
  modal.querySelectorAll('[aria-invalid="true"]').forEach(element => {
    element.removeAttribute('aria-invalid');
    const describedBy = element.getAttribute('aria-describedby') || '';
    if (describedBy.endsWith('Error')) element.removeAttribute('aria-describedby');
  });
  modal.querySelectorAll('.setting-field-error').forEach(element => element.remove());
  modal.querySelectorAll('.settings-tab.has-error').forEach(element => element.classList.remove('has-error'));
}

function clearSettingsFieldError(element) {
  if (!element) return;
  element.classList.remove('invalid');
  const inlineCheck = element.closest('.inline-check');
  if (inlineCheck) inlineCheck.classList.remove('invalid');
  element.removeAttribute('aria-invalid');
  const error = document.getElementById(element.id + 'Error');
  if (error) error.remove();
  const tab = settingsTabForElement(element);
  const panel = document.querySelector('[data-settings-panel="' + tab + '"]');
  if (panel && !panel.querySelector('.setting-field-error')) {
    const tabButton = document.querySelector('[data-settings-tab="' + tab + '"]');
    if (tabButton) tabButton.classList.remove('has-error');
  }
}

function renderSettingsValidation(errors) {
  clearSettingsValidation();
  errors.forEach(error => {
    const element = document.getElementById(error.id);
    if (!element) return;
    const highlight = element.closest('.inline-check') || element;
    highlight.classList.add('invalid');
    element.setAttribute('aria-invalid', 'true');
    const row = element.closest('.setting-row');
    if (row && !document.getElementById(error.id + 'Error')) {
      const note = document.createElement('div');
      note.className = 'setting-field-error';
      note.id = error.id + 'Error';
      note.textContent = error.message;
      row.appendChild(note);
      element.setAttribute('aria-describedby', note.id);
    }
    const tabButton = document.querySelector('[data-settings-tab="' + error.tab + '"]');
    if (tabButton) tabButton.classList.add('has-error');
  });
}

function validateSettings() {
  const errors = [];
  const add = (id, message) => {
    const element = document.getElementById(id);
    if (!element) return;
    errors.push({ id, message, tab: settingsTabForElement(element) });
  };
  const validateNumber = (id, label, min, max) => {
    const element = document.getElementById(id);
    if (!element || element.value.trim() === '') return;
    const value = Number(element.value);
    if (!Number.isFinite(value) || value < min || value > max) add(id, label + '应在 ' + min + ' 到 ' + max + ' 之间。');
  };
  const validateTypedValue = (id, message) => {
    const element = document.getElementById(id);
    if (element && element.value.trim() && !element.validity.valid) add(id, message);
  };

  validateNumber('setFloatingOpacity', '悬浮条透明度', 50, 100);
  validateNumber('setAlertCooldownMinutes', '提醒冷却时间', 0, 240);
  validateNumber('setSmtpPort', 'SMTP 端口', 1, 65535);
  validateNumber('setRiskMaxTokens', '单次输出上限', 300, 4000);
  validateNumber('setRiskCooldownSeconds', '分析冷却时间', 0, 300);
  validateNumber('setRiskCacheMinutes', '重复分析缓存', 0, 60);
  validateTypedValue('setSmtpSender', '发件邮箱格式不正确。');
  validateTypedValue('setSmtpRecipient', '收件邮箱格式不正确。');
  validateTypedValue('setWebhookUrl', 'Webhook 地址格式不正确。');
  validateTypedValue('setDeepseekBaseUrl', 'DeepSeek API 地址格式不正确。');
  validateTypedValue('setOpenaiCompatibleBaseUrl', '兼容接口地址格式不正确。');

  const quietStart = document.getElementById('setAlertQuietStart').value;
  const quietEnd = document.getElementById('setAlertQuietEnd').value;
  if (!!quietStart !== !!quietEnd) add(quietStart ? 'setAlertQuietEnd' : 'setAlertQuietStart', '静默时段需要同时填写开始和结束时间。');

  if (document.getElementById('setWebhookEnabled').checked) {
    const webhookUrl = document.getElementById('setWebhookUrl').value.trim();
    if (!webhookUrl) add('setWebhookUrl', '启用 Webhook 前需要填写接收地址。');
    else if (!webhookUrl.toLowerCase().startsWith('https://')) add('setWebhookUrl', 'Webhook 地址必须使用 HTTPS。');
  }

  if (document.getElementById('setDailyDigestEnabled').checked) {
    if (!document.getElementById('setDailyDigestTime').value) add('setDailyDigestTime', '启用每日摘要前需要设置发送时间。');
    if (!document.getElementById('setDailyDigestEmail').checked && !document.getElementById('setDailyDigestWebhook').checked) {
      add('setDailyDigestEmail', '启用每日摘要前至少选择一个发送渠道。');
    }
  }

  if (document.getElementById('setRiskAssistantEnabled').checked) {
    const provider = document.getElementById('setRiskAssistantProvider').value;
    if (provider === 'deepseek') {
      if (!document.getElementById('setDeepseekBaseUrl').value.trim()) add('setDeepseekBaseUrl', '需要填写 DeepSeek API 地址。');
      if (!document.getElementById('setDeepseekModel').value) add('setDeepseekModel', '需要选择 DeepSeek 模型。');
    } else {
      if (!document.getElementById('setOpenaiCompatibleBaseUrl').value.trim()) add('setOpenaiCompatibleBaseUrl', '需要填写兼容接口地址。');
      if (!document.getElementById('setOpenaiCompatibleModel').value.trim()) add('setOpenaiCompatibleModel', '需要填写兼容模型名称。');
    }
  }

  renderSettingsValidation(errors);
  if (!errors.length) return true;
  const first = errors[0];
  switchSettingsTab(first.tab);
  showSettingsMessage(
    SETTINGS_TAB_LABELS[first.tab] + '有 ' + errors.filter(error => error.tab === first.tab).length + ' 项需要处理：' + first.message,
    'error'
  );
  window.requestAnimationFrame(() => {
    const element = document.getElementById(first.id);
    if (element) element.focus();
  });
  return false;
}

function handleSettingsFieldChange(event) {
  const target = event.target;
  if (!target || !SETTINGS_FIELD_IDS.includes(target.id)) return;
  clearSettingsFieldError(target);
  if (target.id === 'setDailyDigestEmail' || target.id === 'setDailyDigestWebhook') {
    clearSettingsFieldError(document.getElementById('setDailyDigestEmail'));
  }
  if (target.id === 'setAlertQuietStart' || target.id === 'setAlertQuietEnd') {
    clearSettingsFieldError(document.getElementById('setAlertQuietStart'));
    clearSettingsFieldError(document.getElementById('setAlertQuietEnd'));
  }
  if (target.id === 'setFloatingWindowsMode') {
    syncFloatingWindowsModeRows();
  }
  const message = document.getElementById('settingsMessage');
  if (message && message.dataset.state === 'error') showSettingsMessage('', '');
  updateSettingsDirtyState();
}

function handleSettingsTabKeydown(event) {
  const current = event.target.closest && event.target.closest('.settings-tab');
  if (!current) return;
  const tabs = Array.from(document.querySelectorAll('.settings-tab'));
  const index = tabs.indexOf(current);
  if (index < 0) return;
  let nextIndex = index;
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
  else if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = tabs.length - 1;
  else return;
  event.preventDefault();
  const next = tabs[nextIndex];
  switchSettingsTab(next.dataset.settingsTab);
  next.focus();
}

function switchSettingsTab(tab) {
  const nextTab = SETTINGS_TABS.includes(tab) ? tab : 'general';
  activeSettingsTab = nextTab;
  SETTINGS_TABS.forEach(name => {
    const active = nextTab === name;
    const suffix = name.charAt(0).toUpperCase() + name.slice(1);
    const tabButton = document.getElementById('settingsTab' + suffix);
    const panel = document.getElementById('settingsPanel' + suffix);
    tabButton.classList.toggle('active', active);
    tabButton.setAttribute('aria-selected', String(active));
    tabButton.tabIndex = active ? 0 : -1;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
  storeSettingsTab(nextTab);
  const activeButton = document.querySelector('[data-settings-tab="' + nextTab + '"]');
  if (activeButton) {
    window.requestAnimationFrame(() => activeButton.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
  }
  const body = document.querySelector('#settingsBackdrop .settings-body');
  if (body) body.scrollTop = 0;
  if (nextTab === 'risk') refreshRiskModels();
  if (nextTab === 'digest') socket.emit('get_daily_digest_status');
}

function openSettings() {
  settingsLastFocused = document.activeElement;
  applySettings(appSettings);
  clearSettingsValidation();
  showSettingsMessage('', '');
  document.getElementById('settingsBackdrop').classList.add('show');
  switchSettingsTab(readStoredSettingsTab());
  resetSettingsDirtySnapshot();
  window.requestAnimationFrame(() => {
    const activeTab = document.querySelector('.settings-tab.active');
    if (activeTab) activeTab.focus();
  });
}
