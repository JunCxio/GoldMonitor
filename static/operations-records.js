function setOpsStatus(message, ok) {
  const el = document.getElementById('opsStatus');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = ok ? 'var(--down)' : 'var(--up)';
}

function recentOpsTypeLabel(type, data) {
  const payload = data && typeof data === 'object' ? data : {};
  if (type === 'config_export') return '导出配置';
  if (type === 'data_archive_export') return '完整数据归档';
  if (type === 'diagnostics_export') return '生成诊断';
  if (type === 'open_exports_folder') return '打开目录';
  if (type === 'price_history_repair') {
    if (payload.action === 'clean_invalid_records') return '清理历史无效明细';
    if (payload.action === 'rebuild_rollups') return '重建历史汇总';
    if (payload.action === 'sync_json_and_rebuild') return '同步历史 JSON';
    if (payload.action === 'restore_last_repair') return '恢复历史修复';
    return '历史数据修复';
  }
  return '运维操作';
}

function recentOpsTimeLabel(date) {
  return date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function addRecentOpsRecord(type, data) {
  const payload = data && typeof data === 'object' ? data : {};
  const detail = payload.error_detail && typeof payload.error_detail === 'object' ? payload.error_detail : {};
  const dirCheck = payload.export_dir_check && typeof payload.export_dir_check === 'object' ? payload.export_dir_check : {};
  const ok = payload.ok !== false;
  const savedPath = payload.saved_path || '';
  const path = savedPath || payload.export_dir || detail.export_dir || dirCheck.path || '';
  const message = ok
    ? (savedPath ? '文件已保存到导出目录。' : (type === 'open_exports_folder' ? '已打开导出目录。' : (payload.message || '操作完成。')))
    : (detail.message || payload.message || '操作失败。');
  const record = {
    id: Date.now() + '-' + recentOpsRecords.length,
    type,
    label: recentOpsTypeLabel(type, payload),
    ok,
    status: ok ? '成功' : '失败',
    time: recentOpsTimeLabel(new Date()),
    path,
    message,
    error: detail.error || '',
    actions: !ok && Array.isArray(dirCheck.actions) ? dirCheck.actions : [],
  };
  recentOpsRecords = [record, ...recentOpsRecords].slice(0, RECENT_OPS_LIMIT);
  renderRecentOpsRecords();
}

function renderRecentOpsRecords() {
  const list = document.getElementById('recentOpsList');
  if (!list) return;
  if (!recentOpsRecords.length) {
    list.innerHTML = '<div class="ops-recent-empty">暂无操作记录</div>';
    return;
  }
  list.innerHTML = recentOpsRecords.map(record => {
    const stateClass = record.ok ? 'ok' : 'fail';
    const actions = Array.isArray(record.actions) ? record.actions.map(exportDirActionButton).filter(Boolean).join('') : '';
    const path = record.path ? '<div class="ops-recent-path" title="' + escapeHtml(record.path) + '">' + escapeHtml(record.path) + '</div>' : '';
    const failure = !record.ok
      ? '<div class="ops-recent-error"><strong>失败原因</strong><span>' + escapeHtml([record.message, record.error ? '底层错误：' + record.error : ''].filter(Boolean).join(' ')) + '</span></div>'
      : '';
    return [
      '<div class="ops-recent-item ' + stateClass + '">',
      '<div class="ops-recent-head">',
      '<span class="ops-recent-title">' + escapeHtml(record.label) + '</span>',
      '<span class="ops-recent-state ' + stateClass + '">' + escapeHtml(record.status) + '</span>',
      '<span class="ops-recent-time">' + escapeHtml(record.time) + '</span>',
      '</div>',
      path,
      record.ok ? '<div class="ops-recent-message" title="' + escapeHtml(record.message) + '">' + escapeHtml(record.message) + '</div>' : failure,
      actions ? '<div class="export-dir-actions">' + actions + '</div>' : '',
      '</div>',
    ].join('');
  }).join('');
}

function setOpsExportStatus(data, successLabel, fallbackMessage) {
  const el = document.getElementById('opsStatus');
  if (!el) return;
  const payload = data && typeof data === 'object' ? data : {};
  const ok = payload.ok !== false;
  el.style.color = ok ? 'var(--down)' : 'var(--up)';
  if (ok) {
    const savedPath = payload.saved_path || '';
    const filename = payload.filename || '';
    let message = successLabel || '导出已完成';
    if (savedPath) {
      message += '：' + savedPath;
    } else if (filename) {
      message += '，文件名：' + filename + '。';
    } else {
      message += '。';
    }
    el.innerHTML = [
      '<span>' + escapeHtml(message) + '</span>',
      savedPath ? '<button class="btn-clear-sm btn-muted-sm export-dir-action" type="button" onclick="openExportsFolder()">打开目录</button>' : '',
    ].join('');
    return;
  }
  const detail = data && data.error_detail && typeof data.error_detail === 'object' ? data.error_detail : {};
  const dirCheck = data && data.export_dir_check && typeof data.export_dir_check === 'object' ? data.export_dir_check : {};
  const message = detail.message || payload.message || fallbackMessage || '导出失败。';
  const extra = dirCheck.message && dirCheck.message !== message ? dirCheck.message : '';
  const error = detail.error ? '底层错误：' + detail.error : '';
  const actions = Array.isArray(dirCheck.actions) ? dirCheck.actions.map(exportDirActionButton).filter(Boolean) : [];
  el.innerHTML = [
    '<span>' + escapeHtml([message, extra, error].filter(Boolean).join(' ')) + '</span>',
    actions.length ? '<span class="export-dir-actions">' + actions.join('') + '</span>' : '',
  ].join('');
}
