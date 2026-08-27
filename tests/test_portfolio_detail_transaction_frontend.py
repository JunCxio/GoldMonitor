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
  portfolioState: {items: [{id:'position-1', name:'黄金', mode:'rmb'}]},
  portfolioView: 'positions', portfolioDetailView: 'review',
  activePortfolioDetailId: 'position-1', activePortfolioAlertEditorId: null,
  activePortfolioTransactionId: null, portfolioTransactionDrafts: {},
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
  activePortfolioTransactionId: 'new',
  portfolioTransactionDraftFor: () => ({id:'new', position_id:'position-1', type:'sell', mode:'rmb', fee:'0'}),
  buildPortfolioTransactionEditor: item => '<div data-editor-type="' + context.portfolioTransactionDraftFor(item).type + '">流水编辑器</div>',
  renderPortfolioDetailTransactionsList: () => '<div>流水列表</div>',
  escapeHtml: value => String(value),
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(__SOURCE__, context);
const html = vm.runInContext("renderPortfolioDetailTransactions({id:'position-1'}, [])", context);
if (!html.includes('data-editor-type="sell"')) throw new Error('linked detail editor must render immediately');
if (!html.includes('暂无关联流水')) throw new Error('transaction list area must remain visible');
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
  activePortfolioTransactionId: 'new',
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
if (context.portfolioView !== 'positions' || context.portfolioDetailView !== 'review') {
  throw new Error('return must restore the position list state');
}
if (context.renderCount !== 1) throw new Error('return must render once');
""".replace("__SOURCE__", json.dumps(source))
    result = run_node_script(node, script)
    assert result.returncode == 0, result.stderr
