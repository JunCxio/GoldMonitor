from pathlib import Path
import re


root = Path(__file__).resolve().parents[1]
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
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

if '<script src="/static/app.js"></script>' not in template:
    raise SystemExit("template must reference /static/app.js")

if 'id="chartEmptyState"' not in template:
    raise SystemExit("template must expose chart empty state overlay")

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
    "repeat(auto-fit, minmax(min(150px, 100%), 1fr))",
    "repeat(auto-fit, minmax(min(140px, 100%), 1fr))",
    ".portfolio-name, .portfolio-note { grid-column:1 / -1; }",
    ".portfolio-transaction-fields .portfolio-name, .portfolio-transaction-fields .portfolio-note { grid-column:1 / -1; }",
    "box-sizing:border-box",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio editor sizing contract: {required}")

for required in (
    ".btn-risk-sm",
    ".btn-muted-sm",
    ".source-summary-text { color:#f0f0f4; font-size:0.78rem; line-height:1.28; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }",
    ".source-health-menu",
    "bottom:calc(100% + 6px)",
    ".log-title-row",
    "grid-template-columns:repeat(5, minmax(0, 1fr))",
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
):
    if forbidden in css or forbidden in js:
        raise SystemExit(f"static/app.css keeps a fixed portfolio grid that can overflow: {forbidden}")

for required in (
    "preview_import_config",
    "config_import_previewed",
    "pendingConfigImportPayload",
    "function renderConfigImportPreview",
    "再次点击导入确认",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing config import preview contract: {required}")

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
    "const actions = hasNotificationIssue ? [",
    "alertLogView === 'unhandled'",
    "alertLogView === 'handled'",
    "alertLogView === 'failed'",
    "alertNotificationIssues(entry).length > 0",
    "handling_note",
    "payload.handled",
    "处置结果",
    "已处理",
    "未处理",
    "通知失败",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing alert handling contract: {required}")

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
