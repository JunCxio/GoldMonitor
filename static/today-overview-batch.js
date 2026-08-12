let todayOverviewFilteredAttentionItems = [];
let todayOverviewActionRecords = [];
let todayOverviewBatchRecordPending = null;

function todayOverviewUniqueTargets(items, actionKind) {
  const targets = [];
  const seen = new Set();
  items.forEach(item => {
    const actions = Array.isArray(item.quick_actions) ? item.quick_actions : [];
    const action = actions.find(candidate => candidate && candidate.kind === actionKind);
    const targetId = String(action && (action.target_id || item.source_id) || '').trim();
    if (!targetId || seen.has(targetId)) return;
    seen.add(targetId);
    targets.push(targetId);
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
  if (record.remainingCount != null) parts.push('仍待办 ' + record.remainingCount);
  return parts.join(' · ');
}

function renderTodayOverviewBatchTools(items) {
  const box = document.getElementById('todayOverviewBatch');
  const actionsBox = document.getElementById('todayOverviewBatchActions');
  const recordBox = document.getElementById('todayOverviewActionRecord');
  if (!box || !actionsBox || !recordBox) return;
  const handlingIds = todayOverviewUniqueTargets(items, 'handle_alert');
  const resendIds = todayOverviewUniqueTargets(items, 'resend_notification');
  const actions = [];
  if (handlingIds.length > 1) actions.push({
    kind: 'batch_handle_alerts',
    count: handlingIds.length,
  });
  if (resendIds.length > 1) actions.push({
    kind: 'batch_resend_notifications',
    count: resendIds.length,
  });
  const latestRecord = todayOverviewActionRecords[0] || null;
  box.hidden = !actions.length && !latestRecord;
  actionsBox.innerHTML = actions.map(action => [
    '<button class="today-overview-batch-action" type="button"',
    ' onclick="runTodayOverviewBatchAction(\'' + action.kind + '\')"',
    todayOverviewPendingAction ? ' disabled' : '',
    '>' + escapeHtml(todayOverviewBatchActionLabel(action.kind, action.count)) + '</button>',
  ].join('')).join('');
  actionsBox.hidden = actions.length === 0;
  if (latestRecord) {
    recordBox.hidden = false;
    recordBox.innerHTML = [
      '<span>最近操作</span>',
      '<strong>' + escapeHtml(todayOverviewBatchRecordText(latestRecord)) + '</strong>',
      '<small>' + escapeHtml(latestRecord.time) + ' · 本次会话 ' + todayOverviewActionRecords.length + ' 次</small>',
    ].join('');
  } else {
    recordBox.hidden = true;
    recordBox.innerHTML = '';
  }
}

function applyTodayOverviewBatchRefresh(data) {
  if (!todayOverviewBatchRecordPending) return;
  const state = data && typeof data === 'object' ? data : {};
  todayOverviewBatchRecordPending.remainingCount = Math.max(
    0,
    Math.trunc(todayOverviewNumber(state.summary && state.summary.attention_total)),
  );
  todayOverviewActionRecords.unshift(todayOverviewBatchRecordPending);
  todayOverviewActionRecords = todayOverviewActionRecords.slice(0, 5);
  const record = todayOverviewBatchRecordPending;
  todayOverviewBatchRecordPending = null;
  const statusType = record.failureCount ? 'fail' : 'ok';
  setTodayOverviewActionFeedback(todayOverviewBatchRecordText(record) + '。', statusType, true);
}

function completeTodayOverviewBatchAction(data, label) {
  const pending = todayOverviewPendingAction;
  if (!pending || !String(pending.kind || '').startsWith('batch_')) return;
  const result = data && typeof data === 'object' ? data : {};
  todayOverviewPendingAction = null;
  todayOverviewBatchRecordPending = {
    label,
    requestedCount: Math.max(0, Math.trunc(todayOverviewNumber(result.requested_count))),
    successCount: Math.max(0, Math.trunc(todayOverviewNumber(result.success_count))),
    failureCount: Math.max(0, Math.trunc(todayOverviewNumber(result.failure_count))),
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
  const targetIds = todayOverviewUniqueTargets(todayOverviewFilteredAttentionItems, actionKind);
  if (targetIds.length < 2) {
    setTodayOverviewActionFeedback('当前筛选没有足够的可批量处理事项。', 'fail', true);
    return;
  }
  const prompt = kind === 'batch_handle_alerts'
    ? '将当前显示的 ' + targetIds.length + ' 条警报标记为已处理，确定继续？'
    : '将重新发送当前显示的 ' + targetIds.length + ' 条异常通知，可能发送邮件或 Webhook，确定继续？';
  if (!window.confirm(prompt)) return;
  todayOverviewActionFeedback = null;
  todayOverviewBatchRecordPending = null;
  todayOverviewPendingAction = {
    kind,
    ids: targetIds,
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
