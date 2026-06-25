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
    'onclick="setActivePortfolioTransaction(\'new\')"',
    'onclick="exportPortfolio(\'positions\')"',
    'onclick="exportPortfolio(\'transactions\')"',
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
    ".portfolio-summary",
    ".portfolio-item",
    ".portfolio-editor",
    ".portfolio-transaction-type",
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
    "function setPortfolioView",
    "function setActivePortfolioPosition",
    "function setActivePortfolioTransaction",
    "function savePortfolioPosition",
    "function savePortfolioTransaction",
    "function deletePortfolioPosition",
    "function deletePortfolioTransaction",
    "function exportPortfolio",
    "portfolioDrafts",
    "portfolioTransactionDrafts",
    "oninput=\"capturePortfolioDraft",
    "oninput=\"capturePortfolioTransactionDraft",
    "onchange=\"capturePortfolioDraft",
    "onchange=\"capturePortfolioTransactionDraft",
    "portfolio_updated",
    "portfolio_error",
    "portfolio_exported",
    "portfolio_export_error",
    "get_portfolio",
    "save_portfolio_position",
    "save_portfolio_transaction",
    "delete_portfolio_position",
    "delete_portfolio_transaction",
    "export_portfolio",
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
