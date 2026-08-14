const PRICE_HISTORY_REPAIR_LABELS = {
  clean_invalid_records: '清理无效明细',
  rebuild_rollups: '重建汇总数据',
  sync_json_and_rebuild: '同步 JSON 并重建',
  restore_last_repair: '恢复最近修复',
};
const PRICE_HISTORY_RESOLUTION_LABELS = {
  raw: '原始明细',
  '1m': '1 分钟汇总',
  '5m': '5 分钟汇总',
  '1h': '1 小时汇总',
  '1d': '日线汇总',
};

function formatPriceHistoryCount(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number.toLocaleString('zh-CN') : '0';
}

function formatPriceHistoryTime(value) {
  const text = String(value || '').trim();
  return text ? text.replace('T', ' ') : '无数据';
}

function formatPriceHistoryInterval(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value) || value <= 0) return '采样间隔未知';
  if (value % 86400 === 0) return (value / 86400) + ' 天间隔';
  if (value % 3600 === 0) return (value / 3600) + ' 小时间隔';
  if (value % 60 === 0) return (value / 60) + ' 分钟间隔';
  return value + ' 秒间隔';
}

function formatPriceHistoryRetention(minutes) {
  if (minutes === null || minutes === undefined) return '长期保留';
  const value = Number(minutes);
  if (!Number.isFinite(value) || value <= 0) return '不限制保留期';
  if (value % (365 * 24 * 60) === 0) {
    return '保留 ' + (value / (365 * 24 * 60)) + ' 年';
  }
  if (value % (24 * 60) === 0) return '保留 ' + (value / (24 * 60)) + ' 天';
  if (value % 60 === 0) return '保留 ' + (value / 60) + ' 小时';
  return '保留 ' + value + ' 分钟';
}

function formatPriceHistoryCoverageDuration(firstTimestamp, lastTimestamp) {
  const first = Date.parse(String(firstTimestamp || ''));
  const last = Date.parse(String(lastTimestamp || ''));
  if (!Number.isFinite(first) || !Number.isFinite(last)) return '覆盖时长未知';
  const minutes = Math.max(0, Math.round((last - first) / 60000));
  if (minutes === 0) return '单个时间点';
  if (minutes >= 365 * 24 * 60) {
    return '覆盖 ' + (minutes / (365 * 24 * 60)).toFixed(1).replace('.0', '') + ' 年';
  }
  if (minutes >= 24 * 60) {
    return '覆盖 ' + (minutes / (24 * 60)).toFixed(1).replace('.0', '') + ' 天';
  }
  if (minutes >= 60) {
    return '覆盖 ' + (minutes / 60).toFixed(1).replace('.0', '') + ' 小时';
  }
  return '覆盖 ' + minutes + ' 分钟';
}

function priceHistoryCoverageState(item) {
  const total = Number(item && item.total || 0);
  if (!total) return { state: 'empty', label: '暂无数据' };
  const issues = item && item.resolution === 'raw'
    ? Number(item.invalid_timestamp || 0) + Number(item.missing_price || 0)
    : Number(item && item.missing || 0)
      + Number(item && item.mismatched || 0)
      + Number(item && item.unexpected || 0);
  return issues
    ? { state: 'attention', label: formatPriceHistoryCount(issues) + ' 项差异' }
    : { state: 'healthy', label: '状态正常' };
}

function renderPriceHistoryCoverage(database) {
  const container = document.getElementById('priceHistoryMaintenanceCoverage');
  if (!container) return;
  const raw = database && database.raw || {};
  const rollups = database && Array.isArray(database.rollups) ? database.rollups : [];
  const items = [raw, ...rollups].filter(item => item && item.resolution);
  if (!items.length) {
    container.innerHTML = '<div class="price-maintenance-empty">暂无分层覆盖数据。</div>';
    return;
  }
  container.innerHTML = items.map(item => {
    const state = priceHistoryCoverageState(item);
    const hasRange = item.first_timestamp && item.last_timestamp;
    const range = hasRange
      ? formatPriceHistoryTime(item.first_timestamp) + ' 至 '
        + formatPriceHistoryTime(item.last_timestamp)
      : '尚无可显示的数据区间';
    const duration = hasRange
      ? formatPriceHistoryCoverageDuration(item.first_timestamp, item.last_timestamp)
      : '等待数据写入';
    return [
      '<div class="price-maintenance-coverage-row" data-state="' + state.state + '">',
      '<div class="price-maintenance-coverage-ident"><strong>'
        + escapeHtml(PRICE_HISTORY_RESOLUTION_LABELS[item.resolution] || item.resolution)
        + '</strong><span>' + escapeHtml(formatPriceHistoryInterval(item.interval_seconds))
        + ' · ' + escapeHtml(formatPriceHistoryRetention(item.retention_minutes)) + '</span></div>',
      '<div class="price-maintenance-coverage-count"><strong>'
        + escapeHtml(formatPriceHistoryCount(item.total)) + '</strong><span>条记录</span></div>',
      '<div class="price-maintenance-coverage-detail"><span>' + escapeHtml(range)
        + '</span><small>' + escapeHtml(duration) + ' · ' + escapeHtml(state.label)
        + '</small></div>',
      '</div>',
    ].join('');
  }).join('');
}

function setPriceHistoryMaintenanceBusy(pending) {
  priceHistoryMaintenancePending = !!pending;
  const card = document.getElementById('priceHistoryMaintenanceCard');
  const refresh = document.getElementById('refreshPriceHistoryMaintenanceButton');
  const execute = document.getElementById('executePriceHistoryRepairButton');
  if (card) card.setAttribute('aria-busy', String(priceHistoryMaintenancePending));
  if (refresh) {
    refresh.disabled = priceHistoryMaintenancePending;
    refresh.textContent = priceHistoryMaintenancePending ? '正在检查' : '检查数据';
  }
  if (execute) {
    execute.disabled = priceHistoryMaintenancePending
      || !pendingPriceHistoryMaintenancePreview;
  }
  updatePriceHistoryMaintenanceActions();
}

function priceHistoryMaintenanceStatusLabel(status) {
  if (status === 'healthy') return '数据状态正常';
  if (status === 'attention') return '发现可处理问题';
  if (status === 'unavailable') return '数据库暂不可维护';
  if (status === 'empty') return '尚无历史数据';
  return '等待诊断';
}

function updatePriceHistoryMaintenanceActions() {
  const operations = priceHistoryMaintenanceState && priceHistoryMaintenanceState.operations || {};
  const cleanup = document.getElementById('previewPriceHistoryCleanupButton');
  const rebuild = document.getElementById('previewPriceHistoryRebuildButton');
  const sync = document.getElementById('previewPriceHistorySyncButton');
  const restore = document.getElementById('previewPriceHistoryRestoreButton');
  if (cleanup) {
    cleanup.disabled = priceHistoryMaintenancePending
      || !(operations.clean_invalid_records && operations.clean_invalid_records.available);
  }
  if (rebuild) {
    rebuild.disabled = priceHistoryMaintenancePending
      || !(operations.rebuild_rollups && operations.rebuild_rollups.available);
  }
  if (sync) {
    sync.disabled = priceHistoryMaintenancePending
      || !(operations.sync_json_and_rebuild && operations.sync_json_and_rebuild.available);
  }
  if (restore) {
    restore.disabled = priceHistoryMaintenancePending
      || !(operations.restore_last_repair && operations.restore_last_repair.available);
  }
}

function renderPriceHistoryMaintenance(data) {
  priceHistoryMaintenanceState = data && typeof data === 'object' ? data : null;
  const status = document.getElementById('priceHistoryMaintenanceStatus');
  const meta = document.getElementById('priceHistoryMaintenanceMeta');
  const metrics = document.getElementById('priceHistoryMaintenanceMetrics');
  const issues = document.getElementById('priceHistoryMaintenanceIssues');
  if (!status || !meta || !metrics || !issues || !priceHistoryMaintenanceState) return;

  const database = priceHistoryMaintenanceState.database || {};
  const raw = database.raw || {};
  const jsonArchive = priceHistoryMaintenanceState.json_archive || {};
  const comparison = priceHistoryMaintenanceState.comparison || {};
  const state = String(priceHistoryMaintenanceState.status || 'empty');
  status.textContent = priceHistoryMaintenanceStatusLabel(state);
  status.dataset.state = state;
  meta.textContent = database.exists
    ? '检查时间 ' + formatPriceHistoryTime(priceHistoryMaintenanceState.checked_at)
      + '；数据库完整性' + (database.integrity_ok ? '通过' : '未通过')
    : 'SQLite 尚未创建；JSON 归档' + (jsonArchive.exists ? '可检查' : '也不存在');

  const rollups = Array.isArray(database.rollups) ? database.rollups : [];
  const rollupTotal = rollups.reduce((total, item) => total + Number(item.total || 0), 0);
  const metricItems = [
    ['数据库明细', formatPriceHistoryCount(raw.total)],
    ['有效明细', formatPriceHistoryCount(raw.valid)],
    ['汇总记录', formatPriceHistoryCount(rollupTotal)],
    ['JSON 有效点', formatPriceHistoryCount(jsonArchive.unique_valid)],
    ['可补时间点', formatPriceHistoryCount(comparison.missing_in_database)],
    ['汇总差异', formatPriceHistoryCount(
      Number(comparison.rollup_missing || 0)
      + Number(comparison.rollup_mismatched || 0)
      + Number(comparison.rollup_unexpected || 0)
    )],
  ];
  metrics.innerHTML = metricItems.map(item => (
    '<div class="price-maintenance-metric"><span>' + escapeHtml(item[0])
      + '</span><strong>' + escapeHtml(item[1]) + '</strong></div>'
  )).join('');
  renderPriceHistoryCoverage(database);

  const issueItems = Array.isArray(priceHistoryMaintenanceState.issues)
    ? priceHistoryMaintenanceState.issues : [];
  if (!issueItems.length) {
    issues.innerHTML = '<div class="price-maintenance-ok">未发现需要处理的数据差异。</div>';
  } else {
    issues.innerHTML = '<div class="price-maintenance-issue-title">需要关注</div><ul>'
      + issueItems.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ul>';
  }
  setPriceHistoryMaintenanceBusy(false);
}

function refreshPriceHistoryMaintenance() {
  if (priceHistoryMaintenancePending) return;
  clearPriceHistoryRepairPreview();
  priceHistoryMaintenanceRequestType = 'diagnose';
  setPriceHistoryMaintenanceBusy(true);
  setOpsStatus('正在检查历史数据...', true);
  socket.emit('get_price_history_maintenance');
}

function previewPriceHistoryRepair(action) {
  if (priceHistoryMaintenancePending || !PRICE_HISTORY_REPAIR_LABELS[action]) return;
  pendingPriceHistoryMaintenancePreview = null;
  priceHistoryMaintenanceRequestType = 'preview';
  setPriceHistoryMaintenanceBusy(true);
  setOpsStatus('正在生成历史数据修复预览...', true);
  socket.emit('preview_price_history_repair', { action });
}

function priceHistoryRepairEffectItems(preview) {
  const effects = preview && preview.effects || {};
  if (preview.action === 'restore_last_repair') {
    return [
      ['恢复点时间', formatPriceHistoryTime(effects.backup_created_at)],
      ['恢复前操作', PRICE_HISTORY_REPAIR_LABELS[effects.backup_action] || '历史数据修复'],
      ['还原数据库明细', formatPriceHistoryCount(effects.raw_rows_to_restore)],
      ['还原汇总记录', formatPriceHistoryCount(effects.rollup_rows_to_restore)],
    ];
  }
  if (preview.action === 'clean_invalid_records') {
    return [
      ['移除无效时间', formatPriceHistoryCount(effects.invalid_timestamp_rows_to_remove)],
      ['移除缺价记录', formatPriceHistoryCount(effects.missing_price_rows_to_remove)],
      ['保留有效明细', formatPriceHistoryCount(effects.raw_rows_preserved)],
      ['保留未知粒度', formatPriceHistoryCount(effects.unknown_rollups_preserved)],
      ['清理多余汇总', formatPriceHistoryCount(effects.rollup_buckets_to_remove)],
      ['重建汇总桶', formatPriceHistoryCount(effects.rollup_buckets_to_rebuild)],
    ];
  }
  if (preview.action === 'sync_json_and_rebuild') {
    return [
      ['可同步 JSON 点', formatPriceHistoryCount(effects.json_points_eligible)],
      ['新增时间点', formatPriceHistoryCount(effects.json_points_to_add)],
      ['补充空缺字段', formatPriceHistoryCount(effects.json_fields_to_supplement)],
      ['忽略无效记录', formatPriceHistoryCount(effects.invalid_json_ignored)],
      ['保留冲突值', formatPriceHistoryCount(effects.conflicts_preserved)],
      ['清理多余汇总', formatPriceHistoryCount(effects.rollup_buckets_to_remove)],
      ['重建汇总桶', formatPriceHistoryCount(effects.rollup_buckets_to_rebuild)],
    ];
  }
  return [
    ['保留数据库明细', formatPriceHistoryCount(effects.raw_rows_unchanged)],
    ['清理多余汇总', formatPriceHistoryCount(effects.rollup_buckets_to_remove)],
    ['重建汇总桶', formatPriceHistoryCount(effects.rollup_buckets_to_rebuild)],
    ['开始时间', formatPriceHistoryTime(effects.first_timestamp)],
    ['结束时间', formatPriceHistoryTime(effects.last_timestamp)],
  ];
}

function renderPriceHistoryRepairPreview(preview) {
  const container = document.getElementById('priceHistoryMaintenancePreview');
  const title = document.getElementById('priceHistoryMaintenancePreviewTitle');
  const summary = document.getElementById('priceHistoryMaintenancePreviewSummary');
  const effects = document.getElementById('priceHistoryMaintenancePreviewEffects');
  const execute = document.getElementById('executePriceHistoryRepairButton');
  if (!container || !title || !summary || !effects || !execute) return;
  pendingPriceHistoryMaintenancePreview = preview && preview.executable ? preview : null;
  title.textContent = PRICE_HISTORY_REPAIR_LABELS[preview.action] || '修复预览';
  summary.textContent = preview.summary || preview.message || '无法生成修复预览。';
  effects.innerHTML = priceHistoryRepairEffectItems(preview).map(item => (
    '<div><span>' + escapeHtml(item[0]) + '</span><strong>'
      + escapeHtml(item[1]) + '</strong></div>'
  )).join('');
  execute.hidden = !pendingPriceHistoryMaintenancePreview;
  execute.disabled = !pendingPriceHistoryMaintenancePreview;
  container.hidden = false;
  container.dataset.state = pendingPriceHistoryMaintenancePreview ? 'ready' : 'blocked';
}

function clearPriceHistoryRepairPreview() {
  pendingPriceHistoryMaintenancePreview = null;
  const container = document.getElementById('priceHistoryMaintenancePreview');
  const execute = document.getElementById('executePriceHistoryRepairButton');
  if (container) container.hidden = true;
  if (execute) {
    execute.hidden = true;
    execute.disabled = true;
  }
}

function executePriceHistoryRepair() {
  const preview = pendingPriceHistoryMaintenancePreview;
  if (!preview || !preview.executable || priceHistoryMaintenancePending) return;
  const label = PRICE_HISTORY_REPAIR_LABELS[preview.action] || '历史数据修复';
  if (!confirm('确定执行“' + label + '”吗？\n\n' + preview.summary)) return;
  priceHistoryMaintenanceRequestType = 'execute';
  setPriceHistoryMaintenanceBusy(true);
  setOpsStatus('正在执行历史数据修复...', true);
  socket.emit('execute_price_history_repair', {
    action: preview.action,
    confirmed: true,
    preview_token: preview.preview_token,
  });
}

function registerPriceHistoryMaintenanceSocketHandlers(socket) {
  socket.on('price_history_maintenance_updated', data => {
    if (priceHistoryMaintenanceRequestType === 'diagnose') {
      priceHistoryMaintenanceRequestType = '';
    }
    renderPriceHistoryMaintenance(data || {});
  });

  socket.on('price_history_repair_previewed', data => {
    priceHistoryMaintenanceRequestType = '';
    setPriceHistoryMaintenanceBusy(false);
    if (data && data.diagnosis) renderPriceHistoryMaintenance(data.diagnosis);
    renderPriceHistoryRepairPreview(data || {});
    setOpsStatus(
      data && data.executable ? '修复预览已生成，请确认影响范围。' : (data && data.message) || '当前操作不可执行。',
      !!(data && data.executable)
    );
  });

  socket.on('price_history_repair_completed', data => {
    const preview = pendingPriceHistoryMaintenancePreview;
    priceHistoryMaintenanceRequestType = '';
    clearPriceHistoryRepairPreview();
    setPriceHistoryMaintenanceBusy(false);
    if (data && data.diagnosis) renderPriceHistoryMaintenance(data.diagnosis);
    addRecentOpsRecord('price_history_repair', {
      ...(data || {}),
      action: data && data.action || preview && preview.action || '',
    });
    setOpsStatus(data && data.message ? data.message : '历史数据修复完成。', !!(data && data.ok));
    socket.emit('get_price_history', { limit: 600, scope: 'history' });
  });

  socket.on('price_history_maintenance_error', data => {
    const requestType = priceHistoryMaintenanceRequestType;
    const preview = pendingPriceHistoryMaintenancePreview;
    priceHistoryMaintenanceRequestType = '';
    let refreshDiagnosis = false;
    if (requestType === 'execute') {
      clearPriceHistoryRepairPreview();
      addRecentOpsRecord('price_history_repair', {
        ...(data || {}),
        ok: false,
        action: preview && preview.action || '',
      });
      priceHistoryMaintenanceRequestType = 'diagnose';
      refreshDiagnosis = true;
    }
    setPriceHistoryMaintenanceBusy(refreshDiagnosis);
    setOpsStatus(data && data.message ? data.message : '历史数据维护失败。', false);
    if (refreshDiagnosis) socket.emit('get_price_history_maintenance');
  });
}
