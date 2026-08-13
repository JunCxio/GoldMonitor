import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_investment_source():
    return "\n".join(
        (ROOT / "static" / name).read_text(encoding="utf-8")
        for name in ("portfolio-investment.js", "portfolio-investment-actions.js")
    )


def test_investment_plan_state_preserves_execution_window():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = (ROOT / "static" / "portfolio-state.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = { console };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const plan = vm.runInContext(`normalizePortfolioInvestmentPlan({
  id: 'plan-window', start_date: '2026-09-01', end_date: '2026-12-31',
  archived_at: '2027-01-01T10:00:00',
  upcoming_run_ats: ['2026-09-01T09:00:00', '2026-10-01T09:00:00'],
  pending_run_at: '2026-09-01T09:00:00', last_skipped_at: '2026-08-13T10:00:00',
  last_skipped_scheduled_at: '2026-08-01T09:00:00', skip_count: 2
})`, context);
if (plan.start_date !== '2026-09-01' || plan.end_date !== '2026-12-31') {
  throw new Error('execution window must survive portfolio state normalization');
}
if (plan.archived_at !== '2027-01-01T10:00:00') {
  throw new Error('archive state must survive portfolio state normalization');
}
if (plan.pending_run_at !== '2026-09-01T09:00:00' || plan.skip_count !== 2) {
  throw new Error('skip state must survive portfolio state normalization');
}
if (plan.upcoming_run_ats.length !== 2 || plan.upcoming_run_ats[1] !== '2026-10-01T09:00:00') {
  throw new Error('future schedule must survive portfolio state normalization');
}
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_duplicate_investment_plan_creates_paused_new_draft_without_socket_write():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');

const emits = [];
const statuses = [];
let renderCount = 0;
const plan = {
  id: 'plan-source',
  name: '每周积存',
  position_id: 'position-1',
  position_name: '积存金',
  mode: 'rmb',
  amount: 1000,
  fee: 2,
  frequency: 'weekly',
  weekday: 5,
  time: '09:00',
  month: 1,
  day: 1,
  start_date: '2026-09-01',
  end_date: '2027-08-31',
  enabled: true,
};
const context = {
  console,
  portfolioState: { investment_plans: { items: [plan] } },
  portfolioInvestmentDrafts: {},
  portfolioInvestmentDraftNotice: '',
  activePortfolioInvestmentPlanId: null,
  portfolioView: 'position',
  pendingPortfolioSave: null,
  currentMode: 'rmb',
  socket: { emit: (...args) => emits.push(args) },
  setPortfolioStatus: (message, state) => statuses.push({ message, state }),
  renderPortfolio: () => { renderCount += 1; },
  document: { getElementById: () => null },
  window: { confirm: () => true },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);

vm.runInContext("duplicatePortfolioInvestmentPlan('plan-source')", context);
const draft = context.portfolioInvestmentDrafts.new;
const assert = (condition, message) => { if (!condition) throw new Error(message); };

assert(draft.id === 'new', 'duplicate must create a new draft identity');
assert(draft.name === '每周积存 副本', 'duplicate must create a recognizable copy name');
assert(draft.position_id === 'position-1', 'duplicate must preserve linked position');
assert(draft.frequency === 'weekly' && draft.weekday === '5', 'duplicate must preserve weekly schedule');
assert(draft.amount === '1000' && draft.fee === '2', 'duplicate must preserve amount and fee');
assert(draft.start_date === '2026-09-01' && draft.end_date === '2027-08-31', 'duplicate must preserve execution window');
assert(draft.enabled === false, 'duplicate must default to paused');
assert(context.activePortfolioInvestmentPlanId === 'new', 'duplicate must open the new draft');
assert(context.portfolioView === 'investment', 'duplicate must remain in investment view');
assert(emits.length === 0, 'duplicate must not persist or execute before save');
assert(renderCount === 1, 'duplicate must render the new draft once');
assert(statuses.at(-1).state === 'ok', 'duplicate must report draft creation');
assert(context.portfolioInvestmentDraftNotice.includes('确认后再保存'), 'duplicate notice must survive portfolio refreshes');
assert(plan.enabled === true && plan.name === '每周积存', 'duplicate must not mutate source plan');

context.window.confirm = () => false;
context.portfolioInvestmentDrafts.new.name = '用户正在编辑的草稿';
vm.runInContext("duplicatePortfolioInvestmentPlan('plan-source')", context);
assert(context.portfolioInvestmentDrafts.new.name === '用户正在编辑的草稿', 'cancelled replacement must preserve current draft');
assert(emits.length === 0, 'cancelled replacement must not write to backend');
"""
    script = script.replace("__SOURCE__", json.dumps(source))

    result = subprocess.run(
        [node, "-e", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_validates_execution_window_before_socket_write():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const emits = [];
const statuses = [];
const values = {
  Name: '阶段定投', PositionId: '', PositionName: '积存金', Mode: 'rmb',
  Amount: '1000', Fee: '0', Frequency: 'monthly', Time: '09:00',
  Month: '1', Day: '15', Weekday: '1', StartDate: '2026-12-01',
  EndDate: '2026-11-30', Enabled: true,
};
const context = {
  console, portfolioState: { items: [], investment_plans: { items: [] } },
  portfolioInvestmentDrafts: {}, portfolioInvestmentDraftNotice: '',
  pendingPortfolioSave: null, currentMode: 'rmb',
  document: { getElementById: id => {
    const field = id.match(/^portfolioInvestment(.+)_new$/)?.[1];
    if (!field || !(field in values)) return null;
    return { type: field === 'Enabled' ? 'checkbox' : 'text', value: values[field], checked: values[field] };
  } },
  socket: { emit: (...args) => emits.push(args) },
  setPortfolioStatus: (message, state) => statuses.push({ message, state }),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("savePortfolioInvestmentPlan('new')", context);
if (emits.length !== 0) throw new Error('invalid execution window must not be saved');
if (!statuses.at(-1).message.includes('结束日期不能早于开始日期')) throw new Error('invalid execution window must report a clear error');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_confirms_skip_and_sends_expected_run():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const emits = [];
const statuses = [];
let confirmed = false;
const plan = { id: 'plan-1', enabled: true, pending_run_at: '2026-08-15T09:00:00' };
const context = {
  console,
  portfolioState: { investment_plans: { items: [plan] } },
  socket: { emit: (...args) => emits.push(args) },
  setPortfolioStatus: (message, state) => statuses.push({ message, state }),
  window: { confirm: () => confirmed },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("skipPortfolioInvestmentPlan('plan-1', '2026-08-15T09:00:00')", context);
if (emits.length !== 0) throw new Error('cancelled skip must not emit');
confirmed = true;
vm.runInContext("skipPortfolioInvestmentPlan('plan-1', '2026-08-15T09:00:00')", context);
if (emits.length !== 1 || emits[0][0] !== 'skip_portfolio_investment_plan') throw new Error('confirmed skip must emit once');
if (emits[0][1].id !== 'plan-1' || emits[0][1].scheduled_at !== '2026-08-15T09:00:00') throw new Error('skip must send the expected run identity');
if (!statuses.at(-1).message.includes('正在跳过')) throw new Error('skip must report progress');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_requests_preview_and_ignores_stale_response():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const emits = [];
let renderCount = 0;
const values = {
  Name: '月末定投', PositionId: '', PositionName: '积存金', Mode: 'rmb',
  Amount: '1000', Fee: '0', Frequency: 'monthly', Time: '09:00',
  Month: '1', Day: '31', Weekday: '1', StartDate: '2026-09-01',
  EndDate: '2026-12-31', Enabled: true,
};
const context = {
  console,
  currentMode: 'rmb',
  portfolioState: { items: [], investment_plans: { items: [] } },
  portfolioInvestmentDrafts: {},
  portfolioInvestmentSchedulePreviews: {},
  portfolioInvestmentSchedulePreviewSeq: 0,
  socket: { emit: (...args) => emits.push(args) },
  renderPortfolio: () => { renderCount += 1; },
  document: { getElementById: id => {
    const field = id.match(/^portfolioInvestment(.+)_new$/)?.[1];
    if (!field || !(field in values)) return null;
    return { type: field === 'Enabled' ? 'checkbox' : 'text', value: values[field], checked: values[field] };
  } },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("requestPortfolioInvestmentSchedulePreview('new')", context);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
assert(emits.length === 1 && emits[0][0] === 'preview_portfolio_investment_schedule', 'preview request must emit once');
assert(emits[0][1].id === '' && emits[0][1].day === 31, 'new preview must send current schedule without a persisted id');
assert(context.portfolioInvestmentSchedulePreviews.new.loading === true, 'preview must expose loading state');
vm.runInContext("applyPortfolioInvestmentSchedulePreview({id:'new', request_id:'0', ok:true, items:['stale']})", context);
assert(context.portfolioInvestmentSchedulePreviews.new.loading === true, 'stale response must be ignored');
vm.runInContext("applyPortfolioInvestmentSchedulePreview({id:'new', request_id:'1', ok:true, items:['2026-09-30T09:00:00']})", context);
assert(context.portfolioInvestmentSchedulePreviews.new.items[0] === '2026-09-30T09:00:00', 'latest response must update preview');
assert(renderCount === 2, 'request and accepted response must each render once');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_archives_restores_and_guards_permanent_delete():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const emits = [];
const statuses = [];
let confirmed = true;
const active = { id: 'active-plan', archived_at: '' };
const archived = { id: 'archived-plan', archived_at: '2026-08-12T10:00:00' };
const context = {
  console,
  portfolioState: { investment_plans: { items: [active, archived] } },
  socket: { emit: (...args) => emits.push(args) },
  setPortfolioStatus: (message, state) => statuses.push({ message, state }),
  window: { confirm: () => confirmed },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("archivePortfolioInvestmentPlan('active-plan')", context);
vm.runInContext("restorePortfolioInvestmentPlan('archived-plan')", context);
vm.runInContext("deletePortfolioInvestmentPlan('active-plan')", context);
vm.runInContext("deletePortfolioInvestmentPlan('archived-plan')", context);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
assert(emits[0][0] === 'archive_portfolio_investment_plan', 'active plan must archive');
assert(emits[1][0] === 'restore_portfolio_investment_plan', 'archived plan must restore');
assert(statuses.some(item => item.message.includes('请先归档')), 'active plan permanent delete must be rejected');
assert(emits[2][0] === 'delete_portfolio_investment_plan' && emits[2][1].id === 'archived-plan', 'archived plan may be permanently deleted');
confirmed = false;
vm.runInContext("archivePortfolioInvestmentPlan('active-plan')", context);
assert(emits.length === 3, 'cancelled archive must not emit');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
