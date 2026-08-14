import json
import shutil
import subprocess
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
    script = """
const vm = require('vm');

function element() {
  return {
    textContent: '',
    innerHTML: '',
    hidden: false,
    disabled: false,
    dataset: {},
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
  'priceHistoryMaintenanceStatus',
  'priceHistoryMaintenanceMeta',
  'priceHistoryMaintenanceMetrics',
  'priceHistoryMaintenanceIssues',
  'priceHistoryMaintenancePreview',
  'priceHistoryMaintenancePreviewTitle',
  'priceHistoryMaintenancePreviewSummary',
  'priceHistoryMaintenancePreviewEffects',
];
const elements = Object.fromEntries(ids.map(id => [id, element()]));
const listeners = {};
const emits = [];
const statuses = [];
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
  setOpsStatus: (message, ok) => statuses.push({ message, ok }),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__STATE_SOURCE__, context);
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
    raw: { total: 14, valid: 12, invalid_timestamp: 1, missing_price: 1 },
    rollups: [{ total: 24 }, { total: 6 }],
  },
  json_archive: { exists: true, unique_valid: 10 },
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
  },
};
listeners.price_history_maintenance_updated(diagnosis);
assert(elements.priceHistoryMaintenanceStatus.textContent === '发现可处理问题', 'diagnosis status not rendered');
assert(elements.priceHistoryMaintenanceMetrics.innerHTML.includes('数据库明细'), 'diagnosis metrics not rendered');
assert(elements.priceHistoryMaintenanceIssues.innerHTML.includes('发现汇总差异'), 'diagnosis issues not rendered');
assert(!elements.previewPriceHistoryCleanupButton.disabled, 'available cleanup action must be enabled');
assert(!elements.previewPriceHistoryRebuildButton.disabled, 'available rebuild action must be enabled');
assert(!elements.previewPriceHistorySyncButton.disabled, 'available sync action must be enabled');

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

listeners.price_history_repair_completed({
  ok: true,
  message: '修复完成',
  diagnosis: { ...diagnosis, status: 'healthy', issues: [] },
});
assert(emits.at(-1).name === 'get_price_history', 'completion must refresh history view');
assert(elements.priceHistoryMaintenancePreview.hidden, 'completion must close preview');
assert(statuses.at(-1).message === '修复完成', 'completion message missing');
"""
    script = script.replace(
        "__STATE_SOURCE__", json.dumps(state_source)
    ).replace(
        "__MAINTENANCE_SOURCE__", json.dumps(maintenance_source)
    )

    result = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
