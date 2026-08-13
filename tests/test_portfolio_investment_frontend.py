import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


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
