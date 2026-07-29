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

// ========== 历史复盘 ==========
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

function timelineTypeLabel(type) {
  const found = EVENT_TIMELINE_TYPE_DEFS.find(item => item.type === type);
  return found ? found.label : type;
}

function selectedTimelineEvent() {
  const events = Array.isArray(eventTimelineState.events) ? eventTimelineState.events : [];
  return events.find(item => item.id === selectedTimelineEventId) || null;
}

function reviewNoteIdFromEvent(event) {
  if (!event) return '';
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  return String(payload.note_id || payload.id || event.note_id || event.id || '');
}

function reviewNoteLocalInputValue(value) {
  const parsed = timelineDateFromValue(value) || new Date();
  const pad = number => String(number).padStart(2, '0');
  return [
    parsed.getFullYear(),
    pad(parsed.getMonth() + 1),
    pad(parsed.getDate()),
  ].join('-') + 'T' + pad(parsed.getHours()) + ':' + pad(parsed.getMinutes());
}

function setReviewNoteEditorStatus(message, type) {
  const el = document.getElementById('reviewNoteEditorStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'review-note-editor-status' + (type ? ' ' + type : '');
}

function setReviewNoteSaving(saving) {
  const button = document.getElementById('saveReviewNoteButton');
  if (!button) return;
  button.disabled = Boolean(saving);
  button.textContent = saving ? '正在保存' : '保存笔记';
}

function setReviewNoteEditorRelation(state) {
  const relation = document.getElementById('reviewNoteRelation');
  if (!relation) return;
  if (!state.related_event_id) {
    relation.textContent = '独立笔记';
    return;
  }
  relation.textContent = '关联：' + timelineTypeLabel(state.related_event_type) + ' · ' + (state.related_event_title || state.related_event_id);
}

function showReviewNoteEditor(options) {
  const state = Object.assign({
    id: '',
    timestamp: '',
    title: '',
    content: '',
    related_event_id: '',
    related_event_type: '',
    related_event_title: '',
  }, options || {});
  reviewNoteEditorState = {
    id: String(state.id || ''),
    related_event_id: String(state.related_event_id || ''),
    related_event_type: String(state.related_event_type || ''),
    related_event_title: String(state.related_event_title || ''),
  };
  const editor = document.getElementById('reviewNoteEditor');
  const heading = document.getElementById('reviewNoteEditorHeading');
  const timestamp = document.getElementById('reviewNoteTimestamp');
  const title = document.getElementById('reviewNoteTitle');
  const content = document.getElementById('reviewNoteContent');
  if (!editor || !timestamp || !title || !content) return;
  if (heading) heading.textContent = state.id ? '编辑复盘笔记' : '新增复盘笔记';
  timestamp.value = reviewNoteLocalInputValue(state.timestamp);
  title.value = state.title || '';
  content.value = state.content || '';
  setReviewNoteEditorRelation(reviewNoteEditorState);
  setReviewNoteEditorStatus('', '');
  setReviewNoteSaving(false);
  editor.hidden = false;
  requestAnimationFrame(() => content.focus());
}

function openReviewNoteEditor() {
  showReviewNoteEditor({ timestamp: new Date() });
}

function openReviewNoteEditorFromSelectedEvent() {
  const event = selectedTimelineEvent();
  if (!event || event.type === 'review_note') {
    setTimelineStatus('请先选择一条行情、预警、分析、新闻或数据事件。', 'fail');
    return;
  }
  showReviewNoteEditor({
    timestamp: event.timestamp || new Date(),
    related_event_id: event.id,
    related_event_type: event.type,
    related_event_title: event.title || timelineTypeLabel(event.type),
  });
}

function editSelectedReviewNote() {
  const event = selectedTimelineEvent();
  if (!event || event.type !== 'review_note') return;
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  showReviewNoteEditor({
    id: reviewNoteIdFromEvent(event),
    timestamp: payload.timestamp || event.timestamp,
    title: payload.title || event.title || '',
    content: payload.content || event.summary || '',
    related_event_id: payload.related_event_id || '',
    related_event_type: payload.related_event_type || '',
    related_event_title: payload.related_event_title || '',
  });
}

function closeReviewNoteEditor() {
  const editor = document.getElementById('reviewNoteEditor');
  if (editor) editor.hidden = true;
  reviewNoteEditorState = { id: '', related_event_id: '', related_event_type: '', related_event_title: '' };
  setReviewNoteEditorStatus('', '');
  setReviewNoteSaving(false);
}

function saveReviewNote() {
  const timestamp = document.getElementById('reviewNoteTimestamp');
  const title = document.getElementById('reviewNoteTitle');
  const content = document.getElementById('reviewNoteContent');
  if (!timestamp || !title || !content) return;
  const payload = {
    timestamp: timestamp.value.trim(),
    title: title.value.trim(),
    content: content.value.trim(),
    related_event_id: reviewNoteEditorState.related_event_id,
    related_event_type: reviewNoteEditorState.related_event_type,
    related_event_title: reviewNoteEditorState.related_event_title,
  };
  if (!payload.timestamp) {
    setReviewNoteEditorStatus('请选择笔记时间。', 'fail');
    timestamp.focus();
    return;
  }
  if (!payload.content) {
    setReviewNoteEditorStatus('请输入笔记内容。', 'fail');
    content.focus();
    return;
  }
  if (payload.title.length > 80 || payload.content.length > 2000) {
    setReviewNoteEditorStatus('标题最多 80 个字符，内容最多 2000 个字符。', 'fail');
    return;
  }
  if (reviewNoteEditorState.id) payload.id = reviewNoteEditorState.id;
  setReviewNoteSaving(true);
  setReviewNoteEditorStatus('正在保存复盘笔记...', '');
  socket.emit('save_review_note', payload);
}

function deleteSelectedReviewNote() {
  const event = selectedTimelineEvent();
  if (!event || event.type !== 'review_note') return;
  const noteId = reviewNoteIdFromEvent(event);
  if (!noteId) {
    setTimelineStatus('缺少笔记标识，无法删除。', 'fail');
    return;
  }
  if (!window.confirm('确定删除复盘笔记“' + (event.title || '未命名笔记') + '”？')) return;
  setTimelineStatus('正在删除复盘笔记...', '');
  socket.emit('delete_review_note', { id: noteId });
}

function queueReviewNotesTimelineRefresh() {
  if (reviewNotesRefreshTimer) clearTimeout(reviewNotesRefreshTimer);
  reviewNotesRefreshTimer = setTimeout(() => {
    reviewNotesRefreshTimer = null;
    const backdrop = document.getElementById('historyBackdrop');
    if (historyView === 'timeline' && backdrop && backdrop.classList.contains('show')) refreshEventTimeline();
  }, 80);
}

function renderTimelineTypeFilters() {
  const box = document.getElementById('timelineTypeFilters');
  if (!box) return;
  box.innerHTML = EVENT_TIMELINE_TYPE_DEFS.map(item => {
    const checked = eventTimelineTypes.includes(item.type) ? ' checked' : '';
    return [
      '<label>',
      '<input type="checkbox" value="' + escapeHtml(item.type) + '"' + checked + ' onchange="toggleTimelineType(\'' + escapeHtml(item.type) + '\', this.checked)">',
      '<span>' + escapeHtml(item.label) + '</span>',
      '</label>',
    ].join('');
  }).join('');
}

function setTimelineRange(value) {
  const minutes = parseInt(value, 10);
  eventTimelineRange = [60, 240, 1440, 10080, 43200, 129600].includes(minutes) ? minutes : 60;
  refreshEventTimeline();
}

function toggleTimelineType(type, checked) {
  if (checked) {
    if (!eventTimelineTypes.includes(type)) eventTimelineTypes.push(type);
  } else {
    eventTimelineTypes = eventTimelineTypes.filter(item => item !== type);
  }
  if (!eventTimelineTypes.length) eventTimelineTypes = EVENT_TIMELINE_TYPE_DEFS.map(item => item.type);
  renderTimelineTypeFilters();
  refreshEventTimeline();
}

function setTimelineStatus(message, type) {
  const el = document.getElementById('timelineStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'timeline-status' + (type ? ' ' + type : '');
}

function timelineDateFromValue(value) {
  const raw = String(value || '').trim();
  if (!raw) return null;
  let date = new Date(raw);
  if (!Number.isNaN(date.getTime())) return date;
  date = new Date(raw.replace(' ', 'T'));
  if (!Number.isNaN(date.getTime())) return date;
  if (/^\d{1,2}:\d{2}/.test(raw)) {
    const today = new Date();
    const dateText = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
    date = new Date(dateText + 'T' + raw);
    if (!Number.isNaN(date.getTime())) return date;
  }
  return null;
}

function timelineRangeForTimestamp(timestamp) {
  const date = timelineDateFromValue(timestamp);
  if (!date) return eventTimelineRange || 60;
  const diffMinutes = Math.max(0, Math.ceil((Date.now() - date.getTime()) / 60000));
  if (diffMinutes <= 60) return 60;
  if (diffMinutes <= 240) return 240;
  if (diffMinutes <= 1440) return 1440;
  if (diffMinutes <= 10080) return 10080;
  if (diffMinutes <= 43200) return 43200;
  return 129600;
}

function timelineFocusTimeKey(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  if (/^\d{1,2}:\d{2}/.test(raw)) return raw.slice(0, 8);
  return raw.replace('T', ' ').slice(0, 19);
}

function eventMatchesTimelineFocus(event, focus) {
  if (!event || !focus) return false;
  if (focus.type && event.type !== focus.type) return false;
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  if (focus.sourceId && [event.id, payload.id, payload.note_id].some(value => String(value || '') === String(focus.sourceId))) return true;
  const eventTime = timelineFocusTimeKey(event.timestamp);
  const focusTime = timelineFocusTimeKey(focus.timestamp);
  if (!eventTime || !focusTime) return false;
  if (eventTime === focusTime) return true;
  if (focusTime.length <= 8 && eventTime.slice(11, 19).startsWith(focusTime.slice(0, 5))) return true;
  return false;
}

function openEventTimelineAround(timestamp, type, sourceId) {
  pendingTimelineFocus = {
    type: type || '',
    sourceId: sourceId == null ? '' : String(sourceId),
    timestamp: timestamp || '',
  };
  selectedTimelineEventId = null;
  eventTimelineRange = timelineRangeForTimestamp(timestamp);
  eventTimelineTypes = EVENT_TIMELINE_TYPE_DEFS.map(item => item.type);
  const rangeSelect = document.getElementById('timelineRange');
  if (rangeSelect) rangeSelect.value = String(eventTimelineRange);
  document.getElementById('historyBackdrop').classList.add('show');
  renderTimelineTypeFilters();
  switchHistoryView('timeline', true);
  refreshHistory();
  refreshEventTimeline();
}

function refreshEventTimeline() {
  setTimelineStatus('正在加载事件时间轴...', '');
  socket.emit('get_event_timeline', {
    minutes: eventTimelineRange,
    limit: 300,
    types: eventTimelineTypes,
  });
}

function applyEventTimeline(data) {
  eventTimelineState = Object.assign({ events: [], summary: {}, filters: {}, range: {}, price_summary: {} }, data || {});
  const events = Array.isArray(eventTimelineState.events) ? eventTimelineState.events : [];
  let focusMissing = false;
  if (pendingTimelineFocus) {
    const focused = events.find(event => eventMatchesTimelineFocus(event, pendingTimelineFocus));
    if (focused) selectedTimelineEventId = focused.id;
    else focusMissing = true;
    pendingTimelineFocus = null;
  } else if (selectedTimelineEventId && !events.some(event => event.id === selectedTimelineEventId)) {
    selectedTimelineEventId = null;
  }
  setTimelineStatus(focusMissing ? '已打开复盘时间轴，未在当前范围找到对应事件。' : '', focusMissing ? 'fail' : '');
  renderEventTimeline();
  if (selectedTimelineEventId) {
    requestAnimationFrame(() => {
      const active = document.querySelector('#timelineList .timeline-event.active');
      if (active) active.scrollIntoView({ block: 'center', behavior: 'smooth' });
    });
  }
}

function timelineEventTime(timestamp) {
  const text = String(timestamp || '');
  if (!text) return '--';
  return text.replace('T', ' ').slice(0, 19);
}

function renderTimelineSummary() {
  const box = document.getElementById('timelineSummary');
  if (!box) return;
  const summary = eventTimelineState.summary || {};
  const byType = summary.by_type || {};
  const range = eventTimelineState.range || {};
  const statItems = [
    ['事件', summary.total || 0],
    ['预警', byType.alert || 0],
    ['笔记', byType.review_note || 0],
    ['范围', range.minutes ? Math.round(Number(range.minutes) / 60) + 'h' : '--'],
  ];
  box.innerHTML = statItems.map(item => (
    '<div class="history-stat"><div class="history-stat-label">' + escapeHtml(item[0]) + '</div><div class="history-stat-value">' + escapeHtml(String(item[1])) + '</div></div>'
  )).join('');
}

function renderTimelineList() {
  const list = document.getElementById('timelineList');
  if (!list) return;
  const events = Array.isArray(eventTimelineState.events) ? eventTimelineState.events : [];
  if (!events.length) {
    list.innerHTML = '<div class="history-empty">暂无事件</div>';
    return;
  }
  list.innerHTML = events.slice().reverse().map(event => [
    '<button class="timeline-event' + (selectedTimelineEventId === event.id ? ' active' : '') + '" type="button" onclick="selectTimelineEvent(decodeURIComponent(\'' + encodeURIComponent(String(event.id || '')) + '\'))">',
    '<span class="timeline-event-time">' + escapeHtml(timelineEventTime(event.timestamp).slice(11) || '--') + '</span>',
    '<span class="timeline-event-main">',
    '<span class="timeline-event-title">' + escapeHtml(event.title || timelineTypeLabel(event.type)) + '</span>',
    String(event.summary || '').trim() && String(event.summary || '').trim() !== String(event.title || '').trim()
      ? '<span class="timeline-event-summary">' + escapeHtml(event.summary) + '</span>'
      : '',
    '<span class="timeline-event-type">' + escapeHtml(timelineTypeLabel(event.type)) + '</span>',
    '</span>',
    '</button>',
  ].join('')).join('');
}

function selectTimelineEvent(id) {
  selectedTimelineEventId = id;
  renderTimelineList();
  renderTimelineDetail();
}

function detailCell(label, value) {
  const text = value == null || value === '' ? '暂无详情' : String(value);
  return '<div class="timeline-detail-cell"><span>' + escapeHtml(label) + '</span><strong>' + escapeHtml(text) + '</strong></div>';
}

function renderTimelineDetail() {
  const detail = document.getElementById('timelineDetail');
  if (!detail) return;
  const events = Array.isArray(eventTimelineState.events) ? eventTimelineState.events : [];
  const event = events.find(item => item.id === selectedTimelineEventId);
  if (!event) {
    detail.innerHTML = '<div class="history-empty">选择一条事件查看详情</div>';
    return;
  }
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  const cells = [
    detailCell('类型', timelineTypeLabel(event.type)),
    detailCell('来源', event.source),
    detailCell('时间', timelineEventTime(event.timestamp)),
  ];
  let extras = '';
  if (event.type === 'alert') {
    cells.push(detailCell('等级', alertLevelLabel(payload.level)));
    cells.push(detailCell('品种', alertModeLabel(payload.mode)));
    cells.push(detailCell('处置结果', payload.handled ? '已处理' : '未处理'));
    if (payload.handled_at) cells.push(detailCell('处理时间', payload.handled_at));
    if (payload.handling_note) cells.push(detailCell('处理备注', payload.handling_note));
    if (Array.isArray(payload.related_news) && payload.related_news.length) {
      extras += '<div class="timeline-detail-news">' + payload.related_news.slice(0, 3).map(item => (
        '<a href="' + escapeHtml(item.url || '#') + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(item.title || '相关新闻') + '</a>'
      )).join('') + '</div>';
    }
  } else if (event.type === 'risk_analysis') {
    const structured = payload.structured || {};
    const quality = payload.market_quality || payload.data_quality || {};
    cells.push(detailCell('模型', [payload.provider, payload.model].filter(Boolean).join(' / ')));
    cells.push(detailCell('行情质量', quality.score == null ? '' : quality.score + '分'));
    cells.push(detailCell('风险等级', structured.risk_level || ''));
    cells.push(detailCell('主要因素', structured.key_factors || structured.main_factors || ''));
  } else if (event.type === 'news') {
    cells.push(detailCell('来源', payload.source));
    cells.push(detailCell('主题', payload.topic));
    if (payload.url) {
      extras += '<div class="timeline-detail-news"><a href="' + escapeHtml(payload.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(payload.url) + '</a></div>';
    }
  } else if (event.type === 'data_status') {
    cells.push(detailCell('状态', payload.cached ? '缓存' : (payload.ok === false ? '异常' : payload.status)));
    cells.push(detailCell('说明', payload.error || payload.message));
    if (payload.summary) cells.push(detailCell('价差比例', payload.summary.spread_pct == null ? '' : payload.summary.spread_pct + '%'));
  } else if (event.type === 'price_summary') {
    const summary = payload.summary || {};
    const usd = summary.usd || {};
    const rmb = summary.rmb || {};
    cells.push(detailCell('价格点', payload.points));
    cells.push(detailCell('USD/oz', usd.start == null ? '' : usd.start + ' -> ' + usd.end));
    cells.push(detailCell('RMB/克', rmb.start == null ? '' : rmb.start + ' -> ' + rmb.end));
  } else if (event.type === 'review_note') {
    if (payload.updated_at) cells.push(detailCell('最后更新', timelineEventTime(payload.updated_at)));
    if (payload.related_event_id) {
      cells.push(detailCell('关联类型', timelineTypeLabel(payload.related_event_type)));
      cells.push(detailCell('关联事件', payload.related_event_title || payload.related_event_id));
    }
  }
  const actions = event.type === 'review_note'
    ? [
      '<div class="timeline-detail-actions">',
      '<button class="settings-cancel" type="button" onclick="editSelectedReviewNote()">编辑笔记</button>',
      '<button class="dialog-danger" type="button" onclick="deleteSelectedReviewNote()">删除笔记</button>',
      '</div>',
    ].join('')
    : '<div class="timeline-detail-actions"><button class="settings-cancel" type="button" onclick="openReviewNoteEditorFromSelectedEvent()">关联创建笔记</button></div>';
  detail.innerHTML = [
    '<div class="timeline-detail-title">' + escapeHtml(event.title || timelineTypeLabel(event.type)) + '</div>',
    '<div class="timeline-detail-meta">' + escapeHtml(timelineEventTime(event.timestamp)) + ' · ' + escapeHtml(event.source || '--') + '</div>',
    '<div class="timeline-detail-summary">' + escapeHtml(payload.message || payload.content || event.summary || '暂无详情') + '</div>',
    '<div class="timeline-detail-grid">' + cells.join('') + '</div>',
    extras,
    actions,
  ].join('');
}

function renderEventTimeline() {
  renderTimelineSummary();
  renderTimelineList();
  renderTimelineDetail();
}

function exportReviewReport() {
  setTimelineStatus('正在导出复盘报告...', '');
  socket.emit('export_review_report', {
    minutes: eventTimelineRange,
    limit: 300,
    types: eventTimelineTypes,
  });
}

function exportHistoryCsv() {
  socket.emit('export_price_history', {});
}

window.openEventTimelineAround = openEventTimelineAround;
