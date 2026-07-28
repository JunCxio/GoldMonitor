function exportConfig() {
  setOpsStatus('正在导出配置...', true);
  socket.emit('export_config');
}

function exportDataArchive() {
  setOpsStatus('正在创建完整数据归档...', true);
  socket.emit('export_data_archive');
}

function formatDataArchiveBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function resetDataArchivePreview() {
  pendingDataArchiveRestore = null;
  const preview = document.getElementById('dataArchivePreview');
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (preview) preview.innerHTML = '';
  if (restoreButton) {
    restoreButton.hidden = true;
    restoreButton.disabled = false;
  }
}

function renderDataArchivePreview(data, fileName) {
  const preview = document.getElementById('dataArchivePreview');
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (!preview || !restoreButton) return;
  if (!data || data.ok === false || data.restorable === false) {
    preview.innerHTML = '<div class="data-archive-preview-error">' + escapeHtml((data && data.message) || '归档预检失败。') + '</div>';
    restoreButton.hidden = true;
    return;
  }
  const items = Array.isArray(data.items) ? data.items.filter(item => item && item.present) : [];
  const labels = items.slice(0, 8).map(item => item.label || item.key).filter(Boolean);
  const remaining = Math.max(0, items.length - labels.length);
  const detail = labels.join('、') + (remaining ? '等 ' + items.length + ' 项' : '');
  preview.innerHTML = [
    '<div class="data-archive-preview-ok"><strong>归档校验通过</strong></div>',
    '<div>文件：' + escapeHtml(fileName || '') + '</div>',
    '<div>来源版本：' + escapeHtml(data.source_app_version || '未知') + '；导出时间：' + escapeHtml((data.exported_at || '').replace('T', ' ')) + '</div>',
    '<div>数据量：' + escapeHtml(String(data.files || 0)) + ' 项，' + escapeHtml(formatDataArchiveBytes(data.bytes)) + '</div>',
    detail ? '<div>包含：' + escapeHtml(detail) + '</div>' : '',
    data.contains_sensitive_data ? '<div class="data-archive-preview-warning">归档包含通知密钥等敏感配置。</div>' : '',
  ].join('');
  restoreButton.hidden = false;
}

function chooseDataArchive() {
  const input = document.getElementById('dataArchiveFile');
  if (!input) {
    setOpsStatus('未找到归档文件选择入口。', false);
    return;
  }
  input.value = '';
  resetDataArchivePreview();
  input.click();
}

async function previewDataArchive(input) {
  const file = input && input.files ? input.files[0] : null;
  resetDataArchivePreview();
  if (!file) return;
  setOpsStatus('正在校验完整数据归档...', true);
  const formData = new FormData();
  formData.append('archive', file, file.name);
  try {
    const response = await fetch('/api/data-archive/preview', {
      method: 'POST',
      headers: { 'X-GoldMonitor-Token': SOCKET_ACCESS_TOKEN },
      body: formData,
    });
    const data = await response.json();
    renderDataArchivePreview(data, file.name);
    if (!response.ok || !data.restore_token) {
      setOpsStatus(data.message || '归档预检失败。', false);
      return;
    }
    pendingDataArchiveRestore = {
      token: data.restore_token,
      fileName: file.name,
      preview: data,
    };
    setOpsStatus(data.message || '归档预检通过，请确认恢复。', true);
  } catch (error) {
    renderDataArchivePreview({ ok: false, message: '无法上传或校验归档文件。' }, file.name);
    setOpsStatus('无法上传或校验归档文件。', false);
  }
}

async function confirmDataArchiveRestore() {
  if (!pendingDataArchiveRestore || !pendingDataArchiveRestore.token) {
    setOpsStatus('请先选择并校验归档文件。', false);
    return;
  }
  const confirmed = confirm('恢复完整数据会覆盖当前设置、持仓、预警、复盘和历史记录。是否继续？');
  if (!confirmed) return;
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (restoreButton) restoreButton.disabled = true;
  setOpsStatus('正在恢复完整数据，请勿关闭应用...', true);
  try {
    const response = await fetch('/api/data-archive/restore', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-GoldMonitor-Token': SOCKET_ACCESS_TOKEN,
      },
      body: JSON.stringify({ restore_token: pendingDataArchiveRestore.token }),
    });
    const data = await response.json();
    pendingDataArchiveRestore = null;
    if (!response.ok || data.ok === false) {
      setOpsStatus(data.message || '完整数据恢复失败，原数据已回滚。', false);
      if (restoreButton) restoreButton.disabled = false;
      return;
    }
    setOpsStatus(data.message || '完整数据已恢复，正在重新载入界面。', true);
    setTimeout(() => window.location.reload(), 800);
  } catch (error) {
    setOpsStatus('完整数据恢复请求失败，请重新选择归档并确认当前数据状态。', false);
    if (restoreButton) restoreButton.disabled = false;
  }
}
