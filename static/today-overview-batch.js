let todayOverviewFilteredAttentionItems = [];
let todayOverviewActionRecords = [];
let todayOverviewBatchRecordPending = null;
let todayOverviewActionHistoryOpen = false;

function todayOverviewBatchTargets(items, actionKind) {
  const targets = [];
  const seen = new Set();
  items.forEach(item => {
    const actions = Array.isArray(item.quick_actions) ? item.quick_actions : [];
    const action = actions.find(candidate => candidate && candidate.kind === actionKind);
    const targetId = String(action && (action.target_id || item.source_id) || '').trim();
    if (!targetId || seen.has(targetId)) return;
    seen.add(targetId);
    targets.push({
      id: targetId,
      title: String(item.title || '待处理事项'),
      reasonCodes: Array.isArray(item.reason_codes) ? item.reason_codes.map(String) : [],
    });
  });
  return targets;
}

function todayOverviewBatchActionLabel(kind, count) {
  if (kind === 'batch_handle_alerts') return '处理 ' + count + ' 条警报';
  if (kind === 'batch_resend_notifications') return '重发 ' + count + ' 条通知';
  return '批量处理';
}

function todayOverviewBatchRecordText(record) {
  if (!record) return '';
  const parts = [record.label, '成功 ' + record.successCount];
  if (record.failureCount) parts.push('失败 ' + record.failureCount);
  if (record.retainedCount) parts.push(record.retainedCount + ' 条仍有其他问题');
  if (record.remainingCount != null) parts.push('概览剩余 ' + record.remainingCount);
  return parts.join(' · ');
}

function todayOverviewBatchRecordClass(record) {
  if (record.failureCount && record.successCount) return 'partial';
  if (record.failureCount) return 'fail';
  if (record.retainedCount) return 'retained';
  return 'ok';
}

function todayOverviewBatchRemainingReasons(entry, kind) {
  const reasons = [];
  if (kind === 'batch_handle_alerts' && entry) {
    const summary = entry.notification_summary && typeof entry.notification_summary === 'object'
      ? entry.notification_summary
      : {};
    const statuses = Array.isArray(entry.notifications)
      ? entry.notifications.map(item => String(item && item.status || ''))
      : [];
    const notificationStatus = String(summary.status || '');
    const hasNotificationIssue = ['failed', 'partial', 'skipped'].includes(notificationStatus)
      || statuses.some(status => ['failed', 'skipped'].includes(status));
    if (hasNotificationIssue) {
      reasons.push('通知异常');
    }
  }
  if (kind === 'batch_resend_notifications' && entry && entry.handled !== true) {
    reasons.push('警报未处理');
  }
  return reasons;
}

function todayOverviewBatchItemList(title, items, description) {
  if (!items.length) return '';
  return [
    '<section class="today-overview-action-detail">',
    '<div class="today-overview-action-detail-head">',
    '<strong>' + escapeHtml(title) + '</strong>',
    '<span>' + escapeHtml(String(items.length)) + ' 条</span>',
    '</div>',
    description ? '<p>' + escapeHtml(description) + '</p>' : '',
    '<ul>',
    items.map(item => [
      '<li>',
      '<strong>' + escapeHtml(item.title || item.id || '未命名事项') + '</strong>',
      '<small>' + escapeHtml(item.message || item.reason || '请重新检查该事项。') + '</small>',
      '</li>',
    ].join('')).join(''),
    '</ul>',
    '</section>',
  ].join('');
}

function todayOverviewBatchRecordDetails(record) {
  const failures = Array.isArray(record.failures) ? record.failures : [];
  const retainedItems = Array.isArray(record.retainedItems) ? record.retainedItems : [];
  const details = [
    todayOverviewBatchItemList('处理失败', failures, '以下事项未完成，可刷新后再次处理。'),
    todayOverviewBatchItemList('仍在概览中', retainedItems, '批量操作已完成，但这些事项还有其他问题需要处理。'),
  ].filter(Boolean).join('');
  return [
    '<article class="today-overview-action-history-item ' + todayOverviewBatchRecordClass(record) + '">',
    '<div class="today-overview-action-history-head">',
    '<div><span>' + escapeHtml(record.time) + '</span><strong>' + escapeHtml(record.label) + '</strong></div>',
    '<small>请求 ' + record.requestedCount + ' · 成功 ' + record.successCount + ' · 失败 ' + record.failureCount + '</small>',
    '</div>',
    details || '<p class="today-overview-action-clear">本次操作的目标项已完成，未因其他问题继续保留。</p>',
    '</article>',
  ].join('');
}

function renderTodayOverviewActionHistory(recordBox) {
  const latestRecord = todayOverviewActionRecords[0] || null;
  if (!latestRecord) {
    recordBox.hidden = true;
    recordBox.innerHTML = '';
    return;
  }
  recordBox.hidden = false;
  recordBox.innerHTML = [
    '<button class="today-overview-action-record-toggle" type="button"',
    ' onclick="toggleTodayOverviewActionHistory()"',
    ' aria-expanded="' + String(todayOverviewActionHistoryOpen) + '"',
    ' aria-controls="todayOverviewActionHistory">',
    '<span>最近操作</span>',
    '<strong>' + escapeHtml(todayOverviewBatchRecordText(latestRecord)) + '</strong>',
    '<small>' + escapeHtml(latestRecord.time) + ' · 本次会话 ' + todayOverviewActionRecords.length + ' 次</small>',
    '<b>' + (todayOverviewActionHistoryOpen ? '收起记录' : '查看记录') + '</b>',
    '</button>',
    '<div class="today-overview-action-history" id="todayOverviewActionHistory"' + (todayOverviewActionHistoryOpen ? '' : ' hidden') + '>',
    '<div class="today-overview-action-history-title"><span>本次会话操作记录</span><small>最多保留最近 5 次</small></div>',
    todayOverviewActionRecords.map(todayOverviewBatchRecordDetails).join(''),
    '</div>',
  ].join('');
}

function renderTodayOverviewBatchTools(items) {
  const box = document.getElementById('todayOverviewBatch');
  const actionsBox = document.getElementById('todayOverviewBatchActions');
  const recordBox = document.getElementById('todayOverviewActionRecord');
  if (!box || !actionsBox || !recordBox) return;
  const copyTitle = box.querySelector('.today-overview-batch-copy span');
  const copyDescription = box.querySelector('.today-overview-batch-copy small');
  const handlingTargets = todayOverviewBatchTargets(items, 'handle_alert');
  const resendTargets = todayOverviewBatchTargets(items, 'resend_notification');
  const actions = [];
  if (handlingTargets.length > 1) actions.push({
    kind: 'batch_handle_alerts',
    count: handlingTargets.length,
  });
  if (resendTargets.length > 1) actions.push({
    kind: 'batch_resend_notifications',
    count: resendTargets.length,
  });
  const latestRecord = todayOverviewActionRecords[0] || null;
  box.hidden = !actions.length && !latestRecord;
  if (copyTitle) copyTitle.textContent = actions.length ? '批量处理' : '处理记录';
  if (copyDescription) {
    copyDescription.textContent = actions.length
      ? '仅作用于当前筛选中显示的事项'
      : '保留本次打开应用后的最近操作';
  }
  actionsBox.innerHTML = actions.map(action => [
    '<button class="today-overview-batch-action" type="button"',
    ' onclick="runTodayOverviewBatchAction(\'' + action.kind + '\')"',
    todayOverviewPendingAction ? ' disabled' : '',
    '>' + escapeHtml(todayOverviewBatchActionLabel(action.kind, action.count)) + '</button>',
  ].join('')).join('');
  actionsBox.hidden = actions.length === 0;
  renderTodayOverviewActionHistory(recordBox);
}

function toggleTodayOverviewActionHistory() {
  todayOverviewActionHistoryOpen = !todayOverviewActionHistoryOpen;
  renderTodayOverviewBatchTools(todayOverviewFilteredAttentionItems);
}

function applyTodayOverviewBatchRefresh(data) {
  if (!todayOverviewBatchRecordPending) return;
  const state = data && typeof data === 'object' ? data : {};
  todayOverviewBatchRecordPending.remainingCount = Math.max(
    0,
    Math.trunc(todayOverviewNumber(state.summary && state.summary.attention_total)),
  );
  const attention = state.attention && typeof state.attention === 'object' ? state.attention : {};
  const attentionItems = Array.isArray(attention.items) ? attention.items : [];
  const attentionBySourceId = new Map(attentionItems.map(item => [String(item.source_id || ''), item]));
  todayOverviewBatchRecordPending.retainedItems = todayOverviewBatchRecordPending.successIds.map(targetId => {
    const item = attentionBySourceId.get(targetId);
    const target = todayOverviewBatchRecordPending.targets.find(candidate => candidate.id === targetId);
    const entry = todayOverviewBatchRecordPending.successEntries.find(candidate => (
      String(candidate && candidate.id || '') === targetId
    ));
    const reasons = item && Array.isArray(item.reason_codes)
      ? item.reason_codes.map(todayOverviewReasonLabel).filter(Boolean)
      : todayOverviewBatchRemainingReasons(entry, todayOverviewBatchRecordPending.kind);
    if (!item && !reasons.length) return null;
    return {
      id: targetId,
      title: String(item && item.title || (target && target.title) || '待处理事项'),
      reason: reasons.join('、') || '仍有其他待处理状态',
    };
  }).filter(Boolean);
  todayOverviewBatchRecordPending.retainedCount = todayOverviewBatchRecordPending.retainedItems.length;
  todayOverviewActionRecords.unshift(todayOverviewBatchRecordPending);
  todayOverviewActionRecords = todayOverviewActionRecords.slice(0, 5);
  const record = todayOverviewBatchRecordPending;
  todayOverviewBatchRecordPending = null;
  if (record.failureCount) todayOverviewActionHistoryOpen = true;
  const statusType = record.failureCount ? 'fail' : 'ok';
  setTodayOverviewActionFeedback(todayOverviewBatchRecordText(record) + '。', statusType, true);
}

function completeTodayOverviewBatchAction(data, label) {
  const pending = todayOverviewPendingAction;
  if (!pending || !String(pending.kind || '').startsWith('batch_')) return;
  const result = data && typeof data === 'object' ? data : {};
  const entries = Array.isArray(result.entries) ? result.entries : [];
  const failures = Array.isArray(result.failures) ? result.failures : [];
  const requestedCount = Math.max(
    0,
    Math.trunc(todayOverviewNumber(result.requested_count || pending.targets.length)),
  );
  const successCount = Math.max(
    0,
    Math.trunc(todayOverviewNumber(result.success_count == null ? entries.length : result.success_count)),
  );
  const failureCount = Math.max(
    0,
    Math.trunc(todayOverviewNumber(result.failure_count == null ? failures.length : result.failure_count)),
  );
  todayOverviewPendingAction = null;
  todayOverviewBatchRecordPending = {
    kind: pending.kind,
    label,
    requestedCount,
    successCount,
    failureCount,
    targets: pending.targets,
    successEntries: entries.map(entry => ({ ...entry })),
    successIds: entries.map(entry => String(entry && entry.id || '')).filter(Boolean),
    failures: failures.map(failure => {
      const targetId = String(failure && failure.id || '');
      const target = pending.targets.find(candidate => candidate.id === targetId);
      return {
        id: targetId,
        title: String(target && target.title || targetId || '未命名事项'),
        message: String(failure && failure.message || '处理失败，请稍后重试。'),
      };
    }),
    retainedItems: [],
    retainedCount: 0,
    remainingCount: null,
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false }),
  };
  setTodayOverviewStatus('批量操作已完成，正在更新剩余待办…', 'loading');
  requestTodayOverview(false);
}

function failTodayOverviewBatchAction(data, fallback, expectedKind) {
  if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== expectedKind) return;
  todayOverviewPendingAction = null;
  todayOverviewBatchRecordPending = null;
  setTodayOverviewActionFeedback((data && data.message) || fallback, 'fail', true);
  if (todayOverviewState) renderTodayOverview(todayOverviewState);
}

function runTodayOverviewBatchAction(kind) {
  if (todayOverviewPendingAction || !socket.connected) {
    if (!socket.connected) setTodayOverviewActionFeedback('本地服务未连接，暂时无法执行批量操作。', 'fail', true);
    return;
  }
  const actionKind = kind === 'batch_handle_alerts' ? 'handle_alert' : 'resend_notification';
  const targets = todayOverviewBatchTargets(todayOverviewFilteredAttentionItems, actionKind);
  if (targets.length < 2) {
    setTodayOverviewActionFeedback('当前筛选没有足够的可批量处理事项。', 'fail', true);
    return;
  }
  const targetIds = targets.map(target => target.id);
  const prompt = kind === 'batch_handle_alerts'
    ? '将当前显示的 ' + targetIds.length + ' 条警报标记为已处理，确定继续？'
    : '将重新发送当前显示的 ' + targetIds.length + ' 条异常通知，可能发送邮件或 Webhook，确定继续？';
  if (!window.confirm(prompt)) return;
  todayOverviewActionFeedback = null;
  todayOverviewBatchRecordPending = null;
  todayOverviewPendingAction = {
    kind,
    ids: targetIds,
    targets,
    message: kind === 'batch_handle_alerts'
      ? '正在批量更新警报处置状态…'
      : '正在批量重新提交通知…',
  };
  renderTodayOverview(todayOverviewState);
  socket.emit(
    kind === 'batch_handle_alerts'
      ? 'batch_update_alert_log_handling'
      : 'batch_resend_alert_notifications',
    { ids: targetIds },
  );
}

function registerTodayOverviewBatchSocketHandlers(socketClient) {
  socketClient.on('alert_log_handling_batch_updated', data => {
    if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== 'batch_handle_alerts') return;
    completeTodayOverviewBatchAction(data, '批量标记已处理');
  });

  socketClient.on('alert_log_handling_batch_error', data => {
    failTodayOverviewBatchAction(data, '批量处理警报失败。', 'batch_handle_alerts');
  });

  socketClient.on('alert_notification_batch_resent', data => {
    if (!todayOverviewPendingAction || todayOverviewPendingAction.kind !== 'batch_resend_notifications') return;
    completeTodayOverviewBatchAction(data, '批量重提通知');
  });

  socketClient.on('alert_notification_batch_resend_error', data => {
    failTodayOverviewBatchAction(data, '批量重发通知失败。', 'batch_resend_notifications');
  });
}
