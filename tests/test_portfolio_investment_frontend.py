import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def read_investment_source():
    return "\n".join(
        (ROOT / "static" / name).read_text(encoding="utf-8")
        for name in (
            "portfolio-investment-list.js",
            "portfolio-investment-projection.js",
            "portfolio-investment.js",
            "portfolio-investment-actions.js",
        )
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
  target_count: 12, completed_count: 3, remaining_count: 9,
  projection: {mode:'rmb',target_count:12,completed_count:3,remaining_count:9,projected_total_cost:12000,projected_remaining_cost:9000},
  archived_at: '2027-01-01T10:00:00',
  upcoming_run_ats: ['2026-09-01T09:00:00', '2026-10-01T09:00:00'],
  pending_run_at: '2026-09-01T09:00:00', last_skipped_at: '2026-08-13T10:00:00',
  last_skipped_scheduled_at: '2026-08-01T09:00:00', skip_count: 2,
  reliability: {days:90,automatic_execution_count:3,on_time_execution_count:2,catch_up_execution_count:1,manual_execution_count:1,unclassified_execution_count:1,on_time_rate:66.6666667},
  variance: {days:90,execution_count:3,covered_execution_count:2,uncovered_execution_count:1,planned_amount:2200,actual_cost:2203,difference:3,difference_percent:0.1363636,fee:3,rounding_difference:0,latest:{id:'execution-2',timestamp:'2026-08-12T10:00:00',execution_kind:'manual',planned_amount:1200,actual_cost:1201,difference:1,difference_percent:0.0833333,fee:1}}
})`, context);
if (plan.start_date !== '2026-09-01' || plan.end_date !== '2026-12-31') {
  throw new Error('execution window must survive portfolio state normalization');
}
if (plan.archived_at !== '2027-01-01T10:00:00') {
  throw new Error('archive state must survive portfolio state normalization');
}
if (plan.target_count !== 12 || plan.completed_count !== 3 || plan.remaining_count !== 9) {
  throw new Error('target progress must survive portfolio state normalization');
}
if (!plan.projection || plan.projection.projected_remaining_cost !== 9000) {
  throw new Error('budget projection must survive portfolio state normalization');
}
if (plan.pending_run_at !== '2026-09-01T09:00:00' || plan.skip_count !== 2) {
  throw new Error('skip state must survive portfolio state normalization');
}
if (plan.upcoming_run_ats.length !== 2 || plan.upcoming_run_ats[1] !== '2026-10-01T09:00:00') {
  throw new Error('future schedule must survive portfolio state normalization');
}
if (plan.reliability.on_time_rate !== 66.6666667 || plan.reliability.catch_up_execution_count !== 1) {
  throw new Error('plan reliability must survive portfolio state normalization');
}
if (plan.variance.planned_amount !== 2200 || plan.variance.latest.id !== 'execution-2' || plan.variance.uncovered_execution_count !== 1) {
  throw new Error('plan investment comparison must survive portfolio state normalization');
}
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_renders_plan_reliability_in_expanded_detail():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const context = {
  console,
  escapeHtml: value => String(value),
  formatPortfolioMoney: (value, mode) => (mode === 'usd' ? '$' : '¥') + Number(value).toFixed(2),
  formatPortfolioSignedMoney: value => String(value),
  formatPortfolioPercent: value => String(value),
  formatPortfolioNumber: value => String(value),
  portfolioQuantityUnit: () => '克',
  portfolioPnlClass: () => '',
  portfolioInvestmentDateTime: value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const html = vm.runInContext('renderPortfolioInvestmentPerformance', context)({
  id: 'plan-1', mode: 'rmb', target_count: 12,
  reliability: {days:90,automatic_execution_count:3,on_time_execution_count:2,catch_up_execution_count:1,manual_execution_count:1,unclassified_execution_count:1,on_time_rate:66.6666667},
  variance: {days:90,execution_count:3,covered_execution_count:2,uncovered_execution_count:1,planned_amount:2200,actual_cost:2203,difference:3,difference_percent:0.1363636,fee:3,rounding_difference:0,latest:{id:'execution-2',timestamp:'2026-08-12T10:00:00',execution_kind:'manual',planned_amount:1200,actual_cost:1201,difference:1,difference_percent:0.0833333,fee:1}},
  performance: {execution_count:4,total_invested:4000,total_fees:4,total_quantity:8,average_cost:500,average_price:499.5,market_value:4100,pnl:100,pnl_percent:2.5,recent_executions:[]},
});
if (!html.includes('本计划 · 近90天执行稳定性') || !html.includes('66.7%') || !html.includes('2/3 次自动执行')) {
  throw new Error('expanded plan detail must render plan-level reliability');
}
if (!html.includes('补执行') || !html.includes('手动执行') || !html.includes('另有 1 条旧流水未记录执行类型')) {
  throw new Error('plan reliability must preserve execution kind semantics');
}
if (!html.includes('本计划 · 近90天投入对照') || !html.includes('计划买入') || !html.includes('实际支出') || !html.includes('支出差额')) {
  throw new Error('expanded plan detail must render planned and actual investment comparison');
}
if (!html.includes('最近一次：') || !html.includes('计划 ¥1200.00') || !html.includes('实际 ¥1201.00') || !html.includes('另有 1 条旧流水未记录计划金额')) {
  throw new Error('investment comparison must render latest covered execution and legacy coverage notice');
}
if (!html.includes('不代表真实成交滑点')) {
  throw new Error('investment comparison must explain that it is not real trade slippage');
}
if (!html.includes('差额比例 0.1363636') || !html.includes('数量舍入差额 0')) {
  throw new Error('investment comparison must render ratio separately and normalize negligible rounding differences');
}
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_renders_empty_variance_without_zero_values():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const context = {
  console,
  escapeHtml: value => String(value),
  formatPortfolioMoney: (value, mode) => (mode === 'usd' ? '$' : '¥') + Number(value).toFixed(2),
  formatPortfolioSignedMoney: value => String(value),
  formatPortfolioPercent: value => String(value),
  portfolioInvestmentDateTime: value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const html = vm.runInContext('portfolioInvestmentVarianceMarkup', context)({
  days:90, execution_count:0, covered_execution_count:0, uncovered_execution_count:0,
  planned_amount:0, actual_cost:0, difference:0, difference_percent:null,
  fee:0, rounding_difference:0, latest:null,
}, 'rmb');
if (!html.includes('暂无包含计划金额的执行记录')) {
  throw new Error('empty comparison must explain that no covered execution exists');
}
if (!html.includes('含手续费 --') || !html.includes('数量舍入差额 --')) {
  throw new Error('empty comparison must not render misleading zero fee or rounding values');
}
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_filters_and_sorts_plan_list():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
let portfolioInvestmentStatusFilter = 'all';
let portfolioInvestmentSort = 'priority';
let portfolioInvestmentListMode = 'active';
let portfolioSearch = '';
let activePortfolioInvestmentPlanId = 'plan-running';
let renderCount = 0;
const plans = [
  {id:'plan-paused',name:'已暂停计划',status:'paused',enabled:false,next_run_at:'',updated_at:'2026-08-10T09:00:00',performance:{total_invested:2000}},
  {id:'plan-running',name:'运行计划',status:'active',enabled:true,next_run_at:'2026-08-20T09:00:00',updated_at:'2026-08-11T09:00:00',performance:{total_invested:1000}},
  {id:'plan-due',name:'待执行计划',status:'due',enabled:true,next_run_at:'2026-08-12T09:00:00',updated_at:'2026-08-12T09:00:00',performance:{total_invested:500}},
  {id:'plan-attention',name:'异常计划',status:'active',enabled:true,last_result:'waiting_price',next_run_at:'2026-08-18T09:00:00',updated_at:'2026-08-13T09:00:00',performance:{total_invested:3000}},
  {id:'plan-completed',name:'已完成计划',status:'completed',enabled:false,next_run_at:'',updated_at:'2026-08-09T09:00:00',performance:{total_invested:4000}},
  {id:'plan-archived',name:'归档计划',status:'archived',enabled:false,archived_at:'2026-08-08T09:00:00',performance:{total_invested:6000}},
];
const context = {
  console,
  portfolioState: {investment_plans:{items:plans}},
  portfolioInvestmentStatusFilter,
  portfolioInvestmentSort,
  portfolioInvestmentListMode,
  portfolioSearch,
  activePortfolioInvestmentPlanId,
  portfolioInvestmentItems: () => plans,
  portfolioInvestmentFrequencyLabel: () => '每月',
  portfolioInvestmentStateLabel: plan => plan.name,
  portfolioSearchMatches: () => true,
  portfolioOptionValue: (options, value, fallback) => options.some(option => option.value === value) ? value : fallback,
  document: {getElementById: () => null},
  renderPortfolio: () => { renderCount += 1; },
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const ids = () => vm.runInContext('filteredPortfolioInvestments()', context).map(item => item.id);
const assert = (condition, message) => { if (!condition) throw new Error(message); };

assert(ids().join(',') === 'plan-attention,plan-due,plan-running,plan-paused,plan-completed', 'priority sort must put attention and due plans first');
vm.runInContext("setPortfolioInvestmentStatusFilter('attention')", context);
assert(ids().join(',') === 'plan-attention', 'attention filter must isolate actionable plans');
assert(context.activePortfolioInvestmentPlanId === null, 'changing status filter must close expanded plan');
vm.runInContext("setPortfolioInvestmentStatusFilter('running')", context);
assert(ids().join(',') === 'plan-running', 'running filter must isolate active and pending-start plans');
vm.runInContext("setPortfolioInvestmentStatusFilter('all')", context);
vm.runInContext("setPortfolioInvestmentSort('invested')", context);
assert(ids().join(',') === 'plan-completed,plan-attention,plan-paused,plan-running,plan-due', 'invested sort must use plan performance totals');
vm.runInContext("setPortfolioInvestmentSort('invalid')", context);
assert(context.portfolioInvestmentSort === 'priority', 'invalid sort values must fall back safely');
assert(renderCount === 5, 'each filter or sort change must render once');
context.portfolioInvestmentSort = 'next_run';
vm.runInContext("setPortfolioInvestmentListMode('archived')", context);
assert(context.portfolioInvestmentSort === 'priority', 'archived list must reset unsupported next-run sorting');
assert(ids().join(',') === 'plan-archived', 'archived list must contain archived plans only');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_controls_render_status_and_sort_dropdowns():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    render_source = (ROOT / "static" / "portfolio-render.js").read_text(encoding="utf-8")
    investment_source = read_investment_source()
    script = """
const vm = require('vm');
const box = {innerHTML:''};
const context = {
  console,
  portfolioView:'investment', portfolioSearch:'', portfolioInvestmentListMode:'active',
  portfolioInvestmentStatusFilter:'attention', portfolioInvestmentSort:'updated',
  portfolioAnalyticsRange:90, portfolioAnalyticsLoading:false, portfolioAnalyticsState:null,
  document:{getElementById:id => id === 'portfolioControls' ? box : null, addEventListener:() => {}, querySelectorAll:() => []},
  escapeHtml:value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__INVESTMENT_SOURCE__, context);
vm.runInContext(__RENDER_SOURCE__, context);
vm.runInContext('renderPortfolioControls()', context);
if (!box.innerHTML.includes('状态') || !box.innerHTML.includes('需处理') || !box.innerHTML.includes("'investmentStatus'")) {
  throw new Error('active investment controls must render status filter');
}
if (!box.innerHTML.includes('排序') || !box.innerHTML.includes('最近更新') || !box.innerHTML.includes("'investmentSort'")) {
  throw new Error('investment controls must render sort selector');
}
vm.runInContext("portfolioInvestmentListMode = 'archived'; portfolioInvestmentSort = 'priority';", context);
vm.runInContext('renderPortfolioControls()', context);
if (box.innerHTML.includes("'investmentStatus'")) throw new Error('archived plans must not show active status filter');
if (!box.innerHTML.includes("'investmentSort'")) throw new Error('archived plans must preserve sorting');
if (!box.innerHTML.includes('最近归档') || box.innerHTML.includes('下次执行')) throw new Error('archived plans must use archived-specific sorting');
"""
    script = script.replace("__INVESTMENT_SOURCE__", json.dumps(investment_source))
    script = script.replace("__RENDER_SOURCE__", json.dumps(render_source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_normalizes_and_renders_commitment_summary():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    state_source = (ROOT / "static" / "portfolio-state.js").read_text(encoding="utf-8")
    investment_source = read_investment_source()
    script = """
const vm = require('vm');
const box = { classList: { add: () => {} }, innerHTML: '' };
const context = {
  console,
  portfolioState: { investment_plans: { items: [], summary: {} } },
  escapeHtml: value => String(value),
  formatPortfolioMoney: (value, mode) => (mode === 'usd' ? '$' : '¥') + Number(value).toFixed(2),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__STATE_SOURCE__, context);
vm.runInContext(__INVESTMENT_SOURCE__, context);
context.portfolioState.investment_plans = vm.runInContext(`normalizePortfolioInvestmentState({summary:{
  actual_days:30, actual_execution_count:3,
  rmb_actual_invested:306, usd_actual_invested:501,
  actual_trend_months:6, actual_trend:[
    {month:'2026-03',execution_count:0,rmb_invested:0,usd_invested:0},
    {month:'2026-04',execution_count:1,rmb_invested:102,usd_invested:0},
    {month:'2026-05',execution_count:1,rmb_invested:204,usd_invested:1002},
    {month:'2026-06',execution_count:0,rmb_invested:0,usd_invested:0},
    {month:'2026-07',execution_count:1,rmb_invested:306,usd_invested:501},
    {month:'2026-08',execution_count:2,rmb_invested:153,usd_invested:250.5}
  ],
  reliability_days:90, automatic_execution_count:3, on_time_execution_count:2,
  catch_up_execution_count:1, manual_execution_count:2,
  unclassified_execution_count:1, on_time_rate:66.6666667,
  commitment_days:30, commitment_plan_count:2, commitment_run_count:5,
  rmb_commitment:102, usd_commitment:2004,
  commitment_items:[
    {id:'plan-rmb',name:'人民币定投',mode:'rmb',run_count:1,planned_cost_per_run:102,projected_cost:102,first_run_at:'2026-08-12T09:00:00',last_run_at:'2026-08-12T09:00:00'},
    {id:'plan-usd',name:'美元定投',mode:'usd',run_count:4,planned_cost_per_run:501,projected_cost:2004,first_run_at:'2026-08-17T09:00:00',last_run_at:'2026-09-07T09:00:00'}
  ],
  commitment_calendar:[
    {date:'2026-08-12',run_count:1,plan_count:1,rmb_commitment:102,usd_commitment:0,items:[{id:'plan-rmb',name:'人民币定投',mode:'rmb',scheduled_at:'2026-08-12T09:00:00',planned_cost:102}]},
    {date:'2026-08-17',run_count:2,plan_count:2,rmb_commitment:102,usd_commitment:501,items:[{id:'plan-rmb',name:'人民币定投',mode:'rmb',scheduled_at:'2026-08-17T09:00:00',planned_cost:102},{id:'plan-usd',name:'美元定投',mode:'usd',scheduled_at:'2026-08-17T09:00:00',planned_cost:501}]}
  ]
}})`, context);
vm.runInContext('renderPortfolioInvestmentSummary', context)(box);
if (!box.innerHTML.includes('未来30天') || !box.innerHTML.includes('计划投入')) {
  throw new Error('commitment window must render with a clear label');
}
if (!box.innerHTML.includes('近30天') || !box.innerHTML.includes('实际投入')) {
  throw new Error('actual investment window must render with a clear label');
}
if (!box.innerHTML.includes('¥306.00 · $501.00') || !box.innerHTML.includes('实际执行 3 次')) {
  throw new Error('actual investment totals and count must render by currency');
}
if (!box.innerHTML.includes('近6个月投入趋势') || !box.innerHTML.includes('人民币与美元分别按各自峰值缩放')) {
  throw new Error('monthly trend must explain its range and independent currency scales');
}
if (!box.innerHTML.includes('26/03') || !box.innerHTML.includes('¥153.00') || !box.innerHTML.includes('$250.50')) {
  throw new Error('monthly trend must render chronological buckets and both currency amounts');
}
if (!box.innerHTML.includes('近90天执行稳定性') || !box.innerHTML.includes('66.7%') || !box.innerHTML.includes('2/3 次自动执行')) {
  throw new Error('reliability summary must render its window and on-time rate');
}
if (!box.innerHTML.includes('补执行') || !box.innerHTML.includes('手动执行') || !box.innerHTML.includes('另有 1 条旧流水未记录执行类型')) {
  throw new Error('reliability summary must separate execution kinds and explain unclassified records');
}
if (!box.innerHTML.includes('¥102.00 · $2,004.00') || !box.innerHTML.includes('预计 5 期 · 涉及 2 个计划')) {
  throw new Error('commitment totals and counts must render by currency');
}
if (!box.innerHTML.includes('人民币定投') || !box.innerHTML.includes('1 期 · 每期 ¥102.00')) {
  throw new Error('rmb commitment item must explain its amount and run count');
}
if (!box.innerHTML.includes('美元定投') || !box.innerHTML.includes('4 期 · 每期 $501.00')) {
  throw new Error('usd commitment item must explain its amount and run count');
}
if (!box.innerHTML.includes('资金日历') || !box.innerHTML.includes('08月12日') || !box.innerHTML.includes('08月17日')) {
  throw new Error('commitment calendar must render future investment dates');
}
if (!box.innerHTML.includes('¥102.00 · $501.00') || !box.innerHTML.includes('2 期 · 2 个计划')) {
  throw new Error('commitment calendar must aggregate currencies and plans by date');
}
if (!box.innerHTML.includes('<details') || !box.innerHTML.includes('点击日期查看当天计划')) {
  throw new Error('commitment calendar dates must expose expandable plan details');
}
"""
    script = script.replace("__STATE_SOURCE__", json.dumps(state_source))
    script = script.replace("__INVESTMENT_SOURCE__", json.dumps(investment_source))
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
  TargetCount: '12',
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


def test_investment_plan_frontend_validates_and_sends_target_count():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const emits = [];
const statuses = [];
const values = {
  Name: '十二期定投', PositionId: '', PositionName: '积存金', Mode: 'rmb',
  Amount: '1000', Fee: '0', TargetCount: '12', Frequency: 'monthly', Time: '09:00',
  Month: '1', Day: '15', Weekday: '1', StartDate: '', EndDate: '', Enabled: true,
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
if (emits.length !== 1 || emits[0][1].target_count !== 12) throw new Error('valid target count must be saved');
values.TargetCount = '1.5';
vm.runInContext("savePortfolioInvestmentPlan('new')", context);
if (emits.length !== 1) throw new Error('fractional target count must not be saved');
if (!statuses.at(-1).message.includes('目标期数')) throw new Error('invalid target count must report a clear error');
"""
    script = script.replace("__SOURCE__", json.dumps(source))
    result = subprocess.run([node, "-e", script], cwd=ROOT, check=False, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_investment_plan_frontend_prioritizes_completed_state_over_paused_state():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行定投前端行为测试")

    source = read_investment_source()
    script = """
const vm = require('vm');
const context = { console };
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const plan = { enabled: false, status: 'completed', archived_at: '' };
if (vm.runInContext("portfolioInvestmentStateLabel", context)(plan) !== '已完成') {
  throw new Error('completed plan must not be labeled as paused');
}
if (vm.runInContext("portfolioInvestmentNextRunLabel", context)(plan) !== '计划已完成') {
  throw new Error('completed plan must expose a completed next-run label');
}
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
  TargetCount: '12',
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
assert(emits[0][1].amount === 1000 && emits[0][1].fee === 0 && emits[0][1].mode === 'rmb', 'preview must send the fixed investment budget inputs');
assert(emits[0][1].target_count === 12, 'preview must send the target count');
assert(context.portfolioInvestmentSchedulePreviews.new.loading === true, 'preview must expose loading state');
vm.runInContext("applyPortfolioInvestmentSchedulePreview({id:'new', request_id:'0', ok:true, items:['stale'], projection:{target_count:99}})", context);
assert(context.portfolioInvestmentSchedulePreviews.new.loading === true, 'stale response must be ignored');
vm.runInContext("applyPortfolioInvestmentSchedulePreview({id:'new', request_id:'1', ok:true, items:['2026-09-30T09:00:00'], projection:{mode:'rmb',target_count:12,completed_count:3,remaining_count:9,planned_cost_per_run:1000,projected_total_cost:12000,projected_remaining_cost:9000,projected_completion_at:'2027-08-31T09:00:00'}})", context);
assert(context.portfolioInvestmentSchedulePreviews.new.items[0] === '2026-09-30T09:00:00', 'latest response must update preview');
assert(context.portfolioInvestmentSchedulePreviews.new.projection.remaining_count === 9, 'latest response must update the budget projection');
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
