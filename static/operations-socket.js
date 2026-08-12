function registerOperationsSocketHandlers(socket) {
  socket.on('background_task_status', data => {
    applyBackgroundTaskStatus(data || {});
  });

  socket.on('update_status', data => {
    applyUpdateStatus(data || {});
  });

  socket.on('source_health_updated', data => {
    renderSourceHealth(data || {});
  });

  socket.on('market_sources_updated', data => {
    setSourceManagerStatus(data && data.message ? data.message : '数据源配置已更新。', true);
  });

  socket.on('market_sources_error', data => {
    setSourceManagerStatus(data && data.message ? data.message : '数据源配置更新失败。', false);
  });

  socket.on('market_source_retry_result', data => {
    const pending = data && data.pending;
    const message = data && data.message ? data.message : (pending ? '正在探测数据源...' : '数据源探测完成。');
    setSourceManagerStatus(message, pending ? null : !!(data && data.ok));
    if (data && data.source_health) renderSourceHealth(data.source_health);
  });

  socket.on('config_backup_ready', data => {
    if (!data) return;
    if (data.ok === false) {
      addRecentOpsRecord('config_export', data);
      setOpsExportStatus(data, '配置已导出', '配置导出失败。');
      return;
    }
    if (data.saved_path) {
      addRecentOpsRecord('config_export', data);
      setOpsExportStatus(data, '配置已导出', '配置导出失败。');
      return;
    }
    if (!data.content) return;
    const fallbackData = { ...data, filename: data.filename || 'GoldMonitor-config.json' };
    downloadText(fallbackData.filename, data.content, 'application/json;charset=utf-8');
    addRecentOpsRecord('config_export', fallbackData);
    setOpsExportStatus(fallbackData, '配置已导出', '配置导出失败。');
  });

  socket.on('data_archive_exported', data => {
    addRecentOpsRecord('data_archive_export', data || {});
    setOpsExportStatus(data || {}, '完整数据归档已创建', '完整数据归档失败。');
  });

  socket.on('data_archive_export_error', data => {
    addRecentOpsRecord('data_archive_export', data || {});
    setOpsExportStatus(data || {}, '完整数据归档已创建', '完整数据归档失败。');
  });

  socket.on('data_archive_restored', data => {
    if (!data || data.ok === false) return;
    setOpsStatus(data.message || '完整数据已恢复，正在重新载入界面。', true);
  });

  socket.on('diagnostics_ready', data => {
    if (!data) return;
    if (data.ok === false) {
      addRecentOpsRecord('diagnostics_export', data);
      setOpsExportStatus(data, '诊断报告已导出', '诊断报告导出失败。');
      return;
    }
    if (data.saved_path) {
      addRecentOpsRecord('diagnostics_export', data);
      setOpsExportStatus(data, '诊断报告已导出', '诊断报告导出失败。');
      return;
    }
    if (!data.content) return;
    const fallbackData = { ...data, filename: data.filename || 'GoldMonitor-diagnostics.json' };
    downloadText(fallbackData.filename, data.content, 'application/json;charset=utf-8');
    addRecentOpsRecord('diagnostics_export', fallbackData);
    setOpsExportStatus(fallbackData, '诊断报告已导出', '诊断报告导出失败。');
  });

  function hideDiagnosticsCopyFallback() {
    const fallback = document.getElementById('diagnosticsCopyFallback');
    if (!fallback) return;
    fallback.value = '';
    fallback.hidden = true;
  }

  function showDiagnosticsCopyFallback(content) {
    const fallback = document.getElementById('diagnosticsCopyFallback');
    if (!fallback) return;
    fallback.value = content;
    fallback.hidden = false;
    requestAnimationFrame(() => {
      fallback.focus();
      fallback.select();
    });
  }

  function copyTextWithSelection(content) {
    const textarea = document.createElement('textarea');
    textarea.value = content;
    textarea.setAttribute('readonly', 'readonly');
    textarea.style.position = 'fixed';
    textarea.style.left = '-9999px';
    textarea.style.top = '0';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      return document.execCommand('copy');
    } catch (error) {
      return false;
    } finally {
      textarea.remove();
    }
  }

  function copyTextToClipboard(content) {
    const fallbackCopy = () => Promise.resolve(copyTextWithSelection(content));
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(content).then(() => true).catch(fallbackCopy);
    }
    return fallbackCopy();
  }

  socket.on('diagnostics_copy_ready', data => {
    if (!data) return;
    if (data.ok === false) {
      setOpsStatus(data.message || '诊断摘要生成失败。', false);
      return;
    }
    const content = data.content || '';
    if (!content) {
      setOpsStatus('诊断摘要为空，无法复制。', false);
      return;
    }
    copyTextToClipboard(content)
      .then(copied => {
        if (copied) {
          hideDiagnosticsCopyFallback();
          setOpsStatus('诊断摘要已复制。', true);
          return;
        }
        showDiagnosticsCopyFallback(content);
        setOpsStatus('自动复制失败，已展示诊断摘要，可手动复制。', false);
      })
      .catch(() => {
        showDiagnosticsCopyFallback(content);
        setOpsStatus('自动复制失败，已展示诊断摘要，可手动复制。', false);
      });
  });

  socket.on('exports_folder_opened', data => {
    addRecentOpsRecord('open_exports_folder', data || {});
    if (data && data.ok === false) {
      setOpsExportStatus(data, '已打开导出目录', '无法打开导出目录。');
      return;
    }
    setOpsStatus(data && data.message ? data.message : '已打开导出目录。', !!(data && data.ok));
  });

  socket.on('config_import_previewed', data => {
    const text = document.getElementById('configImportText') ? document.getElementById('configImportText').value.trim() : '';
    const previewedPayload = configImportPreviewRequestPayload;
    configImportPreviewRequestPayload = null;
    if (!previewedPayload || previewedPayload !== text) {
      pendingConfigImportPayload = null;
      pendingConfigImportPreview = null;
      setOpsStatus('备份内容已变更，请重新预检。', false);
      return;
    }
    if (data && data.importable) {
      pendingConfigImportPayload = previewedPayload;
      pendingConfigImportPreview = data;
      setOpsStatus(renderConfigImportPreview(data), true);
      return;
    }
    pendingConfigImportPayload = null;
    pendingConfigImportPreview = null;
    setOpsStatus(renderConfigImportPreview(data), false);
  });

  socket.on('config_import_result', data => {
    configImportPreviewRequestPayload = null;
    pendingConfigImportPayload = null;
    pendingConfigImportPreview = null;
    setOpsStatus(data && data.message ? data.message : '配置导入完成。', !!(data && data.ok));
  });

  socket.on('settings_reset_result', data => {
    setOpsStatus(data && data.message ? data.message : '已恢复默认设置。', !!(data && data.ok));
  });


}

// ========== 数据源与运维 ==========
