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
let backgroundTaskStatus = null;
const AUTO_UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
function autoUpdateIntervalMs() {
  return AUTO_UPDATE_CHECK_INTERVAL_MS;
}
let latestSourceHealthState = { items: [], summary: {} };
let latestSourceComparisonState = { items: [], summary: {}, status: 'insufficient' };
