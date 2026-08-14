import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_price_history_maintenance_frontend_preview_and_execute_flow():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行历史数据维护前端测试")

    state_source = (ROOT / "static" / "operations-state.js").read_text(
        encoding="utf-8"
    )
    maintenance_source = (
        ROOT / "static" / "operations-history-maintenance.js"
    ).read_text(encoding="utf-8")
    records_source = (
        ROOT / "static" / "operations-records.js"
    ).read_text(encoding="utf-8")
    script = """
const vm = require('vm');

function element() {
  return {
    textContent: '',
    innerHTML: '',
    hidden: false,
    disabled: false,
    dataset: {},
    style: {},
    attributes: {},
    setAttribute(name, value) { this.attributes[name] = String(value); },
  };
}

const ids = [
  'priceHistoryMaintenanceCard',
  'refreshPriceHistoryMaintenanceButton',
  'executePriceHistoryRepairButton',
  'previewPriceHistoryCleanupButton',
  'previewPriceHistoryRebuildButton',
  'previewPriceHistorySyncButton',
  'previewPriceHistoryRestoreButton',
  'priceHistoryMaintenanceStatus',
  'priceHistoryMaintenanceMeta',
  'priceHistoryMaintenanceMetrics',
  'priceHistoryMaintenanceCoverage',
  'priceHistoryMaintenanceIssues',
  'priceHistoryMaintenancePreview',
  'priceHistoryMaintenancePreviewTitle',
  'priceHistoryMaintenancePreviewSummary',
  'priceHistoryMaintenancePreviewEffects',
  'opsStatus',
];
const elements = Object.fromEntries(ids.map(id => [id, element()]));
const listeners = {};
const emits = [];
const socket = {
  on(name, handler) { listeners[name] = handler; },
  emit(name, payload) { emits.push({ name, payload }); },
};
const context = {
  console,
  document: { getElementById: id => elements[id] || null },
  socket,
  confirm: () => true,
  escapeHtml: value => String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;'),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__STATE_SOURCE__, context);
vm.runInContext(__RECORDS_SOURCE__, context);
vm.runInContext(__MAINTENANCE_SOURCE__, context);

const evaluate = expression => vm.runInContext(expression, context);
const assert = (condition, message) => { if (!condition) throw new Error(message); };

evaluate('registerPriceHistoryMaintenanceSocketHandlers(socket)');
assert(typeof listeners.price_history_maintenance_updated === 'function', 'diagnosis listener missing');
assert(typeof listeners.price_history_repair_previewed === 'function', 'preview listener missing');
assert(typeof listeners.price_history_repair_completed === 'function', 'completion listener missing');

const diagnosis = {
  status: 'attention',
  checked_at: '2026-08-13T12:00:00',
  database: {
    exists: true,
    integrity_ok: true,
    raw: {
      resolution: 'raw', interval_seconds: 10, retention_minutes: 1440,
      total: 14, valid: 12, invalid_timestamp: 1, missing_price: 1,
      first_timestamp: '2026-08-13T10:00:00', last_timestamp: '2026-08-13T12:00:00',
    },
    rollups: [
      {
        resolution: '1m', interval_seconds: 60, retention_minutes: 43200,
        total: 24, first_timestamp: '2026-08-01T10:00:00',
        last_timestamp: '2026-08-13T12:00:00', missing: 1, mismatched: 0,
        unexpected: 0,
      },
      {
        resolution: '5m', interval_seconds: 300, retention_minutes: 129600,
        total: 6, first_timestamp: '2026-08-01T10:00:00',
        last_timestamp: '2026-08-13T12:00:00', missing: 0, mismatched: 0,
        unexpected: 0,
      },
    ],
  },
  json_archive: { exists: true, unique_valid: 10 },
  repair_backup: {
    exists: true,
    available: true,
    action: 'clean_invalid_records',
    created_at: '2026-08-13T11:50:00',
    raw_rows: 14,
    rollup_rows: 30,
  },
  comparison: {
    missing_in_database: 2,
    rollup_missing: 1,
    rollup_mismatched: 1,
    rollup_unexpected: 0,
  },
  issues: ['发现汇总差异'],
  operations: {
    clean_invalid_records: { available: true },
    rebuild_rollups: { available: true },
    sync_json_and_rebuild: { available: true },
    restore_last_repair: { available: true },
  },
};
listeners.price_history_maintenance_updated(diagnosis);
assert(elements.priceHistoryMaintenanceStatus.textContent === '发现可处理问题', 'diagnosis status not rendered');
assert(elements.priceHistoryMaintenanceMetrics.innerHTML.includes('数据库明细'), 'diagnosis metrics not rendered');
assert(elements.priceHistoryMaintenanceCoverage.innerHTML.includes('原始明细'), 'raw coverage not rendered');
assert(elements.priceHistoryMaintenanceCoverage.innerHTML.includes('5 分钟汇总'), 'rollup coverage not rendered');
assert(elements.priceHistoryMaintenanceCoverage.innerHTML.includes('保留 90 天'), 'retention policy not rendered');
assert(elements.priceHistoryMaintenanceCoverage.innerHTML.includes('2 小时'), 'coverage duration not rendered');
assert(elements.priceHistoryMaintenanceCoverage.innerHTML.includes('1 项差异'), 'coverage issue state not rendered');
assert(elements.priceHistoryMaintenanceIssues.innerHTML.includes('发现汇总差异'), 'diagnosis issues not rendered');
assert(!elements.previewPriceHistoryCleanupButton.disabled, 'available cleanup action must be enabled');
assert(!elements.previewPriceHistoryRebuildButton.disabled, 'available rebuild action must be enabled');
assert(!elements.previewPriceHistorySyncButton.disabled, 'available sync action must be enabled');
assert(!elements.previewPriceHistoryRestoreButton.disabled, 'available restore action must be enabled');

evaluate("previewPriceHistoryRepair('restore_last_repair')");
assert(emits.at(-1).name === 'preview_price_history_repair', 'restore preview event not emitted');
assert(emits.at(-1).payload.action === 'restore_last_repair', 'restore preview action mismatch');
listeners.price_history_repair_previewed({
  executable: true,
  action: 'restore_last_repair',
  preview_token: 'preview-restore',
  summary: '恢复最近一次修复前的数据',
  effects: {
    backup_action: 'clean_invalid_records',
    backup_created_at: '2026-08-13T11:50:00',
    raw_rows_to_restore: 14,
    rollup_rows_to_restore: 30,
  },
  diagnosis,
});
assert(elements.priceHistoryMaintenancePreviewTitle.textContent === '恢复最近修复', 'restore preview title mismatch');
assert(elements.priceHistoryMaintenancePreviewEffects.innerHTML.includes('还原数据库明细'), 'restore effects missing');
assert(evaluate("recentOpsTypeLabel('price_history_repair', { action: 'restore_last_repair' })") === '恢复历史修复', 'restore record label mismatch');
evaluate('clearPriceHistoryRepairPreview()');

evaluate("previewPriceHistoryRepair('clean_invalid_records')");
assert(emits.at(-1).name === 'preview_price_history_repair', 'cleanup preview event not emitted');
assert(emits.at(-1).payload.action === 'clean_invalid_records', 'cleanup preview action mismatch');

listeners.price_history_repair_previewed({
  executable: true,
  action: 'clean_invalid_records',
  preview_token: 'preview-cleanup',
  summary: '清理 2 条无效明细',
  effects: {
    invalid_timestamp_rows_to_remove: 1,
    missing_price_rows_to_remove: 1,
    raw_rows_preserved: 12,
    unknown_rollups_preserved: 1,
    rollup_buckets_to_remove: 0,
    rollup_buckets_to_rebuild: 8,
  },
  diagnosis,
});
assert(elements.priceHistoryMaintenancePreviewTitle.textContent === '清理无效明细', 'cleanup preview title mismatch');
assert(elements.priceHistoryMaintenancePreviewEffects.innerHTML.includes('移除无效时间'), 'cleanup effects missing');
assert(elements.priceHistoryMaintenancePreviewEffects.innerHTML.includes('保留未知粒度'), 'cleanup preservation missing');

evaluate("previewPriceHistoryRepair('sync_json_and_rebuild')");
assert(emits.at(-1).name === 'preview_price_history_repair', 'preview event not emitted');
assert(emits.at(-1).payload.action === 'sync_json_and_rebuild', 'preview action mismatch');

listeners.price_history_repair_previewed({
  executable: true,
  action: 'sync_json_and_rebuild',
  preview_token: 'preview-1',
  summary: '补充 2 个时间点',
  effects: {
    json_points_eligible: 3,
    json_points_to_add: 2,
    json_fields_to_supplement: 1,
    invalid_json_ignored: 1,
    conflicts_preserved: 1,
    rollup_buckets_to_remove: 2,
    rollup_buckets_to_rebuild: 8,
  },
  diagnosis,
});
assert(!elements.priceHistoryMaintenancePreview.hidden, 'preview must become visible');
assert(elements.priceHistoryMaintenancePreviewTitle.textContent === '同步 JSON 并重建', 'preview title mismatch');
assert(elements.priceHistoryMaintenancePreviewEffects.innerHTML.includes('新增时间点'), 'preview effects missing');
assert(elements.priceHistoryMaintenancePreviewEffects.innerHTML.includes('清理多余汇总'), 'cleanup effect missing');
assert(!elements.executePriceHistoryRepairButton.disabled, 'executable preview must enable confirmation');

evaluate('executePriceHistoryRepair()');
assert(emits.at(-1).name === 'execute_price_history_repair', 'execute event not emitted');
assert(emits.at(-1).payload.confirmed === true, 'execute event must include confirmation');
assert(emits.at(-1).payload.preview_token === 'preview-1', 'execute event must include preview token');
assert(evaluate('priceHistoryMaintenanceRequestType') === 'execute', 'execute request type missing');

listeners.price_history_maintenance_error({ message: '修复影响范围已变化，请重新预览' });
assert(elements.priceHistoryMaintenancePreview.hidden, 'failed execution must close stale preview');
const failedRecord = evaluate('recentOpsRecords[0]');
assert(failedRecord.type === 'price_history_repair', 'failed repair record missing');
assert(failedRecord.ok === false, 'failed repair record state mismatch');
assert(failedRecord.label === '同步历史 JSON', 'failed repair label mismatch');
assert(emits.at(-1).name === 'get_price_history_maintenance', 'failure must refresh diagnosis');
assert(evaluate('priceHistoryMaintenancePending') === true, 'failure diagnosis refresh must stay pending');
assert(evaluate('priceHistoryMaintenanceRequestType') === 'diagnose', 'failure diagnosis request type missing');

listeners.price_history_maintenance_updated(diagnosis);
assert(evaluate('priceHistoryMaintenancePending') === false, 'diagnosis refresh must clear pending state');
assert(elements.executePriceHistoryRepairButton.disabled, 'stale execute button must stay disabled');

listeners.price_history_repair_previewed({
  executable: true,
  action: 'sync_json_and_rebuild',
  preview_token: 'preview-2',
  summary: '补充 2 个时间点',
  effects: {
    json_points_eligible: 3,
    json_points_to_add: 2,
    json_fields_to_supplement: 1,
    invalid_json_ignored: 1,
    conflicts_preserved: 1,
    rollup_buckets_to_remove: 2,
    rollup_buckets_to_rebuild: 8,
  },
  diagnosis,
});
evaluate('executePriceHistoryRepair()');

listeners.price_history_repair_completed({
  ok: true,
  action: 'sync_json_and_rebuild',
  message: '修复完成',
  diagnosis: { ...diagnosis, status: 'healthy', issues: [] },
});
assert(emits.at(-1).name === 'get_price_history', 'completion must refresh history view');
assert(elements.priceHistoryMaintenancePreview.hidden, 'completion must close preview');
assert(elements.opsStatus.textContent === '修复完成', 'completion message missing');
const successfulRecord = evaluate('recentOpsRecords[0]');
assert(successfulRecord.type === 'price_history_repair', 'successful repair record missing');
assert(successfulRecord.ok === true, 'successful repair record state mismatch');
assert(successfulRecord.label === '同步历史 JSON', 'successful repair label mismatch');
"""
    script = script.replace(
        "__STATE_SOURCE__", json.dumps(state_source)
    ).replace(
        "__RECORDS_SOURCE__", json.dumps(records_source)
    ).replace(
        "__MAINTENANCE_SOURCE__", json.dumps(maintenance_source)
    )

    with tempfile.TemporaryDirectory(
        prefix="goldmonitor-price-history-frontend-"
    ) as temp_dir:
        script_path = Path(temp_dir) / "maintenance-flow.js"
        script_path.write_text(script, encoding="utf-8")
        result = subprocess.run(
            [node, str(script_path)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    assert result.returncode == 0, result.stderr
