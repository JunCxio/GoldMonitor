import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_background_task_auto_refresh_lifecycle():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行前端生命周期测试")

    state_source = (ROOT / "static" / "operations-state.js").read_text(encoding="utf-8")
    tasks_source = (ROOT / "static" / "operations-tasks.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');

const elements = {{
  settingsBackdrop: {{
    classList: {{ contains: name => name === 'show' && backdropVisible }},
  }},
  btnRefreshBackgroundTasks: {{
    disabled: false,
    textContent: '刷新状态',
    attributes: {{}},
    setAttribute(name, value) {{ this.attributes[name] = value; }},
    closest() {{ return taskCard; }},
  }},
}};
const taskCard = {{
  attributes: {{}},
  setAttribute(name, value) {{ this.attributes[name] = value; }},
}};
const documentListeners = {{}};
const windowListeners = {{}};
const intervals = new Map();
const timeouts = new Map();
const emits = [];
let nextTimerId = 1;
let backdropVisible = true;

const context = {{
  console,
  document: {{
    visibilityState: 'visible',
    getElementById: id => elements[id] || null,
    addEventListener: (name, handler) => {{ documentListeners[name] = handler; }},
  }},
  window: {{
    setInterval(handler, delay) {{
      const id = nextTimerId++;
      intervals.set(id, {{ handler, delay }});
      return id;
    }},
    clearInterval(id) {{ intervals.delete(id); }},
    setTimeout(handler, delay) {{
      const id = nextTimerId++;
      timeouts.set(id, {{ handler, delay }});
      return id;
    }},
    clearTimeout(id) {{ timeouts.delete(id); }},
    addEventListener: (name, handler) => {{ windowListeners[name] = handler; }},
  }},
  socket: {{ emit: name => emits.push(name) }},
  activeSettingsTab: 'ops',
  escapeHtml: value => String(value),
  setOpsStatus() {{}},
}};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__STATE_SOURCE__, context);
vm.runInContext(__TASKS_SOURCE__, context);

const evaluate = expression => vm.runInContext(expression, context);
const assert = (condition, message) => {{ if (!condition) throw new Error(message); }};

evaluate('syncBackgroundTaskAutoRefresh()');
assert(emits.length === 1, 'entering operations must request status immediately');
assert(intervals.size === 1, 'entering operations must create one interval');
assert(!elements.btnRefreshBackgroundTasks.disabled, 'automatic refresh must keep the manual action available');
assert(elements.btnRefreshBackgroundTasks.textContent === '刷新状态', 'automatic refresh must not change button label');

evaluate('syncBackgroundTaskAutoRefresh()');
assert(emits.length === 1, 'repeated sync must not duplicate the request while pending');
assert(intervals.size === 1, 'repeated sync must not duplicate the interval');

evaluate('refreshBackgroundTaskStatus()');
assert(emits.length === 1, 'manual refresh during a pending request must reuse that request');
assert(elements.btnRefreshBackgroundTasks.disabled, 'manual refresh must disable its button');
assert(elements.btnRefreshBackgroundTasks.textContent === '正在刷新', 'manual refresh must expose progress');

evaluate('applyBackgroundTaskStatus({ tasks: [], summary: {} })');
assert(!elements.btnRefreshBackgroundTasks.disabled, 'response must restore refresh button');
assert(elements.btnRefreshBackgroundTasks.textContent === '刷新状态', 'response must restore button label');
assert(timeouts.size === 0, 'response must clear request timeout');

const interval = Array.from(intervals.values())[0];
interval.handler();
assert(emits.length === 2, 'active interval must refresh status');
evaluate('applyBackgroundTaskStatus({ tasks: [], summary: {} })');

context.activeSettingsTab = 'general';
evaluate('syncBackgroundTaskAutoRefresh()');
assert(intervals.size === 0, 'leaving operations must clear the interval');

context.activeSettingsTab = 'ops';
evaluate('syncBackgroundTaskAutoRefresh()');
assert(emits.length === 3, 'returning to operations must refresh immediately');
assert(intervals.size === 1, 'returning to operations must create one interval');
evaluate('applyBackgroundTaskStatus({ tasks: [], summary: {} })');

context.document.visibilityState = 'hidden';
documentListeners.visibilitychange();
assert(intervals.size === 0, 'hidden page must clear the interval');

context.document.visibilityState = 'visible';
documentListeners.visibilitychange();
assert(emits.length === 4, 'visible page must refresh immediately');
assert(intervals.size === 1, 'visible page must restore one interval');
evaluate('applyBackgroundTaskStatus({ tasks: [], summary: {} })');

backdropVisible = false;
evaluate('syncBackgroundTaskAutoRefresh()');
assert(intervals.size === 0, 'closed settings must clear the interval');

backdropVisible = true;
evaluate('syncBackgroundTaskAutoRefresh()');
assert(emits.length === 5, 'reopened operations must refresh immediately');
const timeout = Array.from(timeouts.values())[0];
assert(timeout.delay === 10000, 'request timeout must use the configured duration');
timeout.handler();
assert(!elements.btnRefreshBackgroundTasks.disabled, 'timeout must restore refresh button');
evaluate('refreshBackgroundTaskStatus()');
assert(emits.length === 6, 'timeout must allow a later manual refresh');
assert(elements.btnRefreshBackgroundTasks.textContent === '正在刷新', 'manual refresh must expose progress');

windowListeners.pagehide();
assert(intervals.size === 0, 'pagehide must clear the interval');
"""
    script = script.replace("{{", "{").replace("}}", "}")
    script = script.replace("__STATE_SOURCE__", json.dumps(state_source)).replace(
        "__TASKS_SOURCE__", json.dumps(tasks_source)
    )

    result = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
