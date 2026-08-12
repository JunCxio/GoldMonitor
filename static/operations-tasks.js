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
  const transientErrorCount = Math.max(0, errorCount - attentionCount);
  const summaryParts = [];
  if (attentionCount) summaryParts.push(attentionCount + ' 项需处理');
  if (transientErrorCount) summaryParts.push(transientErrorCount + ' 项最近失败');
  if (delayedCount) summaryParts.push(delayedCount + ' 项调度延迟');
  if (runningCount) summaryParts.push(runningCount + ' 项运行中');
  if (disabledCount) summaryParts.push(disabledCount + ' 项停用');
  if (waitingCount) summaryParts.push(waitingCount + ' 项等待首次运行');
  if (!summaryParts.length) summaryParts.push('调度运行正常');
  const updatedAt = payload.updated_at ? '，更新于 ' + formatBackgroundTaskTime(payload.updated_at) : '';
  summary.textContent = summaryParts.join('，') + updatedAt;
  summary.dataset.state = errorCount
    ? 'error'
    : (delayedCount ? 'delayed' : (runningCount ? 'running' : 'ok'));

  list.innerHTML = tasks.map(task => {
    const taskName = String(task.name || '');
    const attentionRequired = !!task.attention_required;
    const scheduleDelayed = !!task.schedule_delayed;
    const stateMeta = backgroundTaskStateMeta(task.state);
    const meta = attentionRequired
      ? { label: '需处理', className: 'error' }
      : scheduleDelayed && stateMeta.className !== 'error'
        ? { label: '延迟', className: 'delayed' }
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
      '<div class="ops-task-item" data-state="' + meta.className + '" data-attention="' + String(attentionRequired) + '" data-delayed="' + String(scheduleDelayed) + '">',
      '<div class="ops-task-ident">',
      '<span class="ops-task-indicator" aria-hidden="true"></span>',
      '<div><strong>' + escapeHtml(task.label || task.name || '后台任务') + '</strong>',
      '<span title="' + escapeHtml(message) + '">' + escapeHtml(message) + '</span></div>',
      '</div>',
      '<div class="ops-task-timing">',
      '<span>最近 ' + escapeHtml(lastRun) + (duration ? ' · ' + escapeHtml(duration) : '') + (failureNote ? ' · ' + escapeHtml(failureNote) : '') + '</span>',
      '<span>下次 ' + escapeHtml(nextRun) + (delayNote ? ' · ' + escapeHtml(delayNote) : '') + '</span>',
      '</div>',
      '<span class="ops-task-state">' + meta.label + '</span>',
      '<button class="settings-cancel btn-form ops-task-run" type="button" data-task-name="' + escapeHtml(taskName) + '" onclick="runBackgroundTaskNow(this.dataset.taskName)"' + (pending || taskRunning ? ' disabled' : '') + '>' + buttonLabel + '</button>',
      '</div>',
    ].join('');
  }).join('');
}

function applyBackgroundTaskStatus(data) {
  backgroundTaskStatus = data && typeof data === 'object' ? data : {};
  renderBackgroundTaskStatus();
}

function refreshBackgroundTaskStatus() {
  const button = document.getElementById('btnRefreshBackgroundTasks');
  if (button) {
    button.disabled = true;
    window.setTimeout(() => { button.disabled = false; }, 600);
  }
  socket.emit('get_background_task_status');
}

function runBackgroundTaskNow(name) {
  const taskName = String(name || '').trim();
  if (!taskName || pendingBackgroundTaskRuns[taskName]) return;
  pendingBackgroundTaskRuns[taskName] = true;
  renderBackgroundTaskStatus();
  setOpsStatus('正在检查后台任务...', true);
  socket.emit('run_background_task', { name: taskName });
}
