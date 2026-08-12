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
  stopBackgroundTaskAutoRefresh();
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
