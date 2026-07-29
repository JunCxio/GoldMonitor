// ========== 持仓导入导出 ==========
function buildPortfolioTransactionTemplateCsv() {
  const lines = [
    PORTFOLIO_TRANSACTION_IMPORT_FIELDS.join(','),
    'transaction-demo-1,position-demo,buy,示例金条,rmb,580,10,0,2026-06-01,模板示例',
    'transaction-demo-2,position-demo,sell,示例金条,rmb,620,2,0,2026-06-15,可删除示例行',
  ];
  return lines.join('\n') + '\n';
}

function downloadPortfolioTransactionTemplate() {
  const blob = new Blob([buildPortfolioTransactionTemplateCsv()], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'goldmonitor_portfolio_transactions_template.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  setPortfolioStatus('CSV 模板已生成。', 'ok');
}

function parsePortfolioCsvRows(csvText) {
  const text = String(csvText || '').replace(/^\ufeff/, '');
  if (!text.trim()) return { fields: [], rows: [], error: 'CSV 内容不能为空。' };
  const parsed = [];
  let row = [];
  let cell = '';
  let inQuotes = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    const next = text[index + 1];
    if (char === '"') {
      if (inQuotes && next === '"') {
        cell += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (char === ',' && !inQuotes) {
      row.push(cell);
      cell = '';
    } else if ((char === '\n' || char === '\r') && !inQuotes) {
      row.push(cell);
      if (row.some(value => String(value || '').trim())) parsed.push(row);
      row = [];
      cell = '';
      if (char === '\r' && next === '\n') index += 1;
    } else {
      cell += char;
    }
  }
  if (inQuotes) return { fields: [], rows: [], error: 'CSV 引号未闭合。' };
  row.push(cell);
  if (row.some(value => String(value || '').trim())) parsed.push(row);
  if (!parsed.length) return { fields: [], rows: [], error: 'CSV 缺少表头。' };
  const fields = parsed[0].map(field => String(field || '').trim().replace(/^\ufeff/, ''));
  if (!fields.some(Boolean)) return { fields: [], rows: [], error: 'CSV 缺少表头。' };
  const rows = parsed.slice(1).map((values, index) => {
    const item = {};
    fields.forEach((field, fieldIndex) => {
      if (field) item[field] = values[fieldIndex] == null ? '' : String(values[fieldIndex]).trim();
    });
    return { rowNumber: index + 2, values: item };
  }).filter(item => Object.values(item.values).some(value => String(value || '').trim()));
  return { fields, rows, error: '' };
}

function portfolioImportSummary(rows) {
  const existingIds = new Set((Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [])
    .map(item => String(item.id || '').trim())
    .filter(Boolean));
  let overwrite = 0;
  rows.forEach(item => {
    const id = String(item.values.id || '').trim();
    if (id && existingIds.has(id)) overwrite += 1;
  });
  return {
    total: rows.length,
    overwrite,
    create: rows.length - overwrite,
    previewCount: Math.min(rows.length, 5),
  };
}

function portfolioImportRowErrors(rows) {
  const errors = [];
  rows.forEach(item => {
    const values = item.values || {};
    const rowNumber = item.rowNumber || '';
    const missing = PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS.filter(field => !String(values[field] || '').trim());
    if (missing.length) errors.push('第 ' + rowNumber + ' 行缺少字段: ' + missing.join(', '));
    if (values.type && !['buy', 'sell'].includes(values.type)) errors.push('第 ' + rowNumber + ' 行 type 必须为 buy 或 sell。');
    if (values.mode && !['rmb', 'usd'].includes(values.mode)) errors.push('第 ' + rowNumber + ' 行 mode 必须为 rmb 或 usd。');
    const price = Number(values.price);
    if (values.price && (!Number.isFinite(price) || price <= 0)) errors.push('第 ' + rowNumber + ' 行 price 必须大于 0。');
    const quantity = Number(values.quantity);
    if (values.quantity && (!Number.isFinite(quantity) || quantity <= 0)) errors.push('第 ' + rowNumber + ' 行 quantity 必须大于 0。');
    const fee = values.fee === '' || values.fee == null ? 0 : Number(values.fee);
    if (!Number.isFinite(fee) || fee < 0) errors.push('第 ' + rowNumber + ' 行 fee 不能小于 0。');
    if (values.trade_date && !/^\d{4}-\d{2}-\d{2}$/.test(values.trade_date)) errors.push('第 ' + rowNumber + ' 行 trade_date 必须为 YYYY-MM-DD。');
  });
  return errors.slice(0, 8);
}

function previewPortfolioImport(fileName, content) {
  const parsed = parsePortfolioCsvRows(content);
  const missingFields = PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS.filter(field => !parsed.fields.includes(field));
  const errors = [];
  if (parsed.error) errors.push(parsed.error);
  if (missingFields.length) errors.push('CSV 缺少必要字段: ' + missingFields.join(', '));
  if (!parsed.error && !parsed.rows.length) errors.push('CSV 没有可导入流水。');
  if (!parsed.error && !missingFields.length) errors.push(...portfolioImportRowErrors(parsed.rows));
  portfolioImportPreview = {
    fileName: fileName || '未命名 CSV',
    content: String(content || ''),
    fields: parsed.fields,
    rows: parsed.rows,
    summary: portfolioImportSummary(parsed.rows),
    errors,
    backendStatus: errors.length ? 'skip' : 'pending',
    backendMessage: errors.length ? '' : '正在复核完整持仓约束...',
    requestId: '',
  };
  renderPortfolioImportPreview();
  setPortfolioStatus(errors.length ? errors[0] : 'CSV 已读取，确认后导入。', errors.length ? 'fail' : 'ok');
  if (!errors.length) requestPortfolioImportBackendPreview();
}

function requestPortfolioImportBackendPreview() {
  if (!portfolioImportPreview || portfolioImportPreview.errors.length) return;
  portfolioImportPreviewRequestSeq += 1;
  const requestId = 'portfolio-import-preview-' + portfolioImportPreviewRequestSeq;
  portfolioImportPreview.requestId = requestId;
  portfolioImportPreview.backendStatus = 'pending';
  portfolioImportPreview.backendMessage = '正在复核完整持仓约束...';
  renderPortfolioImportPreview();
  socket.emit('preview_import_portfolio_transactions', {
    content: portfolioImportPreview.content,
    request_id: requestId,
  });
}

function applyPortfolioImportBackendPreview(data) {
  if (!portfolioImportPreview) return;
  const requestId = data && data.request_id ? String(data.request_id) : '';
  if (requestId && portfolioImportPreview.requestId && requestId !== portfolioImportPreview.requestId) return;
  if (data && data.ok) {
    portfolioImportPreview.backendStatus = 'ok';
    portfolioImportPreview.backendMessage = '后端复核通过。';
    portfolioImportPreview.summary = {
      total: Number(data.count) || 0,
      row_count: Number(data.row_count) || 0,
      valid_count: Number(data.valid_count) || 0,
      create: Number(data.create) || 0,
      overwrite: Number(data.overwrite) || 0,
      previewCount: portfolioImportPreview.summary ? portfolioImportPreview.summary.previewCount : 0,
    };
    portfolioImportPreview.errors = Array.isArray(data.errors) ? data.errors : [];
    portfolioImportPreview.warnings = Array.isArray(data.warnings) ? data.warnings : [];
    renderPortfolioImportPreview();
    setPortfolioStatus('CSV 复核通过，确认后导入。', 'ok');
    return;
  }
  const message = (data && data.message) || 'CSV 后端复核失败。';
  portfolioImportPreview.backendStatus = 'fail';
  portfolioImportPreview.backendMessage = message;
  portfolioImportPreview.errors = Array.isArray(data && data.errors) && data.errors.length ? data.errors : [message];
  portfolioImportPreview.warnings = Array.isArray(data && data.warnings) ? data.warnings : [];
  renderPortfolioImportPreview();
  setPortfolioStatus(message, 'fail');
}

function renderPortfolioImportPreview() {
  const box = document.getElementById('portfolioImportPreview');
  if (!box) return;
  if (!portfolioImportPreview) {
    box.innerHTML = '';
    box.classList.remove('show', 'fail');
    return;
  }
  const preview = portfolioImportPreview;
  const summary = preview.summary || { total: 0, row_count: 0, valid_count: 0, create: 0, overwrite: 0, previewCount: 0 };
  const rows = (preview.rows || []).slice(0, summary.previewCount || 0);
  const hasError = !!(preview.errors && preview.errors.length);
  const backendPending = preview.backendStatus === 'pending';
  const backendOk = preview.backendStatus === 'ok';
  const warnings = Array.isArray(preview.warnings) ? preview.warnings : [];
  box.classList.toggle('show', true);
  box.classList.toggle('fail', hasError);
  const errorHtml = hasError
    ? '<div class="portfolio-import-error">' + preview.errors.map(error => '<div>' + escapeHtml(error) + '</div>').join('') + '</div>'
    : '';
  const warningHtml = warnings.length
    ? '<div class="portfolio-import-preview-state">' + warnings.map(warning => escapeHtml(warning)).join('；') + '</div>'
    : '';
  const stateHtml = preview.backendMessage
    ? '<div class="portfolio-import-preview-state ' + escapeHtml(preview.backendStatus || '') + '">' + escapeHtml(preview.backendMessage) + '</div>'
    : '';
  const rowHtml = rows.map(item => {
    const values = item.values || {};
    const typeText = values.type === 'sell' ? '卖出' : values.type === 'buy' ? '买入' : values.type || '--';
    return [
      '<div class="portfolio-import-preview-row">',
      '<span>' + escapeHtml(values.trade_date || '--') + '</span>',
      '<span>' + escapeHtml(typeText) + '</span>',
      '<span>' + escapeHtml(values.name || '--') + '</span>',
      '<span>' + escapeHtml((values.quantity || '--') + ' / ' + (values.price || '--')) + '</span>',
      '</div>',
    ].join('');
  }).join('');
  box.innerHTML = [
    '<div class="portfolio-import-preview-head">',
    '<div><strong>CSV 导入预览</strong><span>' + escapeHtml(preview.fileName) + '</span></div>',
    '<button class="btn-clear-sm" type="button" onclick="cancelPortfolioImport()">取消</button>',
    '</div>',
    '<div class="portfolio-import-preview-grid">',
    '<div><span>总行数</span><strong>' + escapeHtml(String(summary.row_count || summary.total)) + '</strong></div>',
    '<div><span>有效</span><strong>' + escapeHtml(String(summary.valid_count || summary.total)) + '</strong></div>',
    '<div><span>新增</span><strong>' + escapeHtml(String(summary.create)) + '</strong></div>',
    '<div><span>覆盖</span><strong>' + escapeHtml(String(summary.overwrite)) + '</strong></div>',
    '</div>',
    stateHtml,
    warningHtml,
    errorHtml,
    '<div class="portfolio-import-preview-table">',
    '<div class="portfolio-import-preview-row head"><span>日期</span><span>类型</span><span>名称</span><span>数量/价格</span></div>',
    rowHtml || '<div class="portfolio-import-preview-empty">无可预览流水</div>',
    '</div>',
    '<div class="portfolio-import-actions">',
    '<button class="btn-clear-sm" type="button" onclick="downloadPortfolioTransactionTemplate()">下载模板</button>',
    !hasError && backendOk ? '<button class="btn-set" type="button" onclick="confirmPortfolioImport()">确认导入</button>' : '',
    backendPending ? '<button class="btn-clear-sm" type="button" disabled>复核中</button>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioImportBackup() {
  const box = document.getElementById('portfolioImportBackup');
  if (!box) return;
  const backup = normalizePortfolioImportBackup(portfolioState.import_backup);
  if (!backup.available) {
    box.innerHTML = '';
    box.classList.remove('show');
    return;
  }
  box.classList.add('show');
  const timeText = backup.imported_at ? backup.imported_at.replace('T', ' ') : '未知时间';
  box.innerHTML = [
    '<div class="portfolio-import-backup-head">',
    '<div><strong>最近 CSV 导入</strong><span>' + escapeHtml(timeText) + '</span></div>',
    '<button class="btn-clear-sm" type="button" onclick="undoPortfolioImport()">撤销导入</button>',
    '</div>',
    '<div class="portfolio-import-preview-grid">',
    '<div><span>导入</span><strong>' + escapeHtml(String(backup.count)) + '</strong></div>',
    '<div><span>新增</span><strong>' + escapeHtml(String(backup.create)) + '</strong></div>',
    '<div><span>覆盖</span><strong>' + escapeHtml(String(backup.overwrite)) + '</strong></div>',
    '</div>',
  ].join('');
}

function confirmPortfolioImport() {
  if (!portfolioImportPreview || portfolioImportPreview.errors.length || portfolioImportPreview.backendStatus !== 'ok') {
    setPortfolioStatus('请先选择并复核有效的 CSV 文件。', 'fail');
    return;
  }
  const content = portfolioImportPreview.content;
  setPortfolioStatus('正在导入流水...', '');
  portfolioImportPreview = null;
  renderPortfolioImportPreview();
  socket.emit('import_portfolio_transactions', { content });
}

function cancelPortfolioImport() {
  portfolioImportPreview = null;
  renderPortfolioImportPreview();
  const input = document.getElementById('portfolioImportFile');
  if (input) input.value = '';
  setPortfolioStatus('已取消 CSV 导入。', '');
}

function importPortfolioTransactions() {
  const input = document.getElementById('portfolioImportFile');
  if (!input) {
    setPortfolioStatus('未找到导入入口。', 'fail');
    return;
  }
  input.click();
}

function undoPortfolioImport() {
  setPortfolioStatus('正在撤销最近一次导入...', '');
  socket.emit('undo_portfolio_import');
}

function onPortfolioImportFile(input) {
  const file = input && input.files && input.files[0] ? input.files[0] : null;
  if (!file) return;
  if (file.size > 1024 * 1024) {
    setPortfolioStatus('CSV 文件不能超过 1MB。', 'fail');
    input.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const content = String(reader.result || '');
    if (!content.trim()) {
      setPortfolioStatus('CSV 内容不能为空。', 'fail');
      input.value = '';
      return;
    }
    previewPortfolioImport(file.name, content);
    input.value = '';
  };
  reader.onerror = () => {
    setPortfolioStatus('CSV 读取失败。', 'fail');
    input.value = '';
  };
  reader.readAsText(file, 'utf-8');
}
