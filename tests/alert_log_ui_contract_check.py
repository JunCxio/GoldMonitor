from pathlib import Path


root = Path(__file__).resolve().parents[1]
template = (root / "templates" / "index.html").read_text(encoding="utf-8")
alert_log_js = (root / "static" / "alert-log-center.js").read_text(encoding="utf-8")
app_js = (root / "static" / "app.js").read_text(encoding="utf-8")
js = "\n".join((alert_log_js, app_js))
css = (root / "static" / "app.css").read_text(encoding="utf-8")


alert_log_script = '<script src="/static/alert-log-center.js?v={{ app_version }}"></script>'
if alert_log_script not in template:
    raise SystemExit("alert log UI must load static/alert-log-center.js")

if template.find(alert_log_script) > template.find('<script src="/static/app.js?v={{ app_version }}"></script>'):
    raise SystemExit("alert log center must load before static/app.js")

if "registerAlertLogSocketHandlers(socket);" not in app_js:
    raise SystemExit("frontend must register alert log socket handlers")


for forbidden in (
    'value="pending"',
    'id="alertDetail"',
    'id="alertLogModeTabs"',
    'class="alert-log-tabs"',
    'class="alert-log-tab',
    "setAlertLogView(",
    "选择一条警报查看详情",
    "确认</button>",
    "未确认",
    "已确认",
    "处理状态",
    "读取状态",
    "function acknowledgeAlert",
    "function renderAlertDetail",
    "selectedAlertId",
    "acknowledged ?",
    "log-risk-action",
    "log-handled",
    "标记已处理",
    "取消处理",
):
    if forbidden in template or forbidden in js:
        raise SystemExit(f"alert log UI must not expose acknowledgement/detail workflow: {forbidden}")


for required in (
    'class="log-title-row"',
    'id="alertLogMenu"',
    "toggleAlertLogMenu",
    "renderAlertLog",
    "analyzeAlertFromLog",
    "resendAlertNotification",
    "{ label: '分析'",
    "if (hasNotificationIssue) actions.push",
    "重发通知",
    "alert-log-shell",
    "source-health-summary",
    "source-health-menu",
    "toggleSourceHealthMenu",
    "source-health-details",
):
    if required not in template and required not in js and required not in css:
        raise SystemExit(f"alert log UI missing compact monitor flow anchor: {required}")


print("alert log UI contract checks passed.")
