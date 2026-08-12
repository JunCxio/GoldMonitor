// ========== 持仓列表 ==========
function renderPortfolioPositions(box) {
  const sourceItems = Array.isArray(portfolioState.items) ? portfolioState.items : [];
  const items = filteredPortfolioPositions();
  const parts = [];
  if (activePortfolioPositionId === 'new') {
    parts.push([
      '<div class="portfolio-item expanded">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">新增持仓</div>',
      '<div class="portfolio-meta">保存后按当前行情估值</div>',
      '</div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioEditor({ id: 'new', name: '', mode: currentMode, entry_price: '', quantity: '', entry_date: '', note: '' }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activePortfolioPositionId !== 'new') {
    parts.push('<div class="portfolio-empty">' + (sourceItems.length ? '没有匹配的持仓' : '暂无持仓') + '</div>');
  }
  parts.push(...items.map(item => {
    const cls = [
      'portfolio-item',
      activePortfolioPositionId === item.id || activePortfolioDetailId === item.id ? 'expanded' : '',
    ].filter(Boolean).join(' ');
    const mode = item.mode || 'rmb';
    const quantity = formatPortfolioNumber(item.quantity, 2);
    const unit = portfolioQuantityUnit(mode);
    const averageCost = formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode);
    const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode);
    const valuationLabel = portfolioValuationLabel(item);
    const portfolioStatus = item.portfolio_status || item.valuation_status || '';
    const pnlClass = portfolioPnlClass(item.total_pnl != null ? item.total_pnl : item.pnl);
    const metaParts = [
      portfolioModeLabel(mode),
      quantity === '--' ? '' : quantity + ' ' + unit,
      averageCost === '--' ? '' : '均价 ' + averageCost,
      '当前价 ' + currentPrice,
      item.last_trade_date ? '最近 ' + item.last_trade_date : '',
      item.note || '',
    ].filter(Boolean);
    return [
      '<div class="' + cls + '">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">' + escapeHtml((item.name || '未命名持仓') + ' · ' + valuationLabel) + '</div>',
      '<div class="portfolio-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
      '<div class="portfolio-meta portfolio-pnl ' + pnlClass + '">未实现 ' + escapeHtml(formatPortfolioMoney(item.unrealized_pnl != null ? item.unrealized_pnl : item.pnl, mode)) + ' · 已实现 ' + escapeHtml(formatPortfolioMoney(item.realized_pnl, mode)) + ' · 合计 ' + escapeHtml(formatPortfolioMoney(item.total_pnl, mode)) + '</div>',
      '</div>',
      '<div class="portfolio-actions">',
      '<span class="alert-rule-state ' + portfolioStatusClass(portfolioStatus) + '">' + escapeHtml(portfolioStatusLabel(portfolioStatus)) + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActivePortfolioDetail(\'' + escapeHtml(item.id) + '\')">' + (activePortfolioDetailId === item.id ? '收起' : '详情') + '</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">买入</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'sell\')">卖出</button>',
      '</div>',
      activePortfolioDetailId === item.id ? renderPortfolioPositionDetail(item) : '',
      activePortfolioPositionId === item.id ? buildPortfolioEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function renderPortfolioTransactions(box) {
  const sourceTransactions = Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [];
  const transactions = filteredPortfolioTransactions();
  const parts = [];
  if (activePortfolioTransactionId === 'new') {
    parts.push([
      '<div class="portfolio-item expanded">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line">新增流水</div>',
      '<div class="portfolio-meta">买入会更新平均成本，卖出会计算已实现盈亏</div>',
      '</div>',
      '<div class="portfolio-actions"><span class="alert-rule-state off">新建</span></div>',
      buildPortfolioTransactionEditor({ id: 'new', type: 'buy', mode: currentMode, fee: '0' }),
      '</div>',
    ].join(''));
  }
  if (!transactions.length && activePortfolioTransactionId !== 'new') {
    parts.push('<div class="portfolio-empty">' + (sourceTransactions.length ? '没有匹配的流水' : '暂无流水') + '</div>');
  }
  parts.push(...transactions.map(item => {
    const cls = [
      'portfolio-item',
      activePortfolioTransactionId === item.id ? 'expanded' : '',
    ].filter(Boolean).join(' ');
    const mode = item.mode || 'rmb';
    const typeText = item.type === 'sell' ? '卖出' : '买入';
    const typeClass = item.type === 'sell' ? 'sell' : 'buy';
    const sourceBadge = item.source === 'investment_plan' ? '<span class="portfolio-source-badge">定投</span>' : '';
    const realizedText = item.type === 'sell' ? ' · 已实现 ' + formatPortfolioMoney(item.realized_pnl, mode) : '';
    const metaParts = [
      portfolioModeLabel(mode),
      formatPortfolioMoney(item.price, mode),
      formatPortfolioNumber(item.quantity, 4) + ' ' + portfolioQuantityUnit(mode),
      Number(item.fee) > 0 ? '手续费 ' + formatPortfolioMoney(item.fee, mode) : '',
      item.trade_date || '',
      item.note || '',
    ].filter(Boolean);
    return [
      '<div class="' + cls + '">',
      '<div class="portfolio-main">',
      '<div class="portfolio-line"><span class="portfolio-transaction-type ' + typeClass + '">' + escapeHtml(typeText) + '</span>' + sourceBadge + ' ' + escapeHtml(item.name || '未命名流水') + escapeHtml(realizedText) + '</div>',
      '<div class="portfolio-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
      '</div>',
      '<div class="portfolio-actions">',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActivePortfolioTransaction(\'' + escapeHtml(item.id) + '\')">编辑</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="deletePortfolioTransaction(\'' + escapeHtml(item.id) + '\')">删除</button>',
      '</div>',
      activePortfolioTransactionId === item.id ? buildPortfolioTransactionEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function buildPortfolioTransactionEditor(item) {
  const target = portfolioTransactionDraftFor(item);
  const id = target.id;
  const escapedId = escapeHtml(id);
  const draftInputAttr = ' oninput="capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const draftChangeAttr = ' onchange="capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const modeChangeAttr = ' onchange="capturePortfolioTransactionDraft(\'' + escapedId + '\'); renderPortfolio()"';
  const positionChangeAttr = ' onchange="syncPortfolioTransactionPosition(\'' + escapedId + '\'); capturePortfolioTransactionDraft(\'' + escapedId + '\')"';
  const type = target.type || 'buy';
  const mode = target.mode || currentMode;
  const positionOptions = buildPortfolioPositionOptions(target.position_id);
  return [
    '<div class="portfolio-editor portfolio-transaction-editor">',
    '<div class="portfolio-fields portfolio-transaction-fields">',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionType_' + escapedId + '">类型</label>',
    '<select id="portfolioTransactionType_' + escapedId + '"' + draftChangeAttr + '>',
    '<option value="buy"' + (type === 'buy' ? ' selected' : '') + '>买入</option>',
    '<option value="sell"' + (type === 'sell' ? ' selected' : '') + '>卖出</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionPositionId_' + escapedId + '">关联持仓</label>',
    '<select id="portfolioTransactionPositionId_' + escapedId + '"' + positionChangeAttr + '>',
    '<option value="">新持仓</option>',
    positionOptions,
    '</select>',
    '</div>',
    '<div class="portfolio-field portfolio-name">',
    '<label for="portfolioTransactionName_' + escapedId + '">名称</label>',
    '<input id="portfolioTransactionName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(target.name || '') + '" placeholder="例如 金条"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionMode_' + escapedId + '">单位</label>',
    '<select id="portfolioTransactionMode_' + escapedId + '"' + modeChangeAttr + '>',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionPrice_' + escapedId + '">成交价</label>',
    '<input id="portfolioTransactionPrice_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(target.price || '') + '" placeholder="输入价格"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionQuantity_' + escapedId + '">数量（' + escapeHtml(portfolioQuantityUnit(mode)) + '）</label>',
    '<input id="portfolioTransactionQuantity_' + escapedId + '" type="number" step="0.0001" value="' + escapeHtml(target.quantity || '') + '" placeholder="输入数量"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionFee_' + escapedId + '">手续费</label>',
    '<input id="portfolioTransactionFee_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(target.fee == null ? '0' : target.fee) + '" placeholder="0"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioTransactionTradeDate_' + escapedId + '">交易日期</label>',
    '<input id="portfolioTransactionTradeDate_' + escapedId + '" type="date" value="' + escapeHtml(target.trade_date || '') + '"' + draftChangeAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioTransactionNote_' + escapedId + '">备注</label>',
    '<textarea id="portfolioTransactionNote_' + escapedId + '" maxlength="200" rows="2" placeholder="例如 账户或来源"' + draftInputAttr + '>' + escapeHtml(target.note || '') + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-editor-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioTransaction(\'' + escapedId + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActivePortfolioTransaction(\'' + escapedId + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function buildPortfolioPositionOptions(selectedId) {
  const items = Array.isArray(portfolioState.items) ? portfolioState.items : [];
  return items.map(item => {
    const selected = item.id === selectedId ? ' selected' : '';
    return '<option value="' + escapeHtml(item.id) + '"' + selected + '>' + escapeHtml((item.name || '未命名持仓') + ' · ' + portfolioModeLabel(item.mode)) + '</option>';
  }).join('');
}

function syncPortfolioTransactionPosition(id) {
  const key = portfolioTransactionDraftKey(id);
  const selectedId = portfolioTransactionInputValue(key, 'PositionId');
  const item = (portfolioState.items || []).find(entry => entry.id === selectedId);
  if (!item) {
    capturePortfolioTransactionDraft(id);
    return;
  }
  const nameInput = document.getElementById('portfolioTransactionName_' + key);
  const modeInput = document.getElementById('portfolioTransactionMode_' + key);
  const priceInput = document.getElementById('portfolioTransactionPrice_' + key);
  const previousMode = modeInput ? modeInput.value || currentMode : currentMode;
  const previousDefaultPrice = defaultPortfolioTransactionPrice(previousMode);
  const nextMode = item.mode || currentMode;
  if (nameInput && !nameInput.value) nameInput.value = item.name || '';
  if (priceInput && (!priceInput.value || priceInput.value === previousDefaultPrice)) priceInput.value = defaultPortfolioTransactionPrice(nextMode);
  if (modeInput) modeInput.value = nextMode;
  capturePortfolioTransactionDraft(id);
}
