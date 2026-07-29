from pathlib import Path
import re


root = Path(__file__).resolve().parents[1]
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
app_py = (root / "goldmonitor" / "application.py").read_text(encoding="utf-8")
http_routes_py = (root / "goldmonitor" / "http_routes.py").read_text(encoding="utf-8")
floating_runtime_py = (root / "goldmonitor" / "floating_runtime.py").read_text(encoding="utf-8")
taskbar_runtime_py = (root / "goldmonitor" / "taskbar_runtime.py").read_text(encoding="utf-8")
css_path = root / "static" / "app.css"
js_path = root / "static" / "app.js"
app_state_js_path = root / "static" / "app-state.js"
app_utils_js_path = root / "static" / "app-utils.js"
desktop_close_js_path = root / "static" / "desktop-close.js"
market_dashboard_js_path = root / "static" / "market-dashboard.js"
settings_js_path = root / "static" / "settings-center.js"
settings_state_js_path = root / "static" / "settings-state.js"
settings_socket_js_path = root / "static" / "settings-socket.js"
settings_render_js_path = root / "static" / "settings-render.js"
settings_form_js_path = root / "static" / "settings-form.js"
settings_onboarding_js_path = root / "static" / "settings-onboarding.js"
settings_dialog_js_path = root / "static" / "settings-dialog.js"
settings_actions_js_path = root / "static" / "settings-actions.js"
operations_js_path = root / "static" / "operations-center.js"
operations_state_js_path = root / "static" / "operations-state.js"
operations_socket_js_path = root / "static" / "operations-socket.js"
operations_sources_js_path = root / "static" / "operations-sources.js"
operations_records_js_path = root / "static" / "operations-records.js"
operations_archive_js_path = root / "static" / "operations-archive.js"
operations_config_js_path = root / "static" / "operations-config.js"
operations_actions_js_path = root / "static" / "operations-actions.js"
operations_update_js_path = root / "static" / "operations-update.js"
history_review_js_path = root / "static" / "history-review-center.js"
risk_analysis_js_path = root / "static" / "risk-analysis-center.js"
alert_rule_js_path = root / "static" / "alert-rule-center.js"
alert_rule_state_js_path = root / "static" / "alert-rule-state.js"
alert_rule_socket_js_path = root / "static" / "alert-rule-socket.js"
alert_rule_list_js_path = root / "static" / "alert-rule-list.js"
alert_rule_detail_js_path = root / "static" / "alert-rule-detail.js"
alert_rule_editor_js_path = root / "static" / "alert-rule-editor.js"
alert_rule_render_js_path = root / "static" / "alert-rule-render.js"
alert_rule_legacy_js_path = root / "static" / "alert-rule-legacy.js"
alert_configuration_js_path = root / "static" / "alert-configuration-center.js"
portfolio_js_path = root / "static" / "portfolio-center.js"
portfolio_state_js_path = root / "static" / "portfolio-state.js"
portfolio_render_js_path = root / "static" / "portfolio-render.js"
portfolio_detail_js_path = root / "static" / "portfolio-detail.js"
portfolio_list_js_path = root / "static" / "portfolio-list.js"
portfolio_actions_js_path = root / "static" / "portfolio-actions.js"
portfolio_import_js_path = root / "static" / "portfolio-import.js"
alert_log_js_path = root / "static" / "alert-log-center.js"


if not css_path.exists():
    raise SystemExit("frontend styles must live in static/app.css")

if not js_path.exists():
    raise SystemExit("frontend main script must live in static/app.js")

for shared_path in (app_state_js_path, app_utils_js_path, desktop_close_js_path):
    if not shared_path.exists():
        raise SystemExit(f"frontend shared script is missing: {shared_path.name}")

if not market_dashboard_js_path.exists():
    raise SystemExit("market dashboard script must live in static/market-dashboard.js")

for settings_path in (
    settings_state_js_path,
    settings_socket_js_path,
    settings_render_js_path,
    settings_form_js_path,
    settings_onboarding_js_path,
    settings_dialog_js_path,
    settings_actions_js_path,
    settings_js_path,
):
    if not settings_path.exists():
        raise SystemExit(f"settings script is missing: {settings_path.name}")

for operations_path in (
    operations_state_js_path,
    operations_socket_js_path,
    operations_sources_js_path,
    operations_records_js_path,
    operations_archive_js_path,
    operations_config_js_path,
    operations_actions_js_path,
    operations_update_js_path,
    operations_js_path,
):
    if not operations_path.exists():
        raise SystemExit(f"operations script is missing: {operations_path.name}")

if not history_review_js_path.exists():
    raise SystemExit("history review center script must live in static/history-review-center.js")

if not risk_analysis_js_path.exists():
    raise SystemExit("risk analysis center script must live in static/risk-analysis-center.js")

for alert_rule_path in (
    alert_rule_state_js_path,
    alert_rule_socket_js_path,
    alert_rule_list_js_path,
    alert_rule_detail_js_path,
    alert_rule_editor_js_path,
    alert_rule_render_js_path,
    alert_rule_legacy_js_path,
    alert_rule_js_path,
):
    if not alert_rule_path.exists():
        raise SystemExit(f"alert rule script is missing: {alert_rule_path.name}")

if not alert_configuration_js_path.exists():
    raise SystemExit("alert configuration script must live in static/alert-configuration-center.js")

for portfolio_path in (
    portfolio_state_js_path,
    portfolio_render_js_path,
    portfolio_detail_js_path,
    portfolio_list_js_path,
    portfolio_actions_js_path,
    portfolio_import_js_path,
    portfolio_js_path,
):
    if not portfolio_path.exists():
        raise SystemExit(f"portfolio script is missing: {portfolio_path.name}")

if not alert_log_js_path.exists():
    raise SystemExit("alert log center script must live in static/alert-log-center.js")

app_js = js_path.read_text(encoding="utf-8")
market_dashboard_js = market_dashboard_js_path.read_text(encoding="utf-8")
settings_state_js = settings_state_js_path.read_text(encoding="utf-8")
alert_rule_js = "\n".join((
    alert_rule_state_js_path.read_text(encoding="utf-8"),
    alert_rule_socket_js_path.read_text(encoding="utf-8"),
    alert_rule_list_js_path.read_text(encoding="utf-8"),
    alert_rule_detail_js_path.read_text(encoding="utf-8"),
    alert_rule_editor_js_path.read_text(encoding="utf-8"),
    alert_rule_render_js_path.read_text(encoding="utf-8"),
    alert_rule_legacy_js_path.read_text(encoding="utf-8"),
    alert_rule_js_path.read_text(encoding="utf-8"),
))
alert_configuration_js = alert_configuration_js_path.read_text(encoding="utf-8")
portfolio_js = portfolio_js_path.read_text(encoding="utf-8")
portfolio_module_js = "\n".join((
    portfolio_state_js_path.read_text(encoding="utf-8"),
    portfolio_render_js_path.read_text(encoding="utf-8"),
    portfolio_detail_js_path.read_text(encoding="utf-8"),
    portfolio_list_js_path.read_text(encoding="utf-8"),
    portfolio_actions_js_path.read_text(encoding="utf-8"),
    portfolio_import_js_path.read_text(encoding="utf-8"),
    portfolio_js,
))
settings_module_js = "\n".join((
    settings_state_js,
    settings_socket_js_path.read_text(encoding="utf-8"),
    settings_render_js_path.read_text(encoding="utf-8"),
    settings_form_js_path.read_text(encoding="utf-8"),
    settings_onboarding_js_path.read_text(encoding="utf-8"),
    settings_dialog_js_path.read_text(encoding="utf-8"),
    settings_actions_js_path.read_text(encoding="utf-8"),
    settings_js_path.read_text(encoding="utf-8"),
))
operations_module_js = "\n".join((
    operations_state_js_path.read_text(encoding="utf-8"),
    operations_socket_js_path.read_text(encoding="utf-8"),
    operations_sources_js_path.read_text(encoding="utf-8"),
    operations_records_js_path.read_text(encoding="utf-8"),
    operations_archive_js_path.read_text(encoding="utf-8"),
    operations_config_js_path.read_text(encoding="utf-8"),
    operations_actions_js_path.read_text(encoding="utf-8"),
    operations_update_js_path.read_text(encoding="utf-8"),
    operations_js_path.read_text(encoding="utf-8"),
))
alert_log_js = alert_log_js_path.read_text(encoding="utf-8")

js = "\n".join((
    app_state_js_path.read_text(encoding="utf-8"),
    app_utils_js_path.read_text(encoding="utf-8"),
    market_dashboard_js,
    settings_module_js,
    operations_module_js,
    history_review_js_path.read_text(encoding="utf-8"),
    risk_analysis_js_path.read_text(encoding="utf-8"),
    alert_rule_js,
    alert_configuration_js,
    portfolio_module_js,
    alert_log_js,
    desktop_close_js_path.read_text(encoding="utf-8"),
    app_js,
))

if '<link rel="stylesheet" href="/static/app.css">' not in template:
    raise SystemExit("template must reference /static/app.css")

if '<meta name="goldmonitor-socket-token" content="{{ socket_access_token }}">' not in template:
    raise SystemExit("template must expose the socket token through a meta tag")

if '<script src="/static/app-shell.js?v={{ app_version }}"></script>' not in template:
    raise SystemExit("template must reference versioned /static/app-shell.js")

if '<script src="/static/app.js?v={{ app_version }}"></script>' not in template:
    raise SystemExit("template must reference versioned /static/app.js")

for shared_name in ("app-state.js", "app-utils.js", "desktop-close.js"):
    shared_script = f'<script src="/static/{shared_name}?v={{{{ app_version }}}}"></script>'
    if shared_script not in template:
        raise SystemExit(f"template must reference versioned /static/{shared_name}")

market_dashboard_script = '<script src="/static/market-dashboard.js?v={{ app_version }}"></script>'
if market_dashboard_script not in template:
    raise SystemExit("template must reference versioned /static/market-dashboard.js")

if template.find(market_dashboard_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("market dashboard script must load before static/app.js")

settings_scripts = tuple(
    f'<script src="/static/{name}?v={{{{ app_version }}}}"></script>'
    for name in (
        "settings-state.js",
        "settings-socket.js",
        "settings-render.js",
        "settings-form.js",
        "settings-onboarding.js",
        "settings-dialog.js",
        "settings-actions.js",
        "settings-center.js",
    )
)
for script in settings_scripts:
    if script not in template:
        raise SystemExit(f"template must reference settings script: {script}")
settings_positions = [template.find(script) for script in settings_scripts]
if settings_positions != sorted(settings_positions):
    raise SystemExit("settings scripts must load in dependency order")
if settings_positions[-1] > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("settings scripts must load before static/app.js")

for required in (
    "function registerSettingsSocketHandlers",
    "function applySettings",
    "function validateSettings",
    "function openOnboarding",
    "function setupSettingsInteractions",
    "function saveSettings",
):
    if required not in settings_module_js:
        raise SystemExit(f"settings modules missing contract: {required}")

for moved in (
    "function registerSettingsSocketHandlers",
    "function applySettings",
    "function validateSettings",
    "function openOnboarding",
    "function saveSettings",
):
    if moved in settings_js_path.read_text(encoding="utf-8"):
        raise SystemExit(f"settings center keeps extracted implementation: {moved}")

operations_scripts = tuple(
    f'<script src="/static/{name}?v={{{{ app_version }}}}"></script>'
    for name in (
        "operations-state.js",
        "operations-socket.js",
        "operations-sources.js",
        "operations-records.js",
        "operations-archive.js",
        "operations-config.js",
        "operations-actions.js",
        "operations-update.js",
        "operations-center.js",
    )
)
for script in operations_scripts:
    if script not in template:
        raise SystemExit(f"template must reference operations script: {script}")
operations_positions = [template.find(script) for script in operations_scripts]
if operations_positions != sorted(operations_positions):
    raise SystemExit("operations scripts must load in dependency order")
if operations_positions[-1] > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("operations scripts must load before static/app.js")

for required in (
    "function registerOperationsSocketHandlers",
    "function renderSourceHealth",
    "function renderRecentOpsRecords",
    "function previewDataArchive",
    "function renderConfigImportPreview",
    "function applyUpdateStatus",
):
    if required not in operations_module_js:
        raise SystemExit(f"operations modules missing contract: {required}")

for moved in (
    "function registerOperationsSocketHandlers",
    "function renderSourceHealth",
    "function previewDataArchive",
    "function applyUpdateStatus",
):
    if moved in operations_js_path.read_text(encoding="utf-8"):
        raise SystemExit(f"operations center keeps extracted implementation: {moved}")

history_review_script = '<script src="/static/history-review-center.js?v={{ app_version }}"></script>'
if history_review_script not in template:
    raise SystemExit("template must reference versioned /static/history-review-center.js")

if template.find(history_review_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("history review center script must load before static/app.js")

risk_analysis_script = '<script src="/static/risk-analysis-center.js?v={{ app_version }}"></script>'
if risk_analysis_script not in template:
    raise SystemExit("template must reference versioned /static/risk-analysis-center.js")

if template.find(risk_analysis_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("risk analysis center script must load before static/app.js")

alert_rule_scripts = tuple(
    f'<script src="/static/{name}?v={{{{ app_version }}}}"></script>'
    for name in (
        "alert-rule-state.js",
        "alert-rule-socket.js",
        "alert-rule-list.js",
        "alert-rule-detail.js",
        "alert-rule-editor.js",
        "alert-rule-render.js",
        "alert-rule-legacy.js",
        "alert-rule-center.js",
    )
)
for script in alert_rule_scripts:
    if script not in template:
        raise SystemExit(f"template must reference alert rule script: {script}")
alert_rule_positions = [template.find(script) for script in alert_rule_scripts]
if alert_rule_positions != sorted(alert_rule_positions):
    raise SystemExit("alert rule scripts must load in dependency order")
if alert_rule_positions[-1] > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("alert rule scripts must load before static/app.js")

alert_configuration_script = '<script src="/static/alert-configuration-center.js?v={{ app_version }}"></script>'
if alert_configuration_script not in template:
    raise SystemExit("template must reference versioned /static/alert-configuration-center.js")

if template.find(alert_configuration_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("alert configuration center script must load before static/app.js")

portfolio_script = '<script src="/static/portfolio-center.js?v={{ app_version }}"></script>'
portfolio_scripts = tuple(
    f'<script src="/static/{name}?v={{{{ app_version }}}}"></script>'
    for name in (
        "portfolio-state.js",
        "portfolio-render.js",
        "portfolio-detail.js",
        "portfolio-list.js",
        "portfolio-actions.js",
        "portfolio-import.js",
        "portfolio-center.js",
    )
)
for script in portfolio_scripts:
    if script not in template:
        raise SystemExit(f"template must reference portfolio script: {script}")

portfolio_positions = [template.find(script) for script in portfolio_scripts]
if portfolio_positions != sorted(portfolio_positions):
    raise SystemExit("portfolio scripts must load in dependency order")
if portfolio_positions[-1] > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("portfolio scripts must load before static/app.js")

alert_log_script = '<script src="/static/alert-log-center.js?v={{ app_version }}"></script>'
if alert_log_script not in template:
    raise SystemExit("template must reference versioned /static/alert-log-center.js")

if template.find(alert_log_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("alert log center script must load before static/app.js")

for required in (
    "function registerAlertLogSocketHandlers",
    "function showAlertModal",
    "function renderAlertLog",
    "function flashTitle",
):
    if required not in alert_log_js:
        raise SystemExit(f"static/alert-log-center.js missing alert log contract: {required}")

if "registerAlertLogSocketHandlers(socket);" not in app_js:
    raise SystemExit("static/app.js must register alert log socket handlers")

if "registerAlertRuleSocketHandlers(socket);" not in app_js:
    raise SystemExit("static/app.js must register alert rule socket handlers")

if "registerAlertConfigurationSocketHandlers(socket);" not in app_js:
    raise SystemExit("static/app.js must register alert configuration socket handlers")

if "registerPortfolioSocketHandlers(socket);" not in app_js:
    raise SystemExit("static/app.js must register portfolio socket handlers")

if "registerMarketDashboardSocketHandlers(socket);" not in app_js:
    raise SystemExit("static/app.js must register market dashboard socket handlers")

for required in (
    "function applyMarketInitialState",
    "function registerMarketDashboardSocketHandlers",
    "function switchMode",
    "function switchChartPeriod",
    "function applyFetchStatus",
    "function updatePriceDisplay",
):
    if required not in market_dashboard_js:
        raise SystemExit(f"static/market-dashboard.js missing market dashboard contract: {required}")

for moved in (
    "function switchMode",
    "function switchChartPeriod",
    "function applyFetchStatus",
    "function updatePriceDisplay",
    "socket.on('price_update'",
):
    if moved in app_js:
        raise SystemExit(f"static/app.js keeps extracted market dashboard implementation: {moved}")

for required in (
    "function registerAlertRuleSocketHandlers",
    "let alertRulesState",
    "let alertRuleDraft",
    "socket.on('alert_rule_duplicated'",
):
    if required not in alert_rule_js:
        raise SystemExit(f"alert rule modules missing contract: {required}")

for moved in (
    "function registerAlertRuleSocketHandlers",
    "let alertRulesState",
    "function buildUnifiedAlertRuleEditor",
    "function renderAlertRuleCenter",
):
    if moved in alert_rule_js_path.read_text(encoding="utf-8"):
        raise SystemExit(f"alert rule center keeps extracted implementation: {moved}")

for required in (
    "function registerAlertConfigurationSocketHandlers",
    "function applyAlertConfigurationState",
    "let alertProfiles",
    "let watchTargets",
    "socket.on('thresholds_updated'",
    "socket.on('watch_targets_updated'",
):
    if required not in alert_configuration_js:
        raise SystemExit(f"static/alert-configuration-center.js missing extracted configuration contract: {required}")

for moved in (
    "let alertProfiles",
    "let alertRulesState",
    "let watchTargets",
    "function normalizeAlertProfiles",
    "function normalizeWatchTargetItems",
    "socket.on('alert_rules_updated'",
    "socket.on('alert_profiles_updated'",
):
    if moved in app_js:
        raise SystemExit(f"static/app.js keeps extracted alert configuration implementation: {moved}")

for moved in (
    "let alertEntries = [];",
    "function showAlertModal",
    "function renderAlertLog",
    "socket.on('alert'",
):
    if moved in app_js:
        raise SystemExit(f"static/app.js keeps extracted alert log implementation: {moved}")

for required in (
    "function registerPortfolioSocketHandlers",
    "socketClient.on('portfolio_updated'",
    "socketClient.on('portfolio_import_previewed'",
    "socketClient.on('portfolio_analytics_updated'",
):
    if required not in portfolio_js:
        raise SystemExit(f"static/portfolio-center.js missing extracted portfolio contract: {required}")

for required in (
    "function normalizePortfolioState",
    "function renderPortfolio",
    "function renderPortfolioPositionDetail",
    "function renderPortfolioPositions",
    "function savePortfolioTransaction",
    "function previewPortfolioImport",
):
    if required not in portfolio_module_js:
        raise SystemExit(f"portfolio modules missing contract: {required}")

for moved in (
    "function normalizePortfolioState",
    "function renderPortfolio",
    "function savePortfolioTransaction",
    "function previewPortfolioImport",
):
    if moved in portfolio_js:
        raise SystemExit(f"static/portfolio-center.js keeps extracted implementation: {moved}")

for moved in (
    "socket.on('portfolio_updated'",
    "socket.on('portfolio_import_previewed'",
    "socket.on('portfolio_analytics_updated'",
):
    if moved in app_js:
        raise SystemExit(f"static/app.js keeps extracted portfolio implementation: {moved}")

if '"index.html"' not in http_routes_py or "app_version=app_version" not in http_routes_py:
    raise SystemExit("HTTP routes must inject app_version into index.html")

if 'id="chartEmptyState"' not in template:
    raise SystemExit("template must expose chart empty state overlay")

for required in ('data-period="30d"', 'data-period="90d"', 'value="43200"', 'value="129600"'):
    if required not in template:
        raise SystemExit(f"frontend missing long history range: {required}")

for required in ("resolution_seconds", "chartResolutionDate", "43200", "129600"):
    if required not in js:
        raise SystemExit(f"frontend missing multi-resolution history contract: {required}")

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

for required in (
    'id="alertRuleSelectVisible"',
    'id="alertRuleBatchBar"',
    'oninput="setAlertRuleSearch(this.value)"',
    'onchange="setAlertRuleStatusFilter(this.value)"',
    "function batchUpdateSelectedAlertRules",
    "function buildAlertRuleDetail",
    "function buildAlertRuleSimulationPanel",
    "function simulateUnifiedAlertRule",
    "function alertRuleSimulationValueText",
    "function alertRuleSimulationPortfolioMeta",
    "socket.emit('batch_update_alert_rules'",
    "socket.emit('get_alert_rule_insight'",
    "socket.emit('simulate_alert_rule'",
    "socket.on('alert_rule_insight'",
    "socket.on('alert_rule_simulation'",
    "socket.on('alert_rule_simulation_error'",
):
    if required not in template + js:
        raise SystemExit(f"frontend missing alert rule operations contract: {required}")

if "当前没有历史持仓估值快照，本版不模拟持仓规则" in js:
    raise SystemExit("frontend must allow portfolio alert rule history simulation")

for required in (
    ".alert-center-tools",
    ".alert-center-batch.active",
    ".alert-center-detail",
    ".alert-center-inspection-grid",
    ".alert-center-insight-grid",
    ".alert-center-simulation-grid",
    ".alert-center-simulation-distribution",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing alert rule operations selector: {required}")

for required in (
    'id="floatingTopmostRow"',
    'id="setFloatingAlwaysOnTop"',
    'floating_price_always_on_top',
    'id="floatingFullscreenRow"',
    'id="setFloatingHideOnFullscreen"',
    'floating_price_hide_on_fullscreen',
    'id="floatingLockRow"',
    'id="setFloatingLockPosition"',
    'floating_price_lock_position',
):
    if required not in template + js:
        raise SystemExit(f"frontend missing floating behavior setting: {required}")

for required in (
    'id="floatingWindowsModeRow"',
    'id="setFloatingWindowsMode"',
    'id="taskbarPriceStatus"',
    'value="floating"',
    'value="taskbar"',
    'value="both"',
    'floating_price_windows_mode',
    'has_taskbar_price',
    'taskbar_price_state',
):
    if required not in template + js:
        raise SystemExit(f"frontend missing Windows price display mode: {required}")

for required in (
    "Shell_TrayWnd",
    "TrayNotifyWnd",
    "MSTaskListWClass",
    "WS_EX_NOACTIVATE",
    "taskbar_is_auto_hidden",
):
    if required not in taskbar_runtime_py:
        raise SystemExit(f"taskbar runtime missing safety contract: {required}")

for tracked_id in (
    "setFloatingWindowsMode",
    "setFloatingHideOnFullscreen",
    "setFloatingLockPosition",
):
    if f"'{tracked_id}'" not in settings_state_js:
        raise SystemExit(
            f"frontend floating behavior setting is not tracked for saving: {tracked_id}"
        )

for required in (
    "HWND_NOTOPMOST",
    "floating_window_z_order(get_settings())",
    "should_hide_for_fullscreen",
    "FLOATING_VISIBILITY_TIMER_ID",
):
    if required not in floating_runtime_py:
        raise SystemExit(f"floating runtime missing z-order contract: {required}")

if "WS_EX_NOACTIVATE" not in floating_runtime_py:
    raise SystemExit("floating runtime missing non-activating window style")

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

for required in (
    'class="settings-modal settings-primary-modal"',
    'class="settings-workspace"',
    'aria-orientation="vertical"',
    'class="setting-section setting-section-danger"',
    'id="settingsUnsavedConfirm"',
    'id="settingsDirtyState"',
    'id="settingsSaveButton"',
    'function captureSettingsSnapshot',
    'function validateSettings',
    'function handleSettingsTabKeydown',
    'function handleSettingsDialogKeydown',
    'SETTINGS_TAB_STORAGE_KEY',
):
    if required not in template + js:
        raise SystemExit(f"frontend missing settings workspace contract: {required}")

for required in (
    '.settings-primary-modal',
    '.settings-workspace',
    '.settings-sidebar',
    '.setting-section',
    '.settings-unsaved',
    '.setting-field-error',
    'grid-template-columns:132px minmax(0, 1fr)',
    'grid-template-columns:106px minmax(0, 1fr)',
    '.settings-tab small { display:none; }',
):
    if required not in css:
        raise SystemExit(f"static/app.css missing settings workspace selector: {required}")

if '.settings-workspace { display:flex; flex-direction:column; }' in css:
    raise SystemExit("settings navigation must remain on the left at narrow widths")

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
    "function renderMarketQualityDetails",
    "quality.deductions",
    "function renderSourceManager",
    "function updateMarketSourceEnabled",
    "function moveMarketSource",
    "function retryMarketSource",
    "function resetMarketSources",
    "update_market_sources",
    "retry_market_source",
    "当前主源",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing market source management contract: {required}")

for required in (
    'id="marketQualityDetails"',
    'id="sourceManager"',
    'id="sourceManagerStatus"',
):
    if required not in template:
        raise SystemExit(f"template missing market source management anchor: {required}")

for required in (
    ".market-quality-details",
    ".source-manager",
    ".source-manager-row",
    ".source-manager-current",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing market source management selector: {required}")

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
    'id="riskCompareButton"',
    'id="riskComparison"',
):
    if required not in template:
        raise SystemExit(f"template missing risk history comparison anchor: {required}")

for required in (
    "riskComparisonSelection",
    "function toggleRiskComparisonItem",
    "function compareSelectedRiskHistory",
    "function renderRiskComparison",
    "记录一",
    "记录二",
    "data-side-label",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing risk history comparison contract: {required}")

if not re.search(r"riskComparisonSelection\.length\s*(?:>=\s*2|>\s*1)", js):
    raise SystemExit("risk history comparison must limit selection to two entries")

apply_risk_history_pos = js.find("function applyRiskHistory")
next_function_pos = js.find("\nfunction ", apply_risk_history_pos + 1)
risk_history_block = js[apply_risk_history_pos:next_function_pos if next_function_pos >= 0 else len(js)]
if apply_risk_history_pos < 0 or not re.search(r"riskComparisonSelection\s*=\s*\[\s*\]", risk_history_block):
    raise SystemExit("applyRiskHistory must reset transient risk comparison selection")

compare_risk_history_pos = js.find("function compareSelectedRiskHistory")
next_function_pos = js.find("\nfunction ", compare_risk_history_pos + 1)
compare_risk_history_block = js[
    compare_risk_history_pos:next_function_pos if next_function_pos >= 0 else len(js)
]
if compare_risk_history_pos < 0:
    raise SystemExit("static/app.js must implement risk history comparison")
for forbidden in ("socket.emit", "requestRiskAnalysis"):
    if forbidden in compare_risk_history_block:
        raise SystemExit(f"risk history comparison must remain frontend-only: {forbidden}")

if "不会调用模型" not in template + js:
    raise SystemExit("risk history comparison UI must state that comparison does not call the model")

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

if ".risk-comparison-row" not in css:
    raise SystemExit("static/app.css missing risk history comparison row selector")

if "content:attr(data-side-label)" not in css:
    raise SystemExit("static/app.css must render risk comparison side labels from row attributes")

if not re.search(r"@media\s*\([^)]*max-width[^)]*\)[\s\S]*?\.risk-comparison-row", css):
    raise SystemExit("static/app.css must adapt risk history comparison rows for mobile widths")

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
    "configImportPreviewRequestPayload",
    "function renderConfigImportPreview",
    "function configImportFormatText",
    "schema_version",
    "expected_schema_version",
    "needs_migration",
    "source_app_version",
    "当前备份格式：",
    "旧版备份将在导入时迁移",
    "备份内容已变更，请重新预检",
    "function invalidateConfigImportPreviewOnInput",
    "configImportTextInput.addEventListener('input', invalidateConfigImportPreviewOnInput)",
    "ignored.alert_profiles",
    "忽略重复、无效或超限策略模板",
    "再次点击导入确认",
    "if (section === 'alert_profiles') return '预警策略模板';",
):
    if required not in js:
        raise SystemExit(f"static/app.js missing config import preview contract: {required}")

preview_response_pos = js.find("socket.on('config_import_previewed', data => {")
preview_response_end = js.find("socket.on('config_import_result'", preview_response_pos)
preview_response_block = js[preview_response_pos:preview_response_end]
if not re.search(r"previewedPayload\s*!==\s*text", preview_response_block):
    raise SystemExit("config import preview response must be rejected after the textarea changes")

invalidate_preview_pos = js.find("function invalidateConfigImportPreviewOnInput")
invalidate_preview_end = js.find("\nfunction ", invalidate_preview_pos + 1)
invalidate_preview_block = js[
    invalidate_preview_pos:invalidate_preview_end if invalidate_preview_end >= 0 else len(js)
]
for required in (
    "configImportPreviewRequestPayload = null",
    "pendingConfigImportPayload = null",
    "pendingConfigImportPreview = null",
    "备份内容已变更，请重新预检。",
):
    if invalidate_preview_pos < 0 or required not in invalidate_preview_block:
        raise SystemExit(f"config import input must invalidate preview state immediately: {required}")

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
    "state.alert_profiles || {}",
    "ALERT_PROFILE_SETTING_KEYS",
):
    if required not in alert_configuration_js and required not in app_js:
        raise SystemExit(f"frontend scripts missing alert profile UI contract: {required}")

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
    handler_source = alert_configuration_js if handler != "socket.on('settings_updated', data => {" else js
    handler_pos = handler_source.find(handler)
    next_handler_pos = handler_source.find("socket.on(", handler_pos + len(handler))
    handler_body = handler_source[handler_pos:next_handler_pos if next_handler_pos >= 0 else len(handler_source)] if handler_pos >= 0 else ""
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
    "if (nextTab === 'digest') socket.emit('get_daily_digest_status')",
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
):
    if required not in app_py:
        raise SystemExit(f"application module missing review note contract: {required}")

history_review_socket_py = (root / "goldmonitor" / "socket_history_review.py").read_text(encoding="utf-8")
for required in (
    '@socketio.on("save_review_note")',
    '@socketio.on("delete_review_note")',
):
    if required not in history_review_socket_py:
        raise SystemExit(f"history review socket module missing review note contract: {required}")

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
