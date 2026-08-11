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
