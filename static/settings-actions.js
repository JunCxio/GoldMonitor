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
    floating_price_windows_mode: document.getElementById('setFloatingWindowsMode').value,
    floating_price_taskbar_target: document.getElementById('setFloatingTaskbarTarget').value,
    floating_price_display_mode: document.getElementById('setFloatingDisplayMode').value,
    floating_price_preset: document.getElementById('setFloatingPreset').value,
    floating_price_opacity: document.getElementById('setFloatingOpacity').value.trim(),
    floating_price_snap_edge: document.getElementById('setFloatingSnapEdge').checked,
    floating_price_always_on_top: document.getElementById('setFloatingAlwaysOnTop').checked,
    floating_price_hide_on_fullscreen: document.getElementById('setFloatingHideOnFullscreen').checked,
    floating_price_lock_position: document.getElementById('setFloatingLockPosition').checked,
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
    notification_auto_retry_enabled: document.getElementById('setNotificationAutoRetry').checked,
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

function retryFailedNotifications() {
  const button = document.getElementById('btnRetryFailedNotifications');
  if (button) button.disabled = true;
  setNotificationRetryStatus('正在重试队列中的失败渠道…', null);
  socket.emit('retry_failed_notifications');
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
