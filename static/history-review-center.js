let historyView = 'prices';
let eventTimelineState = { events: [], summary: {}, filters: {}, range: {}, price_summary: {} };
let eventTimelineRange = 60;
let eventTimelineTypes = ['price_summary', 'alert', 'risk_analysis', 'news', 'data_status', 'review_note'];
let selectedTimelineEventId = null;
let pendingTimelineFocus = null;
let reviewNoteEditorState = { id: '', related_event_id: '', related_event_type: '', related_event_title: '' };
let reviewNotesRefreshTimer = null;
const EVENT_TIMELINE_TYPE_DEFS = [
  { type: 'price_summary', label: '价格摘要' },
  { type: 'alert', label: '预警' },
  { type: 'risk_analysis', label: '风险分析' },
  { type: 'news', label: '新闻' },
  { type: 'data_status', label: '数据状态' },
  { type: 'review_note', label: '复盘笔记' },
];
let latestPriceHistoryState = { items: [], stats: {}, total: 0 };

function registerHistoryReviewSocketHandlers(socket) {
  socket.on('price_history_updated', data => {
    applyPriceHistory(data || {});
  });

  socket.on('price_history_export_ready', data => {
    if (!data || !data.content) return;
    downloadText(data.filename || 'GoldMonitor-price-history.csv', data.content, 'text/csv;charset=utf-8');
  });

  socket.on('event_timeline_updated', data => {
    applyEventTimeline(data || {});
  });

  socket.on('event_timeline_error', data => {
    setTimelineStatus((data && data.message) || '事件时间轴加载失败。', 'fail');
  });

  socket.on('review_note_saved', data => {
    setReviewNoteSaving(false);
    if (data && data.ok === false) {
      setReviewNoteEditorStatus(data.message || '复盘笔记保存失败。', 'fail');
      return;
    }
    const note = data && (data.note || data.item) || {};
    if (note.id) {
      pendingTimelineFocus = {
        type: 'review_note',
        sourceId: String(note.id),
        timestamp: note.timestamp || '',
      };
    }
    closeReviewNoteEditor();
    setTimelineStatus((data && data.message) || '复盘笔记已保存。', 'ok');
    queueReviewNotesTimelineRefresh();
  });

  socket.on('review_note_deleted', data => {
    if (data && data.ok === false) {
      setTimelineStatus(data.message || '复盘笔记删除失败。', 'fail');
      return;
    }
    selectedTimelineEventId = null;
    closeReviewNoteEditor();
    setTimelineStatus((data && data.message) || '复盘笔记已删除。', 'ok');
    queueReviewNotesTimelineRefresh();
  });

  socket.on('review_note_error', data => {
    setReviewNoteSaving(false);
    const message = (data && data.message) || '复盘笔记操作失败。';
    const editor = document.getElementById('reviewNoteEditor');
    if (editor && !editor.hidden) setReviewNoteEditorStatus(message, 'fail');
    else setTimelineStatus(message, 'fail');
  });

  socket.on('review_notes_updated', () => {
    queueReviewNotesTimelineRefresh();
  });

  socket.on('review_report_exported', data => {
    const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
    setTimelineStatus(data && data.saved_path ? '已导出 ' + count + ' 条事件，保存至 ' + data.saved_path : '复盘报告已导出。', 'ok');
  });

  socket.on('review_report_error', data => {
    setTimelineStatus((data && data.message) || '复盘报告导出失败。', 'fail');
  });
}

function applyPriceHistory(data) {
  if (Array.isArray(data.events)) {
    chartEvents = normalizeChartEvents(data.events);
  }
  if (data && data.scope === 'chart') {
    chartHistoryState = Object.assign({ period: data.period || chartPeriod, items: [] }, data);
    if (chartHistoryState.period === chartPeriod) switchChartData();
    return;
  }
  latestPriceHistoryState = Object.assign({ items: [], stats: {}, total: 0 }, data || {});
  renderHistory(latestPriceHistoryState);
}

function historyStatValue(stats, field) {
  const item = stats && stats.rmb ? stats.rmb[field] : null;
  if (item == null) return '--';
  return Number(item).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

function renderHistory(data) {
  const statsEl = document.getElementById('historyStats');
  const listEl = document.getElementById('historyList');
  if (!statsEl || !listEl) return;
  const stats = data.stats || {};
  const rmb = stats.rmb || {};
  const items = Array.isArray(data.items) ? data.items : [];
  const statItems = [
    ['样本', data.total || items.length || 0],
    ['最高 RMB', rmb.high == null ? '--' : '¥' + historyStatValue(stats, 'high')],
    ['最低 RMB', rmb.low == null ? '--' : '¥' + historyStatValue(stats, 'low')],
    ['变动', rmb.change_pct == null ? '--' : Number(rmb.change_pct).toFixed(2) + '%'],
  ];
  statsEl.innerHTML = statItems.map(item => (
    '<div class="history-stat"><div class="history-stat-label">' + escapeHtml(item[0]) + '</div><div class="history-stat-value">' + escapeHtml(item[1]) + '</div></div>'
  )).join('');
  if (!items.length) {
    listEl.innerHTML = '<div class="history-empty">暂无历史数据</div>';
    return;
  }
  const rows = items.slice(-240).reverse().map(item => [
    '<div class="history-row">',
    '<span>' + escapeHtml((item.timestamp || '').replace('T', ' ')) + '</span>',
    '<span>' + escapeHtml(item.rmb == null ? '--' : '¥' + Number(item.rmb).toFixed(2)) + '</span>',
    '<span>' + escapeHtml(item.usd == null ? '--' : '$' + Number(item.usd).toFixed(2)) + '</span>',
    '<span>' + escapeHtml(item.rate == null ? '--' : Number(item.rate).toFixed(4)) + '</span>',
    '</div>',
  ].join('')).join('');
  listEl.innerHTML = '<div class="history-row"><span>时间</span><span>RMB/克</span><span>USD/oz</span><span>汇率</span></div>' + rows;
}

function openHistory() {
  document.getElementById('historyBackdrop').classList.add('show');
  renderTimelineTypeFilters();
  switchHistoryView(historyView || 'prices', true);
  refreshHistory();
}

function closeHistory() {
  document.getElementById('historyBackdrop').classList.remove('show');
  closeReviewNoteEditor();
}

function onHistoryBackdrop(event) {
  if (event.target.id === 'historyBackdrop') closeHistory();
}

function refreshHistory() {
  socket.emit('get_price_history', { limit: 600 });
}

function switchHistoryView(view, skipRefresh) {
  historyView = view === 'timeline' ? 'timeline' : 'prices';
  const isTimeline = historyView === 'timeline';
  const priceTab = document.getElementById('historyTabPrices');
  const timelineTab = document.getElementById('historyTabTimeline');
  const pricePanel = document.getElementById('historyPanelPrices');
  const timelinePanel = document.getElementById('historyPanelTimeline');
  if (priceTab) {
    priceTab.classList.toggle('active', !isTimeline);
    priceTab.setAttribute('aria-selected', String(!isTimeline));
  }
  if (timelineTab) {
    timelineTab.classList.toggle('active', isTimeline);
    timelineTab.setAttribute('aria-selected', String(isTimeline));
  }
  if (pricePanel) pricePanel.classList.toggle('active', !isTimeline);
  if (timelinePanel) timelinePanel.classList.toggle('active', isTimeline);
  const csvBtn = document.getElementById('exportHistoryCsvButton');
  const reportBtn = document.getElementById('exportReviewReportButton');
  if (csvBtn) csvBtn.style.display = isTimeline ? 'none' : '';
  if (reportBtn) reportBtn.style.display = isTimeline ? '' : 'none';
  if (isTimeline && !skipRefresh) refreshEventTimeline();
}

function refreshHistoryCurrentView() {
  if (historyView === 'timeline') {
    refreshEventTimeline();
    return;
  }
  refreshHistory();
}
