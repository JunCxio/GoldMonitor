function exportDiagnostics() {
  setOpsStatus('正在生成诊断报告...', true);
  socket.emit('get_diagnostics');
}

function copyDiagnostics() {
  hideDiagnosticsCopyFallback();
  setOpsStatus('正在生成诊断摘要...', true);
  socket.emit('copy_diagnostics');
}

function openExportsFolder() {
  setOpsStatus('正在打开导出目录...', true);
  socket.emit('open_exports_folder');
}

function resetSettings() {
  if (!confirm('确定恢复默认设置并清空阈值吗？')) return;
  setOpsStatus('正在恢复默认设置...', true);
  socket.emit('reset_settings');
}

// ========== 更新 ==========
