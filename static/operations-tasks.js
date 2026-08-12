function backgroundTaskStateMeta(state) {
  const value = String(state || 'waiting');
  if (value === 'running') return { label: '运行中', className: 'running' };
  if (value === 'ok') return { label: '正常', className: 'ok' };
  if (value === 'error') return { label: '失败', className: 'error' };
  if (value === 'disabled') return { label: '停用', className: 'disabled' };
  if (value === 'idle') return { label: '已检查', className: 'idle' };
  return { label: '等待', className: 'waiting' };
}

function formatBackgroundTaskTime(value) {
  if (!value) return '尚未运行';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

function backgroundTaskDurationLabel(value) {
  if (value == null || value === '') return '';
  const duration = Number(value);
  if (!Number.isFinite(duration)) return '';
  if (duration < 1000) return Math.max(0, Math.round(duration)) + ' 毫秒';
  return (duration / 1000).toFixed(duration < 10000 ? 1 : 0) + ' 秒';
}

function backgroundTaskDelayLabel(value) {
  const seconds = Math.max(0, Number(value) || 0);
  if (seconds < 60) return Math.round(seconds) + ' 秒';
  if (seconds < 3600) return Math.round(seconds / 60) + ' 分钟';
  return (seconds / 3600).toFixed(seconds < 36000 ? 1 : 0) + ' 小时';
}

function backgroundTaskQueueMeta(queue) {
  if (!queue || typeof queue !== 'object') return null;
  if (queue.available === false) {
    return { text: '队列状态读取失败', attention: true };
  }
  const pending = Number(queue.pending_count) || 0;
  const eligible = Number(queue.eligible_count) || 0;
  const exhausted = Number(queue.exhausted_count) || 0;
  const expired = Number(queue.expired_count) || 0;
  const nonRetryable = Number(queue.non_retryable_count) || 0;
  const stopped = exhausted + expired + nonRetryable;
  const parts = [pending ? '待重试 ' + pending + ' 条' : '队列为空'];
  if (eligible) parts.push('可立即处理 ' + eligible + ' 条');
  else if (pending && queue.next_retry_at) {
    parts.push('下次 ' + formatBackgroundTaskTime(queue.next_retry_at));
  }
  if (pending && !queue.enabled) parts.push('自动重试未开启');
  if (exhausted) parts.push('达到上限 ' + exhausted + ' 条');
  if (expired) parts.push('已过期 ' + expired + ' 条');
  if (nonRetryable) parts.push('不可重试 ' + nonRetryable + ' 条');
  return {
    text: parts.join(' · '),
    attention: !!queue.attention_required,
    stopped: stopped > 0,
  };
}

function renderBackgroundTaskStatus() {
  const list = document.getElementById('backgroundTaskStatus');
  const summary = document.getElementById('backgroundTaskSummary');
  if (!list || !summary) return;
  const payload = backgroundTaskStatus && typeof backgroundTaskStatus === 'object'
    ? backgroundTaskStatus
    : {};
  const tasks = Array.isArray(payload.tasks) ? payload.tasks : [];
  const counts = payload.summary && typeof payload.summary === 'object' ? payload.summary : {};
  if (!tasks.length) {
    summary.textContent = '等待调度服务状态';
    list.innerHTML = '<div class="ops-task-empty">后台任务尚未初始化。</div>';
    return;
  }

  const errorCount = Number(counts.error || 0);
  const runningCount = Number(counts.running || 0);
  const disabledCount = Number(counts.disabled || 0);
  const waitingCount = Number(counts.waiting || 0);
  const attentionCount = Number(counts.attention || 0);
  const delayedCount = Number(counts.delayed || 0);
  const queueAttentionCount = Number(counts.queue_attention || 0);
  const transientErrorCount = Math.max(0, errorCount - attentionCount);
  const summaryParts = [];
  if (attentionCount) summaryParts.push(attentionCount + ' 项需处理');
  if (transientErrorCount) summaryParts.push(transientErrorCount + ' 项最近失败');
  if (delayedCount) summaryParts.push(delayedCount + ' 项调度延迟');
  if (queueAttentionCount) summaryParts.push('通知队列待处理');
  if (runningCount) summaryParts.push(runningCount + ' 项运行中');
  if (disabledCount) summaryParts.push(disabledCount + ' 项停用');
  if (waitingCount) summaryParts.push(waitingCount + ' 项等待首次运行');
  if (!summaryParts.length) summaryParts.push('调度运行正常');
  const updatedAt = payload.updated_at ? '，更新于 ' + formatBackgroundTaskTime(payload.updated_at) : '';
  summary.textContent = summaryParts.join('，') + updatedAt;
  summary.dataset.state = errorCount
    ? 'error'
    : (delayedCount || queueAttentionCount ? 'delayed' : (runningCount ? 'running' : 'ok'));

  list.innerHTML = tasks.map(task => {
    const taskName = String(task.name || '');
    const attentionRequired = !!task.attention_required;
    const scheduleDelayed = !!task.schedule_delayed;
    const queueMeta = backgroundTaskQueueMeta(task.queue);
    const queueAttention = !!(queueMeta && queueMeta.attention);
    const stateMeta = backgroundTaskStateMeta(task.state);
    const meta = attentionRequired
      ? { label: '需处理', className: 'error' }
      : scheduleDelayed && stateMeta.className !== 'error'
        ? { label: '延迟', className: 'delayed' }
        : queueAttention && stateMeta.className !== 'error'
          ? { label: '待处理', className: 'delayed' }
        : stateMeta;
    const duration = backgroundTaskDurationLabel(task.last_duration_ms);
    const lastRun = formatBackgroundTaskTime(task.last_completed_at || task.last_started_at);
    const nextRun = formatBackgroundTaskTime(task.next_run_at);
    const message = task.last_message || '等待首次运行';
    const failureNote = Number(task.consecutive_failures || 0)
      ? '连续失败 ' + Number(task.consecutive_failures) + ' 次'
      : '';
    const delayNote = scheduleDelayed
      ? '已延迟 ' + backgroundTaskDelayLabel(task.schedule_delay_seconds)
      : '';
    const pending = !!pendingBackgroundTaskRuns[taskName];
    const taskRunning = task.state === 'running';
    const buttonLabel = pending || taskRunning ? '检查中' : '立即检查';
    return [
      '<div class="ops-task-item" data-state="' + meta.className + '" data-attention="' + String(attentionRequired) + '" data-delayed="' + String(scheduleDelayed) + '" data-queue-attention="' + String(queueAttention) + '">',
      '<div class="ops-task-ident">',
      '<span class="ops-task-indicator" aria-hidden="true"></span>',
      '<div><strong>' + escapeHtml(task.label || task.name || '后台任务') + '</strong>',
      '<span title="' + escapeHtml(message) + '">' + escapeHtml(message) + '</span></div>',
      '</div>',
      '<div class="ops-task-timing">',
      '<span>最近 ' + escapeHtml(lastRun) + (duration ? ' · ' + escapeHtml(duration) : '') + (failureNote ? ' · ' + escapeHtml(failureNote) : '') + '</span>',
      '<span>下次 ' + escapeHtml(nextRun) + (delayNote ? ' · ' + escapeHtml(delayNote) : '') + '</span>',
      queueMeta ? '<span class="ops-task-queue" data-state="' + (queueMeta.attention ? 'attention' : (queueMeta.stopped ? 'stopped' : 'normal')) + '">' + escapeHtml(queueMeta.text) + '</span>' : '',
      '</div>',
      '<span class="ops-task-state">' + meta.label + '</span>',
      '<button class="settings-cancel btn-form ops-task-run" type="button" data-task-name="' + escapeHtml(taskName) + '" onclick="runBackgroundTaskNow(this.dataset.taskName)"' + (pending || taskRunning ? ' disabled' : '') + '>' + buttonLabel + '</button>',
      '</div>',
    ].join('');
  }).join('');
}

function applyBackgroundTaskStatus(data) {
  finishBackgroundTaskStatusRequest();
  backgroundTaskStatus = data && typeof data === 'object' ? data : {};
  renderBackgroundTaskStatus();
}

function setBackgroundTaskRefreshPending(pending, manual = false) {
  backgroundTaskRefreshPending = !!pending;
  backgroundTaskManualRefreshPending = backgroundTaskRefreshPending && !!manual;
  const button = document.getElementById('btnRefreshBackgroundTasks');
  if (button) {
    button.disabled = backgroundTaskManualRefreshPending;
    button.textContent = backgroundTaskManualRefreshPending ? '正在刷新' : '刷新状态';
    button.setAttribute('aria-busy', String(backgroundTaskManualRefreshPending));
  }
  const card = button && button.closest('.ops-task-card');
  if (card) card.setAttribute('aria-busy', String(backgroundTaskRefreshPending));
}

function finishBackgroundTaskStatusRequest() {
  if (backgroundTaskRefreshTimeout !== null) {
    window.clearTimeout(backgroundTaskRefreshTimeout);
    backgroundTaskRefreshTimeout = null;
  }
  setBackgroundTaskRefreshPending(false);
}

function requestBackgroundTaskStatus({ manual = false } = {}) {
  if (backgroundTaskRefreshPending) {
    if (manual) setBackgroundTaskRefreshPending(true, true);
    return false;
  }
  setBackgroundTaskRefreshPending(true, manual);
  backgroundTaskRefreshTimeout = window.setTimeout(
    finishBackgroundTaskStatusRequest,
    BACKGROUND_TASK_REFRESH_TIMEOUT_MS,
  );
  socket.emit('get_background_task_status');
  return true;
}

function backgroundTaskAutoRefreshActive() {
  const backdrop = document.getElementById('settingsBackdrop');
  return !!(
    backdrop &&
    backdrop.classList.contains('show') &&
    activeSettingsTab === 'ops' &&
    document.visibilityState === 'visible'
  );
}

function startBackgroundTaskAutoRefresh() {
  if (backgroundTaskRefreshTimer !== null) return;
  requestBackgroundTaskStatus();
  backgroundTaskRefreshTimer = window.setInterval(() => {
    if (!backgroundTaskAutoRefreshActive()) {
      stopBackgroundTaskAutoRefresh();
      return;
    }
    requestBackgroundTaskStatus();
  }, BACKGROUND_TASK_REFRESH_INTERVAL_MS);
}

function stopBackgroundTaskAutoRefresh() {
  if (backgroundTaskRefreshTimer !== null) {
    window.clearInterval(backgroundTaskRefreshTimer);
    backgroundTaskRefreshTimer = null;
  }
}

function syncBackgroundTaskAutoRefresh() {
  if (backgroundTaskAutoRefreshActive()) startBackgroundTaskAutoRefresh();
  else stopBackgroundTaskAutoRefresh();
}

function refreshBackgroundTaskStatus() {
  requestBackgroundTaskStatus({ manual: true });
}

function runBackgroundTaskNow(name) {
  const taskName = String(name || '').trim();
  if (!taskName || pendingBackgroundTaskRuns[taskName]) return;
  pendingBackgroundTaskRuns[taskName] = true;
  renderBackgroundTaskStatus();
  setOpsStatus('正在检查后台任务...', true);
  socket.emit('run_background_task', { name: taskName });
}

document.addEventListener('visibilitychange', syncBackgroundTaskAutoRefresh);
window.addEventListener('pagehide', stopBackgroundTaskAutoRefresh);
