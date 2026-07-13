from pathlib import Path
import re


root = Path(__file__).resolve().parents[1]
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
app_py = (root / "app.py").read_text(encoding="utf-8")
css_path = root / "static" / "app.css"
js_path = root / "static" / "app.js"


if not css_path.exists():
    raise SystemExit("frontend styles must live in static/app.css")

if not js_path.exists():
    raise SystemExit("frontend main script must live in static/app.js")

if '<link rel="stylesheet" href="/static/app.css">' not in template:
    raise SystemExit("template must reference /static/app.css")

if '<meta name="goldmonitor-socket-token" content="{{ socket_access_token }}">' not in template:
    raise SystemExit("template must expose the socket token through a meta tag")

if '<script src="/static/app-shell.js?v={{ app_version }}"></script>' not in template:
    raise SystemExit("template must reference versioned /static/app-shell.js")

if '<script src="/static/app.js?v={{ app_version }}"></script>' not in template:
    raise SystemExit("template must reference versioned /static/app.js")

if "render_template(\"index.html\", socket_access_token=SOCKET_ACCESS_TOKEN, app_version=APP_VERSION)" not in app_py:
    raise SystemExit("app.py must inject app_version into index.html")

if 'id="chartEmptyState"' not in template:
    raise SystemExit("template must expose chart empty state overlay")

for required in ('id="riskEvidence"', 'id="riskDiagnostic"'):
    if required not in template:
        raise SystemExit(f"template must expose risk diagnostic/evidence element: {required}")

for required in (
    'id="portfolioStatus"',
    'id="portfolioViewTabs"',
    'id="portfolioToolsMenu"',
    'onclick="togglePortfolioToolsMenu()"',
    'class="btn-clear-sm btn-risk-sm source-risk-action"',
    'onclick="openRiskAnalysis()"',
    'id="portfolioSummary"',
    'id="portfolioList"',
    'onclick="setPortfolioView(\'positions\')"',
    'onclick="setPortfolioView(\'transactions\')"',
    'onclick="setPortfolioView(\'review\')"',
    'onclick="setActivePortfolioTransaction(\'new\')"',
    'onclick="exportPortfolio(\'positions\')"',
    'onclick="exportPortfolio(\'transactions\')"',
    'onclick="exportPortfolio(\'review\')"',
    'onclick="downloadPortfolioTransactionTemplate()"',
    'onclick="importPortfolioTransactions()"',
    'id="portfolioImportFile"',
    'id="portfolioImportPreview"',
    'id="portfolioImportBackup"',
):
    if required not in template:
        raise SystemExit(f"template missing portfolio anchor: {required}")

threshold_pos = template.find("threshold-card")
portfolio_pos = template.find("portfolio-card")
log_pos = template.find("log-card")
if not (threshold_pos < portfolio_pos < log_pos):
    raise SystemExit("template portfolio-card must appear after threshold-card and before log-card")

if re.search(r"<style\b", template, flags=re.IGNORECASE):
    raise SystemExit("template must not contain inline style blocks")

inline_scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", template, flags=re.IGNORECASE)
if inline_scripts:
    raise SystemExit("template must not contain inline script blocks")

css = css_path.read_text(encoding="utf-8")
js = js_path.read_text(encoding="utf-8")

for required in (
    'id="floatingTopmostRow"',
    'id="setFloatingAlwaysOnTop"',
    'floating_price_always_on_top',
):
    if required not in template + js:
        raise SystemExit(f"frontend missing floating topmost setting: {required}")

for required in (
    "HWND_NOTOPMOST",
    "floating_window_z_order(get_settings_snapshot())",
    "WS_EX_NOACTIVATE",
):
    if required not in app_py:
        raise SystemExit(f"app.py missing floating z-order contract: {required}")

if "{{" in css or "{{" in js:
    raise SystemExit("static frontend assets must not contain template expressions")

for required in (":root", ".container", ".settings-modal", ".price-card"):
    if required not in css:
        raise SystemExit(f"static/app.css missing expected selector: {required}")

for required in (
    "input[type=\"number\"]",
    "appearance:textfield",
    "-moz-appearance:textfield",
    "input[type=\"number\"]::-webkit-outer-spin-button",
    "input[type=\"number\"]::-webkit-inner-spin-button",
    "-webkit-appearance:none",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing global number input spinner contract: {required}")

for required in (
    'id="chooseExportDirButton"',
    'onclick="chooseExportDir()"',
    "function chooseExportDir",
    "window.pywebview.api.choose_export_dir",
    "保存后生效",
    "function renderExportDirStatus",
    "export_dir_check",
    "useDefaultExportDirFromError",
    "choose_export_dir",
    "use_default_export_dir",
    "open_export_dir",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing native export directory picker contract: {required}")

for required in (
    "function setOpsExportStatus",
    "openExportsFolder()",
    "data.error_detail",
    "data.export_dir_check",
    "打开目录",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing export diagnostics loop contract: {required}")

exports_folder_handler = "socket.on('exports_folder_opened', data => {"
exports_folder_pos = js.find(exports_folder_handler)
exports_folder_status_pos = js.find("setOpsExportStatus(data, '已打开导出目录'", exports_folder_pos)
if not (exports_folder_pos >= 0 and exports_folder_status_pos > exports_folder_pos):
    raise SystemExit("exports folder failures must reuse export diagnostics status rendering")

for required in (
    "最近操作记录",
    "id=\"recentOpsList\"",
    "RECENT_OPS_LIMIT",
    "function addRecentOpsRecord",
    "function renderRecentOpsRecords",
    "config_export",
    "diagnostics_export",
    "open_exports_folder",
    "payload.export_dir",
    "文件已保存到导出目录。",
    "失败原因",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing recent operations contract: {required}")

config_backup_pos = js.find("socket.on('config_backup_ready', data => {")
config_record_pos = js.find("addRecentOpsRecord('config_export'", config_backup_pos)
diagnostics_ready_pos = js.find("socket.on('diagnostics_ready', data => {")
diagnostics_record_pos = js.find("addRecentOpsRecord('diagnostics_export'", diagnostics_ready_pos)
open_folder_record_pos = js.find("addRecentOpsRecord('open_exports_folder'", exports_folder_pos)
if not (config_backup_pos >= 0 and config_record_pos > config_backup_pos):
    raise SystemExit("config export results must be recorded in recent operations")
if not (diagnostics_ready_pos >= 0 and diagnostics_record_pos > diagnostics_ready_pos):
    raise SystemExit("diagnostics export results must be recorded in recent operations")
if not (exports_folder_pos >= 0 and open_folder_record_pos > exports_folder_pos):
    raise SystemExit("open export folder results must be recorded in recent operations")

settings_updated_handler = "socket.on('settings_updated', data => {"
settings_updated_pos = js.find(settings_updated_handler)
settings_failed_pos = js.find("if (settingsSaveFailed)", settings_updated_pos)
apply_settings_pos = js.find("applySettings(data || {})", settings_updated_pos)
if not (settings_updated_pos >= 0 and settings_failed_pos >= 0 and apply_settings_pos >= 0 and settings_failed_pos < apply_settings_pos):
    raise SystemExit("settings_updated must preserve visible settings_error state before repainting the form")

reset_export_dir_pos = js.find("function resetExportDirField()")
reset_export_dir_clear_pos = js.find("clearSettingsMessage();", reset_export_dir_pos)
reset_export_dir_status_pos = js.find("renderExportDirStatus(null", reset_export_dir_pos)
if not (
    reset_export_dir_pos >= 0
    and reset_export_dir_clear_pos >= 0
    and reset_export_dir_status_pos >= 0
    and reset_export_dir_clear_pos < reset_export_dir_status_pos
):
    raise SystemExit("resetExportDirField must clear stale settings_error text before showing default export directory recovery")

choose_export_dir_pos = js.find("function chooseExportDir()")
choose_export_dir_clear_pos = js.find("clearSettingsMessage();", choose_export_dir_pos)
choose_export_dir_picker_pos = js.find("if (typeof picker !== 'function')", choose_export_dir_pos)
if not (
    choose_export_dir_pos >= 0
    and choose_export_dir_clear_pos >= 0
    and choose_export_dir_picker_pos >= 0
    and choose_export_dir_clear_pos < choose_export_dir_picker_pos
):
    raise SystemExit("chooseExportDir must clear stale settings_error text before showing picker or manual-input recovery")

for required in (
    ".portfolio-card",
    ".portfolio-head h3",
    ".portfolio-tools-more",
    ".portfolio-tools-menu",
    ".portfolio-tabs",
    ".portfolio-controls",
    ".portfolio-search",
    ".portfolio-filter",
    ".portfolio-sort",
    ".portfolio-select-control",
    ".portfolio-select-trigger",
    ".portfolio-select-menu",
    ".portfolio-select-option",
    ".portfolio-summary",
    ".portfolio-item",
    ".portfolio-editor",
    ".portfolio-transaction-type",
    ".portfolio-review",
    ".portfolio-review-curve",
    ".portfolio-curve-svg",
    ".portfolio-review-card",
    ".portfolio-review-track",
    ".portfolio-import-preview",
    ".portfolio-import-preview-head",
    ".portfolio-import-preview-grid",
    ".portfolio-import-preview-table",
    ".portfolio-import-error",
    ".portfolio-import-actions",
    ".portfolio-import-backup",
    ".portfolio-import-backup-head",
    ".portfolio-detail",
    ".portfolio-detail-focus",
    ".portfolio-detail-focus-main",
    ".portfolio-detail-focus-value",
    ".portfolio-detail-grid",
    ".portfolio-detail-transactions",
    ".portfolio-detail-transactions-head",
    ".portfolio-detail-transactions-list",
    ".portfolio-alert-summary",
    ".portfolio-alert-summary-actions",
    ".portfolio-alert-editor",
    ".portfolio-alert-fields",
    ".portfolio-alert-state",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio selector: {required}")

for required in ("const socket = io", "function switchMode", "function renderAlertLog", "function flashTitle"):
    if required not in js:
        raise SystemExit(f"static/app.js missing expected frontend function: {required}")

for required in (
    "'5min': { label: '5分钟波动'",
    "function klineOhlcForMode",
    "open_rmb",
    "function setChartEmptyState",
    "x: label",
    "if (Array.isArray(data.klines_5min))",
    "暂无5分钟波动数据",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing 5 minute kline frontend contract: {required}")

for required in (
    ".chart-empty-state",
    ".chart-empty-state[hidden]",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing chart empty state contract: {required}")

for required in ("market_quality", "function renderRiskQuality", "function sourceQualityText", "data.quality", "行情质量"):
    if required not in js:
        raise SystemExit(f"static/app.js missing risk quality frontend contract: {required}")

for required in (
    "function renderRiskDiagnostic",
    "risk_analysis_error",
    "data.diagnostic",
    "失败原因",
    "建议处理",
    "function renderRiskEvidence",
    "snapshot.evidence_summary",
    "document.getElementById('riskEvidence')",
    "数据依据",
    "缺失数据",
    "恢复建议",
    "## 数据依据",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing risk evidence frontend contract: {required}")

for required in (
    ".risk-diagnostic",
    ".risk-diagnostic.show",
    ".risk-diagnostic-title",
    ".risk-diagnostic-list",
    ".risk-evidence",
    ".risk-evidence.show",
    ".risk-evidence-grid",
    ".risk-evidence-item",
    ".risk-evidence-warning",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing risk evidence selector: {required}")

for required in (
    "function selectedRiskPrice",
    "function hasRiskAnalysisInput",
    "function riskAnalysisUnavailableMessage",
    "function updateRiskEntryState",
    "riskAnalyzeButton.hidden = !available",
    "document.querySelectorAll('.source-risk-action')",
    "applyFetchStatus({ ok:false, message:riskUnavailable, retryable:true });",
    "if (!openRiskAnalysis()) return;",
    "const riskUnavailable = riskAnalysisUnavailableMessage();",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing risk entry availability contract: {required}")

if ".risk-open[hidden] { display:none; }" not in css:
    raise SystemExit("static/app.css must let hidden risk action override button display")

if ".source-risk-action[hidden] { display:none; }" not in css:
    raise SystemExit("static/app.css must let hidden source risk action override button display")

for required in (
    "function applyPortfolio",
    "function capturePortfolioDraft",
    "function portfolioDraftFor",
    "function clearPortfolioDraft",
    "function capturePortfolioTransactionDraft",
    "function portfolioTransactionDraftFor",
    "function clearPortfolioTransactionDraft",
    "function renderPortfolio",
    "function renderPortfolioControls",
    "function renderPortfolioDropdownControl",
    "function togglePortfolioControlMenu",
    "function setPortfolioControlSelection",
    "function setPortfolioSearch",
    "function setPortfolioPositionFilter",
    "function setPortfolioPositionSort",
    "function setPortfolioTransactionTypeFilter",
    "function setPortfolioTransactionModeFilter",
    "function setPortfolioTransactionSort",
    "function filteredPortfolioPositions",
    "function filteredPortfolioTransactions",
    "function importPortfolioTransactions",
    "function onPortfolioImportFile",
    "function buildPortfolioTransactionTemplateCsv",
    "function downloadPortfolioTransactionTemplate",
    "function parsePortfolioCsvRows",
    "function portfolioImportRowErrors",
    "function previewPortfolioImport",
    "function requestPortfolioImportBackendPreview",
    "function applyPortfolioImportBackendPreview",
    "function renderPortfolioImportPreview",
    "function confirmPortfolioImport",
    "function cancelPortfolioImport",
    "function portfolioImportSummary",
    "function normalizePortfolioImportBackup",
    "function renderPortfolioImportBackup",
    "function undoPortfolioImport",
    "function renderPortfolioReviewCurve",
    "function renderPortfolioReview",
    "function renderPortfolioReviewCard",
    "function renderPortfolioReviewPoint",
    "function renderPortfolioPositionDetail",
    "function renderPortfolioAlertSummary",
    "function buildPortfolioAlertEditor",
    "function portfolioAlertForPosition",
    "function togglePortfolioToolsMenu",
    "function toggleLogEntryMenu",
    "function togglePortfolioAlertEditor",
    "function capturePortfolioAlertDraft",
    "function setPortfolioView",
    "function setActivePortfolioDetail",
    "function setActivePortfolioPosition",
    "function setActivePortfolioTransaction",
    "function savePortfolioPosition",
    "function savePortfolioTransaction",
    "function savePortfolioAlert",
    "function resetPortfolioAlert",
    "function deletePortfolioAlert",
    "function deletePortfolioPosition",
    "function deletePortfolioTransaction",
    "function exportPortfolio",
    "portfolioDrafts",
    "portfolioTransactionDrafts",
    "portfolioAlertDrafts",
    "activePortfolioAlertEditorId",
    "portfolioImportPreview",
    "function portfolioStatusLabel",
    "portfolio_status",
    "near_cost",
    "target_hit",
    "PORTFOLIO_TRANSACTION_IMPORT_FIELDS",
    "确认导入",
    "下载模板",
    "第 ",
    "activePortfolioDetailId",
    "oninput=\"capturePortfolioDraft",
    "oninput=\"capturePortfolioTransactionDraft",
    "oninput=\"capturePortfolioAlertDraft",
    "onchange=\"capturePortfolioDraft",
    "onchange=\"capturePortfolioTransactionDraft",
    "onchange=\"capturePortfolioAlertDraft",
    "portfolio_updated",
    "portfolio_error",
    "portfolio_exported",
    "portfolio_export_error",
    "portfolio_imported",
    "portfolio_import_previewed",
    "portfolio_import_undone",
    "portfolio_import_undo_error",
    "row_count",
    "valid_count",
    "warnings",
    "errors",
    "get_portfolio",
    "save_portfolio_position",
    "save_portfolio_transaction",
    "save_portfolio_alert",
    "reset_portfolio_alert",
    "delete_portfolio_alert",
    "delete_portfolio_position",
    "delete_portfolio_transaction",
    "export_portfolio",
    "import_portfolio_transactions",
    "preview_import_portfolio_transactions",
    "undo_portfolio_import",
    "portfolio-select-menu",
    "portfolio-select-trigger",
    "renderPortfolioDropdownControl('portfolio-filter', '筛选'",
    "renderPortfolioDropdownControl('portfolio-sort', '排序'",
    "'positionFilter'",
    "'positionSort'",
    "'transactionType'",
    "'transactionMode'",
    "'transactionSort'",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio frontend contract: {required}")

for forbidden in (
    '<select onchange="setPortfolioPositionFilter',
    '<select onchange="setPortfolioPositionSort',
    '<select onchange="setPortfolioTransactionTypeFilter',
    '<select onchange="setPortfolioTransactionModeFilter',
    '<select onchange="setPortfolioTransactionSort',
):
    if forbidden in js:
        raise SystemExit(f"portfolio controls must not use native select dropdowns: {forbidden}")

for required in (
    "function portfolioTransactionToday",
    "function defaultPortfolioTransactionPrice",
    "latestData && mode === 'usd' ? latestData.usd : latestData && latestData.rmb",
    "Number.isFinite(number) && number > 0 ? number.toFixed(2) : ''",
    "const mode = source.mode || currentMode",
    "const defaultPrice = isNew ? defaultPortfolioTransactionPrice(mode) : ''",
    "price: source.price == null || (isNew && source.price === '') ? defaultPrice : String(source.price)",
    "trade_date: source.trade_date || (isNew ? portfolioTransactionToday() : '')",
    "price: defaultPortfolioTransactionPrice(mode)",
    "trade_date: portfolioTransactionToday()",
    "const priceInput = document.getElementById('portfolioTransactionPrice_' + key)",
    "const previousMode = modeInput ? modeInput.value || currentMode : currentMode",
    "const previousDefaultPrice = defaultPortfolioTransactionPrice(previousMode)",
    "const nextMode = item.mode || currentMode",
    "if (priceInput && (!priceInput.value || priceInput.value === previousDefaultPrice)) priceInput.value = defaultPortfolioTransactionPrice(nextMode)",
    "if (modeInput) modeInput.value = nextMode",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio transaction defaults contract: {required}")

for required in (
    "let portfolioDetailView = 'review';",
    "function setPortfolioDetailView",
    "function renderPortfolioDetailTabs",
    "function renderPortfolioDetailActions",
    "function togglePortfolioDetailActionMenu",
    "function renderPortfolioDetailOverview",
    "function renderPortfolioDetailTransactions",
    "function renderPortfolioDetailAlert",
    "function activePortfolioDetailItem",
    "function renderPortfolioHeaderChrome",
    "function buildPortfolioReviewSummary",
    "function buildPortfolioReviewTimeline",
    "function renderPortfolioPositionReview",
    "function renderPortfolioReviewSummaryStrip",
    "function renderPortfolioReviewTimeline",
    "function exportPortfolioPositionReview",
    "function openPortfolioAlertEditor",
    "portfolio-detail-tab",
    "portfolio-detail-review-summary",
    "portfolio-review-timeline",
    "portfolio-detail-action-row",
    "portfolio-detail-mode",
    "持仓详情 · 复盘",
    "返回列表",
    "document.querySelectorAll('.portfolio-detail-action-menu')",
    ".portfolio-detail-action-trigger",
    ".portfolio-detail-actions",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio detail review contract: {required}")

for required in (
    "repeat(auto-fit, minmax(min(150px, 100%), 1fr))",
    "repeat(auto-fit, minmax(min(140px, 100%), 1fr))",
    ".portfolio-name, .portfolio-note { grid-column:1 / -1; }",
    ".portfolio-transaction-fields .portfolio-name, .portfolio-transaction-fields .portfolio-note { grid-column:1 / -1; }",
    "box-sizing:border-box",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio editor sizing contract: {required}")

for required in (
    "let pendingTimelineFocus = null;",
    "function timelineRangeForTimestamp",
    "function eventMatchesTimelineFocus",
    "function openEventTimelineAround",
    "function openAlertTimelineFromLog",
    "function openRiskTimelineFromHistory",
    "function handleAlertLogTimelineClick",
    "function handleRiskHistoryTimelineClick",
    "pendingTimelineFocus = {",
    "eventTimelineTypes = EVENT_TIMELINE_TYPE_DEFS.map(item => item.type)",
    "openEventTimelineAround(entry.timestamp || entry.time, 'alert', entry.id)",
    "openEventTimelineAround(item.analysis_time || (item.snapshot && item.snapshot.analysis_time), 'risk_analysis', item.id)",
    "data-log-timeline-id",
    "data-risk-timeline-index",
    "label: '复盘'",
    "risk-history-review",
    "查看复盘",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing timeline deep-link contract: {required}")

for required in (
    ".risk-history-main",
    ".risk-history-review",
    ".timeline-event.active",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing timeline deep-link selector: {required}")

for required in (
    ".portfolio-detail-focus-head",
    ".portfolio-detail-actions",
    ".portfolio-detail-action-trigger",
    ".portfolio-detail-action-menu",
    ".portfolio-detail-tabs",
    ".portfolio-detail-tab",
    ".portfolio-detail-panel",
    ".portfolio-detail-review-summary",
    ".portfolio-detail-review-stat",
    ".portfolio-review-timeline",
    ".portfolio-review-event",
    ".portfolio-review-event-time",
    ".portfolio-review-event-type",
    ".portfolio-review-event-title",
    ".portfolio-review-event-text",
    ".portfolio-related-table",
    ".portfolio-detail-action-row",
    ".portfolio-card.portfolio-detail-mode .portfolio-tabs",
    ".portfolio-card.portfolio-detail-mode .portfolio-controls",
    ".portfolio-card.portfolio-detail-mode .portfolio-summary",
    ".portfolio-card.portfolio-detail-mode .portfolio-import-backup",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio detail review selector: {required}")

for required in (
    ".btn-risk-sm",
    ".btn-muted-sm",
    ".source-summary-text { color:#f0f0f4; font-size:0.78rem; line-height:1.28; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }",
    ".source-health-menu",
    "bottom:calc(100% + 6px)",
    ".log-title-row",
    ".log-list { overflow-y:auto; max-height:240px; display:grid; gap:6px;",
    "background:rgba(255,255,255,0.018)",
    "border:1px solid rgba(255,255,255,0.055)",
    ".log-item { display:grid; grid-template-columns:8px minmax(0, 1fr);",
    ".log-body { min-width:0; }",
    ".log-entry-head { display:flex; align-items:center; justify-content:space-between; gap:8px; min-width:0; min-height:28px; margin-bottom:7px; }",
    ".log-line-head { display:flex; align-items:center; gap:5px; row-gap:3px; flex-wrap:nowrap; min-width:0; min-height:28px; margin-bottom:0; }",
    ".log-time { min-height:28px; display:inline-flex; align-items:center;",
    ".log-action-trigger",
    ".log-msg { display:block; font-size:0.74rem; line-height:1.35; white-space:normal; overflow:visible; overflow-wrap:anywhere; text-overflow:clip; }",
    ".log-entry-menu",
    ".log-entry-menu[hidden]",
    "'<span class=\"log-body\">'",
    "'<span class=\"log-entry-head\">'",
):
    if required not in css and required not in js:
        raise SystemExit(f"frontend missing compact alert log contract: {required}")

for forbidden in (
    "grid-template-columns:minmax(140px, 1fr) minmax(140px, 1fr) minmax(150px, 1fr)",
    "grid-column:span 3",
    ".source-health-menu { position:absolute; right:0; top:calc(100% + 6px);",
    "grid-template-columns:8px minmax(0, 1fr) 58px",
    ".alert-log-tabs",
    ".alert-log-tab",
):
    if forbidden in css or forbidden in js:
        raise SystemExit(f"static/app.css keeps a fixed portfolio grid that can overflow: {forbidden}")

for required in (
    "preview_import_config",
    "config_import_previewed",
    "pendingConfigImportPayload",
    "function renderConfigImportPreview",
    "再次点击导入确认",
    "if (section === 'alert_profiles') return '预警策略模板';",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing config import preview contract: {required}")

for required in (
    'id="alertProfilesPanel"',
    'id="alertProfilesList"',
    'id="alertProfilesMeta"',
    'id="alertProfilesStatus"',
    "预警策略模板",
    "saveCurrentAlertProfile()",
):
    if required not in template:
        raise SystemExit(f"template missing alert profile UI contract: {required}")

for required in (
    "let alertProfiles",
    "function normalizeAlertProfiles",
    "function applyAlertProfiles",
    "function alertProfileSettingsChanged",
    "function clearCurrentAlertProfileMatch",
    "function renderAlertProfiles",
    "function alertProfileSummary",
    "function saveCurrentAlertProfile",
    "function applyAlertProfile",
    "function renameAlertProfile",
    "function deleteAlertProfile",
    "alert_profiles_updated",
    "alert_profile_error",
    "save_alert_profile",
    "apply_alert_profile",
    "rename_alert_profile",
    "delete_alert_profile",
    "data.alert_profiles || {}",
    "ALERT_PROFILE_SETTING_KEYS",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing alert profile UI contract: {required}")

for required in (
    ".alert-profiles",
    ".alert-profiles-head",
    ".alert-profiles-list",
    ".alert-profile-item",
    ".alert-profile-actions",
    ".alert-profiles-status",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing alert profile selector: {required}")

for handler in (
    "socket.on('thresholds_updated', data => {",
    "socket.on('volatility_updated', data => {",
    "socket.on('settings_updated', data => {",
):
    handler_pos = js.find(handler)
    next_handler_pos = js.find("socket.on(", handler_pos + len(handler))
    handler_body = js[handler_pos:next_handler_pos if next_handler_pos >= 0 else len(js)] if handler_pos >= 0 else ""
    if "clearCurrentAlertProfileMatch();" not in handler_body:
        raise SystemExit(f"{handler} must clear stale alert profile current marker")

for required in (
    'id="setExportDir"',
    'id="exportDirStatus"',
    'onclick="resetExportDirField()"',
    "function applyExportDirSetting",
    "function resetExportDirField",
    "export_dir_effective",
    "export_dir_default",
    "export_dir: document.getElementById('setExportDir').value.trim()",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing custom export directory contract: {required}")

for required in (
    'id="settingsTabDigest"',
    'id="settingsPanelDigest"',
    'id="setDailyDigestEnabled"',
    'id="setDailyDigestTime"',
    'id="setDailyDigestEmail"',
    'id="setDailyDigestWebhook"',
    'id="btnPreviewDailyDigest"',
    'id="btnTestDailyDigest"',
    'id="dailyDigestStatus"',
    'id="dailyDigestPreview"',
    "function previewDailyDigest",
    "function testDailyDigest",
    "socket.emit('preview_daily_digest')",
    "socket.emit('test_daily_digest')",
    "socket.on('daily_digest_status'",
    "socket.on('daily_digest_previewed'",
    "socket.on('daily_digest_test_result'",
    "if (data.daily_digest_status) applyDailyDigestStatus(data.daily_digest_status)",
    "if (tab === 'digest') socket.emit('get_daily_digest_status')",
    "daily_digest_enabled: document.getElementById('setDailyDigestEnabled').checked",
    "daily_digest_time: document.getElementById('setDailyDigestTime').value",
    "daily_digest_email_enabled: document.getElementById('setDailyDigestEmail').checked",
    "daily_digest_webhook_enabled: document.getElementById('setDailyDigestWebhook').checked",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing daily digest contract: {required}")

for required in (
    'id="createReviewNoteButton"',
    'id="reviewNoteEditor"',
    'id="reviewNoteRelation"',
    'id="reviewNoteTimestamp"',
    'id="reviewNoteTitle"',
    'id="reviewNoteContent"',
    'id="reviewNoteEditorStatus"',
    'id="saveReviewNoteButton"',
    'maxlength="80"',
    'maxlength="2000"',
    "function openReviewNoteEditor",
    "function closeReviewNoteEditor",
    "function openReviewNoteEditorFromSelectedEvent",
    "function editSelectedReviewNote",
    "function deleteSelectedReviewNote",
    "function saveReviewNote",
    "socket.emit('save_review_note'",
    "socket.emit('delete_review_note'",
    "socket.on('review_note_saved'",
    "socket.on('review_note_deleted'",
    "socket.on('review_note_error'",
    "socket.on('review_notes_updated'",
    "type: 'review_note'",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing review note contract: {required}")

for required in (
    ".review-note-editor",
    ".review-note-fields",
    ".review-note-editor-actions",
    ".timeline-note-create",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing review note selector: {required}")

for required in (
    'REVIEW_NOTES_PATH',
    '@socketio.on("save_review_note")',
    '@socketio.on("delete_review_note")',
):
    if required not in app_py:
        raise SystemExit(f"app.py missing review note contract: {required}")

for required in (
    'onclick="copyDiagnostics()"',
    'id="diagnosticsCopyFallback"',
    "function copyDiagnostics",
    "function copyTextToClipboard",
    "function showDiagnosticsCopyFallback",
    "socket.emit('copy_diagnostics')",
    "diagnostics_copy_ready",
    "navigator.clipboard.writeText",
    "document.execCommand('copy')",
    "诊断摘要已复制",
    "自动复制失败，已展示诊断摘要，可手动复制。",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing diagnostics copy contract: {required}")

for required in (
    'id="opsUpdateStatus"',
    'id="opsUpdateMeta"',
    'onclick="checkUpdateFromOps()"',
    'onclick="openUpdateFromOps()"',
    "function renderOpsUpdateStatus",
    "function checkUpdateFromOps",
    "function openUpdateFromOps",
    "let opsUpdateStatus",
    "renderOpsUpdateStatus(data)",
    "copyDiagnostics()",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing update diagnostics loop contract: {required}")

for required in (
    ".ops-update-card",
    ".ops-update-status",
    ".ops-update-meta",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing ops update selector: {required}")

for required in (
    "update_alert_log_handling",
    "alert_log_handling_updated",
    "function updateAlertHandling",
    "function syncEllipsisTitle",
    "function setupEllipsisTooltips",
    "document.addEventListener('mouseover', syncEllipsisTitle",
    "document.addEventListener('focusin', syncEllipsisTitle",
    "textOverflow === 'ellipsis'",
    "target.setAttribute('title'",
    "head.title = head.textContent",
    "title=\"' + escapeHtml(logMessage) + '\"",
    "function closeRightPanelMenus",
    "function isRightPanelMenuEventTarget",
    "function closeRightPanelMenusOnOutsideClick",
    "closeRightPanelMenus(menu)",
    "if (isRightPanelMenuEventTarget(event.target)) return;",
    "document.addEventListener('click', closeRightPanelMenusOnOutsideClick",
    "document.getElementById('portfolioToolsMenu')",
    "document.getElementById('sourceHealthMenu')",
    "document.getElementById('alertLogMenu')",
    "document.querySelectorAll('.log-entry-menu')",
    "aria-expanded",
    "function renderLogEntryActions",
    "actions.length === 1",
    "actions.length > 1",
    "log-action-direct",
    "log-action-trigger",
    "const actions = [",
    "{ label: '分析'",
    "if (hasNotificationIssue) actions.push",
    "alertNotificationIssues(entry).length > 0",
    "handling_note",
    "payload.handled",
    "处置结果",
    "重发通知",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing alert handling contract: {required}")

for forbidden in (
    "alertLogView === 'unhandled'",
    "alertLogView === 'handled'",
    "alertLogView === 'failed'",
    "const actions = hasNotificationIssue ? [",
    "标记已处理",
    "取消处理",
    "log-handled",
):
    if forbidden in js:
        raise SystemExit(f"static/app.js keeps removed alert log workflow: {forbidden}")

for pattern in (
    r"clearThreshold\(.*?rule\.type.*?>停用预警</button>",
    r"setActiveAlertRule\(.*?rule\.type.*?>放弃编辑</button>",
    r"clearVolatility\(\).*?>停用预警</button>",
    r"setActiveAlertRule\(.*?volatility.*?>放弃编辑</button>",
    r"rule\.clear \+ .*?>停用</button>",
):
    if not re.search(pattern, js):
        raise SystemExit(f"static/app.js missing explicit alert rule action label: {pattern}")

for pattern in (
    r"clearThreshold\(.*?rule\.type.*?>关闭</button>",
    r"setActiveAlertRule\(.*?rule\.type.*?>取消</button>",
    r"clearVolatility\(\).*?>关闭</button>",
    r"setActiveAlertRule\(.*?volatility.*?>取消</button>",
    r"rule\.clear \+ .*?>关闭</button>",
):
    if re.search(pattern, js):
        raise SystemExit(f"static/app.js keeps ambiguous alert rule action label: {pattern}")

if "alertLogView === 'failed' && hasNotificationIssue" in js:
    raise SystemExit("notification-failed log entries must direct-render their single retry action in every alert log view")

print("frontend asset checks passed.")
