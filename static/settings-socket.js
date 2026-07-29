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
