let alertEntries = [];
let alertLogSearch = '';
let activeAlert = null;
let mergedAlertCount = 0;
let flashTimer = null;

function registerAlertLogSocketHandlers(socket) {
  socket.on('alert', data => {
    addLogEntry(data);
    addChartEvent({
      type: 'alert',
      level: data.type || 'warning',
      timestamp: data.timestamp || '',
      time: data.time || '',
      label: alertLevelLabel(data.type),
      message: data.message || '',
    });
    showAlertModal(data);
    flashTitle(data.type === 'critical'
      ? '警告'
      : data.type === 'warning'
        ? '关注'
        : data.type === 'quality'
          ? '行情质量异常'
          : data.type === 'recovery'
            ? '行情质量恢复'
            : '波动预警');
  });

  socket.on('alert_log_exported', data => {
    const status = document.getElementById('alertLogStatus');
    const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : alertEntries.length;
    status.textContent = data && data.saved_path ? '已导出 ' + count + ' 条，保存至 ' + data.saved_path : '告警记录已导出。';
    status.className = 'log-status ok';
  });

  socket.on('alert_log_export_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '告警记录导出失败。';
    status.className = 'log-status fail';
  });

  socket.on('alert_log_cleared', data => {
    const status = document.getElementById('alertLogStatus');
    if (data && data.ok === false) {
      status.textContent = '警报记录清空失败，请检查导出目录权限。';
      status.className = 'log-status fail';
      return;
    }
    setAlertEntries([]);
    status.textContent = '警报记录已清空。';
    status.className = 'log-status ok';
  });

  socket.on('alert_log_status_updated', data => {
    if (!data || !data.entry) return;
    mergeAlertLogEntry(data.entry);
  });

  socket.on('alert_log_handling_updated', data => {
    const status = document.getElementById('alertLogStatus');
    if (data && data.entry) mergeAlertLogEntry(data.entry);
    status.textContent = data && data.entry && data.entry.handled ? '警报已标记为已处理。' : '警报处置已更新。';
    status.className = 'log-status ok';
  });

  socket.on('alert_log_status_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '警报记录状态更新失败。';
    status.className = 'log-status fail';
  });

  socket.on('alert_log_handling_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '警报处置更新失败。';
    status.className = 'log-status fail';
  });

  socket.on('alert_log_handling_batch_updated', data => {
    const status = document.getElementById('alertLogStatus');
    const entries = data && Array.isArray(data.entries) ? data.entries : [];
    entries.forEach(mergeAlertLogEntry);
    const success = Number(data && data.success_count) || 0;
    const failure = Number(data && data.failure_count) || 0;
    status.textContent = failure
      ? '批量处理完成：成功 ' + success + ' 条，失败 ' + failure + ' 条。'
      : '已批量处理 ' + success + ' 条警报。';
    status.className = 'log-status ' + (failure ? 'fail' : 'ok');
  });

  socket.on('alert_log_handling_batch_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '批量处理警报失败。';
    status.className = 'log-status fail';
  });

  socket.on('alert_notification_resent', data => {
    const status = document.getElementById('alertLogStatus');
    if (data && data.entry) mergeAlertLogEntry(data.entry);
    status.textContent = '通知正在重新发送。';
    status.className = 'log-status';
  });

  socket.on('alert_notification_resend_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '通知重发失败。';
    status.className = 'log-status fail';
  });

  socket.on('alert_notification_batch_resent', data => {
    const status = document.getElementById('alertLogStatus');
    const entries = data && Array.isArray(data.entries) ? data.entries : [];
    entries.forEach(mergeAlertLogEntry);
    const success = Number(data && data.success_count) || 0;
    const failure = Number(data && data.failure_count) || 0;
    status.textContent = failure
      ? '批量重提完成：成功 ' + success + ' 条，失败 ' + failure + ' 条。'
      : '已重新提交 ' + success + ' 条通知。';
    status.className = 'log-status ' + (failure ? 'fail' : 'ok');
  });

  socket.on('alert_notification_batch_resend_error', data => {
    const status = document.getElementById('alertLogStatus');
    status.textContent = (data && data.message) || '批量重发通知失败。';
    status.className = 'log-status fail';
  });
}

function playAlertSound(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    if (type === 'critical' || type === 'upper') {
      osc.frequency.value = 1000; osc.type = 'square';
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.4);
    } else if (type === 'warning' || type === 'volatility') {
      osc.frequency.value = 660; osc.type = 'sine';
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.6);
    } else {
      osc.frequency.value = 520; osc.type = 'triangle';
      gain.gain.setValueAtTime(0.1, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.8);
    }
  } catch(e) {}
}

function alertLevelLabel(type) {
  if (type === 'critical') return '关键预警';
  if (type === 'warning') return '价格预警';
  if (type === 'volatility') return '波动预警';
  if (type === 'quality') return '质量异常';
  if (type === 'recovery') return '质量恢复';
  return '金价预警';
}

function alertModeLabel(mode) {
  if (mode === 'usd') return '国际金价';
  if (mode === 'rmb') return '国内金价';
  if (mode === 'quality') return '行情可信度';
  return '金价监控';
}

function renderAlertModal(entry) {
  const modal = document.getElementById('alertModal');
  modal.className = 'settings-modal alert-modal alert-level-' + (entry.type || 'warning');
  document.getElementById('alertTitle').textContent = entry.source === 'market_quality' ? '行情质量通知' : '金价预警';
  document.getElementById('alertBadge').textContent = alertLevelLabel(entry.type);
  const muted = entry.notification_muted && entry.notification_message ? '\n' + entry.notification_message : '';
  document.getElementById('alertMessage').textContent = (entry.message || '达到预警条件') + muted;
  document.getElementById('alertTime').textContent = '时间 ' + (entry.time || '--');
  document.getElementById('alertMode').textContent = alertModeLabel(entry.mode);
  const primaryAction = document.getElementById('alertPrimaryAction');
  if (primaryAction) {
    primaryAction.textContent = entry.source === 'market_quality' ? '查看异常复盘' : '分析本次预警';
  }
  const stackNote = document.getElementById('alertStackNote');
  if (mergedAlertCount > 0) {
    stackNote.textContent = '当前弹窗已合并 ' + mergedAlertCount + ' 条后续预警，警报记录中保留完整明细。';
    stackNote.classList.add('show');
  } else {
    stackNote.textContent = '';
    stackNote.classList.remove('show');
  }
  renderRelatedNews(entry.related_news || []);
  document.getElementById('alertBackdrop').classList.add('show');
}

function renderRelatedNews(items) {
  const box = document.getElementById('relatedNews');
  const list = document.getElementById('relatedNewsList');
  list.innerHTML = '';
  if (!items.length) {
    box.classList.remove('show');
    return;
  }
  items.slice(0, 3).forEach(item => {
    const link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = (item.topic ? '[' + item.topic + '] ' : '') + (item.title || '--');
    list.appendChild(link);
  });
  box.classList.add('show');
}

function showAlertModal(entry) {
  const normalized = entry || {};
  if (activeAlert) {
    mergedAlertCount += 1;
    activeAlert = normalized;
    renderAlertModal(activeAlert);
    return;
  }
  mergedAlertCount = 0;
  activeAlert = normalized;
  renderAlertModal(activeAlert);
}

function closeAlertModal() {
  if (activeAlert && activeAlert.id) updateAlertStatus(activeAlert.id, { read: true });
  document.getElementById('alertBackdrop').classList.remove('show');
  activeAlert = null;
  mergedAlertCount = 0;
}

function analyzeActiveAlert() {
  if (!activeAlert) return;
  const alertContext = {
    source: 'alert',
    time: activeAlert.time || '',
    type: activeAlert.type || '',
    mode: activeAlert.mode || '',
    message: activeAlert.message || '',
  };
  if (!openRiskAnalysis()) return;
  document.getElementById('alertBackdrop').classList.remove('show');
  activeAlert = null;
  mergedAlertCount = 0;
  document.getElementById('riskResult').textContent = '正在分析本次预警...';
  requestRiskAnalysis(alertContext);
}

function runActiveAlertPrimaryAction() {
  if (!activeAlert) return;
  if (activeAlert.source === 'market_quality') {
    const timestamp = activeAlert.market_quality_first_seen_at || activeAlert.timestamp || activeAlert.time;
    const segmentId = activeAlert.market_quality_segment_id || '';
    document.getElementById('alertBackdrop').classList.remove('show');
    activeAlert = null;
    mergedAlertCount = 0;
    openEventTimelineAround(timestamp, 'data_status', segmentId);
    return;
  }
  analyzeActiveAlert();
}

function onAlertBackdrop(event) {
  if (event.target.id === 'alertBackdrop') closeAlertModal();
}

function normalizeAlertEntry(entry) {
  const item = entry && typeof entry === 'object' ? { ...entry } : {};
  item.id = item.id || 'local-' + (item.timestamp || Date.now()) + '-' + Math.random().toString(16).slice(2);
  item.read = item.read === true;
  item.handled = item.handled === true;
  item.handled_at = item.handled_at ? String(item.handled_at) : '';
  item.handling_note = item.handling_note ? String(item.handling_note) : '';
  return item;
}

function setAlertEntries(items) {
  alertEntries = Array.isArray(items) ? items.slice(-50).map(normalizeAlertEntry) : [];
  updateAlertLogSummary();
  renderAlertLog();
}

function setAlertLogSearch(value) {
  alertLogSearch = (value || '').trim().toLowerCase();
  renderAlertLog();
}

function toggleAlertLogMenu() {
  const menu = document.getElementById('alertLogMenu');
  const button = document.getElementById('alertLogMoreButton');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}

function toggleLogEntryMenu(button) {
  const actions = button && button.closest ? button.closest('.log-actions') : null;
  const menu = actions ? actions.querySelector('.log-entry-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function updateAlertLogSummary() {
  const countEl = document.getElementById('alertUnreadCount');
  const unread = alertEntries.filter(entry => !entry.read).length;
  countEl.textContent = unread + ' 新';
  countEl.className = 'log-count' + (unread ? '' : ' empty');
}

function alertLogMatchesSearch(entry) {
  if (!alertLogSearch) return true;
  const haystack = [
    entry.time, entry.timestamp, entry.type, entry.mode, entry.message,
    entry.handling_note, entry.rule_id, entry.rule_name, entry.rule_kind,
    alertLevelLabel(entry.type), alertModeLabel(entry.mode),
  ].join(' ').toLowerCase();
  return haystack.includes(alertLogSearch);
}

function filterAlertLogByRule(id) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  alertLogSearch = ruleId.toLowerCase();
  const input = document.getElementById('alertLogSearch');
  if (input) input.value = ruleId;
  renderAlertLog();
  const list = document.getElementById('logList');
  if (list) list.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function alertNotificationIssues(entry) {
  const summary = entry && entry.notification_summary;
  if (summary && typeof summary === 'object') {
    const status = summary.status || '';
    if (!['failed', 'partial', 'skipped'].includes(status)) return [];
    return [{
      status,
      label: summary.label || '通知',
      message: summary.message || '',
    }];
  }
  const items = Array.isArray(entry.notifications) ? entry.notifications : [];
  return items.filter(item => item && ['failed', 'skipped'].includes(item.status));
}

function alertNotificationDisplay(entry) {
  const summary = entry && entry.notification_summary;
  if (summary && typeof summary === 'object') {
    const status = summary.status || '';
    if (!status || ['none', 'disabled'].includes(status)) return [];
    return [{
      status,
      label: summary.label || '通知',
      message: summary.message || '',
    }];
  }
  const items = Array.isArray(entry && entry.notifications) ? entry.notifications : [];
  return items.filter(item => item && item.status && item.status !== 'disabled');
}

function renderNotificationBadges(entry) {
  const items = alertNotificationDisplay(entry);
  if (!items.length) return '';
  return '<span class="log-notify">' + items.map(item => {
    const status = item.status || '';
    const cls = ['sent', 'queued'].includes(status)
      ? 'ok'
      : (['failed', 'skipped', 'partial'].includes(status) ? 'fail' : (status === 'muted' ? 'muted' : (status === 'pending' ? 'pending' : '')));
    const label = item.label || item.channel || '通知';
    const message = item.message ? '：' + item.message : '';
    return '<span class="log-notify-badge ' + cls + '">' + escapeHtml(label + message) + '</span>';
  }).join('') + '</span>';
}

function renderLogActionButton(action, extraClass) {
  const classes = ['btn-clear-sm', action.buttonClass || 'btn-muted-sm', extraClass || ''].filter(Boolean).join(' ');
  const attrs = action.attrs || '';
  return '<button class="' + escapeHtml(classes) + '" type="button" onclick="' + action.onclick + '"' + attrs + '>' + escapeHtml(action.label) + '</button>';
}

function renderLogEntryActions(actions) {
  if (actions.length === 1) {
    return '<span class="log-actions">' + renderLogActionButton(actions[0], 'log-action-direct') + '</span>';
  }
  if (actions.length > 1) {
    return [
      '<span class="log-actions">',
      '<button class="btn-clear-sm btn-muted-sm log-action-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="toggleLogEntryMenu(this)">操作</button>',
      '<span class="log-entry-menu" hidden>',
      actions.map(action => renderLogActionButton(action, '')).join(''),
      '</span>',
      '</span>',
    ].join('');
  }
  return '<span class="log-actions"></span>';
}

function buildLogEntry(entry) {
  const item = document.createElement('div');
  const encodedId = encodeURIComponent(String(entry.id || ''));
  const hasNotificationIssue = alertNotificationIssues(entry).length > 0;
  const logMessage = entry.message || '达到预警条件';
  const handlingNote = entry.handling_note ? '<span class="log-note">处理备注：' + escapeHtml(entry.handling_note) + '</span>' : '';
  const timelineAction = {
    label: '复盘',
    buttonClass: 'btn-muted-sm',
    onclick: "window.openAlertTimelineFromLog(decodeURIComponent('" + encodedId + "'))",
    attrs: ' data-log-timeline-id="' + encodedId + '"',
  };
  const actions = entry.source === 'market_quality' ? [] : [
    { label: '分析', buttonClass: 'btn-risk-sm', onclick: "analyzeAlertFromLog(decodeURIComponent('" + encodedId + "'))" },
  ];
  if (entry.rule_id || entry.rule_kind) {
    actions.push(
      { label: '查看规则', buttonClass: 'btn-muted-sm', onclick: "viewAlertRuleFromLog(decodeURIComponent('" + encodedId + "'))" },
      { label: '复制规则', buttonClass: 'btn-muted-sm', onclick: "copyAlertRuleFromLog(decodeURIComponent('" + encodedId + "'))" },
    );
  }
  if (hasNotificationIssue) actions.push(
    { label: '重发通知', buttonClass: 'btn-muted-sm', onclick: "resendAlertNotification(decodeURIComponent('" + encodedId + "'))" },
  );
  item.className = [
    'log-item',
    entry.read ? 'read' : 'unread',
    entry.handled ? 'handled' : '',
  ].filter(Boolean).join(' ');
  item.innerHTML = [
    '<span class="log-unread-dot"></span>',
    '<span class="log-body">',
    '<span class="log-entry-head">',
    '<span class="log-line-head">',
    '<span class="log-time">' + escapeHtml(entry.time || entry.timestamp || '') + '</span>',
    '<span class="log-level ' + escapeHtml(entry.type || '') + '">' + escapeHtml(alertLevelLabel(entry.type)) + '</span>',
    '</span>',
    '<span class="log-action-row">' + renderLogActionButton(timelineAction, 'log-action-direct log-review-direct') + renderLogEntryActions(actions) + '</span>',
    '</span>',
    '<span class="log-meta">',
    '<span class="log-msg ' + escapeHtml(entry.type || '') + '" title="' + escapeHtml(logMessage) + '">' + escapeHtml(logMessage) + '</span>',
    handlingNote,
    renderNotificationBadges(entry),
    '</span>',
    '</span>',
  ].join('');
  return item;
}

function renderAlertLog() {
  const list = document.getElementById('logList');
  const items = alertEntries.filter(alertLogMatchesSearch);
  list.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'log-empty';
    empty.textContent = alertEntries.length ? '当前搜索暂无警报' : '暂无警报';
    list.appendChild(empty);
    return;
  }
  items.forEach(entry => list.appendChild(buildLogEntry(entry)));
  list.scrollTop = list.scrollHeight;
}

function addLogEntry(entry) {
  const normalized = normalizeAlertEntry(entry);
  alertEntries.push(normalized);
  while (alertEntries.length > 50) alertEntries.shift();
  updateAlertLogSummary();
  renderAlertLog();
}

function mergeAlertLogEntry(entry) {
  const normalized = normalizeAlertEntry(entry);
  const index = alertEntries.findIndex(item => item.id === normalized.id);
  if (index >= 0) alertEntries[index] = normalized;
  else alertEntries.push(normalized);
  updateAlertLogSummary();
  renderAlertLog();
}

function updateAlertStatus(id, patch) {
  const entry = alertEntries.find(item => item.id === id);
  if (entry) {
    Object.assign(entry, patch || {});
    updateAlertLogSummary();
    renderAlertLog();
  }
  socket.emit('update_alert_log_status', Object.assign({ id }, patch || {}));
}

function updateAlertHandling(id, handled) {
  const entry = alertEntries.find(item => item.id === id);
  const nextHandled = handled === true;
  let note = entry && entry.handling_note ? entry.handling_note : '';
  if (nextHandled) {
    const input = window.prompt('处理备注（可选）', note);
    if (input === null) return;
    note = input || '';
  } else {
    note = '';
  }
  if (entry) {
    entry.handled = nextHandled;
    entry.handled_at = nextHandled ? (entry.handled_at || new Date().toISOString().slice(0, 19)) : '';
    entry.handling_note = note;
    if (nextHandled) entry.read = true;
    updateAlertLogSummary();
    renderAlertLog();
  }
  socket.emit('update_alert_log_handling', { id, handled: nextHandled, note });
}

function analyzeAlertFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  activeAlert = entry;
  analyzeActiveAlert();
}

function scrollToAlertRuleCenter() {
  const center = document.getElementById('alertRuleCenterList');
  if (center) center.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function viewAlertRuleFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  const rule = entry.rule_id ? findUnifiedAlertRule(entry.rule_id) : null;
  if (rule) {
    editUnifiedAlertRule(rule.id);
    setAlertRuleCenterStatus('已定位到该警报对应的规则。', 'ok');
  } else {
    alertRuleFilter = 'all';
    activeUnifiedAlertRuleId = null;
    alertRuleDraft = null;
    renderAlertRuleCenter();
    setAlertRuleCenterStatus('原规则已不存在。当前警报保留了历史条件快照，可使用“复制规则”重新创建。', 'fail');
  }
  scrollToAlertRuleCenter();
}

function copyAlertRuleFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  const rule = entry.rule_id ? findUnifiedAlertRule(entry.rule_id) : null;
  if (rule) {
    duplicateUnifiedAlertRule(rule.id);
    scrollToAlertRuleCenter();
    return;
  }
  if (!entry.rule_kind || !entry.rule_condition) {
    setAlertRuleCenterStatus('该历史警报没有可复制的规则快照。', 'fail');
    scrollToAlertRuleCenter();
    return;
  }
  activeUnifiedAlertRuleId = 'new';
  alertRuleFilter = 'all';
  alertRuleDraft = cloneAlertRuleDraft(null);
  alertRuleDraft.kind = entry.rule_kind;
  alertRuleDraft.name = (entry.rule_name || '历史预警规则') + ' 副本';
  alertRuleDraft.scope = Object.assign(
    { mode: entry.mode || currentMode, position_id: entry.portfolio_position_id || null },
    entry.rule_scope || {},
  );
  alertRuleDraft.condition = Object.assign({}, entry.rule_condition || {});
  alertRuleDraft.delivery = { channels: 'inherit', cooldown_minutes: 'inherit' };
  alertRuleDraft.legacy = {};
  renderAlertRuleCenter();
  setAlertRuleCenterStatus('已从历史警报生成规则草稿，请确认后保存。', 'ok');
  scrollToAlertRuleCenter();
}

function openAlertTimelineFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  if (entry.source === 'market_quality') {
    openEventTimelineAround(
      entry.market_quality_first_seen_at || entry.timestamp || entry.time,
      'data_status',
      entry.market_quality_segment_id || '',
    );
    return;
  }
  openEventTimelineAround(entry.timestamp || entry.time, 'alert', entry.id);
}

function handleAlertLogTimelineClick(event) {
  const button = event.target && event.target.closest ? event.target.closest('[data-log-timeline-id]') : null;
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openAlertTimelineFromLog(decodeURIComponent(button.getAttribute('data-log-timeline-id') || ''));
}

document.addEventListener('click', handleAlertLogTimelineClick, true);

function resendAlertNotification(id) {
  const status = document.getElementById('alertLogStatus');
  status.textContent = '正在重新提交通知...';
  status.className = 'log-status';
  socket.emit('resend_alert_notification', { id });
}

function exportAlertLog() {
  const status = document.getElementById('alertLogStatus');
  status.textContent = '正在导出警报记录...';
  status.className = 'log-status';
  socket.emit('export_alert_log');
}

function clearAlertLog() {
  if (!alertEntries.length) {
    const status = document.getElementById('alertLogStatus');
    status.textContent = '当前没有可清空的警报记录。';
    status.className = 'log-status';
    return;
  }
  if (!confirm('确定清空当前警报记录吗？')) return;
  socket.emit('clear_alert_log');
}

function flashTitle(type) {
  if (flashTimer) clearTimeout(flashTimer);
  const orig = document.title, alertTitle = '['+type+'] 金价监控';
  let count = 0; document.title = alertTitle;
  flashTimer = setInterval(() => {
    document.title = count % 2 === 0 ? orig : alertTitle;
    count++;
    if (count >= 6) { clearInterval(flashTimer); flashTimer = null; document.title = orig; }
  }, 800);
}

window.openAlertTimelineFromLog = openAlertTimelineFromLog;
