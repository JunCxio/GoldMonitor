import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
  id: 'plan-window', start_date: '2026-09-01', end_date: '2026-12-31'
})`, context);
if (plan.start_date !== '2026-09-01' || plan.end_date !== '2026-12-31') {
  throw new Error('execution window must survive portfolio state normalization');
}
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_duplicate_investment_plan_creates_paused_new_draft_without_socket_write():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = (ROOT / "static" / "portfolio-investment.js").read_text(encoding="utf-8")
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

    source = (ROOT / "static" / "portfolio-investment.js").read_text(encoding="utf-8")
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
