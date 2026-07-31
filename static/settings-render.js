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

function syncFloatingWindowsModeRows() {
  const capabilities = appSettings.platform_capabilities || {};
  const menuBarMode = capabilities.floating_price_mode === 'menu_bar';
  const hasTrayPrice = !!capabilities.has_tray_price;
  const modeSelect = document.getElementById('setFloatingWindowsMode');
  const trayOnly = hasTrayPrice && modeSelect && modeSelect.value === 'tray';

  setRowHidden('floatingWindowsModeRow', !hasTrayPrice);
  setRowHidden('floatingPresetRow', menuBarMode || trayOnly);
  setRowHidden('floatingOpacityRow', menuBarMode || trayOnly);
  setRowHidden('floatingSnapRow', menuBarMode || trayOnly);
  setRowHidden('floatingTopmostRow', menuBarMode || trayOnly);
  setRowHidden('floatingFullscreenRow', menuBarMode || trayOnly);
  setRowHidden('floatingLockRow', menuBarMode || trayOnly);
}

function applyPlatformLabels() {
  const platform = appSettings.platform || 'windows';
  const capabilities = appSettings.platform_capabilities || {};
  const isMac = platform === 'macos';
  const menuBarMode = capabilities.floating_price_mode === 'menu_bar';
  const hasTrayPrice = !!capabilities.has_tray_price;

  setText('startupTrayLabel', isMac ? '自启动时进入菜单栏' : '自启动时进入托盘');
  setText('startupTrayDesc', isMac ? '开机启动后不弹出主窗口，可从菜单栏打开。' : '开机启动后不弹出主窗口，可从右下角托盘打开。');
  setText('floatingSectionTitle', menuBarMode ? '菜单栏金价' : (hasTrayPrice ? '桌面与系统托盘行情' : '桌面悬浮条'));
  setText('floatingSectionDesc', menuBarMode ? '调整菜单栏显示内容。' : (hasTrayPrice ? '选择桌面悬浮条、Windows 原生系统托盘或两处同时显示。' : '调整悬浮条内容、尺寸和贴边行为。'));
  setText('floatingPriceLabel', menuBarMode ? '菜单栏金价' : (hasTrayPrice ? '显示常驻行情' : '桌面金价悬浮条'));
  setText('floatingPriceDesc', menuBarMode ? '在 macOS 菜单栏显示当前金价，并提供显示窗口、刷新和风险分析入口。' : (hasTrayPrice ? '系统托盘由 Explorer 原生管理，桌面悬浮条保持为独立可选显示。' : '主窗口隐藏时，仍在桌面右下角显示当前金价。'));
  setText('floatingDisplayDesc', menuBarMode ? '控制菜单栏优先显示人民币、美元或组合价格。' : (hasTrayPrice ? '组合模式下托盘图标显示人民币整数，悬停提示展示人民币和美元完整价格；仅美元模式则显示美元整数。' : '控制桌面悬浮条显示人民币、美元或组合内容。'));
  setText('closeChoiceCopy', isMac ? '隐藏到菜单栏后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。' : '最小化到右下角托盘后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。');
  setText('closeMinimizeOption', isMac ? '隐藏到菜单栏' : '最小化到托盘');
  setText('closeMinimizeButton', isMac ? '隐藏到菜单栏' : '最小化到托盘');

  syncFloatingWindowsModeRows();
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
  document.getElementById('setFloatingWindowsMode').value = appSettings.floating_price_windows_mode || 'floating';
  document.getElementById('setFloatingDisplayMode').value = appSettings.floating_price_display_mode || 'rmb_usd';
  document.getElementById('setFloatingPreset').value = appSettings.floating_price_preset || 'compact';
  document.getElementById('setFloatingOpacity').value = appSettings.floating_price_opacity || 94;
  document.getElementById('setFloatingSnapEdge').checked = appSettings.floating_price_snap_edge !== false;
  document.getElementById('setFloatingAlwaysOnTop').checked = !!appSettings.floating_price_always_on_top;
  document.getElementById('setFloatingHideOnFullscreen').checked = appSettings.floating_price_hide_on_fullscreen !== false;
  document.getElementById('setFloatingLockPosition').checked = !!appSettings.floating_price_lock_position;
  syncFloatingWindowsModeRows();
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
