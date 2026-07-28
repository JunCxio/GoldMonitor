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
