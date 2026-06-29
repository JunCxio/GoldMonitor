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

for required in (
    'id="portfolioStatus"',
    'id="portfolioViewTabs"',
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
    ".portfolio-card",
    ".portfolio-head h3",
    ".portfolio-tabs",
    ".portfolio-controls",
    ".portfolio-search",
    ".portfolio-filter",
    ".portfolio-sort",
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
    ".portfolio-detail-grid",
    ".portfolio-detail-transactions",
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
    "function applyPortfolio",
    "function capturePortfolioDraft",
    "function portfolioDraftFor",
    "function clearPortfolioDraft",
    "function capturePortfolioTransactionDraft",
    "function portfolioTransactionDraftFor",
    "function clearPortfolioTransactionDraft",
    "function renderPortfolio",
    "function renderPortfolioControls",
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
    "function buildPortfolioAlertEditor",
    "function portfolioAlertForPosition",
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
    "portfolioImportPreview",
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
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio frontend contract: {required}")

for required in (
    "repeat(auto-fit, minmax(min(150px, 100%), 1fr))",
    "repeat(auto-fit, minmax(min(140px, 100%), 1fr))",
    ".portfolio-name, .portfolio-note { grid-column:1 / -1; }",
    ".portfolio-transaction-fields .portfolio-name, .portfolio-transaction-fields .portfolio-note { grid-column:1 / -1; }",
    "box-sizing:border-box",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio editor sizing contract: {required}")

for forbidden in (
    "grid-template-columns:minmax(140px, 1fr) minmax(140px, 1fr) minmax(150px, 1fr)",
    "grid-column:span 3",
):
    if forbidden in css:
        raise SystemExit(f"static/app.css keeps a fixed portfolio grid that can overflow: {forbidden}")

print("frontend asset checks passed.")
