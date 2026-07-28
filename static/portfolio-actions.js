// ========== 持仓交互 ==========
function setPortfolioView(view) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  portfolioView = ['positions', 'transactions', 'review'].includes(view) ? view : 'positions';
  if (portfolioView !== 'positions') {
    activePortfolioDetailId = null;
    activePortfolioAlertEditorId = null;
    portfolioDetailView = 'review';
  }
  renderPortfolio();
  if (portfolioView === 'review') requestPortfolioAnalytics(false);
}

function setActivePortfolioDetail(id) {
  captureActivePortfolioAlertDraft();
  const nextId = activePortfolioDetailId === id ? null : id;
  activePortfolioDetailId = nextId;
  if (activePortfolioDetailId) {
    portfolioView = 'positions';
    portfolioDetailView = 'review';
  }
  if (activePortfolioDetailId !== id) activePortfolioAlertEditorId = null;
  if (activePortfolioDetailId && activePortfolioAlertEditorId && activePortfolioAlertEditorId !== activePortfolioDetailId) {
    activePortfolioAlertEditorId = null;
  }
  renderPortfolio();
}

function setPortfolioDetailView(view) {
  captureActivePortfolioAlertDraft();
  portfolioDetailView = ['overview', 'transactions', 'alert', 'review'].includes(view) ? view : 'review';
  renderPortfolio();
}

function togglePortfolioAlertEditor(positionId) {
  captureActivePortfolioAlertDraft();
  activePortfolioAlertEditorId = activePortfolioAlertEditorId === positionId ? null : positionId;
  activePortfolioDetailId = positionId;
  portfolioDetailView = 'alert';
  renderPortfolio();
}

function openPortfolioAlertEditor(positionId) {
  captureActivePortfolioAlertDraft();
  activePortfolioDetailId = positionId;
  portfolioDetailView = 'alert';
  activePortfolioAlertEditorId = positionId;
  renderPortfolio();
}

function setActivePortfolioPosition(id) {
  captureActivePortfolioDraft();
  if (activePortfolioPositionId === id) {
    clearPortfolioDraft(id);
    activePortfolioPositionId = null;
  } else {
    activePortfolioPositionId = id;
  }
  renderPortfolio();
}

function setActivePortfolioTransaction(id, defaults) {
  captureActivePortfolioTransactionDraft();
  if (activePortfolioTransactionId === id && !defaults) {
    clearPortfolioTransactionDraft(id);
    activePortfolioTransactionId = null;
  } else {
    activePortfolioTransactionId = id;
    if (defaults && typeof defaults === 'object') {
      portfolioTransactionDrafts[portfolioTransactionDraftKey(id)] = Object.assign({}, defaults);
    }
  }
  portfolioView = 'transactions';
  renderPortfolio();
}

function startPortfolioTransactionForPosition(positionId, type) {
  const item = (portfolioState.items || []).find(entry => entry.id === positionId);
  let defaults;
  if (item) {
    const mode = item.mode || currentMode;
    defaults = {
      position_id: item.id,
      name: item.name || '',
      type: type === 'sell' ? 'sell' : 'buy',
      mode: mode,
      price: defaultPortfolioTransactionPrice(mode),
      quantity: '',
      fee: '0',
      trade_date: portfolioTransactionToday(),
      note: '',
    };
  } else {
    defaults = {
      type: type === 'sell' ? 'sell' : 'buy',
      mode: currentMode,
      fee: '0',
      price: defaultPortfolioTransactionPrice(currentMode),
      trade_date: portfolioTransactionToday(),
    };
  }
  setActivePortfolioTransaction('new', defaults);
}

function portfolioInputValue(id, field) {
  const el = document.getElementById('portfolio' + field + '_' + id);
  return el ? el.value : '';
}

function savePortfolioPosition(id) {
  const isNew = id === 'new';
  const payload = {
    name: portfolioInputValue(id, 'Name').trim(),
    mode: portfolioInputValue(id, 'Mode').trim(),
    entry_price: portfolioInputValue(id, 'EntryPrice').trim(),
    quantity: portfolioInputValue(id, 'Quantity').trim(),
    entry_date: portfolioInputValue(id, 'EntryDate').trim(),
    note: portfolioInputValue(id, 'Note').trim(),
  };
  if (!payload.name) {
    setPortfolioStatus('请输入持仓名称。', 'fail');
    return;
  }
  const entryPrice = Number(payload.entry_price);
  if (!Number.isFinite(entryPrice) || entryPrice <= 0) {
    setPortfolioStatus('请输入有效的持仓价格。', 'fail');
    return;
  }
  const quantity = Number(payload.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    setPortfolioStatus('请输入有效的持仓数量。', 'fail');
    return;
  }
  if (payload.mode !== 'rmb' && payload.mode !== 'usd') {
    setPortfolioStatus('持仓单位无效。', 'fail');
    return;
  }
  if (!isNew) payload.id = id;
  payload.entry_price = entryPrice;
  payload.quantity = quantity;
  setPortfolioStatus('正在保存持仓...', '');
  pendingPortfolioSave = { kind: 'position', id };
  socket.emit('save_portfolio_position', payload);
}

function deletePortfolioPosition(id) {
  setPortfolioStatus('正在删除持仓...', '');
  socket.emit('delete_portfolio_position', { id });
  clearPortfolioDraft(id);
  clearPortfolioAlertDraft(id);
  if (activePortfolioPositionId === id) activePortfolioPositionId = null;
  if (activePortfolioDetailId === id) activePortfolioDetailId = null;
  if (activePortfolioAlertEditorId === id) activePortfolioAlertEditorId = null;
}

function savePortfolioAlert(positionId) {
  capturePortfolioAlertDraft(positionId);
  const draft = portfolioAlertDrafts[portfolioAlertDraftKey(positionId)] || {};
  const payload = {
    position_id: positionId,
    enabled: draft.enabled !== false,
    take_profit_price: draft.take_profit_price,
    stop_loss_price: draft.stop_loss_price,
    profit_percent: draft.profit_percent,
    loss_percent: draft.loss_percent,
    near_cost_percent: draft.near_cost_percent,
    note: draft.note,
  };
  const existing = portfolioAlertForPosition(positionId);
  if (existing && existing.id) payload.id = existing.id;
  setPortfolioStatus('正在保存持仓提醒...', '');
  pendingPortfolioSave = { kind: 'alert', id: positionId };
  socket.emit('save_portfolio_alert', payload);
}

function resetPortfolioAlert(alertId) {
  setPortfolioStatus('正在重置持仓提醒...', '');
  socket.emit('reset_portfolio_alert', { id: alertId });
}

function deletePortfolioAlert(alertId, positionId) {
  setPortfolioStatus('正在清空持仓提醒...', '');
  socket.emit('delete_portfolio_alert', { id: alertId });
  clearPortfolioAlertDraft(positionId);
  if (activePortfolioAlertEditorId === positionId) activePortfolioAlertEditorId = null;
}

function savePortfolioTransaction(id) {
  const isNew = id === 'new';
  const payload = {
    position_id: portfolioTransactionInputValue(id, 'PositionId').trim(),
    name: portfolioTransactionInputValue(id, 'Name').trim(),
    type: portfolioTransactionInputValue(id, 'Type').trim(),
    mode: portfolioTransactionInputValue(id, 'Mode').trim(),
    price: portfolioTransactionInputValue(id, 'Price').trim(),
    quantity: portfolioTransactionInputValue(id, 'Quantity').trim(),
    fee: portfolioTransactionInputValue(id, 'Fee').trim() || '0',
    trade_date: portfolioTransactionInputValue(id, 'TradeDate').trim(),
    note: portfolioTransactionInputValue(id, 'Note').trim(),
  };
  if (!payload.name) {
    setPortfolioStatus('请输入流水名称。', 'fail');
    return;
  }
  if (payload.type !== 'buy' && payload.type !== 'sell') {
    setPortfolioStatus('流水类型无效。', 'fail');
    return;
  }
  if (payload.type === 'sell' && !payload.position_id) {
    setPortfolioStatus('请选择要卖出的持仓。', 'fail');
    return;
  }
  if (payload.mode !== 'rmb' && payload.mode !== 'usd') {
    setPortfolioStatus('持仓单位无效。', 'fail');
    return;
  }
  const price = Number(payload.price);
  if (!Number.isFinite(price) || price <= 0) {
    setPortfolioStatus('请输入有效的成交价格。', 'fail');
    return;
  }
  const quantity = Number(payload.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) {
    setPortfolioStatus('请输入有效的成交数量。', 'fail');
    return;
  }
  const fee = Number(payload.fee);
  if (!Number.isFinite(fee) || fee < 0) {
    setPortfolioStatus('请输入有效的手续费。', 'fail');
    return;
  }
  if (!isNew) payload.id = id;
  if (!payload.position_id) delete payload.position_id;
  payload.price = price;
  payload.quantity = quantity;
  payload.fee = fee;
  setPortfolioStatus('正在保存流水...', '');
  pendingPortfolioSave = { kind: 'transaction', id };
  socket.emit('save_portfolio_transaction', payload);
}

function deletePortfolioTransaction(id) {
  setPortfolioStatus('正在删除流水...', '');
  socket.emit('delete_portfolio_transaction', { id });
  clearPortfolioTransactionDraft(id);
  if (activePortfolioTransactionId === id) activePortfolioTransactionId = null;
}

function exportPortfolio(kind) {
  const exportKind = ['transactions', 'review'].includes(kind) ? kind : 'positions';
  const statusText = exportKind === 'review'
    ? '正在导出复盘...'
    : exportKind === 'transactions' ? '正在导出流水...' : '正在导出持仓...';
  setPortfolioStatus(statusText, '');
  socket.emit('export_portfolio', { kind: exportKind });
}
