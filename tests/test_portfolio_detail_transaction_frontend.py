import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def run_node_script(node, script):
    return subprocess.run(
        [node],
        input=script,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_detail_transaction_actions_keep_editor_in_detail_and_cancel_cleanly():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-actions.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  portfolioState: {
    items: [{id:'position-1', name:'黄金', mode:'rmb'}, {id:'position-2', name:'白银', mode:'rmb'}],
    transactions: [{id:'transaction-1', position_id:'position-1', name:'黄金', type:'buy', mode:'rmb'}],
  },
  portfolioView: 'positions', portfolioDetailView: 'review',
  activePortfolioDetailId: 'position-1', activePortfolioAlertEditorId: null,
  activePortfolioTransactionId: null, activePortfolioTransactionDetailId: null,
  portfolioTransactionDrafts: {},
  currentMode: 'rmb',
  captureActivePortfolioTransactionDraft: () => {},
  portfolioTransactionDraftKey: id => String(id || 'new'),
  clearPortfolioTransactionDraft: id => delete context.portfolioTransactionDrafts[String(id || 'new')],
  defaultPortfolioTransactionPrice: () => '1000.00',
  portfolioTransactionToday: () => '2026-08-27',
  renderPortfolio: () => { context.renderCount += 1; },
  renderCount: 0,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);

vm.runInContext("startPortfolioTransactionForPosition('position-1', 'buy')", context);
if (context.activePortfolioTransactionId !== 'new') throw new Error('buy editor must be activated');
if (context.portfolioView !== 'positions' || context.portfolioDetailView !== 'transactions') {
  throw new Error('buy editor must remain in the current position detail');
}
if (context.activePortfolioDetailId !== 'position-1') throw new Error('detail context must be preserved');
if (context.portfolioTransactionDrafts.new.type !== 'buy' || context.portfolioTransactionDrafts.new.position_id !== 'position-1') {
  throw new Error('buy draft must link the current position');
}

context.portfolioTransactionDrafts.new.position_id = 'position-2';
vm.runInContext("setActivePortfolioTransaction('new')", context);
if (context.activePortfolioTransactionId !== null || context.portfolioTransactionDrafts.new) {
  throw new Error('cancel must close and clear the detail transaction draft');
}
if (context.portfolioView !== 'positions' || context.activePortfolioDetailId !== 'position-1') {
  throw new Error('cancel must return to the same position detail');
}

vm.runInContext("startPortfolioTransactionForPosition('position-1', 'sell')", context);
if (context.portfolioTransactionDrafts.new.type !== 'sell') throw new Error('sell action must create a sell draft');
if (context.portfolioDetailView !== 'transactions') throw new Error('sell editor must be visible in the transaction tab');

vm.runInContext("setActivePortfolioTransaction('new')", context);
vm.runInContext("setActivePortfolioTransaction('transaction-1')", context);
if (context.activePortfolioTransactionId !== 'transaction-1') throw new Error('existing transaction editor must be activated');
if (context.activePortfolioTransactionDetailId !== 'position-1') throw new Error('existing editor must remember its detail context');
if (context.portfolioView !== 'positions' || context.portfolioDetailView !== 'transactions') {
  throw new Error('existing editor must remain in the current position detail');
}

context.portfolioTransactionDrafts['transaction-1'] = {position_id:'position-2', name:'改名后的流水'};
vm.runInContext("setActivePortfolioTransaction('transaction-1')", context);
if (context.activePortfolioTransactionId !== null || context.portfolioTransactionDrafts['transaction-1']) {
  throw new Error('cancel must clear the existing transaction draft');
}
if (context.portfolioView !== 'positions' || context.activePortfolioDetailId !== 'position-1') {
  throw new Error('cancel after changing association must keep the original detail open');
}
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr


def test_detail_transaction_panel_renders_linked_editor():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-detail.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  activePortfolioTransactionId: 'transaction-1',
  activePortfolioTransactionDetailId: 'position-1',
  portfolioTransactionDraftFor: item => Object.assign({}, item, {type:'sell'}),
  buildPortfolioTransactionEditor: item => '<div data-editor-id="' + item.id + '" data-editor-type="' + context.portfolioTransactionDraftFor(item).type + '">流水编辑器</div>',
  renderPortfolioDetailTransactionsList: () => '<div>流水列表</div>',
  formatPortfolioMoney: value => '¥' + Number(value || 0).toFixed(2),
  formatPortfolioSignedMoney: value => '¥' + Number(value || 0).toFixed(2),
  formatPortfolioNumber: value => Number(value || 0).toFixed(2),
  portfolioQuantityUnit: () => '克',
  portfolioPnlClass: () => '',
  escapeHtml: value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("renderPortfolioDetailTransactionsList = () => '<div>流水列表</div>'", context);
const html = vm.runInContext("renderPortfolioDetailTransactions({id:'position-1'}, [{id:'transaction-1', position_id:'position-1'}])", context);
if (!html.includes('data-editor-id="transaction-1"')) throw new Error('existing linked editor must render immediately');
if (!html.includes('data-editor-type="sell"')) throw new Error('linked detail editor must render immediately');
if (!html.includes('流水列表')) throw new Error('transaction list area must remain visible');
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr


def test_returning_to_list_clears_detail_transaction_draft():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-actions.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  activePortfolioDetailId: 'position-1', activePortfolioAlertEditorId: null,
  activePortfolioTransactionId: 'new', activePortfolioTransactionDetailId: 'position-1',
  portfolioTransactionDrafts: {new: {position_id:'position-1', type:'buy'}},
  portfolioDetailView: 'transactions', portfolioView: 'positions',
  captureActivePortfolioAlertDraft: () => {},
  captureActivePortfolioTransactionDraft: () => {},
  portfolioTransactionDraftKey: id => String(id || 'new'),
  clearPortfolioTransactionDraft: id => delete context.portfolioTransactionDrafts[String(id || 'new')],
  document: {addEventListener: () => {}},
  renderCount: 0,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext('renderPortfolio = () => { globalThis.renderCount += 1; }', context);
vm.runInContext('closePortfolioDetail()', context);
if (context.activePortfolioDetailId !== null) throw new Error('return must close the detail');
if (context.activePortfolioTransactionId !== null || context.portfolioTransactionDrafts.new) {
  throw new Error('return must clear the transaction draft created in this detail');
}
if (context.activePortfolioTransactionDetailId !== null) throw new Error('return must clear the transaction detail context');
if (context.portfolioView !== 'positions' || context.portfolioDetailView !== 'review') {
  throw new Error('return must restore the position list state');
}
if (context.renderCount !== 1) throw new Error('return must render once');
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr


def test_detail_transaction_item_exposes_edit_and_delete_actions():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-detail.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  activePortfolioTransactionId: null,
  activePortfolioTransactionDetailId: null,
  portfolioTransactionDisplay: () => ({mode:'rmb', typeText:'买入', typeClass:'buy', valueText:'成交 ¥680.00', quantityText:'1.00 克'}),
  formatPortfolioMoney: value => '¥' + Number(value).toFixed(2),
  formatPortfolioSignedMoney: value => '¥' + Number(value || 0).toFixed(2),
  formatPortfolioNumber: value => Number(value || 0).toFixed(2),
  portfolioQuantityUnit: () => '克',
  portfolioPnlClass: () => '',
  escapeHtml: value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const html = vm.runInContext("renderPortfolioDetailTransactionItem({id:'position-1', name:'黄金', mode:'rmb'}, {id:'transaction-1', position_id:'position-1', name:'黄金', price:680, quantity:1, fee:0, trade_date:'2026-08-27'})", context);
if (!html.includes("setActivePortfolioTransaction('transaction-1')")) throw new Error('detail item must expose edit action');
if (!html.includes("deletePortfolioTransaction('transaction-1')")) throw new Error('detail item must expose delete action');
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr


def test_delete_transaction_waits_for_confirmation_and_server_result():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-actions.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  portfolioState: {transactions: [{id:'transaction-1', position_id:'position-1'}]},
  activePortfolioDetailId: 'position-1', activePortfolioTransactionDetailId: 'position-1',
  activePortfolioTransactionId: 'transaction-1',
  portfolioTransactionDrafts: {'transaction-1': {position_id:'position-1', name:'保留草稿'}},
  pendingPortfolioSave: null,
  confirmResult: false,
  window: {confirm: () => context.confirmResult},
  socket: {emit: (...args) => context.emits.push(args)},
  emits: [], statuses: [],
  captureActivePortfolioTransactionDraft: () => {},
  clearPortfolioTransactionDraft: id => delete context.portfolioTransactionDrafts[id],
  setPortfolioStatus: (...args) => context.statuses.push(args),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);

vm.runInContext("deletePortfolioTransaction('transaction-1')", context);
if (context.emits.length !== 0 || context.pendingPortfolioSave !== null) throw new Error('cancelled delete must not send a request');
if (!context.portfolioTransactionDrafts['transaction-1'] || context.activePortfolioTransactionId !== 'transaction-1') {
  throw new Error('cancelled delete must preserve editor and draft');
}

context.confirmResult = true;
vm.runInContext("deletePortfolioTransaction('transaction-1')", context);
if (context.emits.length !== 1 || context.emits[0][0] !== 'delete_portfolio_transaction') throw new Error('confirmed delete must send one request');
if (!context.pendingPortfolioSave || context.pendingPortfolioSave.kind !== 'transaction' || context.pendingPortfolioSave.action !== 'delete') {
  throw new Error('confirmed delete must record delete context');
}
if (context.pendingPortfolioSave.detailPositionId !== 'position-1') throw new Error('delete must retain its detail context');
if (!context.portfolioTransactionDrafts['transaction-1'] || context.activePortfolioTransactionId !== 'transaction-1') {
  throw new Error('delete must wait for the server result before clearing editor state');
}
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr


def test_transaction_update_feedback_distinguishes_save_delete_and_preserves_failure_state():
    node = shutil.which("node")
    if not node:
        pytest.skip("需要 Node.js 执行持仓详情前端行为测试")

    source = (ROOT / "static" / "portfolio-center.js").read_text(encoding="utf-8")
    script = """
const vm = require('vm');
const context = {
  console,
  pendingPortfolioSave: {kind:'transaction', action:'save', id:'transaction-1'},
  pendingPortfolioImportMessage: '', pendingPortfolioUndoMessage: '', portfolioInvestmentDraftNotice: '',
  handlers: {}, statuses: [], applyCalls: 0,
  applyPortfolio: () => { context.applyCalls += 1; context.pendingPortfolioSave = null; },
  captureActivePortfolioTransactionDraft: () => {},
  setPortfolioStatus: (...args) => context.statuses.push(args),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
vm.runInContext("registerPortfolioSocketHandlers({on:(name, handler) => { globalThis.handlers[name] = handler; }})", context);

context.handlers.portfolio_updated({});
if (context.statuses.at(-1)[0] !== '流水已保存，持仓数据已重新计算。' || context.statuses.at(-1)[1] !== 'ok') {
  throw new Error('save success feedback must be explicit');
}

context.pendingPortfolioSave = {kind:'transaction', action:'delete', id:'transaction-1'};
context.handlers.portfolio_updated({});
if (context.statuses.at(-1)[0] !== '流水已删除，持仓数据已重新计算。' || context.statuses.at(-1)[1] !== 'ok') {
  throw new Error('delete success feedback must be explicit');
}

context.pendingPortfolioSave = {kind:'transaction', action:'save', id:'transaction-1'};
context.activePortfolioTransactionId = 'transaction-1';
context.activePortfolioTransactionDetailId = 'position-1';
context.portfolioTransactionDrafts = {'transaction-1': {quantity:'999'}};
context.handlers.portfolio_error({message:'卖出数量不能超过当前持仓'});
if (context.pendingPortfolioSave !== null) throw new Error('failed request must leave pending state');
if (context.activePortfolioTransactionId !== 'transaction-1' || context.activePortfolioTransactionDetailId !== 'position-1') {
  throw new Error('failed request must preserve detail editor state');
}
if (context.portfolioTransactionDrafts['transaction-1'].quantity !== '999') throw new Error('failed request must preserve draft');
if (context.statuses.at(-1)[0] !== '卖出数量不能超过当前持仓' || context.statuses.at(-1)[1] !== 'fail') {
  throw new Error('failed request must show backend validation feedback');
}
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr
