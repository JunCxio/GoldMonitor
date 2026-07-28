// ========== 预警配置与观察清单 ==========
const ALERT_PROFILE_SETTING_KEYS = [
  'alert_sound_enabled',
  'alert_dialog_enabled',
  'alert_cooldown_minutes',
  'alert_quiet_start',
  'alert_quiet_end',
  'email_warning_enabled',
  'email_critical_enabled',
  'email_volatility_enabled',
  'webhook_warning_enabled',
  'webhook_critical_enabled',
  'webhook_volatility_enabled',
];

let alertProfiles = { items: [], total: 0, current_profile_id: '' };
let pendingAlertProfileApply = false;
let watchTargets = [];
let activeWatchTargetId = null;

function normalizeVolatilityConfig(data) {
  return {
    percent: data && data.percent != null ? data.percent : null,
    minutes: data && data.minutes ? data.minutes : 10,
    enabled: !!(data && data.enabled),
  };
}

function applyAlertConfigurationState(data) {
  const state = data && typeof data === 'object' ? data : {};
  allThresholds = state.thresholds || {};
  volConfig = normalizeVolatilityConfig(state.volatility_config);
  applyAlertProfiles(state.alert_profiles || {});
  applyWatchTargets(state.watch_targets || []);
}

function registerAlertConfigurationSocketHandlers(socket) {
  socket.on('thresholds_updated', data => {
    allThresholds = data || {};
    updateThresholdInputs();
    clearCurrentAlertProfileMatch();
  });

  socket.on('volatility_updated', data => {
    volConfig = normalizeVolatilityConfig(data);
    updateVolUI();
    clearCurrentAlertProfileMatch();
  });

  socket.on('alert_profiles_updated', data => {
    pendingAlertProfileApply = false;
    applyAlertProfiles(data || {});
    setAlertProfileStatus('预警策略模板已更新。', 'ok');
  });

  socket.on('alert_profile_error', data => {
    pendingAlertProfileApply = false;
    setAlertProfileStatus((data && data.message) || '预警策略模板操作失败。', 'fail');
  });

  socket.on('watch_targets_updated', data => {
    applyWatchTargets(data || []);
    setWatchTargetStatus('观察清单已更新。', 'ok');
  });

  socket.on('watch_target_error', data => {
    setWatchTargetStatus((data && data.message) || '观察清单更新失败。', 'fail');
  });

  socket.on('threshold_error', data => alert(data.message));
}

function normalizeAlertProfiles(data) {
  const items = Array.isArray(data && data.items) ? data.items : [];
  return {
    items,
    total: Number.isFinite(Number(data && data.total)) ? Number(data.total) : items.length,
    current_profile_id: data && data.current_profile_id ? String(data.current_profile_id) : '',
  };
}

function applyAlertProfiles(data) {
  alertProfiles = normalizeAlertProfiles(data);
  renderAlertProfiles();
}

function alertProfileSettingsChanged(data) {
  if (!data || !alertProfiles.current_profile_id) return false;
  return ALERT_PROFILE_SETTING_KEYS.some(key => Object.prototype.hasOwnProperty.call(data, key) && appSettings[key] !== data[key]);
}

function clearCurrentAlertProfileMatch() {
  if (pendingAlertProfileApply) return;
  if (!alertProfiles.current_profile_id) return;
  alertProfiles = Object.assign({}, alertProfiles, { current_profile_id: '' });
  renderAlertProfiles();
}

function setAlertProfileStatus(message, type) {
  const el = document.getElementById('alertProfilesStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'alert-profiles-status' + (type ? ' ' + type : '');
}

function alertProfileSummary(item) {
  const thresholds = item && item.thresholds ? item.thresholds : {};
  const thresholdCount = Object.keys(thresholds).filter(key => thresholds[key] != null).length;
  const vol = item && item.volatility_config;
  const volText = vol && vol.enabled && vol.percent != null ? '波动 ' + vol.percent + '%' : '波动关闭';
  return thresholdCount + ' 个价格阈值 · ' + volText;
}

function renderAlertProfiles() {
  const list = document.getElementById('alertProfilesList');
  const meta = document.getElementById('alertProfilesMeta');
  if (!list || !meta) return;
  const items = alertProfiles.items || [];
  meta.textContent = items.length ? items.length + ' 个模板' : '暂无模板';
  if (!items.length) {
    list.innerHTML = '<div class="alert-profiles-empty">保存当前预警配置后，可按场景一键切换。</div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const idArg = escapeHtml(JSON.stringify(String(item.id || '')));
    const active = alertProfiles.current_profile_id && alertProfiles.current_profile_id === item.id;
    const description = item.description ? '<div class="alert-profile-desc">' + escapeHtml(item.description) + '</div>' : '';
    const applied = item.last_applied_at ? ' · 上次应用 ' + String(item.last_applied_at).replace('T', ' ').slice(0, 16) : '';
    return [
      '<div class="alert-profile-item' + (active ? ' active' : '') + '">',
      '<div class="alert-profile-main">',
      '<div class="alert-profile-name">' + escapeHtml(item.name || '未命名模板') + (active ? '<span>当前</span>' : '') + '</div>',
      description,
      '<div class="alert-profile-meta">' + escapeHtml(alertProfileSummary(item) + applied) + '</div>',
      '</div>',
      '<div class="alert-profile-actions">',
      '<button class="btn-clear-sm" type="button" onclick="applyAlertProfile(' + idArg + ')">应用</button>',
      '<button class="btn-clear-sm" type="button" onclick="renameAlertProfile(' + idArg + ')">重命名</button>',
      '<button class="btn-clear-sm" type="button" onclick="deleteAlertProfile(' + idArg + ')">删除</button>',
      '</div>',
      '</div>',
    ].join('');
  }).join('');
}

function saveCurrentAlertProfile() {
  const name = window.prompt('模板名称', alertProfiles.items.length ? '策略模板 ' + (alertProfiles.items.length + 1) : '买入观察');
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    setAlertProfileStatus('模板名称不能为空。', 'fail');
    return;
  }
  const description = window.prompt('模板说明（可选）', '') || '';
  setAlertProfileStatus('正在保存预警策略模板...', '');
  socket.emit('save_alert_profile', { name: trimmed, description: description.trim() });
}

function applyAlertProfile(id) {
  if (!id) return;
  pendingAlertProfileApply = true;
  setAlertProfileStatus('正在应用预警策略模板...', '');
  socket.emit('apply_alert_profile', { id });
}

function renameAlertProfile(id) {
  const item = (alertProfiles.items || []).find(profile => profile.id === id);
  if (!item) {
    setAlertProfileStatus('未找到预警策略模板。', 'fail');
    return;
  }
  const name = window.prompt('模板名称', item.name || '');
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    setAlertProfileStatus('模板名称不能为空。', 'fail');
    return;
  }
  const description = window.prompt('模板说明（可选）', item.description || '') || '';
  setAlertProfileStatus('正在更新预警策略模板...', '');
  socket.emit('rename_alert_profile', { id, name: trimmed, description: description.trim() });
}

function deleteAlertProfile(id) {
  const item = (alertProfiles.items || []).find(profile => profile.id === id);
  if (!item) {
    setAlertProfileStatus('未找到预警策略模板。', 'fail');
    return;
  }
  if (!window.confirm('删除预警策略模板“' + (item.name || '未命名模板') + '”？')) return;
  setAlertProfileStatus('正在删除预警策略模板...', '');
  socket.emit('delete_alert_profile', { id });
}

function setVolatility() {
  const pctEl = document.getElementById('alertRuleVolPct');
  const minEl = document.getElementById('alertRuleVolMin');
  const pct = pctEl ? (pctEl.value || '2.0') : String(volConfig.percent || '2.0');
  const min = minEl ? (minEl.value || '10') : String(volConfig.minutes || 10);
  const parsedPct = parseFloat(pct);
  const parsedMin = parseInt(min, 10);

  if (!Number.isFinite(parsedPct) || parsedPct <= 0 || !Number.isInteger(parsedMin) || parsedMin < 1) {
    alert('请输入有效的波动预警数字。');
    return;
  }

  volConfig = { percent: parsedPct, minutes: parsedMin, enabled: true };
  updateVolUI();
  socket.emit('set_volatility', { percent: pct, minutes: min, enabled: true });
}

function saveVolatilityRule() {
  const emailInput = document.getElementById('alertRuleEmail_volatility');
  setVolatility();
  if (emailInput) updateEmailSwitch('email_volatility_enabled', emailInput.checked);
}

function clearVolatility() {
  volConfig = { percent: null, minutes: 10, enabled: false };
  updateVolUI();
  socket.emit('set_volatility', { percent: null, minutes: 10, enabled: false });
}

function updateVolUI() {
  renderAlertRules();
}

function checkThresholdProximity() {
  renderAlertRules();
}

function normalizeWatchTargetItems(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

function applyWatchTargets(data) {
  watchTargets = normalizeWatchTargetItems(data).map(item => Object.assign({}, item));
  renderWatchTargets();
}

function setWatchTargetStatus(message, type) {
  const status = document.getElementById('watchTargetStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'watch-target-status' + (type ? ' ' + type : '');
}

function setActiveWatchTarget(id) {
  activeWatchTargetId = activeWatchTargetId === id ? null : id;
  renderWatchTargets();
}

function watchTargetUnit(mode) {
  return mode === 'usd' ? '$' : '¥';
}

function watchTargetModeLabel(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function watchTargetDirectionLabel(direction) {
  return direction === 'rise_to' ? '上涨至' : '下跌至';
}

function watchTargetPrice(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return watchTargetUnit(mode) + number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function watchTargetStateLabel(item) {
  if (item.triggered) return '已触发';
  if (item.enabled === false) return '已停用';
  return '观察中';
}

function watchTargetStateClass(item) {
  if (item.triggered) return 'on';
  if (item.enabled === false) return 'off';
  return 'on';
}

function buildWatchTargetEditor(item) {
  const isNew = !item || item.id === 'new';
  const target = item || { id: 'new', mode: currentMode, direction: 'fall_to', price: '', note: '', enabled: true };
  const id = isNew ? 'new' : target.id;
  const mode = target.mode || currentMode;
  const direction = target.direction || 'fall_to';
  const price = target.price == null ? '' : String(target.price);
  const note = target.note || '';
  const enabledChecked = target.enabled === false ? '' : ' checked';
  return [
    '<div class="watch-target-editor">',
    '<div class="watch-target-fields">',
    '<div class="watch-target-field">',
    '<label for="watchTargetMode_' + escapeHtml(id) + '">单位</label>',
    '<select id="watchTargetMode_' + escapeHtml(id) + '">',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="watch-target-field">',
    '<label for="watchTargetDirection_' + escapeHtml(id) + '">方向</label>',
    '<select id="watchTargetDirection_' + escapeHtml(id) + '">',
    '<option value="fall_to"' + (direction === 'fall_to' ? ' selected' : '') + '>下跌至</option>',
    '<option value="rise_to"' + (direction === 'rise_to' ? ' selected' : '') + '>上涨至</option>',
    '</select>',
    '</div>',
    '<div class="watch-target-field">',
    '<label for="watchTargetPrice_' + escapeHtml(id) + '">目标价</label>',
    '<input id="watchTargetPrice_' + escapeHtml(id) + '" type="number" step="0.01" value="' + escapeHtml(price) + '" placeholder="输入价格">',
    '</div>',
    '<div class="watch-target-field watch-target-note">',
    '<label for="watchTargetNote_' + escapeHtml(id) + '">备注</label>',
    '<input id="watchTargetNote_' + escapeHtml(id) + '" type="text" maxlength="200" value="' + escapeHtml(note) + '" placeholder="例如 预算观察价">',
    '</div>',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>启用观察</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="watchTargetEnabled_' + escapeHtml(id) + '"' + enabledChecked + '><span class="slider"></span></label>',
    '</div>',
    '<div class="watch-target-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveWatchTarget(\'' + escapeHtml(id) + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveWatchTarget(\'' + escapeHtml(id) + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderWatchTargets() {
  const box = document.getElementById('watchTargetList');
  if (!box) return;
  const items = [...watchTargets];
  const parts = [];
  if (activeWatchTargetId === 'new') {
    parts.push([
      '<div class="watch-target-item expanded">',
      '<div class="watch-target-main">',
      '<div class="watch-target-line">新增目标价</div>',
      '<div class="watch-target-meta">保存后开始观察</div>',
      '</div>',
      '<div class="watch-target-actions"><span class="alert-rule-state off">新建</span></div>',
      buildWatchTargetEditor({ id: 'new', mode: currentMode, direction: 'fall_to', price: '', note: '', enabled: true }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activeWatchTargetId !== 'new') {
    parts.push('<div class="watch-target-empty">暂无目标价观察</div>');
  }
  parts.push(...items.map(item => {
    const cls = [
      'watch-target-item',
      activeWatchTargetId === item.id ? 'expanded' : '',
      item.triggered ? 'triggered' : '',
      item.enabled === false ? 'disabled' : '',
    ].filter(Boolean).join(' ');
    const triggerInfo = item.triggered && item.triggered_at
      ? ' · 触发 ' + String(item.triggered_at).replace('T', ' ')
      : '';
    const note = item.note ? ' · ' + item.note : '';
    return [
      '<div class="' + cls + '">',
      '<div class="watch-target-main">',
      '<div class="watch-target-line">' + escapeHtml(watchTargetDirectionLabel(item.direction)) + ' ' + escapeHtml(watchTargetPrice(item.price, item.mode)) + '</div>',
      '<div class="watch-target-meta">' + escapeHtml(watchTargetModeLabel(item.mode) + triggerInfo + note) + '</div>',
      '</div>',
      '<div class="watch-target-actions">',
      '<span class="alert-rule-state ' + watchTargetStateClass(item) + '">' + escapeHtml(watchTargetStateLabel(item)) + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActiveWatchTarget(\'' + escapeHtml(item.id) + '\')">编辑</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="toggleWatchTarget(\'' + escapeHtml(item.id) + '\', ' + (item.enabled === false ? 'true' : 'false') + ')">' + (item.enabled === false ? '启用' : '停用') + '</button>',
      item.triggered ? '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="resetWatchTarget(\'' + escapeHtml(item.id) + '\')">重置</button>' : '',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="deleteWatchTarget(\'' + escapeHtml(item.id) + '\')">删除</button>',
      '</div>',
      activeWatchTargetId === item.id ? buildWatchTargetEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function watchTargetInputValue(id, field) {
  const el = document.getElementById('watchTarget' + field + '_' + id);
  return el ? el.value : '';
}

function saveWatchTarget(id) {
  const isNew = id === 'new';
  const payload = {
    mode: watchTargetInputValue(id, 'Mode'),
    direction: watchTargetInputValue(id, 'Direction'),
    price: watchTargetInputValue(id, 'Price'),
    note: watchTargetInputValue(id, 'Note'),
    enabled: !!document.getElementById('watchTargetEnabled_' + id)?.checked,
  };
  if (!isNew) payload.id = id;
  const price = Number(payload.price);
  if (!Number.isFinite(price) || price <= 0) {
    setWatchTargetStatus('请输入有效的目标价格。', 'fail');
    return;
  }
  setWatchTargetStatus('正在保存观察项...', '');
  socket.emit('set_watch_target', payload);
  activeWatchTargetId = null;
}

function deleteWatchTarget(id) {
  setWatchTargetStatus('正在删除观察项...', '');
  socket.emit('delete_watch_target', { id });
  if (activeWatchTargetId === id) activeWatchTargetId = null;
}

function toggleWatchTarget(id, enabled) {
  setWatchTargetStatus(enabled ? '正在启用观察项...' : '正在停用观察项...', '');
  socket.emit('toggle_watch_target', { id, enabled });
}

function resetWatchTarget(id) {
  setWatchTargetStatus('正在重置触发状态...', '');
  socket.emit('reset_watch_target', { id });
}
