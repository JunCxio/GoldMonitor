const RECENT_OPS_LIMIT = 5;
let pendingUpdateInfo = null;
let pendingConfigImportPayload = null;
let pendingConfigImportPreview = null;
let configImportPreviewRequestPayload = null;
let pendingDataArchiveRestore = null;
let recentOpsRecords = [];
let autoUpdateTimer = null;
let lastAutoUpdateCheckAt = 0;
let opsUpdateStatus = null;
const AUTO_UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
function autoUpdateIntervalMs() {
  return AUTO_UPDATE_CHECK_INTERVAL_MS;
}
let latestSourceHealthState = { items: [], summary: {} };
let latestSourceComparisonState = { items: [], summary: {}, status: 'insufficient' };

function registerOperationsSocketHandlers(socket) {
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
function toggleSourceHealthDetails() {
  const details = document.getElementById('sourceHealthDetails');
  if (!details) return;
  details.hidden = !details.hidden;
}

function sourceQualityText(quality) {
  if (!quality || typeof quality !== 'object') return '';
  const score = quality.score == null ? '--' : quality.score;
  const label = quality.label || quality.level || '--';
  return '行情质量 ' + score + '分/' + label;
}

function setSourceManagerStatus(message, ok) {
  const status = document.getElementById('sourceManagerStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'source-manager-status' + (ok === true ? ' ok' : ok === false ? ' fail' : '');
}

function renderMarketQualityDetails(quality) {
  const box = document.getElementById('marketQualityDetails');
  if (!box) return;
  const reasons = box.querySelector('.market-quality-reasons');
  const deductions = quality && Array.isArray(quality.deductions) ? quality.deductions : [];
  if (!deductions.length) {
    reasons.innerHTML = '<div class="market-quality-reason none"><span class="market-quality-points">0分</span><span>当前没有质量扣分项</span></div>';
    return;
  }
  reasons.innerHTML = deductions.map(item => [
    '<div class="market-quality-reason" title="' + escapeHtml(item.detail || item.label || '') + '">',
    '<span class="market-quality-points">-' + escapeHtml(item.points == null ? '--' : item.points) + '分</span>',
    '<span>' + escapeHtml(item.detail || item.label || '质量异常') + '</span>',
    '</div>',
  ].join('')).join('');
}

function sourceCategoryLabel(category) {
  if (category === 'gold') return '金价源';
  if (category === 'forex') return '汇率源';
  return category || '数据源';
}

function marketSourcePreferences() {
  const adapters = latestSourceHealthState && latestSourceHealthState.adapters || {};
  const enabled = {};
  const order = {};
  Object.keys(adapters).forEach(category => {
    const items = Array.isArray(adapters[category]) ? adapters[category].slice() : [];
    items.sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
    order[category] = items.map(item => item.key).filter(Boolean);
    enabled[category] = items.filter(item => item.enabled).map(item => item.key).filter(Boolean);
  });
  return { enabled, order };
}

function updateMarketSourceEnabled(category, key, checked) {
  const preferences = marketSourcePreferences();
  const categoryEnabled = Array.isArray(preferences.enabled[category]) ? preferences.enabled[category].slice() : [];
  if (checked && !categoryEnabled.includes(key)) categoryEnabled.push(key);
  if (!checked) preferences.enabled[category] = categoryEnabled.filter(item => item !== key);
  else preferences.enabled[category] = preferences.order[category].filter(item => categoryEnabled.includes(item));
  if (!preferences.enabled[category].length) {
    setSourceManagerStatus(sourceCategoryLabel(category) + '至少启用一个。', false);
    renderSourceManager(latestSourceHealthState);
    return;
  }
  setSourceManagerStatus('正在保存数据源配置...', null);
  socket.emit('update_market_sources', preferences);
}

function moveMarketSource(category, key, direction) {
  const preferences = marketSourcePreferences();
  const order = Array.isArray(preferences.order[category]) ? preferences.order[category].slice() : [];
  const currentIndex = order.indexOf(key);
  const nextIndex = currentIndex + Number(direction || 0);
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= order.length) return;
  const displaced = order[nextIndex];
  order[nextIndex] = key;
  order[currentIndex] = displaced;
  preferences.order[category] = order;
  preferences.enabled[category] = order.filter(item => preferences.enabled[category].includes(item));
  setSourceManagerStatus('正在保存数据源顺序...', null);
  socket.emit('update_market_sources', preferences);
}

function retryMarketSource(key) {
  setSourceManagerStatus('正在探测数据源...', null);
  socket.emit('retry_market_source', { key });
}

function resetMarketSources() {
  setSourceManagerStatus('正在恢复默认数据源顺序...', null);
  socket.emit('reset_market_sources');
}

function renderSourceManager(data) {
  const box = document.getElementById('sourceManager');
  if (!box) return;
  const list = box.querySelector('.source-manager-list');
  const adapters = data && data.adapters && typeof data.adapters === 'object' ? data.adapters : {};
  const categories = ['gold', 'forex'].filter(category => Array.isArray(adapters[category]));
  if (!categories.length) {
    list.innerHTML = '<div class="source-manager-meta">等待数据源目录</div>';
    return;
  }
  list.innerHTML = categories.map(category => {
    const items = adapters[category].slice().sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
    const enabledCount = items.filter(item => item.enabled).length;
    const rows = items.map((item, index) => {
      const successRate = item.success_rate_pct == null ? '--' : Number(item.success_rate_pct).toFixed(1) + '%';
      const latency = item.median_latency_ms == null ? '--' : Number(item.median_latency_ms).toFixed(0) + 'ms';
      const failures = Number(item.consecutive_failures || 0);
      const currentLabel = item.active ? '当前主源' : item.current_cached ? '当前缓存来源' : item.current ? '正在切换' : '';
      const disableToggle = !!item.enabled && enabledCount <= 1;
      const safeKey = escapeHtml(item.key || '');
      const safeCategory = escapeHtml(category);
      return [
        '<div class="source-manager-row' + (item.enabled ? '' : ' disabled') + '">',
        '<input class="source-manager-toggle" type="checkbox" aria-label="启用' + escapeHtml(item.name || '') + '" ',
        item.enabled ? 'checked ' : '',
        disableToggle ? 'disabled ' : '',
        'onchange="updateMarketSourceEnabled(\'' + safeCategory + '\',\'' + safeKey + '\',this.checked)">',
        '<div class="source-manager-copy">',
        '<div class="source-manager-name">' + escapeHtml(item.name || '--') + (currentLabel ? '<span class="source-manager-current">' + currentLabel + '</span>' : '') + '</div>',
        '<div class="source-manager-meta">近 ' + escapeHtml(item.sample_count || 0) + ' 次 · 成功率 ' + escapeHtml(successRate) + ' · 中位延迟 ' + escapeHtml(latency) + (failures ? ' · 连续失败 ' + failures + ' 次' : '') + '</div>',
        '</div>',
        '<div class="source-manager-actions">',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="moveMarketSource(\'' + safeCategory + '\',\'' + safeKey + '\',-1)" ' + (index === 0 ? 'disabled' : '') + '>上移</button>',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="moveMarketSource(\'' + safeCategory + '\',\'' + safeKey + '\',1)" ' + (index === items.length - 1 ? 'disabled' : '') + '>下移</button>',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="retryMarketSource(\'' + safeKey + '\')">探测</button>',
        '</div>',
        '</div>',
      ].join('');
    }).join('');
    return '<div class="source-manager-category"><div class="source-manager-category-title">' + sourceCategoryLabel(category) + '</div>' + rows + '</div>';
  }).join('');
}

function renderSourceHealth(data) {
  latestSourceHealthState = data || { items: [], summary: {} };
  if (data && data.comparison) renderSourceComparison(data.comparison);
  renderMarketQualityDetails(data && data.quality ? data.quality : {});
  renderSourceManager(latestSourceHealthState);
  const box = document.getElementById('sourceHealth');
  if (!box) return;
  const items = Array.isArray(data.items) ? data.items : [];
  const summary = data.summary || {};
  const head = box.querySelector('.source-summary-text');
  const list = box.querySelector('.source-health-list');
  const ok = Number(summary.ok || 0);
  const failed = Number(summary.failed || 0);
  const cached = Number(summary.cached || 0);
  const countText = failed
    ? '异常 ' + failed + ' · 正常 ' + ok
    : (cached ? '缓存 ' + cached + ' · 正常 ' + ok : '正常 ' + ok);
  head.textContent = [sourceQualityText(data.quality), countText].filter(Boolean).join(' · ');
  head.title = head.textContent;
  if (!items.length) {
    list.innerHTML = '<div class="source-health-item"><span class="source-health-dot"></span><span class="source-health-name">等待数据源检查</span><span class="source-health-meta">--</span></div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const cls = item.cached ? 'cached' : item.ok ? 'ok' : 'fail';
    const elapsed = item.elapsed_ms == null ? '--' : item.elapsed_ms + 'ms';
    const status = item.cached ? '缓存' : item.ok ? '正常' : '异常';
    const title = item.error ? item.error : status;
    const successRate = item.success_rate_pct == null ? '--' : Number(item.success_rate_pct).toFixed(1) + '%';
    const failures = Number(item.consecutive_failures || 0);
    const rolling = '成功率 ' + successRate + ' · ' + elapsed + (failures ? ' · 连续失败 ' + failures + ' 次' : '');
    return [
      '<div class="source-health-item" title="' + escapeHtml(title) + '">',
      '<span class="source-health-dot ' + cls + '"></span>',
      '<span class="source-health-name">' + escapeHtml(item.name || '--') + (item.active ? ' · 当前主源' : '') + '</span>',
      '<span class="source-health-meta">' + escapeHtml(status + ' · ' + rolling) + '</span>',
      '</div>',
    ].join('');
  }).join('');
}

function renderSourceComparison(data) {
  latestSourceComparisonState = Object.assign({ items: [], summary: {}, status: 'insufficient' }, data || {});
  const box = document.getElementById('sourceComparison');
  if (!box) return;
  const head = box.querySelector('.source-comparison-head span:first-child');
  const badge = box.querySelector('.source-comparison-badge');
  const list = box.querySelector('.source-comparison-list');
  const summary = latestSourceComparisonState.summary || {};
  const status = latestSourceComparisonState.status || 'insufficient';
  const statusText = status === 'anomaly' ? '异常' : status === 'normal' ? '正常' : '不足';
  head.textContent = summary.spread_pct == null
    ? '行情源价差'
    : '行情源价差 ' + Number(summary.spread_pct).toFixed(2) + '%';
  badge.textContent = statusText;
  badge.className = 'source-comparison-badge ' + status;
  const items = Array.isArray(latestSourceComparisonState.items)
    ? latestSourceComparisonState.items.filter(item => item && item.usd != null).slice(0, 4)
    : [];
  if (!items.length) {
    list.innerHTML = '<div class="source-comparison-item"><span class="source-comparison-name">等待行情源样本</span><span class="source-comparison-price">--</span></div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const state = item.cached ? '缓存' : item.stale ? '过期' : item.available ? '可比' : '待确认';
    return [
      '<div class="source-comparison-item" title="' + escapeHtml((item.name || '') + ' · ' + state) + '">',
      '<span class="source-comparison-name">' + escapeHtml(item.name || '--') + ' · ' + escapeHtml(state) + '</span>',
      '<span class="source-comparison-price">$' + Number(item.usd).toFixed(2) + '</span>',
      '</div>',
    ].join('');
  }).join('');
}

function refreshSourceHealth() {
  socket.emit('get_source_health');
}


function setOpsStatus(message, ok) {
  const el = document.getElementById('opsStatus');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = ok ? 'var(--down)' : 'var(--up)';
}

function recentOpsTypeLabel(type) {
  if (type === 'config_export') return '导出配置';
  if (type === 'data_archive_export') return '完整数据归档';
  if (type === 'diagnostics_export') return '生成诊断';
  if (type === 'open_exports_folder') return '打开目录';
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
    label: recentOpsTypeLabel(type),
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

function configImportSectionLabel(section) {
  if (section === 'settings') return '通用设置';
  if (section === 'thresholds') return '预警阈值';
  if (section === 'alert_profiles') return '预警策略模板';
  if (section === 'alert_rules') return '统一预警规则';
  return section || '未知配置';
}

function configImportSecretActionLabel(action) {
  if (action === 'import') return '导入';
  if (action === 'clear') return '清空';
  return '保留现有';
}

function configImportFormatText(data) {
  const schemaVersion = Number(data && data.schema_version);
  const expectedSchemaVersion = Number(data && data.expected_schema_version);
  const format = data && typeof data.format === 'string' ? data.format.trim() : '';
  const sourceAppVersion = data && typeof data.source_app_version === 'string'
    ? data.source_app_version.trim()
    : '';
  if (data && data.needs_migration) {
    return '旧版备份将在导入时迁移' + (sourceAppVersion ? '（来源版本 ' + sourceAppVersion + '）' : '');
  }
  const resolvedVersion = Number.isInteger(schemaVersion) && schemaVersion >= 0
    ? schemaVersion
    : (Number.isInteger(expectedSchemaVersion) && expectedSchemaVersion >= 0 ? expectedSchemaVersion : null);
  const formatText = resolvedVersion !== null ? 'schema v' + resolvedVersion : (format || '当前格式');
  return '当前备份格式：' + formatText + (sourceAppVersion ? '（来源版本 ' + sourceAppVersion + '）' : '');
}

function renderConfigImportPreview(data) {
  if (!data || data.ok === false || data.importable === false) {
    return (data && data.message) || '配置导入预检失败。';
  }
  const rawSections = Array.isArray(data.sections) ? data.sections : [];
  const sections = rawSections.map(configImportSectionLabel);
  const ignored = data.ignored && typeof data.ignored === 'object' ? data.ignored : {};
  const ignoredFieldCount = []
    .concat(Array.isArray(ignored.settings) ? ignored.settings : [])
    .concat(Array.isArray(ignored.thresholds) ? ignored.thresholds : [])
    .length;
  const ignoredProfileCount = Array.isArray(ignored.alert_profiles) ? ignored.alert_profiles.length : 0;
  const ignoredRuleCount = Array.isArray(ignored.alert_rules) ? ignored.alert_rules.length : 0;
  const secretActions = rawSections.includes('settings') && data.secret_actions && typeof data.secret_actions === 'object'
    ? data.secret_actions
    : {};
  const secretSummary = Object.keys(secretActions).reduce((acc, key) => {
    const label = configImportSecretActionLabel(secretActions[key]);
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const secretText = Object.keys(secretSummary).map(label => label + ' ' + secretSummary[label] + ' 项').join('，');
  const parts = [
    '配置预检通过：将导入' + (sections.length ? sections.join('、') : '配置'),
    configImportFormatText(data),
  ];
  if (ignoredFieldCount) parts.push('忽略不支持字段 ' + ignoredFieldCount + ' 项');
  if (ignoredProfileCount) parts.push('忽略重复、无效或超限策略模板 ' + ignoredProfileCount + ' 项');
  if (ignoredRuleCount) parts.push('忽略重复、无效或超限预警规则 ' + ignoredRuleCount + ' 项');
  if (secretText) parts.push('敏感字段：' + secretText);
  parts.push('再次点击导入确认');
  return parts.join('；') + '。';
}

function importConfig() {
  const text = document.getElementById('configImportText').value.trim();
  if (!text) {
    setOpsStatus('请先粘贴配置备份 JSON。', false);
    return;
  }
  if (configImportPreviewRequestPayload !== null) {
    const changed = configImportPreviewRequestPayload !== text;
    setOpsStatus(changed ? '备份内容已变更，当前预检返回后请重新预检。' : '正在预检导入配置...', !changed);
    return;
  }
  if (pendingConfigImportPayload === text && pendingConfigImportPreview && pendingConfigImportPreview.importable) {
    setOpsStatus('正在导入配置...', true);
    socket.emit('import_config', { payload: text });
    pendingConfigImportPayload = null;
    pendingConfigImportPreview = null;
    return;
  }
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  configImportPreviewRequestPayload = text;
  setOpsStatus('正在预检导入配置...', true);
  socket.emit('preview_import_config', { payload: text });
}

function invalidateConfigImportPreviewOnInput() {
  const hasPreviewState = configImportPreviewRequestPayload !== null
    || pendingConfigImportPayload !== null
    || pendingConfigImportPreview !== null;
  if (!hasPreviewState) return;
  configImportPreviewRequestPayload = null;
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  setOpsStatus('备份内容已变更，请重新预检。', false);
}

const configImportTextInput = document.getElementById('configImportText');
if (configImportTextInput) {
  configImportTextInput.addEventListener('input', invalidateConfigImportPreviewOnInput);
}

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
function openUpdate() {
  document.getElementById('updateBackdrop').classList.add('show');
  if (!pendingUpdateInfo) {
    checkUpdate();
  }
}

function closeUpdate() {
  document.getElementById('updateBackdrop').classList.remove('show');
}

function onUpdateBackdrop(event) {
  if (event.target.id === 'updateBackdrop') closeUpdate();
}

function renderOpsUpdateStatus(data) {
  opsUpdateStatus = data || opsUpdateStatus || null;
  const statusEl = document.getElementById('opsUpdateStatus');
  const metaEl = document.getElementById('opsUpdateMeta');
  if (!statusEl || !metaEl) return;
  const state = opsUpdateStatus && opsUpdateStatus.state ? opsUpdateStatus.state : '';
  const message = opsUpdateStatus && opsUpdateStatus.message ? opsUpdateStatus.message : '尚未检查更新。';
  const current = opsUpdateStatus && opsUpdateStatus.current_version ? '当前版本 ' + opsUpdateStatus.current_version : '';
  const latest = opsUpdateStatus && opsUpdateStatus.latest_version ? '最新版本 ' + opsUpdateStatus.latest_version : '';
  const checked = opsUpdateStatus && opsUpdateStatus.checked_at ? '检查时间 ' + String(opsUpdateStatus.checked_at).replace('T', ' ') : '';
  statusEl.textContent = message;
  statusEl.dataset.state = state || 'unknown';
  const meta = [current, latest, checked].filter(Boolean).join(' · ');
  if (meta) metaEl.textContent = meta;
}

function checkUpdateFromOps() {
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  requestUpdateCheck(true);
  setOpsStatus('正在检查更新...', true);
}

function openUpdateFromOps() {
  openUpdate();
}

function checkUpdate() {
  requestUpdateCheck(false);
}

function requestUpdateCheck(silent) {
  pendingUpdateInfo = null;
  document.getElementById('updateButton').classList.remove('update-ready');
  document.getElementById('installUpdateButton').disabled = true;
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  if (!silent) {
    document.getElementById('updateStatus').textContent = '正在检查更新...';
    document.getElementById('updateMeta').textContent = '';
    document.getElementById('updateNotes').style.display = 'none';
  }
  lastAutoUpdateCheckAt = Date.now();
  socket.emit('check_update');
}

function scheduleAutoUpdateCheck() {
  if (autoUpdateTimer) {
    clearTimeout(autoUpdateTimer);
    autoUpdateTimer = null;
  }
  const elapsed = Date.now() - lastAutoUpdateCheckAt;
  const delay = lastAutoUpdateCheckAt ? Math.max(autoUpdateIntervalMs() - elapsed, 60 * 1000) : 2000;
  autoUpdateTimer = setTimeout(() => {
    requestUpdateCheck(true);
    scheduleAutoUpdateCheck();
  }, delay);
}

function applyUpdateStatus(data) {
  renderOpsUpdateStatus(data);
  const statusEl = document.getElementById('updateStatus');
  const metaEl = document.getElementById('updateMeta');
  const notesEl = document.getElementById('updateNotes');
  const installBtn = document.getElementById('installUpdateButton');
  const updateBtn = document.getElementById('updateButton');
  const progressEl = document.getElementById('updateProgress');
  const progressBar = progressEl ? progressEl.querySelector('span') : null;

  const current = data.current_version ? '当前版本 ' + data.current_version : '';
  const latest = data.latest_version ? '最新版本 ' + data.latest_version : '';
  const checked = data.checked_at ? '检查时间 ' + String(data.checked_at).replace('T', ' ') : '';
  metaEl.textContent = [current, latest, checked].filter(Boolean).join(' · ');
  statusEl.textContent = data.message || '更新状态未知。';
  notesEl.textContent = data.notes || '';
  notesEl.style.display = data.notes ? 'block' : 'none';
  if (progressEl && progressBar) {
    const percent = data.progress_percent == null ? null : Math.max(0, Math.min(100, Number(data.progress_percent)));
    progressEl.classList.toggle('show', data.state === 'downloading' || data.state === 'installing');
    progressBar.style.width = Number.isFinite(percent) ? percent + '%' : '35%';
  }

  if (data.state === 'available') {
    pendingUpdateInfo = {
      version: data.latest_version,
      notes: data.notes || '',
    };
    installBtn.disabled = false;
    updateBtn.classList.add('update-ready');
    return;
  }

  if (data.state === 'downloading' || data.state === 'installing') {
    installBtn.disabled = true;
    updateBtn.classList.add('update-ready');
    return;
  }

  pendingUpdateInfo = null;
  installBtn.disabled = true;
  updateBtn.classList.remove('update-ready');
}

function installUpdate() {
  if (!pendingUpdateInfo) return;
  document.getElementById('installUpdateButton').disabled = true;
  document.getElementById('updateStatus').textContent = '正在准备更新...';
  socket.emit('install_update');
}
