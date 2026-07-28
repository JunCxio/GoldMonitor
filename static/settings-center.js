let pendingSettingsSave = false;
let settingsSaveFailed = false;
let settingsSaveTimer = null;
const SETTINGS_TABS = ['general', 'email', 'webhook', 'digest', 'risk', 'ops'];
const SETTINGS_TAB_STORAGE_KEY = 'goldmonitor.settings.activeTab';
const SETTINGS_TAB_LABELS = {
  general: '通用设置',
  email: '邮件通知',
  webhook: 'Webhook',
  digest: '摘要通知',
  risk: '风险分析',
  ops: '运维与数据',
};
const SETTINGS_FIELD_IDS = [
  'setStartup', 'setStartupTray', 'setFloatingPrice', 'setFloatingDisplayMode',
  'setFloatingPreset', 'setFloatingOpacity', 'setFloatingSnapEdge', 'setFloatingAlwaysOnTop',
  'setCloseBehavior', 'setAlertSound', 'setAlertDialog', 'setAlertCooldownMinutes',
  'setAlertQuietStart', 'setAlertQuietEnd', 'setSmtpServer', 'setSmtpPort',
  'setSmtpEncryption', 'setSmtpSender', 'setSmtpPassword', 'clearSmtpPassword',
  'setSmtpRecipient', 'setEmailSubjectTemplate', 'setEmailBodyTemplate', 'setWebhookEnabled',
  'setWebhookUrl', 'setWebhookWarning', 'setWebhookCritical', 'setWebhookVolatility',
  'setDailyDigestEnabled', 'setDailyDigestTime', 'setDailyDigestEmail', 'setDailyDigestWebhook',
  'setRiskAssistantEnabled', 'setRiskAssistantProvider', 'setRiskAssistantDepth',
  'setDeepseekBaseUrl', 'setDeepseekModel', 'setDeepseekApiKey', 'clearDeepseekApiKey',
  'setOpenaiCompatibleBaseUrl', 'setOpenaiCompatibleModel', 'setOpenaiCompatibleApiKey',
  'clearOpenaiCompatibleApiKey', 'setRiskMaxTokens', 'setRiskCooldownSeconds',
  'setRiskCacheMinutes', 'setExportDir',
];
let settingsInitialSnapshot = '';
let settingsDirty = false;
let settingsLastFocused = null;
let activeSettingsTab = 'general';
let onboardingStep = 1;
let onboardingManual = false;
let onboardingAutoChecked = false;
let deepseekModelOptions = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'];
let dailyDigestStatusState = {};

function registerSettingsSocketHandlers(socket) {
  socket.on('settings_updated', data => {
    if (settingsSaveTimer) {
      clearTimeout(settingsSaveTimer);
      settingsSaveTimer = null;
    }
    const shouldClearProfileMatch = alertProfileSettingsChanged(data || {});
    if (settingsSaveFailed) {
      appSettings = Object.assign({}, appSettings, data || {});
      if (shouldClearProfileMatch) clearCurrentAlertProfileMatch();
      pendingSettingsSave = false;
      setSettingsSaving(false);
      return;
    }
    applySettings(data || {});
    if (shouldClearProfileMatch) clearCurrentAlertProfileMatch();
    pendingSettingsSave = false;
    resetSettingsDirtySnapshot();
    showSettingsMessage('设置已保存并生效。', 'ok');
  });

  socket.on('settings_error', data => {
    if (settingsSaveTimer) {
      clearTimeout(settingsSaveTimer);
      settingsSaveTimer = null;
    }
    pendingSettingsSave = false;
    settingsSaveFailed = true;
    setSettingsDirty(true);
    showSettingsMessage(data.message || '设置保存失败。', 'error');
    if (data && data.export_dir_check) renderExportDirStatus(data.export_dir_check);
  });

  socket.on('onboarding_started', data => {
    if (data && data.settings) appSettings = Object.assign({}, appSettings, data.settings);
  });

  socket.on('onboarding_completed', data => {
    const finishButton = document.getElementById('onboardingFinishButton');
    const skipButton = document.getElementById('onboardingSkipButton');
    if (finishButton) finishButton.disabled = false;
    if (skipButton) skipButton.disabled = false;
    if (!data || data.ok === false) return;
    if (data.settings) applySettings(data.settings);
    document.getElementById('onboardingBackdrop').classList.remove('show');
    if (data.startup_error) setOpsStatus('首次使用设置已保存，但开机自启动设置失败，请检查系统权限。', false);
  });

  socket.on('onboarding_error', data => {
    const message = document.getElementById('onboardingMessage');
    const finishButton = document.getElementById('onboardingFinishButton');
    const skipButton = document.getElementById('onboardingSkipButton');
    if (message) message.textContent = (data && data.message) || '首次使用设置保存失败。';
    if (finishButton) finishButton.disabled = false;
    if (skipButton) skipButton.disabled = false;
  });

  socket.on('daily_digest_status', data => {
    applyDailyDigestStatus(data || {});
  });

  socket.on('daily_digest_previewed', data => {
    const button = document.getElementById('btnPreviewDailyDigest');
    if (button) button.disabled = false;
    if (!data || data.ok === false) {
      setDailyDigestStatus((data && data.message) || '生成摘要预览失败。', false);
      return;
    }
    renderDailyDigestPreview(data);
    setDailyDigestStatus('摘要预览已生成，未发送通知。', true);
  });

  socket.on('daily_digest_test_result', data => {
    const button = document.getElementById('btnTestDailyDigest');
    if (button) button.disabled = false;
    if (data && data.digest) renderDailyDigestPreview(data.digest);
    setDailyDigestStatus(
      data && data.message ? '测试发送：' + data.message : '测试发送已完成。',
      !!(data && data.ok)
    );
  });
  socket.on('test_email_result', data => {
    const statusEl = document.getElementById('testEmailStatus');
    const btn = document.getElementById('btnTestEmail');
    btn.disabled = false;
    if (data.ok) {
      statusEl.textContent = data.message;
      statusEl.className = 'test-email-status ok';
    } else {
      statusEl.textContent = data.message;
      statusEl.className = 'test-email-status fail';
    }
  });
  socket.on('test_webhook_result', data => {
    const statusEl = document.getElementById('testWebhookStatus');
    const btn = document.getElementById('btnTestWebhook');
    if (btn) btn.disabled = false;
    if (!statusEl) return;
    statusEl.textContent = data && data.message ? data.message : 'Webhook 测试完成。';
    statusEl.className = 'test-email-status ' + (data && data.ok ? 'ok' : 'fail');
  });
  socket.on('test_alert_result', data => {
    const statusEl = document.getElementById('testAlertStatus');
    if (!statusEl) return;
    statusEl.textContent = data && data.message ? data.message : '测试提醒已触发。';
    statusEl.className = 'test-email-status ' + (data && data.ok ? 'ok' : 'fail');
  });
}

// ========== 设置中心 ==========
function configureSecretClear(inputId, statusId, buttonId, configured, statusText, readyLabel, emptyLabel) {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const button = document.getElementById(buttonId);
  if (!input || !status || !button) return;
  input.checked = false;
  status.textContent = statusText;
  status.dataset.state = configured ? 'ok' : '';
  button.disabled = !configured;
  button.textContent = configured ? readyLabel : emptyLabel;
  button.classList.remove('marked');
  button.dataset.defaultLabel = readyLabel;
  button.dataset.defaultStatus = statusText;
}

function toggleSecretClear(inputId, statusId, buttonId, selectedStatus) {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const button = document.getElementById(buttonId);
  if (!input || !status || !button || button.disabled) return;
  input.checked = !input.checked;
  if (input.checked) {
    status.textContent = selectedStatus;
    status.dataset.state = 'error';
    button.textContent = '取消删除';
    button.classList.add('marked');
    updateSettingsDirtyState();
    return;
  }
  status.textContent = button.dataset.defaultStatus || '';
  status.dataset.state = button.disabled ? '' : 'ok';
  button.textContent = button.dataset.defaultLabel || '删除已保存密钥';
  button.classList.remove('marked');
  updateSettingsDirtyState();
}

// ========== 设置 ==========
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setRowHidden(id, hidden) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('platform-hidden', !!hidden);
}

function applyPlatformLabels() {
  const platform = appSettings.platform || 'windows';
  const capabilities = appSettings.platform_capabilities || {};
  const isMac = platform === 'macos';
  const menuBarMode = capabilities.floating_price_mode === 'menu_bar';

  setText('startupTrayLabel', isMac ? '自启动时进入菜单栏' : '自启动时进入托盘');
  setText('startupTrayDesc', isMac ? '开机启动后不弹出主窗口，可从菜单栏打开。' : '开机启动后不弹出主窗口，可从右下角托盘打开。');
  setText('floatingPriceLabel', menuBarMode ? '菜单栏金价' : '桌面金价悬浮条');
  setText('floatingPriceDesc', menuBarMode ? '在 macOS 菜单栏显示当前金价，并提供显示窗口、刷新和风险分析入口。' : '主窗口隐藏时，仍在桌面右下角显示当前金价。');
  setText('floatingDisplayDesc', menuBarMode ? '控制菜单栏优先显示人民币、美元或组合价格。' : '控制桌面悬浮条显示人民币、美元或组合内容。');
  setText('closeChoiceCopy', isMac ? '隐藏到菜单栏后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。' : '最小化到右下角托盘后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。');
  setText('closeMinimizeOption', isMac ? '隐藏到菜单栏' : '最小化到托盘');
  setText('closeMinimizeButton', isMac ? '隐藏到菜单栏' : '最小化到托盘');

  setRowHidden('floatingPresetRow', menuBarMode);
  setRowHidden('floatingOpacityRow', menuBarMode);
  setRowHidden('floatingSnapRow', menuBarMode);
  setRowHidden('floatingTopmostRow', menuBarMode);
}

function dailyDigestSelectedChannels() {
  const channels = [];
  if (appSettings.daily_digest_email_enabled !== false) channels.push('email');
  if (appSettings.daily_digest_webhook_enabled) channels.push('webhook');
  return channels;
}

function dailyDigestChannelText(channels) {
  const labels = { email: '邮件', webhook: 'Webhook' };
  const selected = Array.isArray(channels) ? channels : [];
  return selected.length ? selected.map(channel => labels[channel] || channel).join('、') : '未选择';
}

function dailyDigestTimestamp(value) {
  const text = String(value || '').trim();
  return text ? text.replace('T', ' ').slice(0, 16) : '';
}

function setDailyDigestStatus(message, ok) {
  const status = document.getElementById('dailyDigestStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'setting-status setting-status-wide';
  if (ok === true) status.dataset.state = 'ok';
  else if (ok === false) status.dataset.state = 'error';
  else delete status.dataset.state;
}

function applyDailyDigestStatus(data) {
  const next = data && typeof data === 'object' ? data : {};
  dailyDigestStatusState = Object.assign({}, dailyDigestStatusState, next, {
    state: Object.assign({}, dailyDigestStatusState.state || {}, next.state || {}),
    schedule: Object.assign({}, dailyDigestStatusState.schedule || {}, next.schedule || {}),
  });
  const enabled = dailyDigestStatusState.enabled != null
    ? !!dailyDigestStatusState.enabled
    : !!appSettings.daily_digest_enabled;
  const time = dailyDigestStatusState.time || appSettings.daily_digest_time || '20:00';
  const channels = Array.isArray(dailyDigestStatusState.channels)
    ? dailyDigestStatusState.channels
    : dailyDigestSelectedChannels();
  const state = dailyDigestStatusState.state || {};
  const schedule = dailyDigestStatusState.schedule || {};
  const parts = [enabled ? '已启用，每日 ' + time : '未启用', '渠道：' + dailyDigestChannelText(channels)];
  const completedAt = dailyDigestTimestamp(state.last_completed_at);
  const testedAt = dailyDigestTimestamp(state.last_test_at);
  if (completedAt) parts.push('最近计划执行：' + completedAt);
  else if (enabled && schedule.reason === 'before_schedule') parts.push('等待今日计划时间');
  else if (enabled && schedule.reason === 'due') parts.push('等待任务执行');
  else if (enabled && schedule.reason === 'invalid_schedule') parts.push('发送时间无效');
  if (testedAt) parts.push('最近测试：' + testedAt);
  if (state.last_message) parts.push(state.last_message);
  const okStatuses = ['sent', 'queued'];
  const failStatuses = ['failed', 'partial', 'skipped'];
  const statusFlag = okStatuses.includes(state.last_status)
    ? true
    : failStatuses.includes(state.last_status) || schedule.reason === 'invalid_schedule'
      ? false
      : null;
  setDailyDigestStatus(parts.join('；'), statusFlag);
}

function renderDailyDigestPreview(data) {
  const preview = document.getElementById('dailyDigestPreview');
  if (!preview) return;
  const digest = data && data.digest ? data.digest : (data || {});
  const subject = String(digest.subject || '').trim();
  const message = String(digest.message || '').trim();
  preview.value = [subject, message].filter(Boolean).join('\n\n');
}

function applySettings(data) {
  appSettings = Object.assign({}, appSettings, data);
  applyPlatformLabels();
  const closeBehavior = appSettings.close_behavior || 'ask';
  document.getElementById('setStartup').checked = !!appSettings.startup_enabled;
  document.getElementById('setStartupTray').checked = !!appSettings.startup_to_tray;
  document.getElementById('setFloatingPrice').checked = appSettings.floating_price_enabled !== false;
  document.getElementById('setFloatingDisplayMode').value = appSettings.floating_price_display_mode || 'rmb_usd';
  document.getElementById('setFloatingPreset').value = appSettings.floating_price_preset || 'compact';
  document.getElementById('setFloatingOpacity').value = appSettings.floating_price_opacity || 94;
  document.getElementById('setFloatingSnapEdge').checked = appSettings.floating_price_snap_edge !== false;
  document.getElementById('setFloatingAlwaysOnTop').checked = !!appSettings.floating_price_always_on_top;
  document.getElementById('setCloseBehavior').value = closeBehavior;
  document.getElementById('setAlertSound').checked = !!appSettings.alert_sound_enabled;
  document.getElementById('setAlertDialog').checked = !!appSettings.alert_dialog_enabled;
  // 邮件通知
  document.getElementById('setSmtpServer').value = appSettings.smtp_server || '';
  document.getElementById('setSmtpPort').value = appSettings.smtp_port || '465';
  document.getElementById('setSmtpEncryption').value = appSettings.smtp_encryption || 'ssl';
  document.getElementById('setSmtpSender').value = appSettings.smtp_sender || '';
  document.getElementById('setSmtpPassword').value = '';
  const smtpPasswordStatus = appSettings.smtp_password_configured
    ? '已保存授权码：' + (appSettings.smtp_password_masked || '******') + '。输入新授权码后保存会替换当前授权码。'
    : '未保存授权码。输入授权码后保存即可启用邮件发送。';
  configureSecretClear(
    'clearSmtpPassword',
    'smtpPasswordStatus',
    'clearSmtpPasswordButton',
    !!appSettings.smtp_password_configured,
    smtpPasswordStatus,
    '删除已保存授权码',
    '暂无已保存授权码'
  );
  document.getElementById('setSmtpRecipient').value = appSettings.smtp_recipient || '';
  document.getElementById('setAlertCooldownMinutes').value = appSettings.alert_cooldown_minutes ?? 30;
  document.getElementById('setAlertQuietStart').value = appSettings.alert_quiet_start || '';
  document.getElementById('setAlertQuietEnd').value = appSettings.alert_quiet_end || '';
  document.getElementById('setEmailSubjectTemplate').value = appSettings.email_subject_template || '[金价预警·{level}] {title}';
  document.getElementById('setEmailBodyTemplate').value = appSettings.email_body_template || '';
  document.getElementById('setWebhookEnabled').checked = !!appSettings.webhook_enabled;
  document.getElementById('setWebhookUrl').value = appSettings.webhook_url || '';
  document.getElementById('setWebhookWarning').checked = appSettings.webhook_warning_enabled !== false;
  document.getElementById('setWebhookCritical').checked = appSettings.webhook_critical_enabled !== false;
  document.getElementById('setWebhookVolatility').checked = appSettings.webhook_volatility_enabled !== false;
  document.getElementById('setDailyDigestEnabled').checked = !!appSettings.daily_digest_enabled;
  document.getElementById('setDailyDigestTime').value = appSettings.daily_digest_time || '20:00';
  document.getElementById('setDailyDigestEmail').checked = appSettings.daily_digest_email_enabled !== false;
  document.getElementById('setDailyDigestWebhook').checked = !!appSettings.daily_digest_webhook_enabled;
  applyDailyDigestStatus(Object.assign({}, dailyDigestStatusState, {
    enabled: !!appSettings.daily_digest_enabled,
    time: appSettings.daily_digest_time || '20:00',
    channels: dailyDigestSelectedChannels(),
  }));
  document.getElementById('testEmailStatus').textContent = '';
  document.getElementById('testEmailStatus').className = 'test-email-status';
  const webhookStatus = document.getElementById('testWebhookStatus');
  if (webhookStatus) {
    webhookStatus.textContent = '';
    webhookStatus.className = 'test-email-status';
  }
  const testAlertStatus = document.getElementById('testAlertStatus');
  if (testAlertStatus) {
    testAlertStatus.textContent = '';
    testAlertStatus.className = 'test-email-status';
  }
  document.getElementById('setRiskAssistantEnabled').checked = appSettings.risk_assistant_enabled !== false;
  document.getElementById('setRiskAssistantProvider').value = appSettings.risk_assistant_provider || 'deepseek';
  document.getElementById('setRiskAssistantDepth').value = appSettings.risk_assistant_depth || 'standard';
  document.getElementById('setDeepseekBaseUrl').value = appSettings.deepseek_base_url || 'https://api.deepseek.com';
  renderDeepseekModelOptions(appSettings.deepseek_model || 'deepseek-v4-pro');
  document.getElementById('setDeepseekApiKey').value = '';
  const keyStatus = appSettings.deepseek_api_key_configured
    ? '已保存密钥：' + (appSettings.deepseek_api_key_masked || '******') + '。输入新 Key 后保存会替换当前密钥。'
    : '未保存密钥。输入 API Key 后保存即可启用该模型。';
  configureSecretClear(
    'clearDeepseekApiKey',
    'deepseekKeyStatus',
    'clearDeepseekApiKeyButton',
    !!appSettings.deepseek_api_key_configured,
    keyStatus,
    '删除已保存密钥',
    '暂无已保存密钥'
  );
  document.getElementById('setOpenaiCompatibleBaseUrl').value = appSettings.openai_compatible_base_url || '';
  document.getElementById('setOpenaiCompatibleModel').value = appSettings.openai_compatible_model || '';
  document.getElementById('setOpenaiCompatibleApiKey').value = '';
  const compatibleKeyStatus = appSettings.openai_compatible_api_key_configured
    ? '已保存密钥：' + (appSettings.openai_compatible_api_key_masked || '******') + '。输入新 Key 后保存会替换当前密钥。'
    : '未保存密钥。输入 API Key 后保存即可启用该接口。';
  configureSecretClear(
    'clearOpenaiCompatibleApiKey',
    'openaiCompatibleKeyStatus',
    'clearOpenaiCompatibleApiKeyButton',
    !!appSettings.openai_compatible_api_key_configured,
    compatibleKeyStatus,
    '删除已保存密钥',
    '暂无已保存密钥'
  );
  document.getElementById('setRiskMaxTokens').value = appSettings.risk_assistant_max_tokens || 1200;
  document.getElementById('setRiskCooldownSeconds').value = appSettings.risk_assistant_cooldown_seconds || 15;
  document.getElementById('setRiskCacheMinutes').value = appSettings.risk_assistant_cache_minutes ?? 10;
  applyExportDirSetting();
  const modelTestStatus = document.getElementById('riskModelTestStatus');
  if (modelTestStatus) {
    modelTestStatus.textContent = '';
    modelTestStatus.className = 'model-test-status';
  }
  updateRiskProviderFields();
  updateRiskButtonState();
  renderAlertRules();
  scheduleAutoUpdateCheck();
}

function applyExportDirSetting() {
  const input = document.getElementById('setExportDir');
  if (!input) return;
  const configured = appSettings.export_dir || '';
  const effective = appSettings.export_dir_effective || appSettings.export_dir_default || '';
  input.value = configured;
  renderExportDirStatus(appSettings.export_dir_check, configured
    ? '当前导出目录：' + effective
    : '当前使用默认导出目录：' + (effective || '未记录'));
}

function exportDirActionButton(action) {
  if (action === 'choose_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="chooseExportDir()">重新选择</button>';
  }
  if (action === 'use_default_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="useDefaultExportDirFromError()">使用默认</button>';
  }
  if (action === 'open_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="openExportsFolder()">打开当前目录</button>';
  }
  return '';
}

function renderExportDirStatus(check, fallbackText) {
  const status = document.getElementById('exportDirStatus');
  if (!status) return;
  const data = check && typeof check === 'object' ? check : null;
  if (!data || !data.status) {
    status.textContent = fallbackText || '留空使用默认导出目录。';
    delete status.dataset.state;
    return;
  }
  const statusClass = data.ok ? 'ok' : 'fail';
  status.dataset.state = data.ok ? 'ok' : 'error';
  const actions = Array.isArray(data.actions) ? data.actions.map(exportDirActionButton).filter(Boolean) : [];
  status.innerHTML = [
    '<span class="export-dir-check ' + statusClass + '">' + escapeHtml(data.message || fallbackText || '') + '</span>',
    actions.length ? '<span class="export-dir-actions">' + actions.join('') + '</span>' : '',
  ].join('');
}

function clearSettingsMessage() {
  showSettingsMessage('', '');
}

function resetExportDirField() {
  const input = document.getElementById('setExportDir');
  if (!input) return;
  input.value = '';
  clearSettingsMessage();
  renderExportDirStatus(null, '保存后将使用默认导出目录：' + (appSettings.export_dir_default || appSettings.export_dir_effective || '未记录'));
  updateSettingsDirtyState();
}

function useDefaultExportDirFromError() {
  resetExportDirField();
  setOpsStatus('已切换为默认导出目录，保存后生效。', true);
}

function chooseExportDir() {
  const input = document.getElementById('setExportDir');
  const status = document.getElementById('exportDirStatus');
  const button = document.getElementById('chooseExportDirButton');
  const picker = window.pywebview && window.pywebview.api && window.pywebview.api.choose_export_dir;
  if (!input) return;
  clearSettingsMessage();
  if (typeof picker !== 'function') {
    const message = '当前浏览器模式不支持系统目录选择器，请手动输入导出目录。';
    if (status) status.textContent = message;
    setOpsStatus(message, false);
    return;
  }

  if (status) status.textContent = '正在打开系统目录选择器...';
  if (button) button.disabled = true;
  Promise.resolve(picker.call(window.pywebview.api))
    .then(data => {
      const message = data && data.message ? data.message : '目录选择完成。';
      if (!data || !data.ok) {
        if (status) status.textContent = message;
        if (!data || !data.cancelled) setOpsStatus(message, false);
        return;
      }
      input.value = data.path || '';
      const savedMessage = message + '，保存后生效。';
      if (status) status.textContent = savedMessage;
      setOpsStatus('已选择导出目录，保存后生效。', true);
      updateSettingsDirtyState();
    })
    .catch(() => {
      const message = '无法打开系统目录选择器，请手动输入导出目录。';
      if (status) status.textContent = message;
      setOpsStatus(message, false);
    })
    .finally(() => {
      if (button) button.disabled = false;
    });
}

function renderDeepseekModelOptions(selected) {
  const select = document.getElementById('setDeepseekModel');
  const model = selected || 'deepseek-v4-pro';
  const options = Array.from(new Set([model, ...deepseekModelOptions].filter(Boolean)));
  select.innerHTML = options.map(item => (
    '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'
  )).join('');
  select.value = model;
}

function updateRiskProviderFields() {
  const provider = document.getElementById('setRiskAssistantProvider').value || 'deepseek';
  document.querySelectorAll('.risk-provider-row').forEach(row => {
    row.classList.toggle('hidden', row.getAttribute('data-provider') !== provider);
  });
}

function refreshRiskModels() {
  const status = document.getElementById('deepseekModelStatus');
  if (status) {
    status.textContent = '正在获取模型列表...';
    delete status.dataset.state;
  }
  socket.emit('get_risk_model_options', { provider: 'deepseek' });
}

function testRiskModel() {
  const status = document.getElementById('riskModelTestStatus');
  if (status) {
    status.textContent = '正在测试当前模型生成能力...';
    status.className = 'model-test-status';
  }
  socket.emit('test_risk_model');
}

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

function onboardingPriceText() {
  if (Number.isFinite(Number(latestData.rmb))) return '¥' + Number(latestData.rmb).toFixed(2) + '/克';
  if (Number.isFinite(Number(latestData.usd))) return '$' + Number(latestData.usd).toFixed(2) + '/盎司';
  return '等待行情';
}

function updateOnboardingStatus() {
  const market = document.getElementById('onboardingMarketStatus');
  const price = document.getElementById('onboardingPriceStatus');
  const source = document.getElementById('onboardingSourceStatus');
  const statusText = document.getElementById('statusText');
  if (market) market.textContent = statusText && statusText.textContent ? statusText.textContent : '本地服务已连接';
  if (price) price.textContent = onboardingPriceText();
  if (source) source.textContent = latestData.gold_source || '等待行情';
}

function populateOnboardingFields() {
  document.getElementById('onboardingDisplayMode').value = appSettings.floating_price_display_mode || 'rmb_usd';
  document.getElementById('onboardingFloatingEnabled').checked = appSettings.floating_price_enabled !== false;
  document.getElementById('onboardingStartupEnabled').checked = !!appSettings.startup_enabled;
  document.getElementById('onboardingStartupTray').checked = appSettings.startup_to_tray !== false;
  document.getElementById('onboardingCloseBehavior').value = appSettings.close_behavior || 'ask';
  document.getElementById('onboardingAlertSound').checked = appSettings.alert_sound_enabled !== false;
  document.getElementById('onboardingAlertDialog').checked = appSettings.alert_dialog_enabled !== false;
  const cooldown = document.getElementById('onboardingCooldown');
  const cooldownValue = String(appSettings.alert_cooldown_minutes ?? 30);
  if (![...cooldown.options].some(option => option.value === cooldownValue)) {
    const option = document.createElement('option');
    option.value = cooldownValue;
    option.textContent = cooldownValue + ' 分钟';
    cooldown.appendChild(option);
  }
  cooldown.value = cooldownValue;
}

function onboardingPreferences() {
  return {
    floating_price_display_mode: document.getElementById('onboardingDisplayMode').value,
    floating_price_enabled: document.getElementById('onboardingFloatingEnabled').checked,
    startup_enabled: document.getElementById('onboardingStartupEnabled').checked,
    startup_to_tray: document.getElementById('onboardingStartupTray').checked,
    close_behavior: document.getElementById('onboardingCloseBehavior').value,
    alert_sound_enabled: document.getElementById('onboardingAlertSound').checked,
    alert_dialog_enabled: document.getElementById('onboardingAlertDialog').checked,
    alert_cooldown_minutes: document.getElementById('onboardingCooldown').value,
  };
}

function renderOnboardingSummary() {
  const summary = document.getElementById('onboardingSummary');
  if (!summary) return;
  const preferences = onboardingPreferences();
  const displayLabels = { rmb_usd: '人民币与美元', rmb_only: '仅人民币', usd_only: '仅美元' };
  const closeLabels = { ask: '关闭时询问', minimize_to_tray: '继续在后台运行', exit: '退出程序' };
  const parts = [
    '悬浮窗：' + (preferences.floating_price_enabled ? displayLabels[preferences.floating_price_display_mode] : '不启用'),
    '开机自启动：' + (preferences.startup_enabled ? '启用' : '不启用'),
    '关闭行为：' + (closeLabels[preferences.close_behavior] || '关闭时询问'),
    '提示音：' + (preferences.alert_sound_enabled ? '启用' : '关闭'),
    '警报窗口：' + (preferences.alert_dialog_enabled ? '启用' : '关闭'),
    '相同规则冷却：' + preferences.alert_cooldown_minutes + ' 分钟',
  ];
  summary.innerHTML = parts.map(part => '<div>' + escapeHtml(part) + '</div>').join('');
}

function showOnboardingStep(step) {
  onboardingStep = Math.max(1, Math.min(4, Number(step) || 1));
  document.querySelectorAll('[data-onboarding-step]').forEach(section => {
    section.classList.toggle('active', Number(section.dataset.onboardingStep) === onboardingStep);
  });
  document.querySelectorAll('[data-onboarding-progress]').forEach(item => {
    item.classList.toggle('active', Number(item.dataset.onboardingProgress) <= onboardingStep);
  });
  document.getElementById('onboardingBackButton').hidden = onboardingStep === 1;
  document.getElementById('onboardingNextButton').hidden = onboardingStep === 4;
  document.getElementById('onboardingFinishButton').hidden = onboardingStep !== 4;
  if (onboardingStep === 1) updateOnboardingStatus();
  if (onboardingStep === 4) renderOnboardingSummary();
}

function openOnboarding(manual) {
  onboardingManual = !!manual;
  populateOnboardingFields();
  const message = document.getElementById('onboardingMessage');
  if (message) message.textContent = '';
  document.getElementById('onboardingSkipButton').textContent = onboardingManual ? '关闭向导' : '暂不设置';
  document.getElementById('onboardingBackdrop').classList.add('show');
  showOnboardingStep(1);
  if (!onboardingManual && !appSettings.onboarding_started) socket.emit('start_onboarding');
}

function maybeOpenOnboarding() {
  if (onboardingAutoChecked) return;
  onboardingAutoChecked = true;
  if (appSettings.onboarding_completed) return;
  setTimeout(() => openOnboarding(false), 120);
}

function reopenOnboarding() {
  if (settingsDirty || pendingSettingsSave) {
    showSettingsMessage('请先保存或放弃当前更改，再重新打开首次使用向导。', 'error');
    return;
  }
  closeSettings(true);
  openOnboarding(true);
}

function changeOnboardingStep(delta) {
  showOnboardingStep(onboardingStep + Number(delta || 0));
}

function finishOnboarding() {
  const finishButton = document.getElementById('onboardingFinishButton');
  if (finishButton) finishButton.disabled = true;
  socket.emit('complete_onboarding', onboardingPreferences());
}

function skipOnboarding() {
  if (onboardingManual) {
    document.getElementById('onboardingBackdrop').classList.remove('show');
    return;
  }
  const skipButton = document.getElementById('onboardingSkipButton');
  if (skipButton) skipButton.disabled = true;
  socket.emit('complete_onboarding', {});
}

function hideSettingsDiscardPrompt() {
  const prompt = document.getElementById('settingsUnsavedConfirm');
  if (prompt) prompt.hidden = true;
}

function discardSettingsChanges() {
  closeSettings(true);
}

function settingsFocusableElements() {
  const modal = document.querySelector('.settings-primary-modal');
  if (!modal) return [];
  return Array.from(modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
    .filter(element => !element.hidden && element.offsetParent !== null);
}

function handleSettingsDialogKeydown(event) {
  const backdrop = document.getElementById('settingsBackdrop');
  if (!backdrop || !backdrop.classList.contains('show')) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeSettings();
    return;
  }
  if (event.key !== 'Tab') return;
  const focusable = settingsFocusableElements();
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function closeSettings(force) {
  const backdrop = document.getElementById('settingsBackdrop');
  if (!backdrop || !backdrop.classList.contains('show')) return;
  if (!force && pendingSettingsSave) {
    showSettingsMessage('设置正在保存，请等待后台确认。', '');
    return;
  }
  if (!force && settingsDirty) {
    const prompt = document.getElementById('settingsUnsavedConfirm');
    if (prompt) prompt.hidden = false;
    const discardButton = document.getElementById('settingsDiscardButton');
    if (discardButton) discardButton.focus();
    return;
  }
  backdrop.classList.remove('show');
  hideSettingsDiscardPrompt();
  clearSettingsValidation();
  settingsInitialSnapshot = '';
  settingsDirty = false;
  if (settingsLastFocused && typeof settingsLastFocused.focus === 'function') settingsLastFocused.focus();
  settingsLastFocused = null;
}

function onSettingsBackdrop(event) {
  if (event.target.id === 'settingsBackdrop') closeSettings();
}

function setupSettingsInteractions() {
  const backdrop = document.getElementById('settingsBackdrop');
  const tabs = document.querySelector('.settings-primary-modal .settings-tabs');
  if (backdrop) {
    backdrop.addEventListener('input', handleSettingsFieldChange);
    backdrop.addEventListener('change', handleSettingsFieldChange);
  }
  if (tabs) tabs.addEventListener('keydown', handleSettingsTabKeydown);
  document.addEventListener('keydown', handleSettingsDialogKeydown);
}

setupSettingsInteractions();

function saveSettings() {
  if (pendingSettingsSave) return;
  if (!settingsDirty) {
    showSettingsMessage('当前没有需要保存的更改。', '');
    return;
  }
  if (!validateSettings()) return;
  const closeBehavior = document.getElementById('setCloseBehavior').value;
  const next = {
    startup_enabled: document.getElementById('setStartup').checked,
    startup_to_tray: document.getElementById('setStartupTray').checked,
    floating_price_enabled: document.getElementById('setFloatingPrice').checked,
    floating_price_display_mode: document.getElementById('setFloatingDisplayMode').value,
    floating_price_preset: document.getElementById('setFloatingPreset').value,
    floating_price_opacity: document.getElementById('setFloatingOpacity').value.trim(),
    floating_price_snap_edge: document.getElementById('setFloatingSnapEdge').checked,
    floating_price_always_on_top: document.getElementById('setFloatingAlwaysOnTop').checked,
    close_behavior: closeBehavior,
    close_remembered: closeBehavior !== 'ask',
    alert_sound_enabled: document.getElementById('setAlertSound').checked,
    alert_dialog_enabled: document.getElementById('setAlertDialog').checked,
    // 邮件通知
    smtp_server: document.getElementById('setSmtpServer').value.trim(),
    smtp_port: document.getElementById('setSmtpPort').value.trim(),
    smtp_encryption: document.getElementById('setSmtpEncryption').value,
    smtp_sender: document.getElementById('setSmtpSender').value.trim(),
    smtp_password: document.getElementById('setSmtpPassword').value,
    smtp_password_clear: document.getElementById('clearSmtpPassword').checked,
    smtp_recipient: document.getElementById('setSmtpRecipient').value.trim(),
    email_warning_enabled: appSettings.email_warning_enabled !== false,
    email_critical_enabled: appSettings.email_critical_enabled !== false,
    email_volatility_enabled: appSettings.email_volatility_enabled !== false,
    alert_cooldown_minutes: document.getElementById('setAlertCooldownMinutes').value.trim(),
    alert_quiet_start: document.getElementById('setAlertQuietStart').value,
    alert_quiet_end: document.getElementById('setAlertQuietEnd').value,
    email_subject_template: document.getElementById('setEmailSubjectTemplate').value,
    email_body_template: document.getElementById('setEmailBodyTemplate').value,
    webhook_enabled: document.getElementById('setWebhookEnabled').checked,
    webhook_url: document.getElementById('setWebhookUrl').value.trim(),
    webhook_warning_enabled: document.getElementById('setWebhookWarning').checked,
    webhook_critical_enabled: document.getElementById('setWebhookCritical').checked,
    webhook_volatility_enabled: document.getElementById('setWebhookVolatility').checked,
    daily_digest_enabled: document.getElementById('setDailyDigestEnabled').checked,
    daily_digest_time: document.getElementById('setDailyDigestTime').value,
    daily_digest_email_enabled: document.getElementById('setDailyDigestEmail').checked,
    daily_digest_webhook_enabled: document.getElementById('setDailyDigestWebhook').checked,
    risk_assistant_enabled: document.getElementById('setRiskAssistantEnabled').checked,
    risk_assistant_provider: document.getElementById('setRiskAssistantProvider').value,
    risk_assistant_depth: document.getElementById('setRiskAssistantDepth').value,
    deepseek_base_url: document.getElementById('setDeepseekBaseUrl').value.trim(),
    deepseek_model: document.getElementById('setDeepseekModel').value,
    deepseek_api_key: document.getElementById('setDeepseekApiKey').value.trim(),
    deepseek_api_key_clear: document.getElementById('clearDeepseekApiKey').checked,
    openai_compatible_base_url: document.getElementById('setOpenaiCompatibleBaseUrl').value.trim(),
    openai_compatible_model: document.getElementById('setOpenaiCompatibleModel').value.trim(),
    openai_compatible_api_key: document.getElementById('setOpenaiCompatibleApiKey').value.trim(),
    openai_compatible_api_key_clear: document.getElementById('clearOpenaiCompatibleApiKey').checked,
    risk_assistant_max_tokens: document.getElementById('setRiskMaxTokens').value.trim(),
    risk_assistant_cooldown_seconds: document.getElementById('setRiskCooldownSeconds').value.trim(),
    risk_assistant_cache_minutes: document.getElementById('setRiskCacheMinutes').value.trim(),
    export_dir: document.getElementById('setExportDir').value.trim(),
  };
  pendingSettingsSave = true;
  settingsSaveFailed = false;
  setSettingsSaving(true);
  showSettingsMessage('正在保存并应用设置...', '');
  socket.emit('update_settings', next);
  if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
  settingsSaveTimer = setTimeout(() => {
    if (!pendingSettingsSave) return;
    pendingSettingsSave = false;
    settingsSaveFailed = true;
    setSettingsDirty(true);
    showSettingsMessage('保存失败：后台服务未响应，请退出托盘中的旧程序后重新打开最新版。', 'error');
  }, 5000);
}

function testEmail() {
  const statusEl = document.getElementById('testEmailStatus');
  const btn = document.getElementById('btnTestEmail');
  statusEl.textContent = '正在发送...';
  statusEl.className = 'test-email-status';
  btn.disabled = true;
  socket.emit('test_email');
}

function testWebhook() {
  const statusEl = document.getElementById('testWebhookStatus');
  const btn = document.getElementById('btnTestWebhook');
  if (statusEl) {
    statusEl.textContent = '正在发送...';
    statusEl.className = 'test-email-status';
  }
  if (btn) btn.disabled = true;
  socket.emit('test_webhook');
}

function previewDailyDigest() {
  const button = document.getElementById('btnPreviewDailyDigest');
  if (button) button.disabled = true;
  setDailyDigestStatus('正在生成摘要预览...', null);
  socket.emit('preview_daily_digest');
}

function testDailyDigest() {
  const button = document.getElementById('btnTestDailyDigest');
  if (button) button.disabled = true;
  setDailyDigestStatus('正在测试发送每日摘要...', null);
  socket.emit('test_daily_digest');
}

function testAlert() {
  const statusEl = document.getElementById('testAlertStatus');
  const btn = document.getElementById('btnTestAlert');
  if (statusEl) {
    statusEl.textContent = '正在触发...';
    statusEl.className = 'test-email-status';
  }
  if (btn) {
    btn.disabled = true;
    setTimeout(() => { btn.disabled = false; }, 1200);
  }
  socket.emit('test_alert', { type: 'warning' });
}
