// ========== 持仓事件 ==========
function registerPortfolioSocketHandlers(socketClient) {
  socketClient.on('portfolio_updated', data => {
    applyPortfolio(data || {});
    if (pendingPortfolioImportMessage) {
      setPortfolioStatus(pendingPortfolioImportMessage, 'ok');
      pendingPortfolioImportMessage = '';
    } else if (pendingPortfolioUndoMessage) {
      setPortfolioStatus(pendingPortfolioUndoMessage, 'ok');
      pendingPortfolioUndoMessage = '';
    } else if (portfolioInvestmentDraftNotice) {
      setPortfolioStatus(portfolioInvestmentDraftNotice, 'ok');
    } else {
      setPortfolioStatus('持仓已更新。', 'ok');
    }
  });

  socketClient.on('portfolio_error', data => {
    pendingPortfolioSave = null;
    setPortfolioStatus((data && data.message) || '持仓更新失败。', 'fail');
  });

  socketClient.on('portfolio_investment_plans_updated', data => {
    captureActivePortfolioInvestmentDraft();
    portfolioState.investment_plans = normalizePortfolioInvestmentState(data);
    if (activePortfolioInvestmentPlanId && activePortfolioInvestmentPlanId !== 'new' && !portfolioState.investment_plans.items.some(item => item.id === activePortfolioInvestmentPlanId)) {
      clearPortfolioInvestmentDraft(activePortfolioInvestmentPlanId);
      activePortfolioInvestmentPlanId = null;
    }
    if (pendingPortfolioSave && pendingPortfolioSave.kind === 'investment') {
      clearPortfolioInvestmentDraft(pendingPortfolioSave.id);
      activePortfolioInvestmentPlanId = null;
      portfolioInvestmentDraftNotice = '';
      pendingPortfolioSave = null;
    }
    renderPortfolio();
  });

  socketClient.on('portfolio_investment_plan_saved', data => {
    setPortfolioStatus(data && data.plan ? '定投计划已保存。' : '定投计划保存完成。', 'ok');
  });

  socketClient.on('portfolio_investment_plan_executed', data => {
    setPortfolioStatus((data && data.message) || '定投计划已执行。', data && data.ok === false ? 'fail' : 'ok');
  });

  socketClient.on('portfolio_investment_plan_skipped', data => {
    setPortfolioStatus((data && data.message) || '已跳过本期定投计划。', data && data.ok === false ? 'fail' : 'ok');
  });

  socketClient.on('portfolio_investment_plan_archived', data => {
    setPortfolioStatus(data && data.plan ? '定投计划已归档。' : '定投计划归档完成。', 'ok');
  });

  socketClient.on('portfolio_investment_plan_restored', data => {
    setPortfolioStatus(data && data.plan ? '定投计划已恢复，当前保持暂停。' : '定投计划恢复完成。', 'ok');
  });

  socketClient.on('portfolio_investment_plan_deleted', () => {
    setPortfolioStatus('已永久删除归档计划，相关持仓流水仍保留。', 'ok');
  });

  socketClient.on('portfolio_investment_schedule_preview', data => {
    applyPortfolioInvestmentSchedulePreview(data || {});
  });

  socketClient.on('portfolio_investment_plan_error', data => {
    pendingPortfolioSave = null;
    setPortfolioStatus((data && data.message) || '定投计划操作失败。', 'fail');
  });

  socketClient.on('portfolio_investment_executions_exported', data => {
    const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
    const planName = data && data.plan_name ? String(data.plan_name) : '定投计划';
    setPortfolioStatus(data && data.saved_path
      ? planName + '的执行记录已导出 ' + count + ' 条，保存至 ' + data.saved_path
      : '定投执行记录已导出。', 'ok');
  });

  socketClient.on('portfolio_investment_executions_export_error', data => {
    setPortfolioStatus((data && data.message) || '定投执行记录导出失败。', 'fail');
  });

  socketClient.on('portfolio_exported', data => {
    const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : portfolioState.total;
    const kindText = data && data.kind === 'review' ? '复盘' : data && data.kind === 'transactions' ? '流水' : '持仓';
    setPortfolioStatus(data && data.saved_path ? '已导出' + kindText + ' ' + count + ' 条，保存至 ' + data.saved_path : kindText + '已导出。', 'ok');
  });

  socketClient.on('portfolio_export_error', data => {
    setPortfolioStatus((data && data.message) || '持仓导出失败。', 'fail');
  });

  socketClient.on('portfolio_analytics_updated', data => {
    portfolioAnalyticsState = data && typeof data === 'object' ? data : null;
    portfolioAnalyticsLoading = false;
    if (portfolioView === 'review') renderPortfolio();
  });

  socketClient.on('portfolio_analytics_error', data => {
    portfolioAnalyticsLoading = false;
    setPortfolioStatus((data && data.message) || '持仓收益与预警分析生成失败。', 'fail');
    if (portfolioView === 'review') renderPortfolio();
  });

  socketClient.on('portfolio_imported', data => {
    const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
    const summary = data && data.summary ? data.summary : {};
    const create = Number(summary.create || 0);
    const overwrite = Number(summary.overwrite || 0);
    pendingPortfolioImportMessage = '已导入流水 ' + count + ' 条（新增 ' + create + '，覆盖 ' + overwrite + '）。';
    setPortfolioStatus(pendingPortfolioImportMessage, 'ok');
  });

  socketClient.on('portfolio_import_previewed', data => {
    applyPortfolioImportBackendPreview(data || {});
  });

  socketClient.on('portfolio_import_undone', data => {
    if (data && data.ok) {
      pendingPortfolioUndoMessage = '已撤销最近一次 CSV 导入。';
      setPortfolioStatus(pendingPortfolioUndoMessage, 'ok');
    }
  });

  socketClient.on('portfolio_import_undo_error', data => {
    setPortfolioStatus((data && data.message) || '撤销导入失败。', 'fail');
    if (data && data.import_backup) {
      portfolioState.import_backup = normalizePortfolioImportBackup(data.import_backup);
      renderPortfolioImportBackup();
    }
  });
}
