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
    'id="portfolioSummary"',
    'id="portfolioList"',
    'onclick="setActivePortfolioPosition(\'new\')"',
    'onclick="exportPortfolio()"',
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

for required in (".portfolio-card", ".portfolio-head h3", ".portfolio-summary", ".portfolio-item", ".portfolio-editor"):
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
    "function renderPortfolio",
    "function setActivePortfolioPosition",
    "function savePortfolioPosition",
    "function deletePortfolioPosition",
    "function exportPortfolio",
    "portfolioDrafts",
    "oninput=\"capturePortfolioDraft",
    "onchange=\"capturePortfolioDraft",
    "portfolio_updated",
    "portfolio_error",
    "portfolio_exported",
    "portfolio_export_error",
    "get_portfolio",
    "save_portfolio_position",
    "delete_portfolio_position",
    "export_portfolio",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing portfolio frontend contract: {required}")

for required in (
    "minmax(150px, 1.4fr)",
    "minmax(120px, 1fr)",
    "grid-column:span 2",
    "box-sizing:border-box",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing portfolio editor sizing contract: {required}")

print("frontend asset checks passed.")
