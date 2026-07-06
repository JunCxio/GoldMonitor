# 更新状态与诊断闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在设置页运维区展示更新状态，并把更新失败排查和诊断摘要复制串成一个闭环。

**Architecture:** 后端保留现有更新流程，新增运行时 `last_update_status` 作为最近一次脱敏更新状态。前端复用现有 `update_status` 事件和更新弹窗，在运维区增加状态摘要与操作入口。诊断摘要读取后端最近更新状态，不暴露下载 URL、SHA256、manifest URL 或本地安装包路径。

**Tech Stack:** Flask-SocketIO 后端、原生 JavaScript 前端、HTML 模板、CSS、现有 Python 契约测试。

---

## File Structure

- Modify `app.py`: 增加运行时更新状态快照、脱敏 helper、诊断摘要“更新状态”小节，并让 `check_update` / `install_update` 发出的状态同步记录。
- Modify `templates/index.html`: 在设置页运维区新增“更新状态”行和状态元素。
- Modify `static/app.js`: 新增运维区更新状态渲染、检查更新入口、打开更新入口，并让 `applyUpdateStatus` 同步两处 UI。
- Modify `static/app.css`: 补充运维区更新状态的紧凑样式。
- Modify `tests/frontend_asset_check.py`: 增加前端契约检查。
- Modify `tests/update_logic_check.py`: 增加后端更新状态脱敏与诊断摘要契约。
- Modify `tests/contract_checks.ps1`: 同步 Windows 发布契约。

### Task 1: 后端更新状态运行时快照

**Files:**
- Modify: `app.py`
- Test: `tests/update_logic_check.py`

- [ ] **Step 1: Write the failing backend test**

Add checks to `tests/update_logic_check.py` after the existing frontend metadata exposure assertions:

```python
app.record_update_status({
    "state": "error",
    "current_version": app.APP_VERSION,
    "latest_version": "9.9.9",
    "checked_at": "2026-07-06T10:00:00",
    "message": "检查更新失败：网络异常",
    "url": WINDOWS_ASSET_URL,
    "sha256": "a" * 64,
    "manifest_url": app.DEFAULT_UPDATE_MANIFEST_URL,
})
snapshot = app.get_last_update_status()
if snapshot.get("url") or snapshot.get("sha256") or snapshot.get("manifest_url"):
    raise SystemExit(f"last update status must hide installer metadata, got: {snapshot}")
if snapshot.get("state") != "error" or "网络异常" not in snapshot.get("message", ""):
    raise SystemExit(f"last update status must keep user-facing failure details, got: {snapshot}")
diagnostics_copy = app.build_diagnostics_clipboard_text()
if "更新状态" not in diagnostics_copy or "网络异常" not in diagnostics_copy:
    raise SystemExit(f"diagnostics copy must include update failure summary, got: {diagnostics_copy}")
if WINDOWS_ASSET_URL in diagnostics_copy or "sha256" in diagnostics_copy or app.DEFAULT_UPDATE_MANIFEST_URL in diagnostics_copy:
    raise SystemExit("diagnostics copy must not leak update installer metadata")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python tests/update_logic_check.py`

Expected: FAIL with `module 'app' has no attribute 'record_update_status'`.

- [ ] **Step 3: Implement minimal backend state**

Add near update manager helpers in `app.py`:

```python
last_update_status = {}
last_update_status_lock = threading.Lock()
PUBLIC_UPDATE_STATUS_KEYS = (
    "state",
    "current_version",
    "latest_version",
    "checked_at",
    "message",
    "notes",
    "progress_percent",
    "downloaded_bytes",
    "total_bytes",
)


def public_update_status(status=None):
    status = status if isinstance(status, dict) else {}
    return {key: status[key] for key in PUBLIC_UPDATE_STATUS_KEYS if key in status}


def record_update_status(status):
    snapshot = public_update_status(status)
    with last_update_status_lock:
        last_update_status.clear()
        last_update_status.update(snapshot)
    return dict(snapshot)


def get_last_update_status():
    with last_update_status_lock:
        return dict(last_update_status)


def emit_update_status(status):
    safe_status = record_update_status(status)
    emit("update_status", safe_status)
    return safe_status
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python tests/update_logic_check.py`

Expected: PASS after Task 2 adds diagnostic text usage.

### Task 2: 后端诊断摘要加入更新状态

**Files:**
- Modify: `app.py`
- Test: `tests/update_logic_check.py`

- [ ] **Step 1: Write failing assertion**

Use the `diagnostics_copy` assertion from Task 1. It must require the heading `更新状态` and the failure text.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python tests/update_logic_check.py`

Expected: FAIL because `build_diagnostics_clipboard_text()` does not include `更新状态`.

- [ ] **Step 3: Implement diagnostic section**

In `build_diagnostics_report()`, add:

```python
"last_update_status": get_last_update_status(),
```

In `build_diagnostics_clipboard_text()`, add:

```python
update_status = payload.get("last_update_status") if isinstance(payload.get("last_update_status"), dict) else get_last_update_status()
update_message = update_status.get("message") or ("尚未检查更新" if not update_status else "更新状态未知")
```

Insert after the `风险分析` section:

```python
"更新状态",
f"- 当前版本: {_diagnostics_value(update_status.get('current_version') or payload.get('version'))}",
f"- 最新版本: {_diagnostics_value(update_status.get('latest_version'))}",
f"- 检查状态: {_diagnostics_value(update_status.get('state'), '尚未检查')}",
f"- 检查时间: {_diagnostics_value(update_status.get('checked_at'))}",
f"- 状态说明: {update_message}",
"",
```

- [ ] **Step 4: Run backend tests**

Run:

```bash
.venv/bin/python tests/update_logic_check.py
.venv/bin/python tests/risk_contract_check.py
```

Expected: both PASS.

### Task 3: 后端更新事件统一记录状态

**Files:**
- Modify: `app.py`
- Test: `tests/update_logic_check.py`

- [ ] **Step 1: Replace update event emits**

In `on_check_update()` and `on_install_update()`, replace direct update status emits with `emit_update_status(...)`.

Examples:

```python
@socketio.on("check_update")
def on_check_update():
    try:
        emit_update_status(get_update_status())
    except ValueError as exc:
        emit_update_status({
            "state": "error",
            "current_version": APP_VERSION,
            "message": str(exc),
        })
```

For `socketio.emit(... room=request.sid)` inside progress callbacks, use:

```python
status = record_update_status({...})
socketio.emit("update_status", status, room=request.sid)
```

- [ ] **Step 2: Run backend tests**

Run:

```bash
.venv/bin/python tests/update_logic_check.py
.venv/bin/python tests/risk_contract_check.py
```

Expected: PASS.

### Task 4: 前端运维区更新状态入口

**Files:**
- Modify: `templates/index.html`
- Modify: `static/app.js`
- Modify: `static/app.css`
- Test: `tests/frontend_asset_check.py`

- [ ] **Step 1: Write failing frontend contract**

Add to `tests/frontend_asset_check.py`:

```python
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
```

Add CSS checks:

```python
for required in (
    ".ops-update-card",
    ".ops-update-status",
    ".ops-update-meta",
):
    if required not in css:
        raise SystemExit(f"static/app.css missing ops update selector: {required}")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python tests/frontend_asset_check.py`

Expected: FAIL with missing `opsUpdateStatus`.

- [ ] **Step 3: Add template row**

In `templates/index.html`, insert before the existing “诊断报告” row:

```html
<div class="setting-row">
  <div>
    <div class="setting-label">更新状态</div>
    <div class="setting-desc">查看当前版本、最近检查结果和失败原因，必要时复制诊断摘要。</div>
  </div>
  <div class="settings-stack ops-update-card">
    <div class="ops-update-copy">
      <div class="ops-update-status" id="opsUpdateStatus">尚未检查更新。</div>
      <div class="ops-update-meta" id="opsUpdateMeta">当前版本 {{ app_version }}</div>
    </div>
    <button class="settings-cancel btn-form" type="button" onclick="checkUpdateFromOps()">检查更新</button>
    <button class="settings-cancel btn-form" type="button" onclick="openUpdateFromOps()">打开更新</button>
    <button class="btn-set btn-form" type="button" onclick="copyDiagnostics()">复制诊断</button>
  </div>
</div>
```

- [ ] **Step 4: Add frontend functions**

In `static/app.js`, add:

```javascript
let opsUpdateStatus = null;

function renderOpsUpdateStatus(data) {
  opsUpdateStatus = data || opsUpdateStatus || null;
  const statusEl = document.getElementById('opsUpdateStatus');
  const metaEl = document.getElementById('opsUpdateMeta');
  if (!statusEl || !metaEl) return;
  const state = opsUpdateStatus && opsUpdateStatus.state ? opsUpdateStatus.state : '';
  const message = opsUpdateStatus && opsUpdateStatus.message ? opsUpdateStatus.message : '尚未检查更新。';
  const current = opsUpdateStatus && opsUpdateStatus.current_version ? '当前版本 ' + opsUpdateStatus.current_version : '';
  const latest = opsUpdateStatus && opsUpdateStatus.latest_version ? '最新版本 ' + opsUpdateStatus.latest_version : '';
  const checked = opsUpdateStatus && opsUpdateStatus.checked_at ? '检查时间 ' + String(opsUpdateStatus.checked_at).replace('T', ' ') : '';
  statusEl.textContent = message;
  statusEl.dataset.state = state || 'unknown';
  metaEl.textContent = [current, latest, checked].filter(Boolean).join(' · ') || metaEl.textContent || '';
}

function checkUpdateFromOps() {
  renderOpsUpdateStatus({ state: 'checking', current_version: appVersion || '', message: '正在检查更新...' });
  requestUpdateCheck(true);
  setOpsStatus('正在检查更新...', true);
}

function openUpdateFromOps() {
  openUpdate();
}
```

Also call `renderOpsUpdateStatus(data);` inside `applyUpdateStatus(data)`.

- [ ] **Step 5: Add CSS**

In `static/app.css`, add compact selectors:

```css
.ops-update-card { align-items:flex-end; max-width:min(520px, 100%); }
.ops-update-copy { min-width:180px; max-width:100%; flex:1 1 220px; text-align:left; }
.ops-update-status { color:var(--text); font-size:0.8rem; line-height:1.35; white-space:normal; overflow-wrap:anywhere; }
.ops-update-status[data-state="error"] { color:var(--up); }
.ops-update-status[data-state="available"] { color:var(--gold); }
.ops-update-meta { margin-top:4px; color:var(--text-dim); font-size:0.72rem; line-height:1.35; white-space:normal; overflow-wrap:anywhere; }
```

- [ ] **Step 6: Run frontend checks**

Run:

```bash
.venv/bin/python tests/frontend_asset_check.py
node --check static/app.js
```

Expected: both PASS.

### Task 5: Full Verification and Commit

**Files:**
- All modified files

- [ ] **Step 1: Run focused checks**

Run:

```bash
.venv/bin/python tests/frontend_asset_check.py
.venv/bin/python tests/update_logic_check.py
.venv/bin/python tests/risk_contract_check.py
node --check static/app.js
```

Expected: PASS.

- [ ] **Step 2: Run full checks**

Run:

```bash
.venv/bin/python -m pytest
PYTHONPYCACHEPREFIX=/private/tmp/goldmonitor-pycache .venv/bin/python -m py_compile app.py
git diff --check
```

Expected: PASS. `pytest` may show the existing LibreSSL warning only.

- [ ] **Step 3: Commit**

Run:

```bash
git add app.py static/app.js static/app.css templates/index.html tests/frontend_asset_check.py tests/update_logic_check.py tests/risk_contract_check.py tests/contract_checks.ps1
git commit -m "feat: 增强更新状态诊断闭环"
```

Expected: commit succeeds on branch `codex/update-diagnostics-loop`.
