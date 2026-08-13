// ========== 定投计划操作 ==========
function savePortfolioInvestmentPlan(id) {
  const payload = {
    name: String(portfolioInvestmentInputValue(id, 'Name') || '').trim(),
    position_id: String(portfolioInvestmentInputValue(id, 'PositionId') || '').trim(),
    position_name: String(portfolioInvestmentInputValue(id, 'PositionName') || '').trim(),
    mode: portfolioInvestmentInputValue(id, 'Mode') || currentMode,
    amount: Number(portfolioInvestmentInputValue(id, 'Amount')),
    fee: Number(portfolioInvestmentInputValue(id, 'Fee') || 0),
    frequency: portfolioInvestmentInputValue(id, 'Frequency') || 'monthly',
    time: portfolioInvestmentInputValue(id, 'Time') || '09:00',
    month: Number(portfolioInvestmentInputValue(id, 'Month') || 1),
    day: Number(portfolioInvestmentInputValue(id, 'Day') || 1),
    weekday: Number(portfolioInvestmentInputValue(id, 'Weekday') || 1),
    start_date: String(portfolioInvestmentInputValue(id, 'StartDate') || '').trim(),
    end_date: String(portfolioInvestmentInputValue(id, 'EndDate') || '').trim(),
    enabled: portfolioInvestmentInputValue(id, 'Enabled') !== false,
  };
  const position = (portfolioState.items || []).find(item => item.id === payload.position_id);
  if (position) {
    payload.position_name = position.name;
    payload.mode = position.mode;
  }
  if (!payload.name) return setPortfolioStatus('请输入计划名称。', 'fail');
  if (!payload.position_name) return setPortfolioStatus('请输入或选择定投持仓。', 'fail');
  if (!Number.isFinite(payload.amount) || payload.amount <= 0) return setPortfolioStatus('请输入有效的定投金额。', 'fail');
  if (!Number.isFinite(payload.fee) || payload.fee < 0) return setPortfolioStatus('手续费不能为负数。', 'fail');
  if (payload.start_date && payload.end_date && payload.start_date > payload.end_date) return setPortfolioStatus('结束日期不能早于开始日期。', 'fail');
  if (id !== 'new') payload.id = id;
  portfolioInvestmentDraftNotice = '';
  pendingPortfolioSave = { kind: 'investment', id };
  setPortfolioStatus('正在保存定投计划...', '');
  socket.emit('save_portfolio_investment_plan', payload);
}

function togglePortfolioInvestmentPlan(id, enabled) {
  setPortfolioStatus(enabled ? '正在启用定投计划...' : '正在暂停定投计划...', '');
  socket.emit('toggle_portfolio_investment_plan', { id, enabled: enabled === true });
}

function executePortfolioInvestmentPlan(id) {
  setPortfolioStatus('正在按最新行情生成买入流水...', '');
  socket.emit('execute_portfolio_investment_plan', { id });
}

function skipPortfolioInvestmentPlan(id, scheduledAt) {
  const plan = portfolioInvestmentItems().find(item => item.id === id);
  if (!plan || !scheduledAt) return setPortfolioStatus('当前没有可跳过的定投期次。', 'fail');
  const scheduledText = portfolioInvestmentDateTime(scheduledAt);
  if (!window.confirm('确定跳过 ' + scheduledText + ' 的计划执行？\n本次不会生成买入流水，计划将继续运行。')) return;
  setPortfolioStatus('正在跳过本期定投计划...', '');
  socket.emit('skip_portfolio_investment_plan', { id, scheduled_at: scheduledAt });
}

function exportPortfolioInvestmentExecutions(id) {
  setPortfolioStatus('正在导出定投执行记录...', '');
  socket.emit('export_portfolio_investment_executions', { id });
}

function archivePortfolioInvestmentPlan(id) {
  if (!window.confirm('确定归档这个定投计划？\n计划会停止运行，已生成的流水、绩效和导出记录都会保留。')) return;
  setPortfolioStatus('正在归档定投计划...', '');
  socket.emit('archive_portfolio_investment_plan', { id });
}

function restorePortfolioInvestmentPlan(id) {
  setPortfolioStatus('正在恢复定投计划...', '');
  socket.emit('restore_portfolio_investment_plan', { id });
}

function deletePortfolioInvestmentPlan(id) {
  const plan = portfolioInvestmentItems().find(item => item.id === id);
  if (!plan || !plan.archived_at) return setPortfolioStatus('请先归档计划，再执行永久删除。', 'fail');
  if (!window.confirm('确定永久删除这个归档计划？\n删除后无法恢复计划，但已生成的持仓流水不会删除。')) return;
  setPortfolioStatus('正在永久删除归档计划...', '');
  socket.emit('delete_portfolio_investment_plan', { id });
}
