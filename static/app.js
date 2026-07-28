// ========== PWA Service Worker ==========
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ========== 全局状态 ==========
const SOCKET_ACCESS_TOKEN = document.querySelector('meta[name="goldmonitor-socket-token"]')?.getAttribute('content') || '';
const socket = io(window.GoldMonitorShell.withSocketDefaults({
  auth: { token: SOCKET_ACCESS_TOKEN },
}));
const PORTFOLIO_TRANSACTION_IMPORT_FIELDS = ['id', 'position_id', 'type', 'name', 'mode', 'price', 'quantity', 'fee', 'trade_date', 'note'];
const PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS = ['name', 'type', 'mode', 'price', 'quantity'];

let portfolioState = { items: [], transactions: [], total: 0, rmb_summary: {}, usd_summary: {}, prices: {}, review: { rmb: {}, usd: {} }, alerts: { items: [], total: 0, enabled: 0, triggered: 0 }, import_backup: { available: false } };
let portfolioAnalyticsState = null;
let portfolioAnalyticsRange = 90;
let portfolioAnalyticsLoading = false;
let portfolioView = 'positions';
let portfolioDetailView = 'review';
let portfolioSearch = '';
let portfolioPositionFilter = 'all';
let portfolioPositionSort = 'recent';
let portfolioTransactionTypeFilter = 'all';
let portfolioTransactionModeFilter = 'all';
let portfolioTransactionSort = 'date_desc';
let activePortfolioPositionId = null;
let activePortfolioDetailId = null;
let activePortfolioAlertEditorId = null;
let portfolioDrafts = {};
let activePortfolioTransactionId = null;
let portfolioTransactionDrafts = {};
let portfolioAlertDrafts = {};
let pendingPortfolioSave = null;
let pendingPortfolioImportMessage = '';
let pendingPortfolioUndoMessage = '';
let portfolioImportPreview = null;
let portfolioImportPreviewRequestSeq = 0;
let appSettings = {
  onboarding_started: false,
  onboarding_completed: false,
  onboarding_version: 1,
  onboarding_completed_at: '',
  platform: 'windows',
  platform_capabilities: {},
  startup_enabled: false,
  startup_to_tray: true,
  floating_price_enabled: true,
  floating_price_opacity: 94,
  floating_price_display_mode: 'rmb_usd',
  floating_price_preset: 'compact',
  floating_price_snap_edge: true,
  floating_price_always_on_top: false,
  close_behavior: 'ask',
  close_remembered: false,
  alert_sound_enabled: true,
  alert_dialog_enabled: true,
  webhook_enabled: false,
  webhook_url: '',
  webhook_warning_enabled: true,
  webhook_critical_enabled: true,
  webhook_volatility_enabled: true,
  daily_digest_enabled: false,
  daily_digest_time: '20:00',
  daily_digest_email_enabled: true,
  daily_digest_webhook_enabled: false,
  email_warning_enabled: true,
  email_critical_enabled: true,
  email_volatility_enabled: true,
  alert_cooldown_minutes: 30,
  alert_quiet_start: '',
  alert_quiet_end: '',
  export_dir: '',
  export_dir_default: '',
  export_dir_effective: '',
  email_subject_template: '[金价预警·{level}] {title}',
  email_body_template: '',
  risk_assistant_enabled: true,
  risk_assistant_provider: 'deepseek',
  risk_assistant_depth: 'standard',
  deepseek_base_url: 'https://api.deepseek.com',
  deepseek_model: 'deepseek-v4-pro',
  deepseek_api_key_configured: false,
  deepseek_api_key_masked: '',
  openai_compatible_base_url: '',
  openai_compatible_model: '',
  openai_compatible_api_key_configured: false,
  openai_compatible_api_key_masked: '',
  risk_assistant_max_tokens: 1200,
  risk_assistant_cooldown_seconds: 15,
  risk_assistant_cache_minutes: 10,
};
// ========== Socket.IO ==========
socket.on('connect', () => {
  document.getElementById('statusDot').classList.remove('disconnected');
  document.getElementById('statusText').textContent = '本地服务已连接';
  document.getElementById('priceRetry').textContent = '重新获取';
});
socket.on('disconnect', () => {
  configImportPreviewRequestPayload = null;
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  document.getElementById('statusDot').classList.add('disconnected');
  document.getElementById('statusText').textContent = '本地服务已断开';
  document.getElementById('priceRetry').textContent = '重新连接';
  applyFetchStatus({
    ok: false,
    message: '本地服务连接已断开，程序会自动尝试重连。',
    retryable: true,
    reconnect: true,
  });
});
socket.on('connect_error', error => {
  document.getElementById('statusDot').classList.add('disconnected');
  document.getElementById('statusText').textContent = '本地服务连接失败';
  const reason = error && error.message ? error.message : '连接超时';
  applyFetchStatus({
    ok: false,
    message: '本地服务连接失败：' + reason,
    retryable: true,
    reconnect: true,
  });
});

socket.on('init_state', data => {
  applyMarketInitialState(data);
  applyAlertConfigurationState(data);
  applyAlertRulesState(data.alert_rules || {});
  applyPortfolio(data.portfolio || {});
  if (data.settings) applySettings(data.settings);
  if (data.daily_digest_status) applyDailyDigestStatus(data.daily_digest_status);
  if (data.risk_analysis_history) applyRiskHistory(data.risk_analysis_history);
  if (data.source_comparison) renderSourceComparison(data.source_comparison);
  if (data.source_health) renderSourceHealth(data.source_health);
  if (data.price_history_state) applyPriceHistory(data.price_history_state);
  updateVolUI();

  updatePriceDisplay(latestData);
  updateDailyStats(latestData);
  initChart();
  switchChartData();
  updateThresholdInputs();

  if (data.fetch_status) applyFetchStatus(data.fetch_status);
  else if (!data.ok) applyFetchStatus({ ok:false, message:'行情数据获取失败', retryable:true });
  setAlertEntries(data.alert_log || []);
  maybeOpenOnboarding();
  socket.emit('get_settings');
});

socket.on('show_close_dialog', data => {
  openCloseDialog(data || {});
});

socket.on('portfolio_updated', data => {
  applyPortfolio(data || {});
  if (pendingPortfolioImportMessage) {
    setPortfolioStatus(pendingPortfolioImportMessage, 'ok');
    pendingPortfolioImportMessage = '';
  } else if (pendingPortfolioUndoMessage) {
    setPortfolioStatus(pendingPortfolioUndoMessage, 'ok');
    pendingPortfolioUndoMessage = '';
  } else {
    setPortfolioStatus('持仓已更新。', 'ok');
  }
});

socket.on('portfolio_error', data => {
  pendingPortfolioSave = null;
  setPortfolioStatus((data && data.message) || '持仓更新失败。', 'fail');
});

socket.on('portfolio_exported', data => {
  const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : portfolioState.total;
  const kindText = data && data.kind === 'review' ? '复盘' : data && data.kind === 'transactions' ? '流水' : '持仓';
  setPortfolioStatus(data && data.saved_path ? '已导出' + kindText + ' ' + count + ' 条，保存至 ' + data.saved_path : kindText + '已导出。', 'ok');
});

socket.on('portfolio_export_error', data => {
  setPortfolioStatus((data && data.message) || '持仓导出失败。', 'fail');
});

socket.on('portfolio_analytics_updated', data => {
  portfolioAnalyticsState = data && typeof data === 'object' ? data : null;
  portfolioAnalyticsLoading = false;
  if (portfolioView === 'review') renderPortfolio();
});

socket.on('portfolio_analytics_error', data => {
  portfolioAnalyticsLoading = false;
  setPortfolioStatus((data && data.message) || '持仓收益与预警分析生成失败。', 'fail');
  if (portfolioView === 'review') renderPortfolio();
});

socket.on('portfolio_imported', data => {
  const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : 0;
  const summary = data && data.summary ? data.summary : {};
  const create = Number(summary.create || 0);
  const overwrite = Number(summary.overwrite || 0);
  pendingPortfolioImportMessage = '已导入流水 ' + count + ' 条（新增 ' + create + '，覆盖 ' + overwrite + '）。';
  setPortfolioStatus(pendingPortfolioImportMessage, 'ok');
});

socket.on('portfolio_import_previewed', data => {
  applyPortfolioImportBackendPreview(data || {});
});

socket.on('portfolio_import_undone', data => {
  if (data && data.ok) {
    pendingPortfolioUndoMessage = '已撤销最近一次 CSV 导入。';
    setPortfolioStatus(pendingPortfolioUndoMessage, 'ok');
  }
});

socket.on('portfolio_import_undo_error', data => {
  setPortfolioStatus((data && data.message) || '撤销导入失败。', 'fail');
  if (data && data.import_backup) {
    portfolioState.import_backup = normalizePortfolioImportBackup(data.import_backup);
    renderPortfolioImportBackup();
  }
});

registerMarketDashboardSocketHandlers(socket);

registerSettingsSocketHandlers(socket);

registerAlertRuleSocketHandlers(socket);

registerAlertConfigurationSocketHandlers(socket);

registerOperationsSocketHandlers(socket);

registerRiskAnalysisSocketHandlers(socket);

registerHistoryReviewSocketHandlers(socket);

registerAlertLogSocketHandlers(socket);

function downloadText(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType || 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

// ========== 通用界面工具 ==========
function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

function syncEllipsisTitle(eventOrElement) {
  let target = eventOrElement && eventOrElement.target ? eventOrElement.target : eventOrElement;
  while (target && target.nodeType === 1 && target !== document.body) {
    const style = window.getComputedStyle(target);
    const isEllipsis = style.textOverflow === 'ellipsis' && style.overflow !== 'visible';
    const text = (target.textContent || '').trim();
    if (isEllipsis && text) {
      const isTruncated = target.scrollWidth > target.clientWidth || target.scrollHeight > target.clientHeight;
      if (isTruncated) {
        if (!target.getAttribute('title') || target.dataset.ellipsisTitle === 'true') {
          target.setAttribute('title', text);
          target.dataset.ellipsisTitle = 'true';
        }
      } else if (target.dataset.ellipsisTitle === 'true') {
        target.removeAttribute('title');
        delete target.dataset.ellipsisTitle;
      }
      return;
    }
    target = target.parentElement;
  }
}

function setupEllipsisTooltips() {
  document.addEventListener('mouseover', syncEllipsisTitle, true);
  document.addEventListener('focusin', syncEllipsisTitle, true);
}

setupEllipsisTooltips();

// ========== 关闭确认 ==========
function openCloseDialog() {
  document.getElementById('closeRemember').checked = false;
  document.getElementById('closeBackdrop').classList.add('show');
}

function closeCloseDialog() {
  document.getElementById('closeBackdrop').classList.remove('show');
}

function submitCloseChoice(choice) {
  closeCloseDialog();
  socket.emit('close_choice', {
    choice,
    remember: document.getElementById('closeRemember').checked,
  });
}

function onCloseBackdrop(event) {
  if (event.target.id === 'closeBackdrop') submitCloseChoice('cancel');
}
