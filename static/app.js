// ========== PWA Service Worker ==========
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

// ========== 音效 ==========
function playAlertSound(type) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    if (type === 'critical' || type === 'upper') {
      osc.frequency.value = 1000; osc.type = 'square';
      gain.gain.setValueAtTime(0.15, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.4);
    } else if (type === 'warning' || type === 'volatility') {
      osc.frequency.value = 660; osc.type = 'sine';
      gain.gain.setValueAtTime(0.12, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.6);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.6);
    } else {
      osc.frequency.value = 520; osc.type = 'triangle';
      gain.gain.setValueAtTime(0.1, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.8);
      osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.8);
    }
  } catch(e) {}
}

// ========== 全局状态 ==========
const SOCKET_ACCESS_TOKEN = document.querySelector('meta[name="goldmonitor-socket-token"]')?.getAttribute('content') || '';
const BASE_TITLE = '金价监控';
const socket = io(window.GoldMonitorShell.withSocketDefaults({
  auth: { token: SOCKET_ACCESS_TOKEN },
}));
let currentMode = 'rmb';
let chartPeriod = 'realtime';
let chart = null;
const MAX_POINTS = 60;
const RECENT_OPS_LIMIT = 5;
const CHART_PERIODS = {
  realtime: { label: '价格走势', minutes: null, limit: 60, live: true },
  '1h': { label: '1小时走势', minutes: 60, limit: 360 },
  '4h': { label: '4小时走势', minutes: 240, limit: 720 },
  day: { label: '日内走势', minutes: 1440, limit: 1440 },
  '7d': { label: '7日走势', minutes: 10080, limit: 2100 },
  '30d': { label: '30日走势', minutes: 43200, limit: 1500 },
  '90d': { label: '90日走势', minutes: 129600, limit: 2160 },
  '5min': { label: '5分钟波动', minutes: null, limit: 96, kline: true },
};
const PORTFOLIO_TRANSACTION_IMPORT_FIELDS = ['id', 'position_id', 'type', 'name', 'mode', 'price', 'quantity', 'fee', 'trade_date', 'note'];
const PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS = ['name', 'type', 'mode', 'price', 'quantity'];
const ALERT_RULE_DEFS = [
  { type: 'upper_warning', title: '上涨关注', direction: '高于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'upper_critical', title: '上涨警告', direction: '高于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
  { type: 'lower_warning', title: '下跌关注', direction: '低于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'lower_critical', title: '下跌警告', direction: '低于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
];
const ALERT_PROFILE_SETTING_KEYS = [
  'alert_sound_enabled',
  'alert_dialog_enabled',
  'alert_cooldown_minutes',
  'alert_quiet_start',
  'alert_quiet_end',
  'email_warning_enabled',
  'email_critical_enabled',
  'email_volatility_enabled',
  'webhook_warning_enabled',
  'webhook_critical_enabled',
  'webhook_volatility_enabled',
];

let historyUsd = { labels: [], prices: [] };
let historyRmb = { labels: [], prices: [] };
let klines5min = [];
let chartHistoryState = { period: null, items: [] };
let chartEvents = [];
let latestData = null;
let allThresholds = {};
let volConfig = { percent: null, minutes: 10, enabled: false };
let activeAlertRule = null;
let alertProfiles = { items: [], total: 0, current_profile_id: '' };
let pendingAlertProfileApply = false;
let alertRulesState = { schema_version: 1, items: [], total: 0, summary: {}, by_kind: {}, migration: {}, invalid_count: 0, load_error: '' };
let alertRuleFilter = 'all';
let alertRuleStatusFilter = 'all';
let alertRuleSearch = '';
let selectedAlertRuleIds = [];
let activeUnifiedAlertRuleId = null;
let activeAlertRuleDetailId = null;
let alertRuleDraft = null;
let alertRuleInsights = {};
let alertRuleInsightLoading = {};
let alertRuleSimulation = null;
let alertRuleSimulationLoading = false;
let alertRuleSimulationRequestId = '';
let alertRuleSimulationDays = 30;
let watchTargets = [];
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
let activeWatchTargetId = null;
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
let pendingSettingsSave = false;
let settingsSaveFailed = false;
let settingsSaveTimer = null;
let pendingUpdateInfo = null;
let pendingConfigImportPayload = null;
let pendingConfigImportPreview = null;
let configImportPreviewRequestPayload = null;
let pendingDataArchiveRestore = null;
let recentOpsRecords = [];
let autoUpdateTimer = null;
let lastAutoUpdateCheckAt = 0;
let opsUpdateStatus = null;
let onboardingStep = 1;
let onboardingManual = false;
let onboardingAutoChecked = false;
const AUTO_UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
function autoUpdateIntervalMs() {
  return AUTO_UPDATE_CHECK_INTERVAL_MS;
}
let alertEntries = [];
let alertLogSearch = '';
let activeAlert = null;
let mergedAlertCount = 0;
let riskAnalysisRunning = false;
let riskAnalysisHistory = [];
let riskComparisonSelection = [];
let pendingRiskForceTrigger = null;
let deepseekModelOptions = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'];
let latestPriceHistoryState = { items: [], stats: {}, total: 0 };
let latestSourceHealthState = { items: [], summary: {} };
let latestSourceComparisonState = { items: [], summary: {}, status: 'insufficient' };
let dailyDigestStatusState = {};

function chartUnitLabel() {
  return currentMode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function updateChartTitle() {
  const config = CHART_PERIODS[chartPeriod] || CHART_PERIODS.realtime;
  document.getElementById('chartTitle').textContent = config.label + ' · ' + chartUnitLabel();
}

function requestChartHistory(period) {
  const config = CHART_PERIODS[period];
  if (!config || config.live || config.kline) return;
  socket.emit('get_price_history', {
    scope: 'chart',
    period,
    minutes: config.minutes,
    limit: config.limit,
  });
}

function longChartPeriod() {
  return ['7d', '30d', '90d'].includes(chartPeriod);
}

function chartResolutionDate(date) {
  if (chartPeriod === 'realtime' || Number.isNaN(date.getTime())) return date;
  const seconds = chartHistoryState.period === chartPeriod
    ? Number(chartHistoryState.resolution_seconds || 0)
    : 0;
  if (!seconds) return date;
  const bucket = new Date(date.getTime());
  if (seconds >= 86400) {
    bucket.setHours(0, 0, 0, 0);
    return bucket;
  }
  const milliseconds = seconds * 1000;
  return new Date(Math.floor(bucket.getTime() / milliseconds) * milliseconds);
}

function chartHistoryLabel(item) {
  const raw = item.timestamp || item.time || '';
  if (!raw) return '--';
  const date = chartResolutionDate(new Date(raw));
  if (!Number.isNaN(date.getTime())) {
    const hhmm = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    if (longChartPeriod()) {
      return (date.getMonth() + 1) + '/' + date.getDate() + ' ' + hhmm;
    }
    return hhmm;
  }
  return String(raw).replace('T', ' ').slice(0, longChartPeriod() ? 16 : 8);
}

function klineNumber(kline, key) {
  const value = kline[key];
  if (value == null || value === '') return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function klineOhlcForMode(kline, label) {
  const suffix = currentMode === 'usd' ? '' : '_rmb';
  const open = klineNumber(kline, 'open' + suffix);
  const high = klineNumber(kline, 'high' + suffix);
  const low = klineNumber(kline, 'low' + suffix);
  const close = klineNumber(kline, 'close' + suffix);
  if (![open, high, low, close].every(Number.isFinite)) return null;
  return { x: label, y: close, o: open, h: high, l: low, c: close };
}

function setChartEmptyState(message) {
  const empty = document.getElementById('chartEmptyState');
  if (!empty) return;
  if (message) {
    empty.textContent = message;
    empty.hidden = false;
  } else {
    empty.textContent = '';
    empty.hidden = true;
  }
}

function chartEmptyMessage(pointCount) {
  if (pointCount) return '';
  if (chartPeriod === '5min') return '暂无5分钟波动数据，需累计至少2个有效行情采样点。';
  if (chartPeriod !== 'realtime') return '暂无历史价格数据。';
  return '';
}

function normalizeChartEvents(events) {
  if (!Array.isArray(events)) return [];
  const seen = new Set();
  return events
    .filter(item => item && (item.timestamp || item.time))
    .map(item => ({
      type: item.type || 'alert',
      level: item.level || item.type || 'warning',
      timestamp: item.timestamp || '',
      time: item.time || '',
      label: item.label || (item.type === 'risk' ? '风险分析' : '预警'),
      message: item.message || '',
    }))
    .filter(item => {
      const key = [item.type, item.level, item.timestamp, item.time, item.message].join('|');
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(-120);
}

function addChartEvent(event) {
  chartEvents = normalizeChartEvents([...chartEvents, event]);
  switchChartData();
}

function chartEventLabel(event) {
  const raw = event.timestamp || event.time || '';
  const date = chartResolutionDate(new Date(raw));
  if (!Number.isNaN(date.getTime())) {
    if (longChartPeriod()) {
      const hhmm = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
      return (date.getMonth() + 1) + '/' + date.getDate() + ' ' + hhmm;
    }
    if (chartPeriod === 'realtime') {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    }
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
  }
  const text = String(raw).replace('T', ' ');
  if (chartPeriod === 'realtime' && /^\d{2}:\d{2}:\d{2}$/.test(text)) return text;
  if (/^\d{2}:\d{2}/.test(text)) return chartPeriod === 'realtime' ? text.slice(0, 8) : text.slice(0, 5);
  return text.slice(0, longChartPeriod() ? 16 : 5);
}

function activeChartEvents(labels) {
  const labelSet = new Set((labels || []).map(item => String(item)));
  return chartEvents
    .map(item => Object.assign({}, item, { chartLabel: chartEventLabel(item) }))
    .filter(item => labelSet.has(item.chartLabel));
}

const chartEventPlugin = {
  id: 'goldMonitorEvents',
  afterDatasetsDraw(chartInstance, args, pluginOptions) {
    const events = pluginOptions && Array.isArray(pluginOptions.events) ? pluginOptions.events : [];
    if (!events.length) return;
    const xScale = chartInstance.scales.x;
    const area = chartInstance.chartArea;
    const ctx = chartInstance.ctx;
    const labels = chartInstance.data.labels.map(item => String(item));
    ctx.save();
    events.forEach(event => {
      const index = labels.indexOf(String(event.chartLabel));
      if (index < 0) return;
      const x = xScale.getPixelForValue(index);
      const isRisk = event.type === 'risk';
      const color = isRisk ? 'rgba(91,155,213,0.85)' : event.level === 'critical' ? 'rgba(224,85,106,0.9)' : 'rgba(232,184,48,0.85)';
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(x, area.top + 4);
      ctx.lineTo(x, area.bottom - 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, area.top + 8, 3, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.restore();
  },
};

// ========== 模式切换 ==========
function switchMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
  document.querySelector(`.mode-btn[data-mode="${mode}"]`).classList.add('active');
  const isUsd = mode === 'usd';
  document.getElementById('priceLabel').textContent = isUsd ? 'XAU/USD · 美元/盎司' : 'XAU/CNY · 人民币/克';
  updateChartTitle();
  const thresholdUnit = document.getElementById('thresholdUnit');
  if (thresholdUnit) thresholdUnit.textContent = isUsd ? '(USD/oz)' : '(RMB/克)';
  if (latestData) { updatePriceDisplay(latestData); updateDailyStats(latestData); }
  updateRiskButtonState();
  switchChartData();
  updateThresholdInputs();
  renderAlertRuleCenter();
}

// ========== 图表周期切换 ==========
function switchChartPeriod(period) {
  if (!CHART_PERIODS[period]) period = 'realtime';
  chartPeriod = period;
  document.querySelectorAll('.chart-tg').forEach(b => b.classList.remove('active'));
  const active = document.querySelector(`.chart-tg[data-period="${period}"]`);
  if (active) active.classList.add('active');
  updateChartTitle();
  requestChartHistory(period);
  switchChartData();
}

function switchChartData() {
  if (!chart) return;
  const isUsd = currentMode === 'usd';
  let labels, prices;

  if (chartPeriod === '5min') {
    const rows = klines5min
      .map(kline => ({ label: kline.time, point: klineOhlcForMode(kline, kline.time) }))
      .filter(row => row.point);
    labels = rows.map(row => row.label);
    prices = rows.map(row => row.point);
  } else if (chartPeriod !== 'realtime') {
    const items = chartHistoryState.period === chartPeriod && Array.isArray(chartHistoryState.items)
      ? chartHistoryState.items
      : [];
    const field = isUsd ? 'usd' : 'rmb';
    labels = items.map(chartHistoryLabel);
    prices = items.map(item => item[field]).filter(value => value != null);
    if (prices.length !== labels.length) {
      const filtered = items.filter(item => item[field] != null);
      labels = filtered.map(chartHistoryLabel);
      prices = filtered.map(item => item[field]);
    }
  } else {
    const hist = isUsd ? historyUsd : historyRmb;
    labels = [...hist.labels]; prices = [...hist.prices];
  }
  chart.data.labels = labels;
  chart.data.datasets[0].data = prices;
  chart.options.plugins.goldMonitorEvents = { events: activeChartEvents(labels) };
  chart.options.scales.y.ticks.callback = v => (isUsd ? '$' : '¥') + v.toLocaleString('en-US');
  setChartEmptyState(chartEmptyMessage(prices.length));
  chart.update();
}

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
  latestData = {
    usd: data.usd, rmb: data.rmb, rate: data.rate,
    gold_source: data.gold_source,
    gold_time: data.gold_time,
    gold_cached: data.gold_cached,
    gold_error: data.gold_error,
    rate_source: data.rate_source,
    rate_time: data.rate_time,
    rate_cached: data.rate_cached,
    rate_error: data.rate_error,
    previous_usd: data.previous_usd, previous_rmb: data.previous_rmb,
    change_usd: data.usd && data.previous_usd ? data.usd - data.previous_usd : 0,
    change_pct_usd: data.usd && data.previous_usd ? (data.usd - data.previous_usd) / data.previous_usd * 100 : 0,
    change_rmb: data.rmb && data.previous_rmb ? data.rmb - data.previous_rmb : 0,
    change_pct_rmb: data.rmb && data.previous_rmb ? (data.rmb - data.previous_rmb) / data.previous_rmb * 100 : 0,
    time: data.history.length ? data.history[data.history.length-1].time : '--',
    daily: data.daily || {},
  };
  historyUsd = { labels:[], prices:[] };
  historyRmb = { labels:[], prices:[] };
  data.history.forEach(h => {
    historyUsd.labels.push(h.time); historyUsd.prices.push(h.usd);
    historyRmb.labels.push(h.time); historyRmb.prices.push(h.rmb);
  });
  klines5min = data.klines_5min || [];
  allThresholds = data.thresholds || {};
  volConfig = data.volatility_config || { percent: null, minutes: 10, enabled: false };
  applyAlertRulesState(data.alert_rules || {});
  applyAlertProfiles(data.alert_profiles || {});
  applyWatchTargets(data.watch_targets || []);
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

socket.on('price_update', data => {
  latestData = data;
  if (Array.isArray(data.klines_5min)) {
    klines5min = data.klines_5min;
  }

  historyUsd.labels.push(data.time); historyUsd.prices.push(data.usd);
  historyRmb.labels.push(data.time); historyRmb.prices.push(data.rmb);
  if (historyUsd.labels.length > MAX_POINTS) { historyUsd.labels.shift(); historyUsd.prices.shift(); }
  if (historyRmb.labels.length > MAX_POINTS) { historyRmb.labels.shift(); historyRmb.prices.shift(); }

  updatePriceDisplay(data);
  updateDailyStats(data);
  requestPortfolioRefresh();
  if (data.source_comparison) renderSourceComparison(data.source_comparison);
  if (chart && chartPeriod === 'realtime') {
    const hist = currentMode === 'usd' ? historyUsd : historyRmb;
    chart.data.labels = [...hist.labels];
    chart.data.datasets[0].data = [...hist.prices];
    chart.options.plugins.goldMonitorEvents = { events: activeChartEvents(chart.data.labels) };
    setChartEmptyState(chartEmptyMessage(chart.data.datasets[0].data.length));
    chart.update('none');
  } else if (chart && chartPeriod === '5min') {
    switchChartData();
  }
  checkThresholdProximity();
});

socket.on('fetch_error', data => applyFetchStatus(data || { ok:false, message:'行情数据获取失败', retryable:true }));

socket.on('fetch_status', data => {
  applyFetchStatus(data || {});
});

socket.on('alert', data => {
  addLogEntry(data);
  addChartEvent({
    type: 'alert',
    level: data.type || 'warning',
    timestamp: data.timestamp || '',
    time: data.time || '',
    label: alertLevelLabel(data.type),
    message: data.message || '',
  });
  showAlertModal(data);
  flashTitle(data.type === 'critical' ? '警告' : data.type === 'warning' ? '关注' : '波动预警');
});

socket.on('alert_log_exported', data => {
  const status = document.getElementById('alertLogStatus');
  const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : alertEntries.length;
  status.textContent = data && data.saved_path ? '已导出 ' + count + ' 条，保存至 ' + data.saved_path : '告警记录已导出。';
  status.className = 'log-status ok';
});

socket.on('alert_log_export_error', data => {
  const status = document.getElementById('alertLogStatus');
  status.textContent = (data && data.message) || '告警记录导出失败。';
  status.className = 'log-status fail';
});

socket.on('alert_log_cleared', data => {
  const status = document.getElementById('alertLogStatus');
  if (data && data.ok === false) {
    status.textContent = '警报记录清空失败，请检查导出目录权限。';
    status.className = 'log-status fail';
    return;
  }
  setAlertEntries([]);
  status.textContent = '警报记录已清空。';
  status.className = 'log-status ok';
});

socket.on('alert_log_status_updated', data => {
  if (!data || !data.entry) return;
  mergeAlertLogEntry(data.entry);
});

socket.on('alert_log_handling_updated', data => {
  const status = document.getElementById('alertLogStatus');
  if (data && data.entry) mergeAlertLogEntry(data.entry);
  status.textContent = data && data.entry && data.entry.handled ? '警报已标记为已处理。' : '警报处置已更新。';
  status.className = 'log-status ok';
});

socket.on('alert_log_status_error', data => {
  const status = document.getElementById('alertLogStatus');
  status.textContent = (data && data.message) || '警报记录状态更新失败。';
  status.className = 'log-status fail';
});

socket.on('alert_log_handling_error', data => {
  const status = document.getElementById('alertLogStatus');
  status.textContent = (data && data.message) || '警报处置更新失败。';
  status.className = 'log-status fail';
});

socket.on('alert_notification_resent', data => {
  const status = document.getElementById('alertLogStatus');
  if (data && data.entry) mergeAlertLogEntry(data.entry);
  status.textContent = '通知正在重新发送。';
  status.className = 'log-status';
});

socket.on('alert_notification_resend_error', data => {
  const status = document.getElementById('alertLogStatus');
  status.textContent = (data && data.message) || '通知重发失败。';
  status.className = 'log-status fail';
});

socket.on('show_close_dialog', data => {
  openCloseDialog(data || {});
});

socket.on('thresholds_updated', data => {
  allThresholds = data;
  updateThresholdInputs();
  clearCurrentAlertProfileMatch();
});

socket.on('volatility_updated', data => {
  volConfig = {
    percent: data.percent != null ? data.percent : null,
    minutes: data.minutes || 10,
    enabled: !!data.enabled,
  };
  updateVolUI();
  clearCurrentAlertProfileMatch();
});

socket.on('alert_rules_updated', data => {
  applyAlertRulesState(data || {});
});

socket.on('alert_rule_saved', data => {
  activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  resetAlertRuleSimulation();
  setAlertRuleCenterStatus('预警规则已保存。', 'ok');
});

socket.on('alert_rule_deleted', data => {
  if (data && activeUnifiedAlertRuleId === data.id) activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  setAlertRuleCenterStatus('预警规则已删除。', 'ok');
});

socket.on('alert_rule_toggled', data => {
  setAlertRuleCenterStatus(data && data.enabled ? '预警规则已启用。' : '预警规则已停用。', 'ok');
});

socket.on('alert_rule_reset', () => {
  setAlertRuleCenterStatus('预警规则触发状态已重置。', 'ok');
});

socket.on('alert_rules_batch_updated', data => {
  const count = Number(data && data.count) || 0;
  const actionLabel = {
    enable: '启用',
    disable: '停用',
    reset: '重置',
    delete: '删除',
  }[data && data.action] || '更新';
  selectedAlertRuleIds = [];
  setAlertRuleCenterStatus('已批量' + actionLabel + ' ' + count + ' 条规则。', 'ok');
});

socket.on('alert_rule_insight', data => {
  const ruleId = data && data.rule_id ? String(data.rule_id) : '';
  if (!ruleId) return;
  alertRuleInsights[ruleId] = data;
  delete alertRuleInsightLoading[ruleId];
  renderAlertRuleCenter();
});

socket.on('alert_rule_simulation', data => {
  const requestId = data && data.request_id ? String(data.request_id) : '';
  if (!requestId || requestId !== alertRuleSimulationRequestId) return;
  alertRuleSimulationLoading = false;
  alertRuleSimulation = data;
  setAlertRuleCenterStatus(data && data.usable ? '历史模拟已完成。' : (data && data.message) || '现有历史数据无法完成模拟。', data && data.usable ? 'ok' : 'fail');
  renderAlertRuleCenter();
});

socket.on('alert_rule_simulation_error', data => {
  const requestId = data && data.request_id ? String(data.request_id) : '';
  if (!requestId || requestId !== alertRuleSimulationRequestId) return;
  alertRuleSimulationLoading = false;
  alertRuleSimulation = { error: (data && data.message) || '历史模拟失败，请稍后重试。' };
  setAlertRuleCenterStatus(alertRuleSimulation.error, 'fail');
  renderAlertRuleCenter();
});

socket.on('alert_rule_duplicated', data => {
  const rule = data && data.rule ? data.rule : null;
  activeUnifiedAlertRuleId = rule && rule.id ? rule.id : null;
  alertRuleDraft = rule ? cloneAlertRuleDraft(rule) : null;
  resetAlertRuleSimulation();
  setAlertRuleCenterStatus('已复制规则，可继续编辑。', 'ok');
  renderAlertRuleCenter();
});

socket.on('alert_rule_error', data => {
  alertRuleInsightLoading = {};
  setAlertRuleCenterStatus((data && data.message) || '预警规则操作失败，未保存的内容仍保留。', 'fail');
  renderAlertRuleCenter();
});

socket.on('alert_rule_migration_status', data => {
  if (!data) return;
  if (data.load_error) setAlertRuleCenterStatus(data.load_error, 'fail');
});

socket.on('alert_profiles_updated', data => {
  pendingAlertProfileApply = false;
  applyAlertProfiles(data || {});
  setAlertProfileStatus('预警策略模板已更新。', 'ok');
});

socket.on('alert_profile_error', data => {
  pendingAlertProfileApply = false;
  setAlertProfileStatus((data && data.message) || '预警策略模板操作失败。', 'fail');
});

socket.on('watch_targets_updated', data => {
  applyWatchTargets(data || []);
  setWatchTargetStatus('观察清单已更新。', 'ok');
});

socket.on('watch_target_error', data => {
  setWatchTargetStatus((data && data.message) || '观察清单更新失败。', 'fail');
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

socket.on('settings_updated', data => {
  if (settingsSaveTimer) {
    clearTimeout(settingsSaveTimer);
    settingsSaveTimer = null;
  }
  const shouldClearProfileMatch = alertProfileSettingsChanged(data || {});
  if (settingsSaveFailed) {
    appSettings = Object.assign({}, appSettings, data || {});
    if (shouldClearProfileMatch) clearCurrentAlertProfileMatch();
    pendingSettingsSave = false;
    return;
  }
  applySettings(data || {});
  if (shouldClearProfileMatch) clearCurrentAlertProfileMatch();
  document.getElementById('settingsMessage').textContent = '';
  if (pendingSettingsSave) closeSettings();
  pendingSettingsSave = false;
});

socket.on('settings_error', data => {
  if (settingsSaveTimer) {
    clearTimeout(settingsSaveTimer);
    settingsSaveTimer = null;
  }
  pendingSettingsSave = false;
  settingsSaveFailed = true;
  document.getElementById('settingsMessage').textContent = data.message || '设置保存失败';
  if (data && data.export_dir_check) renderExportDirStatus(data.export_dir_check);
});

socket.on('onboarding_started', data => {
  if (data && data.settings) appSettings = Object.assign({}, appSettings, data.settings);
});

socket.on('onboarding_completed', data => {
  const finishButton = document.getElementById('onboardingFinishButton');
  const skipButton = document.getElementById('onboardingSkipButton');
  if (finishButton) finishButton.disabled = false;
  if (skipButton) skipButton.disabled = false;
  if (!data || data.ok === false) return;
  if (data.settings) applySettings(data.settings);
  document.getElementById('onboardingBackdrop').classList.remove('show');
  if (data.startup_error) setOpsStatus('首次使用设置已保存，但开机自启动设置失败，请检查系统权限。', false);
});

socket.on('onboarding_error', data => {
  const message = document.getElementById('onboardingMessage');
  const finishButton = document.getElementById('onboardingFinishButton');
  const skipButton = document.getElementById('onboardingSkipButton');
  if (message) message.textContent = (data && data.message) || '首次使用设置保存失败。';
  if (finishButton) finishButton.disabled = false;
  if (skipButton) skipButton.disabled = false;
});

socket.on('daily_digest_status', data => {
  applyDailyDigestStatus(data || {});
});

socket.on('daily_digest_previewed', data => {
  const button = document.getElementById('btnPreviewDailyDigest');
  if (button) button.disabled = false;
  if (!data || data.ok === false) {
    setDailyDigestStatus((data && data.message) || '生成摘要预览失败。', false);
    return;
  }
  renderDailyDigestPreview(data);
  setDailyDigestStatus('摘要预览已生成，未发送通知。', true);
});

socket.on('daily_digest_test_result', data => {
  const button = document.getElementById('btnTestDailyDigest');
  if (button) button.disabled = false;
  if (data && data.digest) renderDailyDigestPreview(data.digest);
  setDailyDigestStatus(
    data && data.message ? '测试发送：' + data.message : '测试发送已完成。',
    !!(data && data.ok)
  );
});

socket.on('threshold_error', data => alert(data.message));

socket.on('update_status', data => {
  applyUpdateStatus(data || {});
});

socket.on('risk_analysis_status', data => {
  riskAnalysisRunning = !!(data && data.running);
  if (data && data.message) {
    applyRiskStatus(data.message, riskAnalysisRunning ? 'loading' : '');
  }
  updateRiskButtonState();
});

socket.on('risk_analysis_result', data => {
  riskAnalysisRunning = false;
  const usageText = formatRiskUsage(data && data.usage ? data.usage : null);
  renderRiskDiagnostic(null);
  applyRiskStatus(usageText ? '分析完成。' + usageText : '分析完成。', '');
  renderRiskSnapshot(data && data.snapshot ? data.snapshot : null);
  renderRiskStructured(data && data.structured ? data.structured : null);
  document.getElementById('riskResult').textContent = data && data.content ? data.content : '未返回分析内容。';
  pendingRiskForceTrigger = null;
  setRiskForceButtonVisible(false);
  if (data && data.snapshot) {
    addChartEvent({
      type: 'risk',
      level: 'analysis',
      timestamp: data.snapshot.analysis_time || '',
      label: data.structured && data.structured.risk_level ? '风险 ' + data.structured.risk_level : '风险分析',
      message: data.content || '',
    });
  }
  updateRiskButtonState();
});

socket.on('risk_analysis_error', data => {
  riskAnalysisRunning = false;
  applyRiskStatus(data && data.message ? data.message : '风险分析失败。', 'error');
  renderRiskDiagnostic(data && data.diagnostic ? data.diagnostic : null);
  if (data && data.snapshot) renderRiskSnapshot(data.snapshot);
  updateRiskButtonState();
});

socket.on('risk_analysis_cache_hit', data => {
  riskAnalysisRunning = false;
  renderRiskDiagnostic(null);
  const age = data && data.cache_age_seconds != null ? Math.max(0, Number(data.cache_age_seconds)) : 0;
  const ageText = age >= 60 ? Math.floor(age / 60) + ' 分钟前' : Math.max(1, age) + ' 秒前';
  applyRiskStatus((data && data.message ? data.message : '已复用最近同一行情分析。') + ' 生成于 ' + ageText + '。', '');
  renderRiskSnapshot(data && data.snapshot ? data.snapshot : null);
  renderRiskStructured(data && data.structured ? data.structured : null);
  document.getElementById('riskResult').textContent = data && data.content ? data.content : '暂无缓存分析内容。';
  pendingRiskForceTrigger = data && data.trigger ? data.trigger : null;
  setRiskForceButtonVisible(true);
  if (data && data.snapshot) {
    addChartEvent({
      type: 'risk',
      level: 'analysis',
      timestamp: data.snapshot.analysis_time || '',
      label: data.structured && data.structured.risk_level ? '风险 ' + data.structured.risk_level : '风险分析',
      message: data.content || '',
    });
  }
  updateRiskButtonState();
});

socket.on('risk_analysis_history_updated', data => {
  applyRiskHistory(data || {});
});

socket.on('risk_model_test_result', data => {
  const el = document.getElementById('riskModelTestStatus');
  if (!el) return;
  el.textContent = data && data.message ? data.message : '模型测试完成。';
  el.className = 'model-test-status ' + (data && data.ok ? 'ok' : 'fail');
});

socket.on('open_risk_analysis', data => {
  if (!openRiskAnalysis()) return;
  if (data && data.run) requestRiskAnalysis({ source: data.source || 'floating_price' });
});

socket.on('risk_model_options_updated', data => {
  if (!data || data.provider !== 'deepseek') return;
  deepseekModelOptions = Array.isArray(data.models) && data.models.length ? data.models : deepseekModelOptions;
  renderDeepseekModelOptions(appSettings.deepseek_model || 'deepseek-v4-pro');
  const status = document.getElementById('deepseekModelStatus');
  if (status) {
    status.textContent = data.error
      ? data.error + ' 当前显示兜底模型。'
      : '模型列表已更新，来源：' + (data.source === 'api' ? '接口' : '兜底列表') + '。';
  }
});

socket.on('source_health_updated', data => {
  renderSourceHealth(data || {});
});

socket.on('market_sources_updated', data => {
  setSourceManagerStatus(data && data.message ? data.message : '数据源配置已更新。', true);
});

socket.on('market_sources_error', data => {
  setSourceManagerStatus(data && data.message ? data.message : '数据源配置更新失败。', false);
});

socket.on('market_source_retry_result', data => {
  const pending = data && data.pending;
  const message = data && data.message ? data.message : (pending ? '正在探测数据源...' : '数据源探测完成。');
  setSourceManagerStatus(message, pending ? null : !!(data && data.ok));
  if (data && data.source_health) renderSourceHealth(data.source_health);
});

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

socket.on('config_backup_ready', data => {
  if (!data) return;
  if (data.ok === false) {
    addRecentOpsRecord('config_export', data);
    setOpsExportStatus(data, '配置已导出', '配置导出失败。');
    return;
  }
  if (data.saved_path) {
    addRecentOpsRecord('config_export', data);
    setOpsExportStatus(data, '配置已导出', '配置导出失败。');
    return;
  }
  if (!data.content) return;
  const fallbackData = { ...data, filename: data.filename || 'GoldMonitor-config.json' };
  downloadText(fallbackData.filename, data.content, 'application/json;charset=utf-8');
  addRecentOpsRecord('config_export', fallbackData);
  setOpsExportStatus(fallbackData, '配置已导出', '配置导出失败。');
});

socket.on('data_archive_exported', data => {
  addRecentOpsRecord('data_archive_export', data || {});
  setOpsExportStatus(data || {}, '完整数据归档已创建', '完整数据归档失败。');
});

socket.on('data_archive_export_error', data => {
  addRecentOpsRecord('data_archive_export', data || {});
  setOpsExportStatus(data || {}, '完整数据归档已创建', '完整数据归档失败。');
});

socket.on('data_archive_restored', data => {
  if (!data || data.ok === false) return;
  setOpsStatus(data.message || '完整数据已恢复，正在重新载入界面。', true);
});

socket.on('diagnostics_ready', data => {
  if (!data) return;
  if (data.ok === false) {
    addRecentOpsRecord('diagnostics_export', data);
    setOpsExportStatus(data, '诊断报告已导出', '诊断报告导出失败。');
    return;
  }
  if (data.saved_path) {
    addRecentOpsRecord('diagnostics_export', data);
    setOpsExportStatus(data, '诊断报告已导出', '诊断报告导出失败。');
    return;
  }
  if (!data.content) return;
  const fallbackData = { ...data, filename: data.filename || 'GoldMonitor-diagnostics.json' };
  downloadText(fallbackData.filename, data.content, 'application/json;charset=utf-8');
  addRecentOpsRecord('diagnostics_export', fallbackData);
  setOpsExportStatus(fallbackData, '诊断报告已导出', '诊断报告导出失败。');
});

function hideDiagnosticsCopyFallback() {
  const fallback = document.getElementById('diagnosticsCopyFallback');
  if (!fallback) return;
  fallback.value = '';
  fallback.hidden = true;
}

function showDiagnosticsCopyFallback(content) {
  const fallback = document.getElementById('diagnosticsCopyFallback');
  if (!fallback) return;
  fallback.value = content;
  fallback.hidden = false;
  requestAnimationFrame(() => {
    fallback.focus();
    fallback.select();
  });
}

function copyTextWithSelection(content) {
  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.setAttribute('readonly', 'readonly');
  textarea.style.position = 'fixed';
  textarea.style.left = '-9999px';
  textarea.style.top = '0';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  try {
    return document.execCommand('copy');
  } catch (error) {
    return false;
  } finally {
    textarea.remove();
  }
}

function copyTextToClipboard(content) {
  const fallbackCopy = () => Promise.resolve(copyTextWithSelection(content));
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(content).then(() => true).catch(fallbackCopy);
  }
  return fallbackCopy();
}

socket.on('diagnostics_copy_ready', data => {
  if (!data) return;
  if (data.ok === false) {
    setOpsStatus(data.message || '诊断摘要生成失败。', false);
    return;
  }
  const content = data.content || '';
  if (!content) {
    setOpsStatus('诊断摘要为空，无法复制。', false);
    return;
  }
  copyTextToClipboard(content)
    .then(copied => {
      if (copied) {
        hideDiagnosticsCopyFallback();
        setOpsStatus('诊断摘要已复制。', true);
        return;
      }
      showDiagnosticsCopyFallback(content);
      setOpsStatus('自动复制失败，已展示诊断摘要，可手动复制。', false);
    })
    .catch(() => {
      showDiagnosticsCopyFallback(content);
      setOpsStatus('自动复制失败，已展示诊断摘要，可手动复制。', false);
    });
});

socket.on('exports_folder_opened', data => {
  addRecentOpsRecord('open_exports_folder', data || {});
  if (data && data.ok === false) {
    setOpsExportStatus(data, '已打开导出目录', '无法打开导出目录。');
    return;
  }
  setOpsStatus(data && data.message ? data.message : '已打开导出目录。', !!(data && data.ok));
});

socket.on('config_import_previewed', data => {
  const text = document.getElementById('configImportText') ? document.getElementById('configImportText').value.trim() : '';
  const previewedPayload = configImportPreviewRequestPayload;
  configImportPreviewRequestPayload = null;
  if (!previewedPayload || previewedPayload !== text) {
    pendingConfigImportPayload = null;
    pendingConfigImportPreview = null;
    setOpsStatus('备份内容已变更，请重新预检。', false);
    return;
  }
  if (data && data.importable) {
    pendingConfigImportPayload = previewedPayload;
    pendingConfigImportPreview = data;
    setOpsStatus(renderConfigImportPreview(data), true);
    return;
  }
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  setOpsStatus(renderConfigImportPreview(data), false);
});

socket.on('config_import_result', data => {
  configImportPreviewRequestPayload = null;
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  setOpsStatus(data && data.message ? data.message : '配置导入完成。', !!(data && data.ok));
});

socket.on('settings_reset_result', data => {
  setOpsStatus(data && data.message ? data.message : '已恢复默认设置。', !!(data && data.ok));
});

socket.on('test_alert_result', data => {
  const statusEl = document.getElementById('testAlertStatus');
  if (!statusEl) return;
  statusEl.textContent = data && data.message ? data.message : '测试提醒已触发。';
  statusEl.className = 'test-email-status ' + (data && data.ok ? 'ok' : 'fail');
});

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

function toggleSourceHealthDetails() {
  const details = document.getElementById('sourceHealthDetails');
  if (!details) return;
  details.hidden = !details.hidden;
}

function sourceQualityText(quality) {
  if (!quality || typeof quality !== 'object') return '';
  const score = quality.score == null ? '--' : quality.score;
  const label = quality.label || quality.level || '--';
  return '行情质量 ' + score + '分/' + label;
}

function setSourceManagerStatus(message, ok) {
  const status = document.getElementById('sourceManagerStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'source-manager-status' + (ok === true ? ' ok' : ok === false ? ' fail' : '');
}

function renderMarketQualityDetails(quality) {
  const box = document.getElementById('marketQualityDetails');
  if (!box) return;
  const reasons = box.querySelector('.market-quality-reasons');
  const deductions = quality && Array.isArray(quality.deductions) ? quality.deductions : [];
  if (!deductions.length) {
    reasons.innerHTML = '<div class="market-quality-reason none"><span class="market-quality-points">0分</span><span>当前没有质量扣分项</span></div>';
    return;
  }
  reasons.innerHTML = deductions.map(item => [
    '<div class="market-quality-reason" title="' + escapeHtml(item.detail || item.label || '') + '">',
    '<span class="market-quality-points">-' + escapeHtml(item.points == null ? '--' : item.points) + '分</span>',
    '<span>' + escapeHtml(item.detail || item.label || '质量异常') + '</span>',
    '</div>',
  ].join('')).join('');
}

function sourceCategoryLabel(category) {
  if (category === 'gold') return '金价源';
  if (category === 'forex') return '汇率源';
  return category || '数据源';
}

function marketSourcePreferences() {
  const adapters = latestSourceHealthState && latestSourceHealthState.adapters || {};
  const enabled = {};
  const order = {};
  Object.keys(adapters).forEach(category => {
    const items = Array.isArray(adapters[category]) ? adapters[category].slice() : [];
    items.sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
    order[category] = items.map(item => item.key).filter(Boolean);
    enabled[category] = items.filter(item => item.enabled).map(item => item.key).filter(Boolean);
  });
  return { enabled, order };
}

function updateMarketSourceEnabled(category, key, checked) {
  const preferences = marketSourcePreferences();
  const categoryEnabled = Array.isArray(preferences.enabled[category]) ? preferences.enabled[category].slice() : [];
  if (checked && !categoryEnabled.includes(key)) categoryEnabled.push(key);
  if (!checked) preferences.enabled[category] = categoryEnabled.filter(item => item !== key);
  else preferences.enabled[category] = preferences.order[category].filter(item => categoryEnabled.includes(item));
  if (!preferences.enabled[category].length) {
    setSourceManagerStatus(sourceCategoryLabel(category) + '至少启用一个。', false);
    renderSourceManager(latestSourceHealthState);
    return;
  }
  setSourceManagerStatus('正在保存数据源配置...', null);
  socket.emit('update_market_sources', preferences);
}

function moveMarketSource(category, key, direction) {
  const preferences = marketSourcePreferences();
  const order = Array.isArray(preferences.order[category]) ? preferences.order[category].slice() : [];
  const currentIndex = order.indexOf(key);
  const nextIndex = currentIndex + Number(direction || 0);
  if (currentIndex < 0 || nextIndex < 0 || nextIndex >= order.length) return;
  const displaced = order[nextIndex];
  order[nextIndex] = key;
  order[currentIndex] = displaced;
  preferences.order[category] = order;
  preferences.enabled[category] = order.filter(item => preferences.enabled[category].includes(item));
  setSourceManagerStatus('正在保存数据源顺序...', null);
  socket.emit('update_market_sources', preferences);
}

function retryMarketSource(key) {
  setSourceManagerStatus('正在探测数据源...', null);
  socket.emit('retry_market_source', { key });
}

function resetMarketSources() {
  setSourceManagerStatus('正在恢复默认数据源顺序...', null);
  socket.emit('reset_market_sources');
}

function renderSourceManager(data) {
  const box = document.getElementById('sourceManager');
  if (!box) return;
  const list = box.querySelector('.source-manager-list');
  const adapters = data && data.adapters && typeof data.adapters === 'object' ? data.adapters : {};
  const categories = ['gold', 'forex'].filter(category => Array.isArray(adapters[category]));
  if (!categories.length) {
    list.innerHTML = '<div class="source-manager-meta">等待数据源目录</div>';
    return;
  }
  list.innerHTML = categories.map(category => {
    const items = adapters[category].slice().sort((left, right) => Number(left.order || 0) - Number(right.order || 0));
    const enabledCount = items.filter(item => item.enabled).length;
    const rows = items.map((item, index) => {
      const successRate = item.success_rate_pct == null ? '--' : Number(item.success_rate_pct).toFixed(1) + '%';
      const latency = item.median_latency_ms == null ? '--' : Number(item.median_latency_ms).toFixed(0) + 'ms';
      const failures = Number(item.consecutive_failures || 0);
      const currentLabel = item.active ? '当前主源' : item.current_cached ? '当前缓存来源' : item.current ? '正在切换' : '';
      const disableToggle = !!item.enabled && enabledCount <= 1;
      const safeKey = escapeHtml(item.key || '');
      const safeCategory = escapeHtml(category);
      return [
        '<div class="source-manager-row' + (item.enabled ? '' : ' disabled') + '">',
        '<input class="source-manager-toggle" type="checkbox" aria-label="启用' + escapeHtml(item.name || '') + '" ',
        item.enabled ? 'checked ' : '',
        disableToggle ? 'disabled ' : '',
        'onchange="updateMarketSourceEnabled(\'' + safeCategory + '\',\'' + safeKey + '\',this.checked)">',
        '<div class="source-manager-copy">',
        '<div class="source-manager-name">' + escapeHtml(item.name || '--') + (currentLabel ? '<span class="source-manager-current">' + currentLabel + '</span>' : '') + '</div>',
        '<div class="source-manager-meta">近 ' + escapeHtml(item.sample_count || 0) + ' 次 · 成功率 ' + escapeHtml(successRate) + ' · 中位延迟 ' + escapeHtml(latency) + (failures ? ' · 连续失败 ' + failures + ' 次' : '') + '</div>',
        '</div>',
        '<div class="source-manager-actions">',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="moveMarketSource(\'' + safeCategory + '\',\'' + safeKey + '\',-1)" ' + (index === 0 ? 'disabled' : '') + '>上移</button>',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="moveMarketSource(\'' + safeCategory + '\',\'' + safeKey + '\',1)" ' + (index === items.length - 1 ? 'disabled' : '') + '>下移</button>',
        '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="retryMarketSource(\'' + safeKey + '\')">探测</button>',
        '</div>',
        '</div>',
      ].join('');
    }).join('');
    return '<div class="source-manager-category"><div class="source-manager-category-title">' + sourceCategoryLabel(category) + '</div>' + rows + '</div>';
  }).join('');
}

function renderSourceHealth(data) {
  latestSourceHealthState = data || { items: [], summary: {} };
  if (data && data.comparison) renderSourceComparison(data.comparison);
  renderMarketQualityDetails(data && data.quality ? data.quality : {});
  renderSourceManager(latestSourceHealthState);
  const box = document.getElementById('sourceHealth');
  if (!box) return;
  const items = Array.isArray(data.items) ? data.items : [];
  const summary = data.summary || {};
  const head = box.querySelector('.source-summary-text');
  const list = box.querySelector('.source-health-list');
  const ok = Number(summary.ok || 0);
  const failed = Number(summary.failed || 0);
  const cached = Number(summary.cached || 0);
  const countText = failed
    ? '异常 ' + failed + ' · 正常 ' + ok
    : (cached ? '缓存 ' + cached + ' · 正常 ' + ok : '正常 ' + ok);
  head.textContent = [sourceQualityText(data.quality), countText].filter(Boolean).join(' · ');
  head.title = head.textContent;
  if (!items.length) {
    list.innerHTML = '<div class="source-health-item"><span class="source-health-dot"></span><span class="source-health-name">等待数据源检查</span><span class="source-health-meta">--</span></div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const cls = item.cached ? 'cached' : item.ok ? 'ok' : 'fail';
    const elapsed = item.elapsed_ms == null ? '--' : item.elapsed_ms + 'ms';
    const status = item.cached ? '缓存' : item.ok ? '正常' : '异常';
    const title = item.error ? item.error : status;
    const successRate = item.success_rate_pct == null ? '--' : Number(item.success_rate_pct).toFixed(1) + '%';
    const failures = Number(item.consecutive_failures || 0);
    const rolling = '成功率 ' + successRate + ' · ' + elapsed + (failures ? ' · 连续失败 ' + failures + ' 次' : '');
    return [
      '<div class="source-health-item" title="' + escapeHtml(title) + '">',
      '<span class="source-health-dot ' + cls + '"></span>',
      '<span class="source-health-name">' + escapeHtml(item.name || '--') + (item.active ? ' · 当前主源' : '') + '</span>',
      '<span class="source-health-meta">' + escapeHtml(status + ' · ' + rolling) + '</span>',
      '</div>',
    ].join('');
  }).join('');
}

function renderSourceComparison(data) {
  latestSourceComparisonState = Object.assign({ items: [], summary: {}, status: 'insufficient' }, data || {});
  const box = document.getElementById('sourceComparison');
  if (!box) return;
  const head = box.querySelector('.source-comparison-head span:first-child');
  const badge = box.querySelector('.source-comparison-badge');
  const list = box.querySelector('.source-comparison-list');
  const summary = latestSourceComparisonState.summary || {};
  const status = latestSourceComparisonState.status || 'insufficient';
  const statusText = status === 'anomaly' ? '异常' : status === 'normal' ? '正常' : '不足';
  head.textContent = summary.spread_pct == null
    ? '行情源价差'
    : '行情源价差 ' + Number(summary.spread_pct).toFixed(2) + '%';
  badge.textContent = statusText;
  badge.className = 'source-comparison-badge ' + status;
  const items = Array.isArray(latestSourceComparisonState.items)
    ? latestSourceComparisonState.items.filter(item => item && item.usd != null).slice(0, 4)
    : [];
  if (!items.length) {
    list.innerHTML = '<div class="source-comparison-item"><span class="source-comparison-name">等待行情源样本</span><span class="source-comparison-price">--</span></div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const state = item.cached ? '缓存' : item.stale ? '过期' : item.available ? '可比' : '待确认';
    return [
      '<div class="source-comparison-item" title="' + escapeHtml((item.name || '') + ' · ' + state) + '">',
      '<span class="source-comparison-name">' + escapeHtml(item.name || '--') + ' · ' + escapeHtml(state) + '</span>',
      '<span class="source-comparison-price">$' + Number(item.usd).toFixed(2) + '</span>',
      '</div>',
    ].join('');
  }).join('');
}

function refreshSourceHealth() {
  socket.emit('get_source_health');
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

function setOpsStatus(message, ok) {
  const el = document.getElementById('opsStatus');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = ok ? 'var(--down)' : 'var(--up)';
}

function recentOpsTypeLabel(type) {
  if (type === 'config_export') return '导出配置';
  if (type === 'data_archive_export') return '完整数据归档';
  if (type === 'diagnostics_export') return '生成诊断';
  if (type === 'open_exports_folder') return '打开目录';
  return '运维操作';
}

function recentOpsTimeLabel(date) {
  return date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function addRecentOpsRecord(type, data) {
  const payload = data && typeof data === 'object' ? data : {};
  const detail = payload.error_detail && typeof payload.error_detail === 'object' ? payload.error_detail : {};
  const dirCheck = payload.export_dir_check && typeof payload.export_dir_check === 'object' ? payload.export_dir_check : {};
  const ok = payload.ok !== false;
  const savedPath = payload.saved_path || '';
  const path = savedPath || payload.export_dir || detail.export_dir || dirCheck.path || '';
  const message = ok
    ? (savedPath ? '文件已保存到导出目录。' : (type === 'open_exports_folder' ? '已打开导出目录。' : (payload.message || '操作完成。')))
    : (detail.message || payload.message || '操作失败。');
  const record = {
    id: Date.now() + '-' + recentOpsRecords.length,
    type,
    label: recentOpsTypeLabel(type),
    ok,
    status: ok ? '成功' : '失败',
    time: recentOpsTimeLabel(new Date()),
    path,
    message,
    error: detail.error || '',
    actions: !ok && Array.isArray(dirCheck.actions) ? dirCheck.actions : [],
  };
  recentOpsRecords = [record, ...recentOpsRecords].slice(0, RECENT_OPS_LIMIT);
  renderRecentOpsRecords();
}

function renderRecentOpsRecords() {
  const list = document.getElementById('recentOpsList');
  if (!list) return;
  if (!recentOpsRecords.length) {
    list.innerHTML = '<div class="ops-recent-empty">暂无操作记录</div>';
    return;
  }
  list.innerHTML = recentOpsRecords.map(record => {
    const stateClass = record.ok ? 'ok' : 'fail';
    const actions = Array.isArray(record.actions) ? record.actions.map(exportDirActionButton).filter(Boolean).join('') : '';
    const path = record.path ? '<div class="ops-recent-path" title="' + escapeHtml(record.path) + '">' + escapeHtml(record.path) + '</div>' : '';
    const failure = !record.ok
      ? '<div class="ops-recent-error"><strong>失败原因</strong><span>' + escapeHtml([record.message, record.error ? '底层错误：' + record.error : ''].filter(Boolean).join(' ')) + '</span></div>'
      : '';
    return [
      '<div class="ops-recent-item ' + stateClass + '">',
      '<div class="ops-recent-head">',
      '<span class="ops-recent-title">' + escapeHtml(record.label) + '</span>',
      '<span class="ops-recent-state ' + stateClass + '">' + escapeHtml(record.status) + '</span>',
      '<span class="ops-recent-time">' + escapeHtml(record.time) + '</span>',
      '</div>',
      path,
      record.ok ? '<div class="ops-recent-message" title="' + escapeHtml(record.message) + '">' + escapeHtml(record.message) + '</div>' : failure,
      actions ? '<div class="export-dir-actions">' + actions + '</div>' : '',
      '</div>',
    ].join('');
  }).join('');
}

function setOpsExportStatus(data, successLabel, fallbackMessage) {
  const el = document.getElementById('opsStatus');
  if (!el) return;
  const payload = data && typeof data === 'object' ? data : {};
  const ok = payload.ok !== false;
  el.style.color = ok ? 'var(--down)' : 'var(--up)';
  if (ok) {
    const savedPath = payload.saved_path || '';
    const filename = payload.filename || '';
    let message = successLabel || '导出已完成';
    if (savedPath) {
      message += '：' + savedPath;
    } else if (filename) {
      message += '，文件名：' + filename + '。';
    } else {
      message += '。';
    }
    el.innerHTML = [
      '<span>' + escapeHtml(message) + '</span>',
      savedPath ? '<button class="btn-clear-sm btn-muted-sm export-dir-action" type="button" onclick="openExportsFolder()">打开目录</button>' : '',
    ].join('');
    return;
  }
  const detail = data && data.error_detail && typeof data.error_detail === 'object' ? data.error_detail : {};
  const dirCheck = data && data.export_dir_check && typeof data.export_dir_check === 'object' ? data.export_dir_check : {};
  const message = detail.message || payload.message || fallbackMessage || '导出失败。';
  const extra = dirCheck.message && dirCheck.message !== message ? dirCheck.message : '';
  const error = detail.error ? '底层错误：' + detail.error : '';
  const actions = Array.isArray(dirCheck.actions) ? dirCheck.actions.map(exportDirActionButton).filter(Boolean) : [];
  el.innerHTML = [
    '<span>' + escapeHtml([message, extra, error].filter(Boolean).join(' ')) + '</span>',
    actions.length ? '<span class="export-dir-actions">' + actions.join('') + '</span>' : '',
  ].join('');
}

function exportConfig() {
  setOpsStatus('正在导出配置...', true);
  socket.emit('export_config');
}

function exportDataArchive() {
  setOpsStatus('正在创建完整数据归档...', true);
  socket.emit('export_data_archive');
}

function formatDataArchiveBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function resetDataArchivePreview() {
  pendingDataArchiveRestore = null;
  const preview = document.getElementById('dataArchivePreview');
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (preview) preview.innerHTML = '';
  if (restoreButton) {
    restoreButton.hidden = true;
    restoreButton.disabled = false;
  }
}

function renderDataArchivePreview(data, fileName) {
  const preview = document.getElementById('dataArchivePreview');
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (!preview || !restoreButton) return;
  if (!data || data.ok === false || data.restorable === false) {
    preview.innerHTML = '<div class="data-archive-preview-error">' + escapeHtml((data && data.message) || '归档预检失败。') + '</div>';
    restoreButton.hidden = true;
    return;
  }
  const items = Array.isArray(data.items) ? data.items.filter(item => item && item.present) : [];
  const labels = items.slice(0, 8).map(item => item.label || item.key).filter(Boolean);
  const remaining = Math.max(0, items.length - labels.length);
  const detail = labels.join('、') + (remaining ? '等 ' + items.length + ' 项' : '');
  preview.innerHTML = [
    '<div class="data-archive-preview-ok"><strong>归档校验通过</strong></div>',
    '<div>文件：' + escapeHtml(fileName || '') + '</div>',
    '<div>来源版本：' + escapeHtml(data.source_app_version || '未知') + '；导出时间：' + escapeHtml((data.exported_at || '').replace('T', ' ')) + '</div>',
    '<div>数据量：' + escapeHtml(String(data.files || 0)) + ' 项，' + escapeHtml(formatDataArchiveBytes(data.bytes)) + '</div>',
    detail ? '<div>包含：' + escapeHtml(detail) + '</div>' : '',
    data.contains_sensitive_data ? '<div class="data-archive-preview-warning">归档包含通知密钥等敏感配置。</div>' : '',
  ].join('');
  restoreButton.hidden = false;
}

function chooseDataArchive() {
  const input = document.getElementById('dataArchiveFile');
  if (!input) {
    setOpsStatus('未找到归档文件选择入口。', false);
    return;
  }
  input.value = '';
  resetDataArchivePreview();
  input.click();
}

async function previewDataArchive(input) {
  const file = input && input.files ? input.files[0] : null;
  resetDataArchivePreview();
  if (!file) return;
  setOpsStatus('正在校验完整数据归档...', true);
  const formData = new FormData();
  formData.append('archive', file, file.name);
  try {
    const response = await fetch('/api/data-archive/preview', {
      method: 'POST',
      headers: { 'X-GoldMonitor-Token': SOCKET_ACCESS_TOKEN },
      body: formData,
    });
    const data = await response.json();
    renderDataArchivePreview(data, file.name);
    if (!response.ok || !data.restore_token) {
      setOpsStatus(data.message || '归档预检失败。', false);
      return;
    }
    pendingDataArchiveRestore = {
      token: data.restore_token,
      fileName: file.name,
      preview: data,
    };
    setOpsStatus(data.message || '归档预检通过，请确认恢复。', true);
  } catch (error) {
    renderDataArchivePreview({ ok: false, message: '无法上传或校验归档文件。' }, file.name);
    setOpsStatus('无法上传或校验归档文件。', false);
  }
}

async function confirmDataArchiveRestore() {
  if (!pendingDataArchiveRestore || !pendingDataArchiveRestore.token) {
    setOpsStatus('请先选择并校验归档文件。', false);
    return;
  }
  const confirmed = confirm('恢复完整数据会覆盖当前设置、持仓、预警、复盘和历史记录。是否继续？');
  if (!confirmed) return;
  const restoreButton = document.getElementById('restoreDataArchiveButton');
  if (restoreButton) restoreButton.disabled = true;
  setOpsStatus('正在恢复完整数据，请勿关闭应用...', true);
  try {
    const response = await fetch('/api/data-archive/restore', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-GoldMonitor-Token': SOCKET_ACCESS_TOKEN,
      },
      body: JSON.stringify({ restore_token: pendingDataArchiveRestore.token }),
    });
    const data = await response.json();
    pendingDataArchiveRestore = null;
    if (!response.ok || data.ok === false) {
      setOpsStatus(data.message || '完整数据恢复失败，原数据已回滚。', false);
      if (restoreButton) restoreButton.disabled = false;
      return;
    }
    setOpsStatus(data.message || '完整数据已恢复，正在重新载入界面。', true);
    setTimeout(() => window.location.reload(), 800);
  } catch (error) {
    setOpsStatus('完整数据恢复请求失败，请重新选择归档并确认当前数据状态。', false);
    if (restoreButton) restoreButton.disabled = false;
  }
}

function configImportSectionLabel(section) {
  if (section === 'settings') return '通用设置';
  if (section === 'thresholds') return '预警阈值';
  if (section === 'alert_profiles') return '预警策略模板';
  if (section === 'alert_rules') return '统一预警规则';
  return section || '未知配置';
}

function configImportSecretActionLabel(action) {
  if (action === 'import') return '导入';
  if (action === 'clear') return '清空';
  return '保留现有';
}

function configImportFormatText(data) {
  const schemaVersion = Number(data && data.schema_version);
  const expectedSchemaVersion = Number(data && data.expected_schema_version);
  const format = data && typeof data.format === 'string' ? data.format.trim() : '';
  const sourceAppVersion = data && typeof data.source_app_version === 'string'
    ? data.source_app_version.trim()
    : '';
  if (data && data.needs_migration) {
    return '旧版备份将在导入时迁移' + (sourceAppVersion ? '（来源版本 ' + sourceAppVersion + '）' : '');
  }
  const resolvedVersion = Number.isInteger(schemaVersion) && schemaVersion >= 0
    ? schemaVersion
    : (Number.isInteger(expectedSchemaVersion) && expectedSchemaVersion >= 0 ? expectedSchemaVersion : null);
  const formatText = resolvedVersion !== null ? 'schema v' + resolvedVersion : (format || '当前格式');
  return '当前备份格式：' + formatText + (sourceAppVersion ? '（来源版本 ' + sourceAppVersion + '）' : '');
}

function renderConfigImportPreview(data) {
  if (!data || data.ok === false || data.importable === false) {
    return (data && data.message) || '配置导入预检失败。';
  }
  const rawSections = Array.isArray(data.sections) ? data.sections : [];
  const sections = rawSections.map(configImportSectionLabel);
  const ignored = data.ignored && typeof data.ignored === 'object' ? data.ignored : {};
  const ignoredFieldCount = []
    .concat(Array.isArray(ignored.settings) ? ignored.settings : [])
    .concat(Array.isArray(ignored.thresholds) ? ignored.thresholds : [])
    .length;
  const ignoredProfileCount = Array.isArray(ignored.alert_profiles) ? ignored.alert_profiles.length : 0;
  const ignoredRuleCount = Array.isArray(ignored.alert_rules) ? ignored.alert_rules.length : 0;
  const secretActions = rawSections.includes('settings') && data.secret_actions && typeof data.secret_actions === 'object'
    ? data.secret_actions
    : {};
  const secretSummary = Object.keys(secretActions).reduce((acc, key) => {
    const label = configImportSecretActionLabel(secretActions[key]);
    acc[label] = (acc[label] || 0) + 1;
    return acc;
  }, {});
  const secretText = Object.keys(secretSummary).map(label => label + ' ' + secretSummary[label] + ' 项').join('，');
  const parts = [
    '配置预检通过：将导入' + (sections.length ? sections.join('、') : '配置'),
    configImportFormatText(data),
  ];
  if (ignoredFieldCount) parts.push('忽略不支持字段 ' + ignoredFieldCount + ' 项');
  if (ignoredProfileCount) parts.push('忽略重复、无效或超限策略模板 ' + ignoredProfileCount + ' 项');
  if (ignoredRuleCount) parts.push('忽略重复、无效或超限预警规则 ' + ignoredRuleCount + ' 项');
  if (secretText) parts.push('敏感字段：' + secretText);
  parts.push('再次点击导入确认');
  return parts.join('；') + '。';
}

function importConfig() {
  const text = document.getElementById('configImportText').value.trim();
  if (!text) {
    setOpsStatus('请先粘贴配置备份 JSON。', false);
    return;
  }
  if (configImportPreviewRequestPayload !== null) {
    const changed = configImportPreviewRequestPayload !== text;
    setOpsStatus(changed ? '备份内容已变更，当前预检返回后请重新预检。' : '正在预检导入配置...', !changed);
    return;
  }
  if (pendingConfigImportPayload === text && pendingConfigImportPreview && pendingConfigImportPreview.importable) {
    setOpsStatus('正在导入配置...', true);
    socket.emit('import_config', { payload: text });
    pendingConfigImportPayload = null;
    pendingConfigImportPreview = null;
    return;
  }
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  configImportPreviewRequestPayload = text;
  setOpsStatus('正在预检导入配置...', true);
  socket.emit('preview_import_config', { payload: text });
}

function invalidateConfigImportPreviewOnInput() {
  const hasPreviewState = configImportPreviewRequestPayload !== null
    || pendingConfigImportPayload !== null
    || pendingConfigImportPreview !== null;
  if (!hasPreviewState) return;
  configImportPreviewRequestPayload = null;
  pendingConfigImportPayload = null;
  pendingConfigImportPreview = null;
  setOpsStatus('备份内容已变更，请重新预检。', false);
}

const configImportTextInput = document.getElementById('configImportText');
if (configImportTextInput) {
  configImportTextInput.addEventListener('input', invalidateConfigImportPreviewOnInput);
}

function exportDiagnostics() {
  setOpsStatus('正在生成诊断报告...', true);
  socket.emit('get_diagnostics');
}

function copyDiagnostics() {
  hideDiagnosticsCopyFallback();
  setOpsStatus('正在生成诊断摘要...', true);
  socket.emit('copy_diagnostics');
}

function openExportsFolder() {
  setOpsStatus('正在打开导出目录...', true);
  socket.emit('open_exports_folder');
}

function resetSettings() {
  if (!confirm('确定恢复默认设置并清空阈值吗？')) return;
  setOpsStatus('正在恢复默认设置...', true);
  socket.emit('reset_settings');
}

function configureSecretClear(inputId, statusId, buttonId, configured, statusText, readyLabel, emptyLabel) {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const button = document.getElementById(buttonId);
  if (!input || !status || !button) return;
  input.checked = false;
  status.textContent = statusText;
  button.disabled = !configured;
  button.textContent = configured ? readyLabel : emptyLabel;
  button.classList.remove('marked');
  button.dataset.defaultLabel = readyLabel;
  button.dataset.defaultStatus = statusText;
}

function toggleSecretClear(inputId, statusId, buttonId, selectedStatus) {
  const input = document.getElementById(inputId);
  const status = document.getElementById(statusId);
  const button = document.getElementById(buttonId);
  if (!input || !status || !button || button.disabled) return;
  input.checked = !input.checked;
  if (input.checked) {
    status.textContent = selectedStatus;
    button.textContent = '取消删除';
    button.classList.add('marked');
    return;
  }
  status.textContent = button.dataset.defaultStatus || '';
  button.textContent = button.dataset.defaultLabel || '删除已保存密钥';
  button.classList.remove('marked');
}

// ========== 设置 ==========
function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setRowHidden(id, hidden) {
  const el = document.getElementById(id);
  if (el) el.classList.toggle('platform-hidden', !!hidden);
}

function applyPlatformLabels() {
  const platform = appSettings.platform || 'windows';
  const capabilities = appSettings.platform_capabilities || {};
  const isMac = platform === 'macos';
  const menuBarMode = capabilities.floating_price_mode === 'menu_bar';

  setText('startupTrayLabel', isMac ? '自启动时进入菜单栏' : '自启动时进入托盘');
  setText('startupTrayDesc', isMac ? '开机启动后不弹出主窗口，可从菜单栏打开。' : '开机启动后不弹出主窗口，可从右下角托盘打开。');
  setText('floatingPriceLabel', menuBarMode ? '菜单栏金价' : '桌面金价悬浮条');
  setText('floatingPriceDesc', menuBarMode ? '在 macOS 菜单栏显示当前金价，并提供显示窗口、刷新和风险分析入口。' : '主窗口隐藏时，仍在桌面右下角显示当前金价。');
  setText('floatingDisplayDesc', menuBarMode ? '控制菜单栏优先显示人民币、美元或组合价格。' : '控制桌面悬浮条显示人民币、美元或组合内容。');
  setText('closeChoiceCopy', isMac ? '隐藏到菜单栏后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。' : '最小化到右下角托盘后，程序会继续监控金价并在触发条件时提醒。也可以直接退出程序。');
  setText('closeMinimizeOption', isMac ? '隐藏到菜单栏' : '最小化到托盘');
  setText('closeMinimizeButton', isMac ? '隐藏到菜单栏' : '最小化到托盘');

  setRowHidden('floatingPresetRow', menuBarMode);
  setRowHidden('floatingOpacityRow', menuBarMode);
  setRowHidden('floatingSnapRow', menuBarMode);
  setRowHidden('floatingTopmostRow', menuBarMode);
}

function dailyDigestSelectedChannels() {
  const channels = [];
  if (appSettings.daily_digest_email_enabled !== false) channels.push('email');
  if (appSettings.daily_digest_webhook_enabled) channels.push('webhook');
  return channels;
}

function dailyDigestChannelText(channels) {
  const labels = { email: '邮件', webhook: 'Webhook' };
  const selected = Array.isArray(channels) ? channels : [];
  return selected.length ? selected.map(channel => labels[channel] || channel).join('、') : '未选择';
}

function dailyDigestTimestamp(value) {
  const text = String(value || '').trim();
  return text ? text.replace('T', ' ').slice(0, 16) : '';
}

function setDailyDigestStatus(message, ok) {
  const status = document.getElementById('dailyDigestStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'test-email-status' + (ok === true ? ' ok' : ok === false ? ' fail' : '');
}

function applyDailyDigestStatus(data) {
  const next = data && typeof data === 'object' ? data : {};
  dailyDigestStatusState = Object.assign({}, dailyDigestStatusState, next, {
    state: Object.assign({}, dailyDigestStatusState.state || {}, next.state || {}),
    schedule: Object.assign({}, dailyDigestStatusState.schedule || {}, next.schedule || {}),
  });
  const enabled = dailyDigestStatusState.enabled != null
    ? !!dailyDigestStatusState.enabled
    : !!appSettings.daily_digest_enabled;
  const time = dailyDigestStatusState.time || appSettings.daily_digest_time || '20:00';
  const channels = Array.isArray(dailyDigestStatusState.channels)
    ? dailyDigestStatusState.channels
    : dailyDigestSelectedChannels();
  const state = dailyDigestStatusState.state || {};
  const schedule = dailyDigestStatusState.schedule || {};
  const parts = [enabled ? '已启用，每日 ' + time : '未启用', '渠道：' + dailyDigestChannelText(channels)];
  const completedAt = dailyDigestTimestamp(state.last_completed_at);
  const testedAt = dailyDigestTimestamp(state.last_test_at);
  if (completedAt) parts.push('最近计划执行：' + completedAt);
  else if (enabled && schedule.reason === 'before_schedule') parts.push('等待今日计划时间');
  else if (enabled && schedule.reason === 'due') parts.push('等待任务执行');
  else if (enabled && schedule.reason === 'invalid_schedule') parts.push('发送时间无效');
  if (testedAt) parts.push('最近测试：' + testedAt);
  if (state.last_message) parts.push(state.last_message);
  const okStatuses = ['sent', 'queued'];
  const failStatuses = ['failed', 'partial', 'skipped'];
  const statusFlag = okStatuses.includes(state.last_status)
    ? true
    : failStatuses.includes(state.last_status) || schedule.reason === 'invalid_schedule'
      ? false
      : null;
  setDailyDigestStatus(parts.join('；'), statusFlag);
}

function renderDailyDigestPreview(data) {
  const preview = document.getElementById('dailyDigestPreview');
  if (!preview) return;
  const digest = data && data.digest ? data.digest : (data || {});
  const subject = String(digest.subject || '').trim();
  const message = String(digest.message || '').trim();
  preview.value = [subject, message].filter(Boolean).join('\n\n');
}

function applySettings(data) {
  appSettings = Object.assign({}, appSettings, data);
  applyPlatformLabels();
  const closeBehavior = appSettings.close_behavior || 'ask';
  document.getElementById('setStartup').checked = !!appSettings.startup_enabled;
  document.getElementById('setStartupTray').checked = !!appSettings.startup_to_tray;
  document.getElementById('setFloatingPrice').checked = appSettings.floating_price_enabled !== false;
  document.getElementById('setFloatingDisplayMode').value = appSettings.floating_price_display_mode || 'rmb_usd';
  document.getElementById('setFloatingPreset').value = appSettings.floating_price_preset || 'compact';
  document.getElementById('setFloatingOpacity').value = appSettings.floating_price_opacity || 94;
  document.getElementById('setFloatingSnapEdge').checked = appSettings.floating_price_snap_edge !== false;
  document.getElementById('setFloatingAlwaysOnTop').checked = !!appSettings.floating_price_always_on_top;
  document.getElementById('setCloseBehavior').value = closeBehavior;
  document.getElementById('setAlertSound').checked = !!appSettings.alert_sound_enabled;
  document.getElementById('setAlertDialog').checked = !!appSettings.alert_dialog_enabled;
  // 邮件通知
  document.getElementById('setSmtpServer').value = appSettings.smtp_server || '';
  document.getElementById('setSmtpPort').value = appSettings.smtp_port || '465';
  document.getElementById('setSmtpEncryption').value = appSettings.smtp_encryption || 'ssl';
  document.getElementById('setSmtpSender').value = appSettings.smtp_sender || '';
  document.getElementById('setSmtpPassword').value = '';
  const smtpPasswordStatus = appSettings.smtp_password_configured
    ? '已保存授权码：' + (appSettings.smtp_password_masked || '******') + '。输入新授权码后保存会替换当前授权码。'
    : '未保存授权码。输入授权码后保存即可启用邮件发送。';
  configureSecretClear(
    'clearSmtpPassword',
    'smtpPasswordStatus',
    'clearSmtpPasswordButton',
    !!appSettings.smtp_password_configured,
    smtpPasswordStatus,
    '删除已保存授权码',
    '暂无已保存授权码'
  );
  document.getElementById('setSmtpRecipient').value = appSettings.smtp_recipient || '';
  document.getElementById('setAlertCooldownMinutes').value = appSettings.alert_cooldown_minutes ?? 30;
  document.getElementById('setAlertQuietStart').value = appSettings.alert_quiet_start || '';
  document.getElementById('setAlertQuietEnd').value = appSettings.alert_quiet_end || '';
  document.getElementById('setEmailSubjectTemplate').value = appSettings.email_subject_template || '[金价预警·{level}] {title}';
  document.getElementById('setEmailBodyTemplate').value = appSettings.email_body_template || '';
  document.getElementById('setWebhookEnabled').checked = !!appSettings.webhook_enabled;
  document.getElementById('setWebhookUrl').value = appSettings.webhook_url || '';
  document.getElementById('setWebhookWarning').checked = appSettings.webhook_warning_enabled !== false;
  document.getElementById('setWebhookCritical').checked = appSettings.webhook_critical_enabled !== false;
  document.getElementById('setWebhookVolatility').checked = appSettings.webhook_volatility_enabled !== false;
  document.getElementById('setDailyDigestEnabled').checked = !!appSettings.daily_digest_enabled;
  document.getElementById('setDailyDigestTime').value = appSettings.daily_digest_time || '20:00';
  document.getElementById('setDailyDigestEmail').checked = appSettings.daily_digest_email_enabled !== false;
  document.getElementById('setDailyDigestWebhook').checked = !!appSettings.daily_digest_webhook_enabled;
  applyDailyDigestStatus(Object.assign({}, dailyDigestStatusState, {
    enabled: !!appSettings.daily_digest_enabled,
    time: appSettings.daily_digest_time || '20:00',
    channels: dailyDigestSelectedChannels(),
  }));
  document.getElementById('testEmailStatus').textContent = '';
  document.getElementById('testEmailStatus').className = 'test-email-status';
  const webhookStatus = document.getElementById('testWebhookStatus');
  if (webhookStatus) {
    webhookStatus.textContent = '';
    webhookStatus.className = 'test-email-status';
  }
  const testAlertStatus = document.getElementById('testAlertStatus');
  if (testAlertStatus) {
    testAlertStatus.textContent = '';
    testAlertStatus.className = 'test-email-status';
  }
  document.getElementById('setRiskAssistantEnabled').checked = appSettings.risk_assistant_enabled !== false;
  document.getElementById('setRiskAssistantProvider').value = appSettings.risk_assistant_provider || 'deepseek';
  document.getElementById('setRiskAssistantDepth').value = appSettings.risk_assistant_depth || 'standard';
  document.getElementById('setDeepseekBaseUrl').value = appSettings.deepseek_base_url || 'https://api.deepseek.com';
  renderDeepseekModelOptions(appSettings.deepseek_model || 'deepseek-v4-pro');
  document.getElementById('setDeepseekApiKey').value = '';
  const keyStatus = appSettings.deepseek_api_key_configured
    ? '已保存密钥：' + (appSettings.deepseek_api_key_masked || '******') + '。输入新 Key 后保存会替换当前密钥。'
    : '未保存密钥。输入 API Key 后保存即可启用该模型。';
  configureSecretClear(
    'clearDeepseekApiKey',
    'deepseekKeyStatus',
    'clearDeepseekApiKeyButton',
    !!appSettings.deepseek_api_key_configured,
    keyStatus,
    '删除已保存密钥',
    '暂无已保存密钥'
  );
  document.getElementById('setOpenaiCompatibleBaseUrl').value = appSettings.openai_compatible_base_url || '';
  document.getElementById('setOpenaiCompatibleModel').value = appSettings.openai_compatible_model || '';
  document.getElementById('setOpenaiCompatibleApiKey').value = '';
  const compatibleKeyStatus = appSettings.openai_compatible_api_key_configured
    ? '已保存密钥：' + (appSettings.openai_compatible_api_key_masked || '******') + '。输入新 Key 后保存会替换当前密钥。'
    : '未保存密钥。输入 API Key 后保存即可启用该接口。';
  configureSecretClear(
    'clearOpenaiCompatibleApiKey',
    'openaiCompatibleKeyStatus',
    'clearOpenaiCompatibleApiKeyButton',
    !!appSettings.openai_compatible_api_key_configured,
    compatibleKeyStatus,
    '删除已保存密钥',
    '暂无已保存密钥'
  );
  document.getElementById('setRiskMaxTokens').value = appSettings.risk_assistant_max_tokens || 1200;
  document.getElementById('setRiskCooldownSeconds').value = appSettings.risk_assistant_cooldown_seconds || 15;
  document.getElementById('setRiskCacheMinutes').value = appSettings.risk_assistant_cache_minutes ?? 10;
  applyExportDirSetting();
  const modelTestStatus = document.getElementById('riskModelTestStatus');
  if (modelTestStatus) {
    modelTestStatus.textContent = '';
    modelTestStatus.className = 'model-test-status';
  }
  updateRiskProviderFields();
  updateRiskButtonState();
  renderAlertRules();
  scheduleAutoUpdateCheck();
}

function applyExportDirSetting() {
  const input = document.getElementById('setExportDir');
  if (!input) return;
  const configured = appSettings.export_dir || '';
  const effective = appSettings.export_dir_effective || appSettings.export_dir_default || '';
  input.value = configured;
  renderExportDirStatus(appSettings.export_dir_check, configured
    ? '当前导出目录：' + effective
    : '当前使用默认导出目录：' + (effective || '未记录'));
}

function exportDirActionButton(action) {
  if (action === 'choose_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="chooseExportDir()">重新选择</button>';
  }
  if (action === 'use_default_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="useDefaultExportDirFromError()">使用默认</button>';
  }
  if (action === 'open_export_dir') {
    return '<button class="btn-clear-sm export-dir-action" type="button" onclick="openExportsFolder()">打开当前目录</button>';
  }
  return '';
}

function renderExportDirStatus(check, fallbackText) {
  const status = document.getElementById('exportDirStatus');
  if (!status) return;
  const data = check && typeof check === 'object' ? check : null;
  if (!data || !data.status) {
    status.textContent = fallbackText || '留空使用默认导出目录。';
    return;
  }
  const statusClass = data.ok ? 'ok' : 'fail';
  const actions = Array.isArray(data.actions) ? data.actions.map(exportDirActionButton).filter(Boolean) : [];
  status.innerHTML = [
    '<span class="export-dir-check ' + statusClass + '">' + escapeHtml(data.message || fallbackText || '') + '</span>',
    actions.length ? '<span class="export-dir-actions">' + actions.join('') + '</span>' : '',
  ].join('');
}

function clearSettingsMessage() {
  const message = document.getElementById('settingsMessage');
  if (message) message.textContent = '';
}

function resetExportDirField() {
  const input = document.getElementById('setExportDir');
  if (!input) return;
  input.value = '';
  clearSettingsMessage();
  renderExportDirStatus(null, '保存后将使用默认导出目录：' + (appSettings.export_dir_default || appSettings.export_dir_effective || '未记录'));
}

function useDefaultExportDirFromError() {
  resetExportDirField();
  setOpsStatus('已切换为默认导出目录，保存后生效。', true);
}

function chooseExportDir() {
  const input = document.getElementById('setExportDir');
  const status = document.getElementById('exportDirStatus');
  const button = document.getElementById('chooseExportDirButton');
  const picker = window.pywebview && window.pywebview.api && window.pywebview.api.choose_export_dir;
  if (!input) return;
  clearSettingsMessage();
  if (typeof picker !== 'function') {
    const message = '当前浏览器模式不支持系统目录选择器，请手动输入导出目录。';
    if (status) status.textContent = message;
    setOpsStatus(message, false);
    return;
  }

  if (status) status.textContent = '正在打开系统目录选择器...';
  if (button) button.disabled = true;
  Promise.resolve(picker.call(window.pywebview.api))
    .then(data => {
      const message = data && data.message ? data.message : '目录选择完成。';
      if (!data || !data.ok) {
        if (status) status.textContent = message;
        if (!data || !data.cancelled) setOpsStatus(message, false);
        return;
      }
      input.value = data.path || '';
      const savedMessage = message + '，保存后生效。';
      if (status) status.textContent = savedMessage;
      setOpsStatus('已选择导出目录，保存后生效。', true);
    })
    .catch(() => {
      const message = '无法打开系统目录选择器，请手动输入导出目录。';
      if (status) status.textContent = message;
      setOpsStatus(message, false);
    })
    .finally(() => {
      if (button) button.disabled = false;
    });
}

function renderDeepseekModelOptions(selected) {
  const select = document.getElementById('setDeepseekModel');
  const model = selected || 'deepseek-v4-pro';
  const options = Array.from(new Set([model, ...deepseekModelOptions].filter(Boolean)));
  select.innerHTML = options.map(item => (
    '<option value="' + escapeHtml(item) + '">' + escapeHtml(item) + '</option>'
  )).join('');
  select.value = model;
}

function updateRiskProviderFields() {
  const provider = document.getElementById('setRiskAssistantProvider').value || 'deepseek';
  document.querySelectorAll('.risk-provider-row').forEach(row => {
    row.classList.toggle('hidden', row.getAttribute('data-provider') !== provider);
  });
}

function refreshRiskModels() {
  const status = document.getElementById('deepseekModelStatus');
  if (status) status.textContent = '正在获取模型列表...';
  socket.emit('get_risk_model_options', { provider: 'deepseek' });
}

function testRiskModel() {
  const status = document.getElementById('riskModelTestStatus');
  if (status) {
    status.textContent = '正在测试当前模型生成能力...';
    status.className = 'model-test-status';
  }
  socket.emit('test_risk_model');
}

function switchSettingsTab(tab) {
  const tabs = ['general', 'email', 'webhook', 'digest', 'risk', 'ops'];
  tabs.forEach(name => {
    const active = tab === name;
    const suffix = name.charAt(0).toUpperCase() + name.slice(1);
    document.getElementById('settingsTab' + suffix).classList.toggle('active', active);
    document.getElementById('settingsTab' + suffix).setAttribute('aria-selected', String(active));
    document.getElementById('settingsPanel' + suffix).classList.toggle('active', active);
  });
  const body = document.querySelector('#settingsBackdrop .settings-body');
  if (body) body.scrollTop = 0;
  if (tab === 'risk') refreshRiskModels();
  if (tab === 'digest') socket.emit('get_daily_digest_status');
}

function openSettings() {
  applySettings(appSettings);
  switchSettingsTab('general');
  document.getElementById('settingsMessage').textContent = '';
  document.getElementById('settingsBackdrop').classList.add('show');
}

function onboardingPriceText() {
  if (Number.isFinite(Number(latestData.rmb))) return '¥' + Number(latestData.rmb).toFixed(2) + '/克';
  if (Number.isFinite(Number(latestData.usd))) return '$' + Number(latestData.usd).toFixed(2) + '/盎司';
  return '等待行情';
}

function updateOnboardingStatus() {
  const market = document.getElementById('onboardingMarketStatus');
  const price = document.getElementById('onboardingPriceStatus');
  const source = document.getElementById('onboardingSourceStatus');
  const statusText = document.getElementById('statusText');
  if (market) market.textContent = statusText && statusText.textContent ? statusText.textContent : '本地服务已连接';
  if (price) price.textContent = onboardingPriceText();
  if (source) source.textContent = latestData.gold_source || '等待行情';
}

function populateOnboardingFields() {
  document.getElementById('onboardingDisplayMode').value = appSettings.floating_price_display_mode || 'rmb_usd';
  document.getElementById('onboardingFloatingEnabled').checked = appSettings.floating_price_enabled !== false;
  document.getElementById('onboardingStartupEnabled').checked = !!appSettings.startup_enabled;
  document.getElementById('onboardingStartupTray').checked = appSettings.startup_to_tray !== false;
  document.getElementById('onboardingCloseBehavior').value = appSettings.close_behavior || 'ask';
  document.getElementById('onboardingAlertSound').checked = appSettings.alert_sound_enabled !== false;
  document.getElementById('onboardingAlertDialog').checked = appSettings.alert_dialog_enabled !== false;
  const cooldown = document.getElementById('onboardingCooldown');
  const cooldownValue = String(appSettings.alert_cooldown_minutes ?? 30);
  if (![...cooldown.options].some(option => option.value === cooldownValue)) {
    const option = document.createElement('option');
    option.value = cooldownValue;
    option.textContent = cooldownValue + ' 分钟';
    cooldown.appendChild(option);
  }
  cooldown.value = cooldownValue;
}

function onboardingPreferences() {
  return {
    floating_price_display_mode: document.getElementById('onboardingDisplayMode').value,
    floating_price_enabled: document.getElementById('onboardingFloatingEnabled').checked,
    startup_enabled: document.getElementById('onboardingStartupEnabled').checked,
    startup_to_tray: document.getElementById('onboardingStartupTray').checked,
    close_behavior: document.getElementById('onboardingCloseBehavior').value,
    alert_sound_enabled: document.getElementById('onboardingAlertSound').checked,
    alert_dialog_enabled: document.getElementById('onboardingAlertDialog').checked,
    alert_cooldown_minutes: document.getElementById('onboardingCooldown').value,
  };
}

function renderOnboardingSummary() {
  const summary = document.getElementById('onboardingSummary');
  if (!summary) return;
  const preferences = onboardingPreferences();
  const displayLabels = { rmb_usd: '人民币与美元', rmb_only: '仅人民币', usd_only: '仅美元' };
  const closeLabels = { ask: '关闭时询问', minimize_to_tray: '继续在后台运行', exit: '退出程序' };
  const parts = [
    '悬浮窗：' + (preferences.floating_price_enabled ? displayLabels[preferences.floating_price_display_mode] : '不启用'),
    '开机自启动：' + (preferences.startup_enabled ? '启用' : '不启用'),
    '关闭行为：' + (closeLabels[preferences.close_behavior] || '关闭时询问'),
    '提示音：' + (preferences.alert_sound_enabled ? '启用' : '关闭'),
    '警报窗口：' + (preferences.alert_dialog_enabled ? '启用' : '关闭'),
    '相同规则冷却：' + preferences.alert_cooldown_minutes + ' 分钟',
  ];
  summary.innerHTML = parts.map(part => '<div>' + escapeHtml(part) + '</div>').join('');
}

function showOnboardingStep(step) {
  onboardingStep = Math.max(1, Math.min(4, Number(step) || 1));
  document.querySelectorAll('[data-onboarding-step]').forEach(section => {
    section.classList.toggle('active', Number(section.dataset.onboardingStep) === onboardingStep);
  });
  document.querySelectorAll('[data-onboarding-progress]').forEach(item => {
    item.classList.toggle('active', Number(item.dataset.onboardingProgress) <= onboardingStep);
  });
  document.getElementById('onboardingBackButton').hidden = onboardingStep === 1;
  document.getElementById('onboardingNextButton').hidden = onboardingStep === 4;
  document.getElementById('onboardingFinishButton').hidden = onboardingStep !== 4;
  if (onboardingStep === 1) updateOnboardingStatus();
  if (onboardingStep === 4) renderOnboardingSummary();
}

function openOnboarding(manual) {
  onboardingManual = !!manual;
  populateOnboardingFields();
  const message = document.getElementById('onboardingMessage');
  if (message) message.textContent = '';
  document.getElementById('onboardingSkipButton').textContent = onboardingManual ? '关闭向导' : '暂不设置';
  document.getElementById('onboardingBackdrop').classList.add('show');
  showOnboardingStep(1);
  if (!onboardingManual && !appSettings.onboarding_started) socket.emit('start_onboarding');
}

function maybeOpenOnboarding() {
  if (onboardingAutoChecked) return;
  onboardingAutoChecked = true;
  if (appSettings.onboarding_completed) return;
  setTimeout(() => openOnboarding(false), 120);
}

function reopenOnboarding() {
  closeSettings();
  openOnboarding(true);
}

function changeOnboardingStep(delta) {
  showOnboardingStep(onboardingStep + Number(delta || 0));
}

function finishOnboarding() {
  const finishButton = document.getElementById('onboardingFinishButton');
  if (finishButton) finishButton.disabled = true;
  socket.emit('complete_onboarding', onboardingPreferences());
}

function skipOnboarding() {
  if (onboardingManual) {
    document.getElementById('onboardingBackdrop').classList.remove('show');
    return;
  }
  const skipButton = document.getElementById('onboardingSkipButton');
  if (skipButton) skipButton.disabled = true;
  socket.emit('complete_onboarding', {});
}

function closeSettings() {
  document.getElementById('settingsBackdrop').classList.remove('show');
}

function onSettingsBackdrop(event) {
  if (event.target.id === 'settingsBackdrop') closeSettings();
}

function saveSettings() {
  const closeBehavior = document.getElementById('setCloseBehavior').value;
  const next = {
    startup_enabled: document.getElementById('setStartup').checked,
    startup_to_tray: document.getElementById('setStartupTray').checked,
    floating_price_enabled: document.getElementById('setFloatingPrice').checked,
    floating_price_display_mode: document.getElementById('setFloatingDisplayMode').value,
    floating_price_preset: document.getElementById('setFloatingPreset').value,
    floating_price_opacity: document.getElementById('setFloatingOpacity').value.trim(),
    floating_price_snap_edge: document.getElementById('setFloatingSnapEdge').checked,
    floating_price_always_on_top: document.getElementById('setFloatingAlwaysOnTop').checked,
    close_behavior: closeBehavior,
    close_remembered: closeBehavior !== 'ask',
    alert_sound_enabled: document.getElementById('setAlertSound').checked,
    alert_dialog_enabled: document.getElementById('setAlertDialog').checked,
    // 邮件通知
    smtp_server: document.getElementById('setSmtpServer').value.trim(),
    smtp_port: document.getElementById('setSmtpPort').value.trim(),
    smtp_encryption: document.getElementById('setSmtpEncryption').value,
    smtp_sender: document.getElementById('setSmtpSender').value.trim(),
    smtp_password: document.getElementById('setSmtpPassword').value,
    smtp_password_clear: document.getElementById('clearSmtpPassword').checked,
    smtp_recipient: document.getElementById('setSmtpRecipient').value.trim(),
    email_warning_enabled: appSettings.email_warning_enabled !== false,
    email_critical_enabled: appSettings.email_critical_enabled !== false,
    email_volatility_enabled: appSettings.email_volatility_enabled !== false,
    alert_cooldown_minutes: document.getElementById('setAlertCooldownMinutes').value.trim(),
    alert_quiet_start: document.getElementById('setAlertQuietStart').value,
    alert_quiet_end: document.getElementById('setAlertQuietEnd').value,
    email_subject_template: document.getElementById('setEmailSubjectTemplate').value,
    email_body_template: document.getElementById('setEmailBodyTemplate').value,
    webhook_enabled: document.getElementById('setWebhookEnabled').checked,
    webhook_url: document.getElementById('setWebhookUrl').value.trim(),
    webhook_warning_enabled: document.getElementById('setWebhookWarning').checked,
    webhook_critical_enabled: document.getElementById('setWebhookCritical').checked,
    webhook_volatility_enabled: document.getElementById('setWebhookVolatility').checked,
    daily_digest_enabled: document.getElementById('setDailyDigestEnabled').checked,
    daily_digest_time: document.getElementById('setDailyDigestTime').value,
    daily_digest_email_enabled: document.getElementById('setDailyDigestEmail').checked,
    daily_digest_webhook_enabled: document.getElementById('setDailyDigestWebhook').checked,
    risk_assistant_enabled: document.getElementById('setRiskAssistantEnabled').checked,
    risk_assistant_provider: document.getElementById('setRiskAssistantProvider').value,
    risk_assistant_depth: document.getElementById('setRiskAssistantDepth').value,
    deepseek_base_url: document.getElementById('setDeepseekBaseUrl').value.trim(),
    deepseek_model: document.getElementById('setDeepseekModel').value,
    deepseek_api_key: document.getElementById('setDeepseekApiKey').value.trim(),
    deepseek_api_key_clear: document.getElementById('clearDeepseekApiKey').checked,
    openai_compatible_base_url: document.getElementById('setOpenaiCompatibleBaseUrl').value.trim(),
    openai_compatible_model: document.getElementById('setOpenaiCompatibleModel').value.trim(),
    openai_compatible_api_key: document.getElementById('setOpenaiCompatibleApiKey').value.trim(),
    openai_compatible_api_key_clear: document.getElementById('clearOpenaiCompatibleApiKey').checked,
    risk_assistant_max_tokens: document.getElementById('setRiskMaxTokens').value.trim(),
    risk_assistant_cooldown_seconds: document.getElementById('setRiskCooldownSeconds').value.trim(),
    risk_assistant_cache_minutes: document.getElementById('setRiskCacheMinutes').value.trim(),
    export_dir: document.getElementById('setExportDir').value.trim(),
  };
  pendingSettingsSave = true;
  settingsSaveFailed = false;
  document.getElementById('settingsMessage').textContent = '正在保存...';
  socket.emit('update_settings', next);
  if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
  settingsSaveTimer = setTimeout(() => {
    if (!pendingSettingsSave) return;
    pendingSettingsSave = false;
    settingsSaveFailed = true;
    document.getElementById('settingsMessage').textContent = '保存失败：后台服务未响应，请退出托盘中的旧程序后重新打开最新版。';
  }, 5000);
}

function testEmail() {
  const statusEl = document.getElementById('testEmailStatus');
  const btn = document.getElementById('btnTestEmail');
  statusEl.textContent = '正在发送...';
  statusEl.className = 'test-email-status';
  btn.disabled = true;
  socket.emit('test_email');
}

socket.on('test_email_result', data => {
  const statusEl = document.getElementById('testEmailStatus');
  const btn = document.getElementById('btnTestEmail');
  btn.disabled = false;
  if (data.ok) {
    statusEl.textContent = data.message;
    statusEl.className = 'test-email-status ok';
  } else {
    statusEl.textContent = data.message;
    statusEl.className = 'test-email-status fail';
  }
});

function testWebhook() {
  const statusEl = document.getElementById('testWebhookStatus');
  const btn = document.getElementById('btnTestWebhook');
  if (statusEl) {
    statusEl.textContent = '正在发送...';
    statusEl.className = 'test-email-status';
  }
  if (btn) btn.disabled = true;
  socket.emit('test_webhook');
}

socket.on('test_webhook_result', data => {
  const statusEl = document.getElementById('testWebhookStatus');
  const btn = document.getElementById('btnTestWebhook');
  if (btn) btn.disabled = false;
  if (!statusEl) return;
  statusEl.textContent = data && data.message ? data.message : 'Webhook 测试完成。';
  statusEl.className = 'test-email-status ' + (data && data.ok ? 'ok' : 'fail');
});

function previewDailyDigest() {
  const button = document.getElementById('btnPreviewDailyDigest');
  if (button) button.disabled = true;
  setDailyDigestStatus('正在生成摘要预览...', null);
  socket.emit('preview_daily_digest');
}

function testDailyDigest() {
  const button = document.getElementById('btnTestDailyDigest');
  if (button) button.disabled = true;
  setDailyDigestStatus('正在测试发送每日摘要...', null);
  socket.emit('test_daily_digest');
}

function testAlert() {
  const statusEl = document.getElementById('testAlertStatus');
  const btn = document.getElementById('btnTestAlert');
  if (statusEl) {
    statusEl.textContent = '正在触发...';
    statusEl.className = 'test-email-status';
  }
  if (btn) {
    btn.disabled = true;
    setTimeout(() => { btn.disabled = false; }, 1200);
  }
  socket.emit('test_alert', { type: 'warning' });
}

// ========== 风险分析助手 ==========
function selectedRiskPrice(data) {
  const source = data || latestData || {};
  return currentMode === 'usd' ? source.usd : source.rmb;
}

function hasRiskAnalysisInput(data) {
  const price = Number(selectedRiskPrice(data));
  return Number.isFinite(price) && price > 0;
}

function riskAnalysisUnavailableMessage() {
  if (!hasRiskAnalysisInput()) return '当前没有可用于风险分析的行情价格，请先重新获取行情数据。';
  const retry = document.getElementById('priceRetry');
  if (retry && retry.classList.contains('show')) return '当前行情状态异常，请先重新获取行情数据后再分析。';
  return '';
}

function updateRiskEntryState() {
  const riskAnalyzeButton = document.getElementById('riskAnalyzeButton');
  const available = !riskAnalysisUnavailableMessage();
  if (riskAnalyzeButton) {
    riskAnalyzeButton.hidden = !available;
    riskAnalyzeButton.disabled = !available || !appSettings.risk_assistant_enabled;
    riskAnalyzeButton.setAttribute('aria-hidden', available ? 'false' : 'true');
  }
  document.querySelectorAll('.source-risk-action').forEach(button => {
    button.hidden = !available;
    button.disabled = !available || !appSettings.risk_assistant_enabled;
    button.setAttribute('aria-hidden', available ? 'false' : 'true');
  });
}

function openRiskAnalysis() {
  const riskUnavailable = riskAnalysisUnavailableMessage();
  if (riskUnavailable) {
    applyFetchStatus({ ok:false, message:riskUnavailable, retryable:true });
    return false;
  }
  document.getElementById('riskBackdrop').classList.add('show');
  socket.emit('get_risk_analysis_history');
  const providerMessage = riskProviderErrorMessage();
  if (!appSettings.risk_assistant_enabled) {
    applyRiskStatus('风险分析助手已关闭，请先在设置中启用。', 'error');
  } else if (providerMessage) {
    applyRiskStatus(providerMessage, 'error');
  } else if (!document.getElementById('riskResult').textContent || document.getElementById('riskResult').textContent === '暂无分析结果。') {
    applyRiskStatus('点击开始分析，助手会基于当前行情生成风险趋势判断。', '');
  }
  updateRiskButtonState();
  return true;
}

function closeRiskAnalysis() {
  document.getElementById('riskBackdrop').classList.remove('show');
}

function onRiskBackdrop(event) {
  if (event.target.id === 'riskBackdrop') closeRiskAnalysis();
}

function applyRiskStatus(message, type) {
  const statusEl = document.getElementById('riskStatus');
  statusEl.textContent = message || '';
  statusEl.className = 'risk-status' + (type ? ' ' + type : '');
}

function renderRiskDiagnostic(diagnostic) {
  const el = document.getElementById('riskDiagnostic');
  if (!el) return;
  if (!diagnostic) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const provider = [diagnostic.provider, diagnostic.model].filter(Boolean).join(' / ');
  const recovery = Array.isArray(diagnostic.recovery) ? diagnostic.recovery.filter(Boolean) : [];
  const recoveryHtml = recovery.length
    ? '<ul class="risk-diagnostic-list">' + recovery.map(item => '<li>' + escapeHtml(item) + '</li>').join('') + '</ul>'
    : '<div>' + escapeHtml('稍后重试；如果问题持续，请导出诊断报告核对配置和网络状态。') + '</div>';
  el.innerHTML = [
    '<div class="risk-diagnostic-title">失败原因 · ' + escapeHtml(diagnostic.title || '风险分析失败') + '</div>',
    provider ? '<div class="risk-diagnostic-meta">模型 ' + escapeHtml(provider) + '</div>' : '',
    '<div class="risk-diagnostic-section"><strong>原因</strong><div>' + escapeHtml(diagnostic.reason || '未知错误') + '</div></div>',
    '<div class="risk-diagnostic-section"><strong>影响</strong><div>' + escapeHtml(diagnostic.impact || '风险分析未生成，本次不会写入分析历史。') + '</div></div>',
    '<div class="risk-diagnostic-section"><strong>建议处理</strong>' + recoveryHtml + '</div>',
  ].join('');
  el.classList.add('show');
}

function updateRiskButtonState() {
  const runBtn = document.getElementById('riskRunButton');
  const forceBtn = document.getElementById('riskForceRunButton');
  const riskUnavailable = riskAnalysisUnavailableMessage();
  const disabled = riskAnalysisRunning || !appSettings.risk_assistant_enabled || !!riskProviderErrorMessage() || !!riskUnavailable;
  if (runBtn) {
    runBtn.disabled = disabled;
    runBtn.textContent = riskAnalysisRunning ? '分析中...' : '开始分析';
  }
  if (forceBtn) forceBtn.disabled = disabled;
  updateRiskEntryState();
}

function requestRiskAnalysis(trigger, force) {
  if (riskAnalysisRunning) return;
  const riskUnavailable = riskAnalysisUnavailableMessage();
  if (riskUnavailable) {
    applyRiskStatus(riskUnavailable, 'error');
    updateRiskButtonState();
    return;
  }
  if (!appSettings.risk_assistant_enabled) {
    applyRiskStatus('风险分析助手已关闭，请先在设置中启用。', 'error');
    return;
  }
  const providerMessage = riskProviderErrorMessage();
  if (providerMessage) {
    applyRiskStatus(providerMessage, 'error');
    return;
  }
  riskAnalysisRunning = true;
  document.getElementById('riskResult').textContent = '正在分析当前行情...';
  renderRiskDiagnostic(null);
  renderRiskSnapshot(null);
  renderRiskStructured(null);
  pendingRiskForceTrigger = null;
  setRiskForceButtonVisible(false);
  applyRiskStatus('正在生成风险分析...', 'loading');
  updateRiskButtonState();
  socket.emit('request_risk_analysis', Object.assign({}, trigger ? { trigger } : {}, force ? { force: true } : {}));
}

function setRiskForceButtonVisible(visible) {
  const btn = document.getElementById('riskForceRunButton');
  if (btn) btn.style.display = visible ? '' : 'none';
}

function rerunRiskAnalysis() {
  requestRiskAnalysis(pendingRiskForceTrigger || null, true);
}

function riskProviderErrorMessage() {
  const provider = appSettings.risk_assistant_provider || 'deepseek';
  if (provider === 'deepseek') {
    if (!appSettings.deepseek_api_key_configured) return '请先在设置中配置 DeepSeek API Key。';
    if (!appSettings.deepseek_model) return '请先选择 DeepSeek 模型。';
    return '';
  }
  if (provider === 'openai_compatible') {
    if (!appSettings.openai_compatible_base_url) return '请先配置兼容接口地址。';
    if (!appSettings.openai_compatible_model) return '请先配置兼容模型。';
    if (!appSettings.openai_compatible_api_key_configured) return '请先配置兼容 API Key。';
    return '';
  }
  return '当前模型提供商暂不支持。';
}

function formatRiskNumber(value, suffix) {
  if (value === null || value === undefined || value === '') return '--';
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString('en-US', { maximumFractionDigits: 2 }) + (suffix || '');
}

function formatRiskUsage(usage) {
  if (!usage || usage.total_tokens == null) return '';
  return '本次用量 ' + usage.total_tokens + ' tokens。';
}

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

function renderRiskEvidence(snapshot) {
  const el = document.getElementById('riskEvidence');
  if (!el) return;
  if (!snapshot) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const evidence = snapshot.evidence_summary || {};
  const goldCached = evidence.gold_cached ? '缓存' : '实时';
  const rateCached = evidence.rate_cached ? '缓存' : '实时';
  const qualityLabel = evidence.quality_label || '--';
  const qualityScore = evidence.quality_score == null ? '--' : evidence.quality_score + '分';
  const items = [
    ['当前金价', 'RMB ' + formatRiskNumber(evidence.price_rmb ?? snapshot.price_rmb, '/克') + ' · USD ' + formatRiskNumber(evidence.price_usd ?? snapshot.price_usd, '/oz')],
    ['行情源', (evidence.gold_source || snapshot.gold_source || '--') + ' · ' + goldCached + (evidence.gold_time ? ' · ' + evidence.gold_time : '')],
    ['汇率源', (evidence.rate_source || snapshot.rate_source || '--') + ' · ' + rateCached + (evidence.rate_time ? ' · ' + evidence.rate_time : '')],
    ['样本规模', '历史 ' + (evidence.history_points ?? snapshot.history_points ?? 0) + ' 点 · 5分钟K线 ' + (evidence.kline_points ?? snapshot.kline_points ?? 0) + ' 根'],
    ['近期资讯', (evidence.news_count ?? snapshot.news_count ?? 0) + ' 条'],
    ['数据质量', qualityScore + ' · ' + qualityLabel],
  ];
  const missing = Array.isArray(evidence.missing) ? evidence.missing.filter(Boolean) : [];
  const recovery = Array.isArray(evidence.recovery) ? evidence.recovery.filter(Boolean) : [];
  const warning = missing.length || recovery.length
    ? '<div class="risk-evidence-warning"><strong>缺失数据</strong>：' + escapeHtml(missing.join('、') || '暂无') + '<br><strong>恢复建议</strong>：' + escapeHtml(recovery.join('；') || '继续等待数据更新') + '</div>'
    : '';
  const qualitySummary = evidence.quality_summary ? '<div class="risk-evidence-warning">' + escapeHtml(evidence.quality_summary) + '</div>' : '';
  el.innerHTML = [
    '<div class="risk-block-title">数据依据</div>',
    '<div class="risk-evidence-grid">',
    items.map(item => '<div class="risk-evidence-item"><div class="risk-evidence-label">' + escapeHtml(item[0]) + '</div><div class="risk-evidence-value">' + escapeHtml(item[1]) + '</div></div>').join(''),
    '</div>',
    warning + qualitySummary,
  ].join('');
  el.classList.add('show');
}

function renderRiskSnapshot(snapshot) {
  const meta = document.getElementById('riskMeta');
  if (!snapshot) {
    meta.innerHTML = '';
    meta.classList.remove('show');
    renderRiskEvidence(null);
    renderRiskQuality(null);
    renderRiskTrends(null);
    renderRiskScorecard(null);
    renderRiskStructured(null);
    return;
  }
  const items = [
    '时间 ' + (snapshot.analysis_time || '--'),
    'RMB ' + formatRiskNumber(snapshot.price_rmb, '/克'),
    'USD ' + formatRiskNumber(snapshot.price_usd, '/oz'),
    '汇率 ' + formatRiskNumber(snapshot.usdcny_rate, ''),
    '历史点 ' + (snapshot.history_points || 0),
    'K线 ' + (snapshot.kline_points || 0),
    '资讯 ' + (snapshot.news_count || 0),
  ];
  const marketQuality = snapshot.market_quality && Object.keys(snapshot.market_quality).length ? snapshot.market_quality : null;
  const quality = marketQuality || snapshot.data_quality || null;
  if (quality) items.push('行情质量 ' + quality.score + '分/' + (quality.label || quality.level || '--'));
  if (snapshot.sample_warning) items.push(snapshot.sample_warning);
  meta.innerHTML = items.map(item => '<span>' + escapeHtml(item) + '</span>').join('');
  meta.classList.add('show');
  renderRiskEvidence(snapshot);
  renderRiskQuality(quality);
  renderRiskTrends(snapshot.multi_period_trends || []);
  renderRiskScorecard(snapshot.risk_scorecard || null);
}

function renderRiskQuality(quality) {
  const el = document.getElementById('riskQuality');
  if (!quality) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const reasons = Array.isArray(quality.reasons) ? quality.reasons.filter(Boolean).join('；') : '';
  const summary = quality.summary || reasons || quality.label || '暂无说明';
  el.innerHTML = [
    '<div class="risk-block-title">行情质量</div>',
    '<div class="risk-quality-score">' + escapeHtml(quality.score == null ? '--' : quality.score) + '</div>',
    '<div class="risk-quality-level">等级 ' + escapeHtml(quality.level || '--') + '</div>',
    '<div class="risk-quality-summary">' + escapeHtml(summary) + '</div>',
  ].join('');
  el.classList.add('show');
}

function riskTrendClass(direction) {
  if (direction === '上行') return 'up';
  if (direction === '下行') return 'down';
  if (direction === '震荡') return 'flat';
  return 'missing';
}

function renderRiskTrends(trends) {
  const el = document.getElementById('riskTrends');
  if (!Array.isArray(trends) || !trends.length) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const items = trends.map(item => {
    const direction = item.direction_rmb || item.direction_usd || '样本不足';
    const pct = item.rmb && item.rmb.change_pct != null ? item.rmb.change_pct : item.usd && item.usd.change_pct;
    return [
      '<div class="risk-trend-item">',
      '<div class="risk-trend-period">' + escapeHtml(item.minutes || '--') + '分钟 · ' + escapeHtml(item.points || 0) + '点</div>',
      '<div class="risk-trend-direction ' + riskTrendClass(direction) + '">' + escapeHtml(direction) + '</div>',
      '<div class="risk-trend-change">变动 ' + escapeHtml(pct == null ? '--' : Number(pct).toFixed(2) + '%') + '</div>',
      '</div>',
    ].join('');
  }).join('');
  el.innerHTML = '<div class="risk-block-title">多周期趋势</div><div class="risk-trend-list">' + items + '</div>';
  el.classList.add('show');
}

function renderRiskScorecard(scorecard) {
  const el = document.getElementById('riskScorecard');
  if (!scorecard) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  const items = [
    ['总体风险', scorecard.overall_risk],
    ['趋势强度', scorecard.trend_strength],
    ['波动风险', scorecard.volatility_risk],
    ['汇率影响', scorecard.fx_impact],
    ['事件风险', scorecard.event_risk],
    ['数据可信度', scorecard.data_credibility],
  ];
  el.innerHTML = '<div class="risk-block-title">风险评分卡</div><div class="risk-score-grid">' + items.map(item => (
    '<div class="risk-score-item"><div class="risk-score-label">' + escapeHtml(item[0]) + '</div><div class="risk-score-value">' + escapeHtml(item[1] == null ? '--' : item[1]) + '</div></div>'
  )).join('') + '</div>';
  el.classList.add('show');
}

function renderRiskStructured(structured) {
  const el = document.getElementById('riskStructured');
  if (!el) return;
  const labels = [
    ['risk_level', '风险等级'],
    ['trend_direction', '趋势方向'],
    ['data_credibility', '数据可信度'],
    ['main_factors', '主要影响因素'],
    ['watch_range', '观察价格区间'],
    ['follow_up', '后续关注'],
  ];
  const items = labels
    .map(([key, label]) => [label, structured && structured[key]])
    .filter(([, value]) => value);
  if (!items.length) {
    el.innerHTML = '';
    el.classList.remove('show');
    return;
  }
  el.innerHTML = items.map(([label, value]) => (
    '<div class="risk-structured-item"><div class="risk-structured-label">' + escapeHtml(label) + '</div><div class="risk-structured-value">' + escapeHtml(value) + '</div></div>'
  )).join('');
  el.classList.add('show');
}

function applyRiskHistory(data) {
  riskAnalysisHistory = Array.isArray(data && data.items) ? data.items : [];
  riskComparisonSelection = [];
  const comparison = document.getElementById('riskComparison');
  if (comparison) {
    comparison.innerHTML = '';
    comparison.hidden = true;
  }
  renderRiskHistory();
}

function renderRiskHistory() {
  const list = document.getElementById('riskHistoryList');
  const clearBtn = document.getElementById('riskClearHistoryButton');
  const compareBtn = document.getElementById('riskCompareButton');
  if (clearBtn) clearBtn.disabled = riskAnalysisHistory.length === 0;
  if (compareBtn) {
    compareBtn.disabled = riskComparisonSelection.length !== 2;
    compareBtn.textContent = riskComparisonSelection.length
      ? '对比所选（' + riskComparisonSelection.length + '/2）'
      : '对比所选';
  }
  if (!riskAnalysisHistory.length) {
    list.innerHTML = '<div class="risk-history-empty">暂无历史记录</div>';
    return;
  }
  list.innerHTML = riskAnalysisHistory.map((item, index) => {
    const firstLine = String(item.content || '').split('\n').find(Boolean) || '历史分析';
    const qualitySource = item.snapshot ? (item.snapshot.market_quality || item.snapshot.data_quality) : null;
    const quality = qualitySource ? ' · 行情质量 ' + qualitySource.score + '分' : '';
    const evidence = item.evidence_summary || (item.snapshot && item.snapshot.evidence_summary) || {};
    const samples = evidence.history_points != null || evidence.kline_points != null
      ? ' · 历史' + (evidence.history_points ?? 0) + '/K线' + (evidence.kline_points ?? 0)
      : '';
    const selectedForComparison = riskComparisonSelection.includes(index);
    return [
      '<div class="risk-history-item' + (selectedForComparison ? ' selected' : '') + '">',
      '<button class="risk-history-main" type="button" onclick="openRiskHistoryItem(' + index + ')">',
      '<div class="risk-history-time">' + escapeHtml(item.analysis_time || '--') + escapeHtml(quality) + escapeHtml(samples) + '</div>',
      '<div class="risk-history-text">' + escapeHtml(firstLine) + '</div>',
      '</button>',
      '<button class="btn-clear-sm btn-muted-sm risk-history-compare" type="button" aria-pressed="' + String(selectedForComparison) + '" onclick="toggleRiskComparisonItem(' + index + ')">' + (selectedForComparison ? '已选' : '选择对比') + '</button>',
      '<button class="btn-clear-sm btn-muted-sm risk-history-review" type="button" data-risk-timeline-index="' + index + '" onclick="window.openRiskTimelineFromHistory(' + index + ')">查看复盘</button>',
      '</div>',
    ].join('');
  }).join('');
}

function clearRenderedRiskComparison() {
  const comparison = document.getElementById('riskComparison');
  if (!comparison) return;
  comparison.innerHTML = '';
  comparison.hidden = true;
}

function toggleRiskComparisonItem(index) {
  if (!Number.isInteger(index) || !riskAnalysisHistory[index]) return;
  const selectedIndex = riskComparisonSelection.indexOf(index);
  if (selectedIndex >= 0) {
    riskComparisonSelection.splice(selectedIndex, 1);
    clearRenderedRiskComparison();
    applyRiskStatus('已取消该条对比选择。', '');
    renderRiskHistory();
    return;
  }
  if (riskComparisonSelection.length >= 2) {
    applyRiskStatus('最多选择两条风险分析，请先取消一条已选记录。', 'error');
    return;
  }
  riskComparisonSelection.push(index);
  clearRenderedRiskComparison();
  applyRiskStatus(
    riskComparisonSelection.length === 2 ? '已选择两条风险分析，可以开始对比。' : '已选择一条风险分析，请再选择一条。',
    ''
  );
  renderRiskHistory();
}

function riskComparisonValue(value) {
  if (value === null || value === undefined || value === '') return '暂无';
  if (typeof value === 'number' && !Number.isFinite(value)) return '暂无';
  return String(value);
}

function riskComparisonNumber(value, suffix) {
  if (value === null || value === undefined || value === '') return '暂无';
  const number = Number(value);
  if (!Number.isFinite(number)) return '暂无';
  return number.toLocaleString('en-US', { maximumFractionDigits: 4 }) + (suffix || '');
}

function riskComparisonSource(snapshot, sourceKey, cachedKey) {
  const source = snapshot && snapshot[sourceKey];
  if (!source) return '暂无';
  const cached = snapshot[cachedKey];
  const state = cached === true ? '缓存' : cached === false ? '实时' : '状态暂无';
  return String(source) + ' · ' + state;
}

function riskComparisonQuality(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return '暂无';
  const marketQuality = snapshot.market_quality && Object.keys(snapshot.market_quality).length
    ? snapshot.market_quality
    : null;
  const quality = marketQuality || (snapshot.data_quality && Object.keys(snapshot.data_quality).length ? snapshot.data_quality : null);
  if (!quality) return '暂无';
  const score = riskComparisonValue(quality.score);
  const label = riskComparisonValue(quality.label || quality.level);
  if (score === '暂无' && label === '暂无') return '暂无';
  if (score === '暂无') return label;
  if (label === '暂无') return score + '分';
  return score + '分 · ' + label;
}

function riskComparisonSamples(snapshot) {
  if (!snapshot || typeof snapshot !== 'object') return '暂无';
  const values = [
    ['历史', snapshot.history_points, '点'],
    ['K线', snapshot.kline_points, '根'],
    ['资讯', snapshot.news_count, '条'],
  ].filter(item => item[1] !== null && item[1] !== undefined && item[1] !== '');
  if (!values.length) return '暂无';
  return values.map(item => item[0] + ' ' + riskComparisonNumber(item[1], item[2])).join(' · ');
}

function riskComparisonEntryTime(item) {
  if (!item || typeof item !== 'object') return '';
  return item.analysis_time || (item.snapshot && item.snapshot.analysis_time) || '';
}

function riskComparisonParsedTime(item) {
  const value = riskComparisonEntryTime(item);
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function riskComparisonRow(field, label, earlierValue, laterValue, sideLabels) {
  const earlierText = riskComparisonValue(earlierValue);
  const laterText = riskComparisonValue(laterValue);
  const changedClass = earlierText === laterText ? '' : ' changed';
  const labels = sideLabels || { earlier: '较早', later: '较新' };
  return [
    '<div class="risk-comparison-row' + changedClass + '" data-field="' + escapeHtml(field) + '">',
    '<div class="risk-comparison-label">' + escapeHtml(label) + '</div>',
    '<div class="risk-comparison-value" data-side="earlier" data-side-label="' + escapeHtml(labels.earlier) + '">' + escapeHtml(earlierText) + '</div>',
    '<div class="risk-comparison-value" data-side="later" data-side-label="' + escapeHtml(labels.later) + '">' + escapeHtml(laterText) + '</div>',
    '</div>',
  ].join('');
}

function renderRiskComparison(earlier, later, sideLabels) {
  const comparison = document.getElementById('riskComparison');
  if (!comparison) return;
  const labels = sideLabels || { earlier: '较早', later: '较新' };
  const earlierSnapshot = earlier && earlier.snapshot && typeof earlier.snapshot === 'object' ? earlier.snapshot : {};
  const laterSnapshot = later && later.snapshot && typeof later.snapshot === 'object' ? later.snapshot : {};
  const earlierStructured = earlier && earlier.structured && typeof earlier.structured === 'object' ? earlier.structured : {};
  const laterStructured = later && later.structured && typeof later.structured === 'object' ? later.structured : {};
  const earlierScorecard = earlierSnapshot.risk_scorecard && typeof earlierSnapshot.risk_scorecard === 'object' ? earlierSnapshot.risk_scorecard : {};
  const laterScorecard = laterSnapshot.risk_scorecard && typeof laterSnapshot.risk_scorecard === 'object' ? laterSnapshot.risk_scorecard : {};
  const structuredFields = [
    ['risk_level', '风险等级'],
    ['trend_direction', '趋势方向'],
    ['data_credibility', '数据可信度'],
    ['main_factors', '主要影响因素'],
    ['watch_range', '观察价格区间'],
    ['follow_up', '后续关注'],
  ];
  const scorecardFields = [
    ['overall_risk', '总体风险'],
    ['trend_strength', '趋势强度'],
    ['volatility_risk', '波动风险'],
    ['fx_impact', '汇率影响'],
    ['event_risk', '事件风险'],
    ['data_credibility', '数据可信度'],
  ];
  const snapshotFields = [
    ['price_rmb', '人民币克价', item => riskComparisonNumber(item.price_rmb, ' 元/克')],
    ['price_usd', '国际金价', item => riskComparisonNumber(item.price_usd, ' 美元/盎司')],
    ['usdcny_rate', '美元人民币汇率', item => riskComparisonNumber(item.usdcny_rate, '')],
    ['gold_source', '金价来源', item => riskComparisonSource(item, 'gold_source', 'gold_cached')],
    ['rate_source', '汇率来源', item => riskComparisonSource(item, 'rate_source', 'rate_cached')],
    ['quality', '行情质量', item => riskComparisonQuality(item)],
    ['samples', '样本规模', item => riskComparisonSamples(item)],
  ];
  const section = (title, rows) => [
    '<section class="risk-comparison-section">',
    '<div class="risk-comparison-title">' + escapeHtml(title) + '</div>',
    '<div class="risk-comparison-grid">' + rows.join('') + '</div>',
    '</section>',
  ].join('');
  const earlierProvider = [earlier.provider, earlier.model].filter(Boolean).join(' / ') || '暂无';
  const laterProvider = [later.provider, later.model].filter(Boolean).join(' / ') || '暂无';
  comparison.innerHTML = [
    '<div class="risk-comparison-head">',
    '<div class="risk-block-title">风险分析对比</div>',
    '<div class="risk-comparison-sides">',
    '<div class="risk-comparison-side" data-side="earlier"><strong>' + escapeHtml(labels.earlier) + '</strong><span>' + escapeHtml(riskComparisonValue(riskComparisonEntryTime(earlier))) + '</span><span>' + escapeHtml(earlierProvider) + '</span></div>',
    '<div class="risk-comparison-side" data-side="later"><strong>' + escapeHtml(labels.later) + '</strong><span>' + escapeHtml(riskComparisonValue(riskComparisonEntryTime(later))) + '</span><span>' + escapeHtml(laterProvider) + '</span></div>',
    '</div>',
    '</div>',
    section('结构化字段', structuredFields.map(item => riskComparisonRow(item[0], item[1], earlierStructured[item[0]], laterStructured[item[0]], labels))),
    section('风险评分卡', scorecardFields.map(item => riskComparisonRow(item[0], item[1], earlierScorecard[item[0]], laterScorecard[item[0]], labels))),
    section('行情快照', snapshotFields.map(item => riskComparisonRow(item[0], item[1], item[2](earlierSnapshot), item[2](laterSnapshot), labels))),
  ].join('');
  comparison.hidden = false;
}

function compareSelectedRiskHistory() {
  if (riskComparisonSelection.length !== 2) {
    applyRiskStatus('请选择两条风险分析后再对比。', 'error');
    return;
  }
  const selected = riskComparisonSelection.map(index => riskAnalysisHistory[index]);
  if (selected.some(item => !item)) {
    riskComparisonSelection = [];
    clearRenderedRiskComparison();
    renderRiskHistory();
    applyRiskStatus('所选历史记录已更新，请重新选择两条风险分析。', 'error');
    return;
  }
  let earlier = selected[0];
  let later = selected[1];
  const earlierTime = riskComparisonParsedTime(earlier);
  const laterTime = riskComparisonParsedTime(later);
  const timesAreComparable = earlierTime !== null && laterTime !== null;
  const sideLabels = timesAreComparable
    ? { earlier: '较早', later: '较新' }
    : { earlier: '记录一', later: '记录二' };
  if (timesAreComparable && earlierTime > laterTime) {
    earlier = selected[1];
    later = selected[0];
  }
  renderRiskComparison(earlier, later, sideLabels);
  applyRiskStatus('已生成本地风险分析对比，不会调用模型。', '');
}

function openRiskHistoryItem(index) {
  const item = riskAnalysisHistory[index];
  if (!item) return;
  renderRiskSnapshot(item.snapshot || null);
  renderRiskStructured(item.structured || null);
  document.getElementById('riskResult').textContent = item.content || '历史记录无内容。';
  const usageText = formatRiskUsage(item.usage || null);
  applyRiskStatus(usageText ? '已打开历史分析。' + usageText : '已打开历史分析。', '');
}

function openRiskTimelineFromHistory(index) {
  const item = riskAnalysisHistory[index];
  if (!item) return;
  openEventTimelineAround(item.analysis_time || (item.snapshot && item.snapshot.analysis_time), 'risk_analysis', item.id);
}

function handleRiskHistoryTimelineClick(event) {
  const button = event.target && event.target.closest ? event.target.closest('[data-risk-timeline-index]') : null;
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openRiskTimelineFromHistory(Number(button.getAttribute('data-risk-timeline-index')));
}

document.addEventListener('click', handleRiskHistoryTimelineClick, true);

function clearRiskHistory() {
  if (riskAnalysisRunning) return;
  socket.emit('clear_risk_analysis_history');
}

function currentRiskReportMarkdown() {
  const result = document.getElementById('riskResult').textContent || '';
  const meta = Array.from(document.querySelectorAll('#riskMeta span')).map(item => item.textContent).join('\n');
  const evidence = document.getElementById('riskEvidence') ? document.getElementById('riskEvidence').innerText.trim() : '';
  const parts = ['# 风险分析报告'];
  if (meta) parts.push('', '## 数据快照', meta);
  if (evidence) parts.push('', '## 数据依据', evidence);
  parts.push('', '## 分析内容', result || '暂无分析结果。');
  return parts.join('\n');
}

function copyRiskReport() {
  const content = currentRiskReportMarkdown();
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(content).then(() => applyRiskStatus('报告已复制。', '')).catch(() => applyRiskStatus('复制失败，请手动选择内容。', 'error'));
    return;
  }
  applyRiskStatus('当前环境不支持自动复制，请手动选择内容。', 'error');
}

function exportRiskReport() {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  downloadText('GoldMonitor-risk-report-' + stamp + '.md', currentRiskReportMarkdown(), 'text/markdown;charset=utf-8');
  applyRiskStatus('报告已导出。', '');
}

// ========== 更新 ==========
function openUpdate() {
  document.getElementById('updateBackdrop').classList.add('show');
  if (!pendingUpdateInfo) {
    checkUpdate();
  }
}

function closeUpdate() {
  document.getElementById('updateBackdrop').classList.remove('show');
}

function onUpdateBackdrop(event) {
  if (event.target.id === 'updateBackdrop') closeUpdate();
}

function renderOpsUpdateStatus(data) {
  opsUpdateStatus = data || opsUpdateStatus || null;
  const statusEl = document.getElementById('opsUpdateStatus');
  const metaEl = document.getElementById('opsUpdateMeta');
  if (!statusEl || !metaEl) return;
  const state = opsUpdateStatus && opsUpdateStatus.state ? opsUpdateStatus.state : '';
  const message = opsUpdateStatus && opsUpdateStatus.message ? opsUpdateStatus.message : '尚未检查更新。';
  const current = opsUpdateStatus && opsUpdateStatus.current_version ? '当前版本 ' + opsUpdateStatus.current_version : '';
  const latest = opsUpdateStatus && opsUpdateStatus.latest_version ? '最新版本 ' + opsUpdateStatus.latest_version : '';
  const checked = opsUpdateStatus && opsUpdateStatus.checked_at ? '检查时间 ' + String(opsUpdateStatus.checked_at).replace('T', ' ') : '';
  statusEl.textContent = message;
  statusEl.dataset.state = state || 'unknown';
  const meta = [current, latest, checked].filter(Boolean).join(' · ');
  if (meta) metaEl.textContent = meta;
}

function checkUpdateFromOps() {
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  requestUpdateCheck(true);
  setOpsStatus('正在检查更新...', true);
}

function openUpdateFromOps() {
  openUpdate();
}

function checkUpdate() {
  requestUpdateCheck(false);
}

function requestUpdateCheck(silent) {
  pendingUpdateInfo = null;
  document.getElementById('updateButton').classList.remove('update-ready');
  document.getElementById('installUpdateButton').disabled = true;
  renderOpsUpdateStatus({ state: 'checking', message: '正在检查更新...' });
  if (!silent) {
    document.getElementById('updateStatus').textContent = '正在检查更新...';
    document.getElementById('updateMeta').textContent = '';
    document.getElementById('updateNotes').style.display = 'none';
  }
  lastAutoUpdateCheckAt = Date.now();
  socket.emit('check_update');
}

function scheduleAutoUpdateCheck() {
  if (autoUpdateTimer) {
    clearTimeout(autoUpdateTimer);
    autoUpdateTimer = null;
  }
  const elapsed = Date.now() - lastAutoUpdateCheckAt;
  const delay = lastAutoUpdateCheckAt ? Math.max(autoUpdateIntervalMs() - elapsed, 60 * 1000) : 2000;
  autoUpdateTimer = setTimeout(() => {
    requestUpdateCheck(true);
    scheduleAutoUpdateCheck();
  }, delay);
}

function applyUpdateStatus(data) {
  renderOpsUpdateStatus(data);
  const statusEl = document.getElementById('updateStatus');
  const metaEl = document.getElementById('updateMeta');
  const notesEl = document.getElementById('updateNotes');
  const installBtn = document.getElementById('installUpdateButton');
  const updateBtn = document.getElementById('updateButton');
  const progressEl = document.getElementById('updateProgress');
  const progressBar = progressEl ? progressEl.querySelector('span') : null;

  const current = data.current_version ? '当前版本 ' + data.current_version : '';
  const latest = data.latest_version ? '最新版本 ' + data.latest_version : '';
  const checked = data.checked_at ? '检查时间 ' + String(data.checked_at).replace('T', ' ') : '';
  metaEl.textContent = [current, latest, checked].filter(Boolean).join(' · ');
  statusEl.textContent = data.message || '更新状态未知。';
  notesEl.textContent = data.notes || '';
  notesEl.style.display = data.notes ? 'block' : 'none';
  if (progressEl && progressBar) {
    const percent = data.progress_percent == null ? null : Math.max(0, Math.min(100, Number(data.progress_percent)));
    progressEl.classList.toggle('show', data.state === 'downloading' || data.state === 'installing');
    progressBar.style.width = Number.isFinite(percent) ? percent + '%' : '35%';
  }

  if (data.state === 'available') {
    pendingUpdateInfo = {
      version: data.latest_version,
      notes: data.notes || '',
    };
    installBtn.disabled = false;
    updateBtn.classList.add('update-ready');
    return;
  }

  if (data.state === 'downloading' || data.state === 'installing') {
    installBtn.disabled = true;
    updateBtn.classList.add('update-ready');
    return;
  }

  pendingUpdateInfo = null;
  installBtn.disabled = true;
  updateBtn.classList.remove('update-ready');
}

function installUpdate() {
  if (!pendingUpdateInfo) return;
  document.getElementById('installUpdateButton').disabled = true;
  document.getElementById('updateStatus').textContent = '正在准备更新...';
  socket.emit('install_update');
}

// ========== 行情状态 ==========
function applyFetchStatus(data) {
  const stale = document.getElementById('priceStale');
  const retry = document.getElementById('priceRetry');
  const ok = data.ok === true;
  const status = data.status || (ok ? 'ok' : 'error');
  const degraded = data.degraded === true || status === 'degraded';
  const message = data.message || (ok && !degraded ? '行情数据正常' : degraded ? '行情数据降级' : '行情数据获取失败');
  retry.textContent = data.reconnect ? '重新连接' : '重新获取';
  stale.textContent = message;
  retry.disabled = data.retryable === false;

  if (ok && !degraded) {
    stale.classList.remove('show');
    retry.classList.remove('show');
    updateRiskButtonState();
    return;
  }

  stale.classList.add('show');
  if (data.retryable !== false) retry.classList.add('show');
  else retry.classList.remove('show');
  updateRiskButtonState();
}

function refreshPrice() {
  const retry = document.getElementById('priceRetry');
  retry.disabled = true;
  if (!socket.connected) {
    applyFetchStatus({ ok:false, message:'正在重新连接本地服务...', retryable:false, reconnect:true });
    socket.connect();
    setTimeout(() => {
      if (!socket.connected) applyFetchStatus({ ok:false, message:'本地服务仍未连接，请确认程序没有被安全软件拦截。', retryable:true, reconnect:true });
    }, 2500);
    return;
  }
  applyFetchStatus({ ok:false, message:'正在重新获取行情数据...', retryable:false });
  socket.emit('refresh_price');
}

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

// ========== 应用内告警 ==========
function alertLevelLabel(type) {
  if (type === 'critical') return '关键预警';
  if (type === 'warning') return '价格预警';
  if (type === 'volatility') return '波动预警';
  return '金价预警';
}

function alertModeLabel(mode) {
  if (mode === 'usd') return '国际金价';
  if (mode === 'rmb') return '国内金价';
  return '金价监控';
}

function renderAlertModal(entry) {
  const modal = document.getElementById('alertModal');
  modal.className = 'settings-modal alert-modal alert-level-' + (entry.type || 'warning');
  document.getElementById('alertBadge').textContent = alertLevelLabel(entry.type);
  const muted = entry.notification_muted && entry.notification_message ? '\n' + entry.notification_message : '';
  document.getElementById('alertMessage').textContent = (entry.message || '达到预警条件') + muted;
  document.getElementById('alertTime').textContent = '时间 ' + (entry.time || '--');
  document.getElementById('alertMode').textContent = alertModeLabel(entry.mode);
  const stackNote = document.getElementById('alertStackNote');
  if (mergedAlertCount > 0) {
    stackNote.textContent = '当前弹窗已合并 ' + mergedAlertCount + ' 条后续预警，警报记录中保留完整明细。';
    stackNote.classList.add('show');
  } else {
    stackNote.textContent = '';
    stackNote.classList.remove('show');
  }
  renderRelatedNews(entry.related_news || []);
  document.getElementById('alertBackdrop').classList.add('show');
}

function renderRelatedNews(items) {
  const box = document.getElementById('relatedNews');
  const list = document.getElementById('relatedNewsList');
  list.innerHTML = '';
  if (!items.length) {
    box.classList.remove('show');
    return;
  }
  items.slice(0, 3).forEach(item => {
    const link = document.createElement('a');
    link.href = item.url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = (item.topic ? '[' + item.topic + '] ' : '') + (item.title || '--');
    list.appendChild(link);
  });
  box.classList.add('show');
}

function showAlertModal(entry) {
  const normalized = entry || {};
  if (activeAlert) {
    mergedAlertCount += 1;
    activeAlert = normalized;
    renderAlertModal(activeAlert);
    return;
  }
  mergedAlertCount = 0;
  activeAlert = normalized;
  renderAlertModal(activeAlert);
}

function closeAlertModal() {
  if (activeAlert && activeAlert.id) updateAlertStatus(activeAlert.id, { read: true });
  document.getElementById('alertBackdrop').classList.remove('show');
  activeAlert = null;
  mergedAlertCount = 0;
}

function analyzeActiveAlert() {
  if (!activeAlert) return;
  const alertContext = {
    source: 'alert',
    time: activeAlert.time || '',
    type: activeAlert.type || '',
    mode: activeAlert.mode || '',
    message: activeAlert.message || '',
  };
  if (!openRiskAnalysis()) return;
  document.getElementById('alertBackdrop').classList.remove('show');
  activeAlert = null;
  mergedAlertCount = 0;
  document.getElementById('riskResult').textContent = '正在分析本次预警...';
  requestRiskAnalysis(alertContext);
}

function onAlertBackdrop(event) {
  if (event.target.id === 'alertBackdrop') closeAlertModal();
}

// ========== UI更新 ==========

function updatePriceDisplay(data) {
  const isUsd = currentMode === 'usd';
  const price = isUsd ? data.usd : data.rmb;
  const prev = isUsd ? data.previous_usd : data.previous_rmb;
  const change = isUsd ? data.change_usd : data.change_rmb;
  const pct = isUsd ? data.change_pct_usd : data.change_pct_rmb;
  const unit = isUsd ? '$' : '¥';

  const priceEl = document.getElementById('priceValue');
  if (price == null) { priceEl.textContent = '--'; document.title = BASE_TITLE; updateRiskButtonState(); return; }

  const newText = unit + price.toLocaleString('en-US', { minimumFractionDigits:2, maximumFractionDigits:2 });
  document.title = BASE_TITLE + ' ' + newText + (isUsd ? '/oz' : '/克');
  if (priceEl.textContent !== newText && priceEl.textContent !== '--') {
    priceEl.style.transform = 'translateY(-4px)'; priceEl.style.opacity = '0.6';
    setTimeout(() => { priceEl.textContent = newText; priceEl.style.transform = 'translateY(0)'; priceEl.style.opacity = '1'; }, 150);
  } else { priceEl.textContent = newText; }

  const changeEl = document.getElementById('priceChange');
  if (prev == null || change == null) {
    changeEl.innerHTML = '首次获取'; changeEl.className = 'price-change neutral';
  } else {
    const sign = change >= 0 ? '▲' : '▼';
    const dirCls = change > 0 ? 'up' : change < 0 ? 'down' : 'neutral';
    changeEl.innerHTML = sign + ' ' + unit + Math.abs(change).toFixed(2) + ' (' + Math.abs(pct).toFixed(2) + '%)';
    changeEl.className = 'price-change ' + dirCls;
  }
  document.getElementById('priceTime').textContent = data.time || '--';
  const rateEl = document.getElementById('priceRate');
  const goldSource = data.gold_source ? '行情源 ' + data.gold_source : '';
  if (data.rate) {
    const rateKind = data.rate_cached ? '缓存汇率' : '实时汇率';
    const rateSource = data.rate_source ? ' · ' + data.rate_source : '';
    rateEl.textContent = (goldSource ? goldSource + ' · ' : '') + '1盎司 = 31.1035g · ' + rateKind + ' ' + data.rate.toFixed(4) + rateSource;
  }
  else rateEl.textContent = goldSource;
  updateRiskButtonState();
}

function updateDailyStats(data) {
  const isUsd = currentMode === 'usd';
  const d = data.daily || {};
  const unit = isUsd ? '$' : '¥';

  const openVal = isUsd ? d.open_usd : d.open_rmb;
  const highVal = isUsd ? d.high_usd : d.high_rmb;
  const lowVal  = isUsd ? d.low_usd : d.low_rmb;
  const dayChg  = isUsd ? d.change_usd : d.change_rmb;
  const dayPct  = isUsd ? d.pct_usd : d.pct_rmb;

  document.getElementById('statOpen').textContent = openVal != null ? unit + Number(openVal).toLocaleString('en-US',{minimumFractionDigits:2}) : '--';
  document.getElementById('statHigh').textContent = highVal != null ? unit + Number(highVal).toLocaleString('en-US',{minimumFractionDigits:2}) : '--';
  document.getElementById('statLow').textContent  = lowVal  != null ? unit + Number(lowVal).toLocaleString('en-US',{minimumFractionDigits:2}) : '--';

  const chgEl = document.getElementById('statDayChg');
  if (dayChg != null) {
    const sign = dayChg >= 0 ? '+' : '';
    chgEl.textContent = sign + dayChg.toFixed(2) + (dayPct != null ? ' (' + (dayPct>=0?'+':'') + dayPct.toFixed(2) + '%)' : '');
    chgEl.style.color = dayChg > 0 ? 'var(--up)' : dayChg < 0 ? 'var(--down)' : 'var(--text)';
  } else { chgEl.textContent = '--'; chgEl.style.color = 'var(--text)'; }
}

function initChart() {
  if (chart) chart.destroy();
  const ctx = document.getElementById('priceChart').getContext('2d');
  const isUsd = currentMode === 'usd';
  const hist = isUsd ? historyUsd : historyRmb;

  chart = new Chart(ctx, {
    type: 'line',
    plugins: [chartEventPlugin],
    data: {
      labels: [...hist.labels],
      datasets: [{
        data: [...hist.prices],
        borderColor: '#e8b830', backgroundColor: 'rgba(232,184,48,0.06)',
        borderWidth: 2, fill: true, pointRadius: 0, pointHoverRadius: 4,
        pointHoverBackgroundColor: '#e8b830', tension: 0.25,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      animation: { duration: 400, easing: 'easeOutQuart' },
      interaction: { intersect: false, mode: 'index' },
      plugins: {
        legend: { display: false },
        goldMonitorEvents: { events: activeChartEvents(hist.labels) },
        tooltip: {
          backgroundColor: '#16162a', titleColor: '#aaa', bodyColor: '#e8b830',
          borderColor: 'rgba(255,255,255,0.08)', borderWidth: 1, cornerRadius: 8, padding: 10,
          callbacks: {
            label: ctx => {
              const sym = currentMode === 'usd'?'$':'¥';
              const raw = ctx.raw;
              if (typeof raw === 'object' && raw !== null && 'o' in raw) {
                return [
                  ' 开: ' + sym + Number(raw.o).toFixed(2),
                  ' 高: ' + sym + Number(raw.h).toFixed(2),
                  ' 低: ' + sym + Number(raw.l).toFixed(2),
                  ' 收: ' + sym + Number(raw.c).toFixed(2),
                ];
              }
              return '  ' + sym + Number(raw).toLocaleString('en-US',{minimumFractionDigits:2});
            },
          },
        },
      },
      scales: {
        x: { ticks:{ color:'rgba(255,255,255,0.25)', maxTicksLimit:8, font:{size:9} }, grid:{ color:'rgba(255,255,255,0.03)' } },
        y: { ticks:{ color:'rgba(255,255,255,0.3)', font:{size:9}, callback:v=>(isUsd?'$':'¥')+v.toLocaleString('en-US') }, grid:{ color:'rgba(255,255,255,0.04)' } },
      },
    },
  });
}

// ========== 阈值 ==========
function normalizeAlertProfiles(data) {
  const items = Array.isArray(data && data.items) ? data.items : [];
  return {
    items,
    total: Number.isFinite(Number(data && data.total)) ? Number(data.total) : items.length,
    current_profile_id: data && data.current_profile_id ? String(data.current_profile_id) : '',
  };
}

function applyAlertProfiles(data) {
  alertProfiles = normalizeAlertProfiles(data);
  renderAlertProfiles();
}

function alertProfileSettingsChanged(data) {
  if (!data || !alertProfiles.current_profile_id) return false;
  return ALERT_PROFILE_SETTING_KEYS.some(key => Object.prototype.hasOwnProperty.call(data, key) && appSettings[key] !== data[key]);
}

function clearCurrentAlertProfileMatch() {
  if (pendingAlertProfileApply) return;
  if (!alertProfiles.current_profile_id) return;
  alertProfiles = Object.assign({}, alertProfiles, { current_profile_id: '' });
  renderAlertProfiles();
}

function setAlertProfileStatus(message, type) {
  const el = document.getElementById('alertProfilesStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'alert-profiles-status' + (type ? ' ' + type : '');
}

function alertProfileSummary(item) {
  const thresholds = item && item.thresholds ? item.thresholds : {};
  const thresholdCount = Object.keys(thresholds).filter(key => thresholds[key] != null).length;
  const vol = item && item.volatility_config;
  const volText = vol && vol.enabled && vol.percent != null ? '波动 ' + vol.percent + '%' : '波动关闭';
  return thresholdCount + ' 个价格阈值 · ' + volText;
}

function renderAlertProfiles() {
  const list = document.getElementById('alertProfilesList');
  const meta = document.getElementById('alertProfilesMeta');
  if (!list || !meta) return;
  const items = alertProfiles.items || [];
  meta.textContent = items.length ? items.length + ' 个模板' : '暂无模板';
  if (!items.length) {
    list.innerHTML = '<div class="alert-profiles-empty">保存当前预警配置后，可按场景一键切换。</div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const idArg = escapeHtml(JSON.stringify(String(item.id || '')));
    const active = alertProfiles.current_profile_id && alertProfiles.current_profile_id === item.id;
    const description = item.description ? '<div class="alert-profile-desc">' + escapeHtml(item.description) + '</div>' : '';
    const applied = item.last_applied_at ? ' · 上次应用 ' + String(item.last_applied_at).replace('T', ' ').slice(0, 16) : '';
    return [
      '<div class="alert-profile-item' + (active ? ' active' : '') + '">',
      '<div class="alert-profile-main">',
      '<div class="alert-profile-name">' + escapeHtml(item.name || '未命名模板') + (active ? '<span>当前</span>' : '') + '</div>',
      description,
      '<div class="alert-profile-meta">' + escapeHtml(alertProfileSummary(item) + applied) + '</div>',
      '</div>',
      '<div class="alert-profile-actions">',
      '<button class="btn-clear-sm" type="button" onclick="applyAlertProfile(' + idArg + ')">应用</button>',
      '<button class="btn-clear-sm" type="button" onclick="renameAlertProfile(' + idArg + ')">重命名</button>',
      '<button class="btn-clear-sm" type="button" onclick="deleteAlertProfile(' + idArg + ')">删除</button>',
      '</div>',
      '</div>',
    ].join('');
  }).join('');
}

function saveCurrentAlertProfile() {
  const name = window.prompt('模板名称', alertProfiles.items.length ? '策略模板 ' + (alertProfiles.items.length + 1) : '买入观察');
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    setAlertProfileStatus('模板名称不能为空。', 'fail');
    return;
  }
  const description = window.prompt('模板说明（可选）', '') || '';
  setAlertProfileStatus('正在保存预警策略模板...', '');
  socket.emit('save_alert_profile', { name: trimmed, description: description.trim() });
}

function applyAlertProfile(id) {
  if (!id) return;
  pendingAlertProfileApply = true;
  setAlertProfileStatus('正在应用预警策略模板...', '');
  socket.emit('apply_alert_profile', { id });
}

function renameAlertProfile(id) {
  const item = (alertProfiles.items || []).find(profile => profile.id === id);
  if (!item) {
    setAlertProfileStatus('未找到预警策略模板。', 'fail');
    return;
  }
  const name = window.prompt('模板名称', item.name || '');
  if (name == null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    setAlertProfileStatus('模板名称不能为空。', 'fail');
    return;
  }
  const description = window.prompt('模板说明（可选）', item.description || '') || '';
  setAlertProfileStatus('正在更新预警策略模板...', '');
  socket.emit('rename_alert_profile', { id, name: trimmed, description: description.trim() });
}

function deleteAlertProfile(id) {
  const item = (alertProfiles.items || []).find(profile => profile.id === id);
  if (!item) {
    setAlertProfileStatus('未找到预警策略模板。', 'fail');
    return;
  }
  if (!window.confirm('删除预警策略模板“' + (item.name || '未命名模板') + '”？')) return;
  setAlertProfileStatus('正在删除预警策略模板...', '');
  socket.emit('delete_alert_profile', { id });
}

// ========== 统一预警中心 ==========
function normalizeAlertRulesState(data) {
  const items = Array.isArray(data && data.items) ? data.items : [];
  return {
    schema_version: Number(data && data.schema_version) || 1,
    items,
    total: Number.isFinite(Number(data && data.total)) ? Number(data.total) : items.length,
    summary: data && data.summary && typeof data.summary === 'object' ? data.summary : {},
    by_kind: data && data.by_kind && typeof data.by_kind === 'object' ? data.by_kind : {},
    migration: data && data.migration && typeof data.migration === 'object' ? data.migration : {},
    invalid_count: Number(data && data.invalid_count) || 0,
    load_error: data && data.load_error ? String(data.load_error) : '',
  };
}

function applyAlertRulesState(data) {
  alertRulesState = normalizeAlertRulesState(data);
  const existingIds = new Set((alertRulesState.items || []).map(rule => rule.id));
  selectedAlertRuleIds = selectedAlertRuleIds.filter(id => existingIds.has(id));
  if (activeAlertRuleDetailId && !existingIds.has(activeAlertRuleDetailId)) activeAlertRuleDetailId = null;
  if (alertRulesState.load_error) setAlertRuleCenterStatus(alertRulesState.load_error, 'fail');
  renderAlertRuleCenter();
}

function setAlertRuleCenterStatus(message, type) {
  const el = document.getElementById('alertRuleCenterStatus');
  if (!el) return;
  el.textContent = message || '';
  el.className = 'alert-center-status' + (type ? ' ' + type : '');
}

function alertRuleKindLabel(kind) {
  return {
    price_threshold: '价格',
    volatility: '波动',
    watch_target: '目标价',
    portfolio: '持仓',
  }[kind] || '规则';
}

function alertRuleStatusLabel(status) {
  return {
    watching: '监控中',
    triggered: '已触发',
    expired: '已过期',
    disabled: '已停用',
    waiting_data: '等待数据',
    orphaned: '关联失效',
    scheduled: '待生效',
  }[status] || '状态未知';
}

function alertRuleStatusClass(status) {
  if (status === 'watching') return 'watching';
  if (status === 'triggered') return 'triggered';
  if (status === 'expired' || status === 'orphaned') return 'problem';
  if (status === 'waiting_data' || status === 'scheduled') return 'waiting';
  return 'disabled';
}

function alertRuleUnit(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function alertRuleValueText(value, mode, suffix) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  if (suffix) return number.toLocaleString('en-US', { maximumFractionDigits: 2 }) + suffix;
  const unit = mode === 'usd' ? '$' : '¥';
  return unit + number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function alertRuleConditionText(rule) {
  const scope = rule && rule.scope ? rule.scope : {};
  const condition = rule && rule.condition ? rule.condition : {};
  const mode = scope.mode || 'rmb';
  if (rule.kind === 'volatility') {
    return (condition.window_minutes || 10) + ' 分钟内波动达到 ' + alertRuleValueText(condition.value, mode, '%');
  }
  if (rule.kind === 'portfolio') {
    const label = {
      take_profit: '止盈价达到',
      stop_loss: '止损价达到',
      profit_percent: '浮盈达到',
      loss_percent: '浮亏达到',
      near_cost: '距离成本不超过',
    }[condition.condition_key] || '持仓条件';
    const suffix = ['profit_percent', 'loss_percent', 'near_cost'].includes(condition.condition_key) ? '%' : '';
    return (rule.scope_label || scope.position_id || '未关联持仓') + ' · ' + label + ' ' + alertRuleValueText(condition.value, mode, suffix);
  }
  const operator = condition.operator === 'gte' ? '上涨至' : '下跌至';
  return alertRuleUnit(mode) + ' · ' + operator + ' ' + alertRuleValueText(condition.value, mode, '');
}

function alertRuleDeliveryText(rule) {
  const delivery = rule && rule.delivery ? rule.delivery : {};
  const channels = delivery.channels;
  const cooldown = delivery.cooldown_minutes;
  let channelText = '继承通知';
  if (Array.isArray(channels)) {
    const labels = channels.map(channel => ({ local: '本机', email: '邮件', webhook: 'Webhook' }[channel] || channel));
    channelText = labels.length ? labels.join('、') : '仅记录';
  }
  const cooldownText = cooldown === 'inherit' || cooldown == null ? '继承冷却' : '冷却 ' + cooldown + ' 分钟';
  return channelText + ' · ' + cooldownText;
}

function alertRuleValidityText(rule) {
  const validity = rule && rule.validity ? rule.validity : {};
  if (validity.expires_at) return '有效至 ' + String(validity.expires_at).replace('T', ' ').slice(0, 16);
  if (validity.starts_at) return String(validity.starts_at).replace('T', ' ').slice(0, 16) + ' 起生效';
  return '长期有效';
}

function setAlertRuleFilter(filter) {
  alertRuleFilter = ['all', 'price_threshold', 'volatility', 'watch_target', 'portfolio'].includes(filter) ? filter : 'all';
  renderAlertRuleCenter();
}

function setAlertRuleStatusFilter(status) {
  alertRuleStatusFilter = ['all', 'watching', 'triggered', 'waiting_data', 'scheduled', 'expired', 'orphaned', 'disabled'].includes(status) ? status : 'all';
  renderAlertRuleCenter();
}

function setAlertRuleSearch(value) {
  alertRuleSearch = String(value || '').trim().toLowerCase();
  renderAlertRuleCenter();
}

function filteredAlertRules() {
  return (alertRulesState.items || []).filter(rule => {
    const status = (rule.state || {}).status || (rule.enabled === false ? 'disabled' : 'watching');
    if (alertRuleFilter !== 'all' && rule.kind !== alertRuleFilter) return false;
    if (alertRuleStatusFilter !== 'all' && status !== alertRuleStatusFilter) return false;
    if (!alertRuleSearch) return true;
    const haystack = [
      rule.id,
      rule.name,
      alertRuleKindLabel(rule.kind),
      alertRuleStatusLabel(status),
      alertRuleConditionText(rule),
      alertRuleDeliveryText(rule),
      rule.note,
    ].join(' ').toLowerCase();
    return haystack.includes(alertRuleSearch);
  });
}

function toggleAlertRuleSelection(id, checked) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  if (checked && !selectedAlertRuleIds.includes(ruleId)) selectedAlertRuleIds.push(ruleId);
  if (!checked) selectedAlertRuleIds = selectedAlertRuleIds.filter(item => item !== ruleId);
  renderAlertRuleCenter();
}

function toggleVisibleAlertRuleSelection(checked) {
  const visibleIds = filteredAlertRules().map(rule => rule.id).filter(Boolean);
  if (checked) {
    selectedAlertRuleIds = Array.from(new Set(selectedAlertRuleIds.concat(visibleIds)));
  } else {
    const visibleSet = new Set(visibleIds);
    selectedAlertRuleIds = selectedAlertRuleIds.filter(id => !visibleSet.has(id));
  }
  renderAlertRuleCenter();
}

function batchUpdateSelectedAlertRules(action) {
  const ids = selectedAlertRuleIds.slice();
  if (!ids.length) {
    setAlertRuleCenterStatus('请先选择要操作的预警规则。', 'fail');
    return;
  }
  if (action === 'delete' && !window.confirm('删除已选的 ' + ids.length + ' 条预警规则？此操作不会删除历史警报记录。')) return;
  const actionLabel = { enable: '启用', disable: '停用', reset: '重置', delete: '删除' }[action] || '更新';
  setAlertRuleCenterStatus('正在批量' + actionLabel + '规则...', '');
  socket.emit('batch_update_alert_rules', { ids, action });
}

function renderAlertRuleBatchBar(visibleItems) {
  const bar = document.getElementById('alertRuleBatchBar');
  if (bar) {
    bar.innerHTML = selectedAlertRuleIds.length ? [
      '<span>已选 ' + selectedAlertRuleIds.length + ' 条</span>',
      '<div>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'enable\')">启用</button>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'disable\')">停用</button>',
      '<button class="btn-clear-sm" type="button" onclick="batchUpdateSelectedAlertRules(\'reset\')">重置</button>',
      '<button class="btn-clear-sm alert-center-batch-delete" type="button" onclick="batchUpdateSelectedAlertRules(\'delete\')">删除</button>',
      '</div>',
    ].join('') : '';
    bar.className = 'alert-center-batch' + (selectedAlertRuleIds.length ? ' active' : '');
  }
  const selectVisible = document.getElementById('alertRuleSelectVisible');
  if (!selectVisible) return;
  const visibleIds = (visibleItems || []).map(rule => rule.id).filter(Boolean);
  const selectedVisibleCount = visibleIds.filter(id => selectedAlertRuleIds.includes(id)).length;
  selectVisible.checked = !!visibleIds.length && selectedVisibleCount === visibleIds.length;
  selectVisible.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleIds.length;
  selectVisible.disabled = !visibleIds.length;
}

function findUnifiedAlertRule(id) {
  return (alertRulesState.items || []).find(rule => rule.id === id) || null;
}

function cloneAlertRuleDraft(rule) {
  if (!rule) {
    return {
      kind: 'price_threshold',
      name: '',
      enabled: true,
      scope: { mode: currentMode, position_id: null },
      condition: { operator: 'gte', value: '', window_minutes: 10, condition_key: 'take_profit' },
      delivery: { channels: 'inherit', cooldown_minutes: 'inherit' },
      validity: { starts_at: '', expires_at: '' },
      note: '',
      alert_level: 'warning',
    };
  }
  return JSON.parse(JSON.stringify(rule));
}

function resetAlertRuleSimulation() {
  alertRuleSimulation = null;
  alertRuleSimulationLoading = false;
  alertRuleSimulationRequestId = '';
}

function invalidateAlertRuleSimulation() {
  const hadResult = alertRuleSimulationLoading || !!alertRuleSimulation;
  resetAlertRuleSimulation();
  if (!hadResult) return;
  const result = document.getElementById('alertRuleSimulationResult');
  if (result) result.innerHTML = '<div class="alert-center-simulation-empty">规则已修改，请重新运行历史模拟。</div>';
  setAlertRuleCenterStatus('规则已修改，请重新运行历史模拟。', '');
}

function openNewAlertRule(kind) {
  activeUnifiedAlertRuleId = 'new';
  activeAlertRuleDetailId = null;
  alertRuleDraft = cloneAlertRuleDraft(null);
  resetAlertRuleSimulation();
  if (kind && ['price_threshold', 'volatility', 'watch_target', 'portfolio'].includes(kind)) {
    alertRuleDraft.kind = kind;
  }
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
  requestAnimationFrame(() => document.getElementById('alertRuleName')?.focus());
}

function editUnifiedAlertRule(id) {
  const rule = findUnifiedAlertRule(id);
  if (!rule) {
    setAlertRuleCenterStatus('该规则已不存在，可从历史警报复制规则快照。', 'fail');
    return;
  }
  activeUnifiedAlertRuleId = id;
  activeAlertRuleDetailId = null;
  alertRuleDraft = cloneAlertRuleDraft(rule);
  resetAlertRuleSimulation();
  alertRuleFilter = 'all';
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
  requestAnimationFrame(() => document.getElementById('alertRuleName')?.focus());
}

function cancelUnifiedAlertRuleEdit() {
  activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  resetAlertRuleSimulation();
  setAlertRuleCenterStatus('', '');
  renderAlertRuleCenter();
}

function refreshAlertRuleInsight(id) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  alertRuleInsightLoading[ruleId] = true;
  socket.emit('get_alert_rule_insight', { id: ruleId, days: 30 });
  renderAlertRuleCenter();
}

function toggleAlertRuleDetail(id) {
  const ruleId = String(id || '');
  activeUnifiedAlertRuleId = null;
  alertRuleDraft = null;
  activeAlertRuleDetailId = activeAlertRuleDetailId === ruleId ? null : ruleId;
  if (activeAlertRuleDetailId && !alertRuleInsights[ruleId] && !alertRuleInsightLoading[ruleId]) {
    refreshAlertRuleInsight(ruleId);
    return;
  }
  renderAlertRuleCenter();
}

function alertRuleDiagnosticValue(value, rule, valueKind) {
  if (value == null || value === '') return '--';
  if (valueKind === 'percent') return alertRuleValueText(value, (rule.scope || {}).mode, '%');
  return alertRuleValueText(value, (rule.scope || {}).mode, '');
}

function alertRuleInspectionReason(reason) {
  return {
    watching: '条件尚未满足，规则持续监控。',
    condition_met: '当前条件已满足，等待本轮评估写入触发结果。',
    triggered_condition_met: '规则已触发，当前条件仍然满足。',
    triggered_latched: '规则已触发并保持锁定，重置后才会重新观察。',
    price_missing: '当前行情不可用，暂不执行判断。',
    history_insufficient: '价格历史样本不足，暂不能计算窗口波动。',
    position_missing: '关联持仓已不存在，需要修改或删除规则。',
    position_data_missing: '持仓存在，但当前估值数据不足。',
    disabled: '规则已停用，不参与评估。',
    scheduled: '尚未到开始时间。',
    expired: '规则已超过有效期。',
    orphaned: '关联对象不存在。',
    waiting_data: '正在等待可用数据。',
  }[reason] || '等待下一轮评估。';
}

function alertRuleRateText(value) {
  if (value == null || value === '') return '--';
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(1) + '%' : '--';
}

function buildAlertRuleDetail(rule) {
  const inspection = rule.inspection || {};
  const valueKind = inspection.value_kind || 'price';
  const distanceText = inspection.distance_to_trigger == null
    ? '--'
    : (Number(inspection.distance_to_trigger) <= 0 ? '已满足' : alertRuleDiagnosticValue(inspection.distance_to_trigger, rule, valueKind));
  const sampleText = inspection.required_samples
    ? '<span>窗口样本 ' + (inspection.sample_count || 0) + ' / ' + inspection.required_samples + '</span>'
    : '';
  const insight = alertRuleInsights[rule.id];
  let insightHtml = '<div class="alert-center-insight-loading">正在读取最近 30 天触发复盘...</div>';
  if (!alertRuleInsightLoading[rule.id] && insight) {
    const effectiveness = insight.effectiveness || {};
    const delivery = effectiveness.delivery || {};
    const response = effectiveness.response || {};
    const followThrough = effectiveness.market_follow_through || {};
    const deliveryState = insight.delivery || {};
    const channelText = deliveryState.record_only
      ? '仅记录'
      : (deliveryState.channels || []).map(channel => channel.label + (channel.ready ? '' : '（' + (channel.reason || '不可用') + '）')).join('、');
    const latest = Array.isArray(insight.recent_alerts) && insight.recent_alerts.length ? insight.recent_alerts[0] : null;
    insightHtml = [
      '<div class="alert-center-insight-grid">',
      '<div><span>30 天触发</span><strong>' + (Number(effectiveness.period_alerts) || 0) + '</strong></div>',
      '<div><span>通知送达率</span><strong>' + alertRuleRateText(delivery.sent_rate) + '</strong></div>',
      '<div><span>已处理率</span><strong>' + alertRuleRateText(response.handled_rate) + '</strong></div>',
      '<div><span>24 小时延续率</span><strong>' + alertRuleRateText(followThrough.rate) + '</strong></div>',
      '</div>',
      '<div class="alert-center-detail-line"><span>实际通知</span><strong>' + escapeHtml(channelText || '无可用渠道') + '</strong></div>',
      '<div class="alert-center-detail-line"><span>实际冷却</span><strong>' + escapeHtml(String(deliveryState.cooldown_minutes || 0)) + ' 分钟' + (deliveryState.cooldown_inherited ? '（继承）' : '') + '</strong></div>',
      latest ? '<div class="alert-center-detail-line"><span>最近记录</span><strong>' + escapeHtml(String(latest.timestamp || '').replace('T', ' ').slice(0, 16)) + (latest.handled ? ' · 已处理' : ' · 未处理') + '</strong></div>' : '',
    ].join('');
  }
  return [
    '<div class="alert-center-detail">',
    '<div class="alert-center-detail-head"><strong>运行诊断</strong><span>' + escapeHtml(alertRuleInspectionReason(inspection.reason)) + '</span></div>',
    '<div class="alert-center-inspection-grid">',
    '<div><span>当前值</span><strong>' + escapeHtml(alertRuleDiagnosticValue(inspection.current_value, rule, valueKind)) + '</strong></div>',
    '<div><span>目标值</span><strong>' + escapeHtml(alertRuleDiagnosticValue(inspection.target_value, rule, valueKind)) + '</strong></div>',
    '<div><span>距触发</span><strong>' + escapeHtml(distanceText) + '</strong></div>',
    '<div><span>最近评估</span><strong>' + escapeHtml(inspection.last_evaluated_at ? String(inspection.last_evaluated_at).replace('T', ' ').slice(0, 16) : '实时行情') + '</strong></div>',
    '</div>',
    sampleText ? '<div class="alert-center-detail-samples">' + sampleText + '</div>' : '',
    '<div class="alert-center-detail-head alert-center-insight-head"><strong>触发复盘</strong><span>行情延续率仅用于复盘，不代表预测准确率。</span></div>',
    insightHtml,
    '<div class="alert-center-detail-actions"><button class="btn-clear-sm" type="button" onclick="filterAlertLogByRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">查看记录</button><button class="btn-clear-sm" type="button" onclick="refreshAlertRuleInsight(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">刷新复盘</button></div>',
    '</div>',
  ].join('');
}

function alertRuleEditorValue(id) {
  const el = document.getElementById(id);
  return el ? el.value : '';
}

function alertRuleEditorChecked(id) {
  return !!document.getElementById(id)?.checked;
}

function captureAlertRuleDraft(preserveSimulation) {
  if (!activeUnifiedAlertRuleId || !document.getElementById('alertRuleKind')) return;
  const existing = activeUnifiedAlertRuleId === 'new' ? null : findUnifiedAlertRule(activeUnifiedAlertRuleId);
  const kind = alertRuleEditorValue('alertRuleKind');
  const mode = alertRuleEditorValue('alertRuleMode') || 'rmb';
  const deliveryMode = alertRuleEditorValue('alertRuleDeliveryMode') || 'inherit';
  const cooldownMode = alertRuleEditorValue('alertRuleCooldownMode') || 'inherit';
  let channels = 'inherit';
  if (deliveryMode === 'record') channels = [];
  if (deliveryMode === 'custom') {
    channels = ['local', 'email', 'webhook'].filter(channel => alertRuleEditorChecked('alertRuleChannel_' + channel));
  }
  const condition = { value: alertRuleEditorValue('alertRuleConditionValue') };
  if (kind === 'volatility') {
    condition.operator = 'abs_change_gte';
    condition.window_minutes = alertRuleEditorValue('alertRuleWindowMinutes');
  } else if (kind === 'portfolio') {
    condition.condition_key = alertRuleEditorValue('alertRulePortfolioCondition');
  } else {
    condition.operator = alertRuleEditorValue('alertRuleOperator') || 'gte';
  }
  alertRuleDraft = {
    id: existing ? existing.id : undefined,
    kind,
    name: alertRuleEditorValue('alertRuleName'),
    enabled: alertRuleEditorChecked('alertRuleEnabled'),
    scope: {
      mode,
      position_id: kind === 'portfolio' ? alertRuleEditorValue('alertRulePosition') : null,
    },
    condition,
    delivery: {
      channels,
      cooldown_minutes: cooldownMode === 'custom' ? alertRuleEditorValue('alertRuleCooldownMinutes') : 'inherit',
    },
    validity: {
      starts_at: alertRuleEditorValue('alertRuleStartsAt'),
      expires_at: alertRuleEditorValue('alertRuleExpiresAt'),
    },
    note: alertRuleEditorValue('alertRuleNote'),
    alert_level: kind === 'volatility' ? 'volatility' : alertRuleEditorValue('alertRuleLevel') || 'warning',
    legacy: existing && existing.kind === kind ? (existing.legacy || {}) : {},
  };
  if (!preserveSimulation) invalidateAlertRuleSimulation();
}

function changeAlertRuleKind(kind) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.kind = kind;
  alertRuleDraft.scope = Object.assign({ mode: currentMode, position_id: null }, alertRuleDraft.scope || {});
  alertRuleDraft.condition = {
    operator: kind === 'volatility' ? 'abs_change_gte' : 'gte',
    value: alertRuleDraft.condition && alertRuleDraft.condition.value ? alertRuleDraft.condition.value : '',
    window_minutes: 10,
    condition_key: 'take_profit',
  };
  alertRuleDraft.legacy = {};
  renderAlertRuleCenter();
}

function changeAlertRuleCooldownMode(mode) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.delivery = { ...(alertRuleDraft.delivery || {}) };
  alertRuleDraft.delivery.cooldown_minutes = mode === 'custom' ? 30 : 'inherit';
  renderAlertRuleCenter();
}

function changeAlertRuleDeliveryMode(mode) {
  captureAlertRuleDraft();
  if (!alertRuleDraft) return;
  alertRuleDraft.delivery = { ...(alertRuleDraft.delivery || {}) };
  if (mode === 'custom') alertRuleDraft.delivery.channels = ['local'];
  else if (mode === 'record') alertRuleDraft.delivery.channels = [];
  else alertRuleDraft.delivery.channels = 'inherit';
  renderAlertRuleCenter();
}

function validatedAlertRuleDraft() {
  captureAlertRuleDraft(true);
  const payload = alertRuleDraft ? JSON.parse(JSON.stringify(alertRuleDraft)) : null;
  const value = Number(payload && payload.condition && payload.condition.value);
  if (!payload || !Number.isFinite(value) || value <= 0) {
    setAlertRuleCenterStatus('请输入大于 0 的条件值。', 'fail');
    return null;
  }
  if (payload.kind === 'portfolio' && !(payload.scope && payload.scope.position_id)) {
    setAlertRuleCenterStatus('请选择要关联的持仓。', 'fail');
    return null;
  }
  if (payload.kind === 'volatility') {
    const minutes = Number(payload.condition.window_minutes);
    if (!Number.isInteger(minutes) || minutes < 1) {
      setAlertRuleCenterStatus('观察窗口必须是大于 0 的整数分钟。', 'fail');
      return null;
    }
  }
  return payload;
}

function setAlertRuleSimulationDays(value) {
  const days = Number(value);
  alertRuleSimulationDays = [7, 30, 90].includes(days) ? days : 30;
  resetAlertRuleSimulation();
  renderAlertRuleCenter();
}

function simulateUnifiedAlertRule() {
  const payload = validatedAlertRuleDraft();
  if (!payload) return;
  alertRuleSimulationRequestId = 'rule-simulation-' + Date.now().toString(36);
  alertRuleSimulation = null;
  alertRuleSimulationLoading = true;
  setAlertRuleCenterStatus('正在模拟历史行情...', '');
  socket.emit('simulate_alert_rule', {
    request_id: alertRuleSimulationRequestId,
    days: alertRuleSimulationDays,
    rule: payload,
  });
  renderAlertRuleCenter();
}

function alertRuleSimulationEventText(event, draft) {
  if (!event) return '';
  const mode = (draft.scope || {}).mode || 'rmb';
  const value = alertRuleValueText(event.value, mode, '');
  const change = event.change_percent == null ? '' : ' · 波动 ' + Number(event.change_percent).toFixed(2) + '%';
  return String(event.timestamp || '').replace('T', ' ').slice(0, 16) + ' · ' + value + change;
}

function buildAlertRuleSimulationPanel(draft) {
  const isPortfolio = draft.kind === 'portfolio';
  let resultHtml = '<div class="alert-center-simulation-empty">根据本地历史行情估算规则命中与冷却后的触发次数，不修改规则和历史数据。</div>';
  if (isPortfolio) {
    resultHtml = '<div class="alert-center-simulation-empty">当前没有历史持仓估值快照，本版不模拟持仓规则。</div>';
  } else if (alertRuleSimulationLoading) {
    resultHtml = '<div class="alert-center-insight-loading">正在读取并模拟历史行情...</div>';
  } else if (alertRuleSimulation && alertRuleSimulation.error) {
    resultHtml = '<div class="alert-center-simulation-error">' + escapeHtml(alertRuleSimulation.error) + '</div>';
  } else if (alertRuleSimulation) {
    const simulation = alertRuleSimulation;
    const coverage = simulation.coverage || {};
    if (!simulation.supported || !simulation.usable) {
      resultHtml = [
        '<div class="alert-center-simulation-error">' + escapeHtml(simulation.message || '现有历史数据不足，无法完成模拟。') + '</div>',
        coverage.point_count ? '<div class="alert-center-simulation-meta">已读取 ' + Number(coverage.point_count) + ' 个价格点，采样间隔约 ' + escapeHtml(coverage.sampling_interval_label || '未知') + '。</div>' : '',
      ].join('');
    } else {
      const distribution = (simulation.time_distribution || []).map(item => '<span>' + escapeHtml(item.label || '') + '<strong>' + (Number(item.count) || 0) + '</strong></span>').join('');
      const recent = (simulation.recent_triggers || []).slice(0, 3).map(item => '<li>' + escapeHtml(alertRuleSimulationEventText(item, draft)) + '</li>').join('');
      const coverageText = coverage.from && coverage.to
        ? String(coverage.from).replace('T', ' ').slice(0, 16) + ' 至 ' + String(coverage.to).replace('T', ' ').slice(0, 16)
        : '无可用时间范围';
      resultHtml = [
        '<div class="alert-center-simulation-grid">',
        '<div><span>历史样本</span><strong>' + (Number(coverage.point_count) || 0) + '</strong></div>',
        '<div><span>规则命中</span><strong>' + (Number(simulation.match_count) || 0) + '</strong></div>',
        '<div><span>冷却后触发</span><strong>' + (Number(simulation.effective_trigger_count) || 0) + '</strong></div>',
        '<div><span>被抑制</span><strong>' + (Number(simulation.suppressed_count) || 0) + '</strong></div>',
        '</div>',
        '<div class="alert-center-simulation-meta">覆盖 ' + escapeHtml(coverageText) + ' · 采样间隔约 ' + escapeHtml(coverage.sampling_interval_label || '未知') + ' · 冷却 ' + (Number(simulation.cooldown_minutes) || 0) + ' 分钟' + (coverage.partial ? ' · 覆盖不足' : '') + '</div>',
        '<div class="alert-center-simulation-distribution">' + distribution + '</div>',
        recent ? '<ul class="alert-center-simulation-events">' + recent + '</ul>' : '<div class="alert-center-simulation-empty">该范围内没有估算触发记录。</div>',
        '<div class="alert-center-simulation-note">' + escapeHtml(simulation.message || '') + ' 历史模拟仅用于配置评估，不代表预测准确率或投资建议。</div>',
      ].join('');
    }
  }
  return [
    '<div class="alert-center-simulation">',
    '<div class="alert-center-simulation-head"><div><strong>历史模拟</strong><span>忽略当前启停和有效期，仅按条件与冷却策略计算。</span></div><div>',
    '<select id="alertRuleSimulationDays" aria-label="历史模拟范围" onchange="setAlertRuleSimulationDays(this.value)"' + (isPortfolio ? ' disabled' : '') + '>',
    '<option value="7"' + (alertRuleSimulationDays === 7 ? ' selected' : '') + '>7 天</option>',
    '<option value="30"' + (alertRuleSimulationDays === 30 ? ' selected' : '') + '>30 天</option>',
    '<option value="90"' + (alertRuleSimulationDays === 90 ? ' selected' : '') + '>90 天</option>',
    '</select>',
    '<button class="btn-clear-sm" type="button" onclick="simulateUnifiedAlertRule()"' + (isPortfolio || alertRuleSimulationLoading ? ' disabled' : '') + '>运行模拟</button>',
    '</div></div>',
    '<div id="alertRuleSimulationResult">' + resultHtml + '</div>',
    '</div>',
  ].join('');
}

function alertRuleEditorConditionFields(draft) {
  const condition = draft.condition || {};
  if (draft.kind === 'portfolio') {
    const positions = Array.isArray(portfolioState.items) ? portfolioState.items : [];
    const options = positions.map(item => '<option value="' + escapeHtml(item.id || '') + '"' + ((draft.scope || {}).position_id === item.id ? ' selected' : '') + '>' + escapeHtml(item.name || item.id || '未命名持仓') + '</option>').join('');
    return [
      '<label class="alert-center-field"><span>关联持仓</span><select id="alertRulePosition"><option value="">请选择持仓</option>' + options + '</select></label>',
      '<label class="alert-center-field"><span>提醒条件</span><select id="alertRulePortfolioCondition">',
      '<option value="take_profit"' + (condition.condition_key === 'take_profit' ? ' selected' : '') + '>止盈价</option>',
      '<option value="stop_loss"' + (condition.condition_key === 'stop_loss' ? ' selected' : '') + '>止损价</option>',
      '<option value="profit_percent"' + (condition.condition_key === 'profit_percent' ? ' selected' : '') + '>浮盈比例</option>',
      '<option value="loss_percent"' + (condition.condition_key === 'loss_percent' ? ' selected' : '') + '>浮亏比例</option>',
      '<option value="near_cost"' + (condition.condition_key === 'near_cost' ? ' selected' : '') + '>接近成本</option>',
      '</select></label>',
      '<label class="alert-center-field"><span>条件值</span><input id="alertRuleConditionValue" type="number" step="0.01" min="0" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="输入价格或比例"></label>',
    ].join('');
  }
  if (draft.kind === 'volatility') {
    return [
      '<label class="alert-center-field"><span>单位</span><select id="alertRuleMode"><option value="rmb"' + ((draft.scope || {}).mode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + ((draft.scope || {}).mode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></label>',
      '<label class="alert-center-field"><span>观察窗口</span><input id="alertRuleWindowMinutes" type="number" min="1" max="1440" step="1" value="' + escapeHtml(condition.window_minutes || 10) + '"></label>',
      '<label class="alert-center-field"><span>波动幅度（%）</span><input id="alertRuleConditionValue" type="number" min="0" step="0.1" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="例如 1.5"></label>',
    ].join('');
  }
  return [
    '<label class="alert-center-field"><span>单位</span><select id="alertRuleMode"><option value="rmb"' + ((draft.scope || {}).mode === 'rmb' ? ' selected' : '') + '>RMB/克</option><option value="usd"' + ((draft.scope || {}).mode === 'usd' ? ' selected' : '') + '>USD/oz</option></select></label>',
    '<label class="alert-center-field"><span>方向</span><select id="alertRuleOperator"><option value="gte"' + (condition.operator === 'gte' ? ' selected' : '') + '>上涨至或高于</option><option value="lte"' + (condition.operator === 'lte' ? ' selected' : '') + '>下跌至或低于</option></select></label>',
    '<label class="alert-center-field"><span>目标价格</span><input id="alertRuleConditionValue" type="number" min="0" step="0.01" value="' + escapeHtml(condition.value == null ? '' : condition.value) + '" placeholder="输入价格"></label>',
  ].join('');
}

function buildUnifiedAlertRuleEditor() {
  const draft = alertRuleDraft || cloneAlertRuleDraft(null);
  const delivery = draft.delivery || {};
  const channels = delivery.channels;
  const deliveryMode = channels === 'inherit' || channels == null ? 'inherit' : (Array.isArray(channels) && !channels.length ? 'record' : 'custom');
  const selectedChannels = Array.isArray(channels) ? channels : [];
  const cooldownMode = delivery.cooldown_minutes === 'inherit' || delivery.cooldown_minutes == null ? 'inherit' : 'custom';
  const validity = draft.validity || {};
  const editorTitle = activeUnifiedAlertRuleId === 'new' ? '新增预警规则' : '编辑预警规则';
  return [
    '<div class="alert-center-editor" oninput="captureAlertRuleDraft()">',
    '<div class="alert-center-editor-head"><strong>' + editorTitle + '</strong><span>保存失败时保留当前输入</span></div>',
    '<div class="alert-center-form-grid">',
    '<label class="alert-center-field"><span>类型</span><select id="alertRuleKind" onchange="changeAlertRuleKind(this.value)">',
    '<option value="price_threshold"' + (draft.kind === 'price_threshold' ? ' selected' : '') + '>价格阈值</option>',
    '<option value="volatility"' + (draft.kind === 'volatility' ? ' selected' : '') + '>波动规则</option>',
    '<option value="watch_target"' + (draft.kind === 'watch_target' ? ' selected' : '') + '>目标价观察</option>',
    '<option value="portfolio"' + (draft.kind === 'portfolio' ? ' selected' : '') + '>持仓提醒</option>',
    '</select></label>',
    '<label class="alert-center-field alert-center-field-wide"><span>名称</span><input id="alertRuleName" type="text" maxlength="80" value="' + escapeHtml(draft.name || '') + '" placeholder="留空时自动生成"></label>',
    alertRuleEditorConditionFields(draft),
    '<label class="alert-center-field"><span>级别</span><select id="alertRuleLevel"' + (draft.kind === 'volatility' ? ' disabled' : '') + '><option value="warning"' + (draft.alert_level !== 'critical' ? ' selected' : '') + '>关注</option><option value="critical"' + (draft.alert_level === 'critical' ? ' selected' : '') + '>警告</option></select></label>',
    '<label class="alert-center-field"><span>开始时间</span><input id="alertRuleStartsAt" type="datetime-local" value="' + escapeHtml(String(validity.starts_at || '').slice(0, 16)) + '"></label>',
    '<label class="alert-center-field"><span>失效时间</span><input id="alertRuleExpiresAt" type="datetime-local" value="' + escapeHtml(String(validity.expires_at || '').slice(0, 16)) + '"></label>',
    '<label class="alert-center-field"><span>冷却策略</span><select id="alertRuleCooldownMode" onchange="changeAlertRuleCooldownMode(this.value)"><option value="inherit"' + (cooldownMode === 'inherit' ? ' selected' : '') + '>继承全局</option><option value="custom"' + (cooldownMode === 'custom' ? ' selected' : '') + '>单独设置</option></select></label>',
    cooldownMode === 'custom' ? '<label class="alert-center-field"><span>冷却分钟</span><input id="alertRuleCooldownMinutes" type="number" min="0" max="1440" step="1" value="' + escapeHtml(delivery.cooldown_minutes == null ? 30 : delivery.cooldown_minutes) + '"></label>' : '<input id="alertRuleCooldownMinutes" type="hidden" value="inherit">',
    '<label class="alert-center-field"><span>通知策略</span><select id="alertRuleDeliveryMode" onchange="changeAlertRuleDeliveryMode(this.value)"><option value="inherit"' + (deliveryMode === 'inherit' ? ' selected' : '') + '>继承全局</option><option value="custom"' + (deliveryMode === 'custom' ? ' selected' : '') + '>指定渠道</option><option value="record"' + (deliveryMode === 'record' ? ' selected' : '') + '>仅记录</option></select></label>',
    deliveryMode === 'custom' ? '<div class="alert-center-channel-field"><span>通知渠道</span><label><input id="alertRuleChannel_local" type="checkbox"' + (selectedChannels.includes('local') ? ' checked' : '') + '>本机</label><label><input id="alertRuleChannel_email" type="checkbox"' + (selectedChannels.includes('email') ? ' checked' : '') + '>邮件</label><label><input id="alertRuleChannel_webhook" type="checkbox"' + (selectedChannels.includes('webhook') ? ' checked' : '') + '>Webhook</label></div>' : '<input id="alertRuleChannel_local" type="hidden"><input id="alertRuleChannel_email" type="hidden"><input id="alertRuleChannel_webhook" type="hidden">',
    '<label class="alert-center-field alert-center-field-wide"><span>备注</span><input id="alertRuleNote" type="text" maxlength="200" value="' + escapeHtml(draft.note || '') + '" placeholder="可选"></label>',
    '</div>',
    buildAlertRuleSimulationPanel(draft),
    '<div class="alert-center-editor-foot"><label class="alert-center-enabled"><input id="alertRuleEnabled" type="checkbox"' + (draft.enabled === false ? '' : ' checked') + '>保存后启用</label><div><button class="btn-clear-sm" type="button" onclick="cancelUnifiedAlertRuleEdit()">取消</button><button class="btn-set" type="button" onclick="saveUnifiedAlertRule()">保存规则</button></div></div>',
    '</div>',
  ].join('');
}

function saveUnifiedAlertRule() {
  const payload = validatedAlertRuleDraft();
  if (!payload) return;
  setAlertRuleCenterStatus('正在保存预警规则...', '');
  socket.emit('save_alert_rule', payload);
}

function toggleUnifiedAlertRule(id, enabled) {
  setAlertRuleCenterStatus(enabled ? '正在启用规则...' : '正在停用规则...', '');
  socket.emit('toggle_alert_rule', { id, enabled });
}

function duplicateUnifiedAlertRule(id) {
  setAlertRuleCenterStatus('正在复制规则...', '');
  socket.emit('duplicate_alert_rule', { id });
}

function resetUnifiedAlertRule(id) {
  setAlertRuleCenterStatus('正在重置触发状态...', '');
  socket.emit('reset_alert_rule_state', { id });
}

function deleteUnifiedAlertRule(id) {
  const rule = findUnifiedAlertRule(id);
  if (!rule || !window.confirm('删除预警规则“' + (rule.name || '未命名规则') + '”？')) return;
  setAlertRuleCenterStatus('正在删除规则...', '');
  socket.emit('delete_alert_rule', { id });
}

function renderAlertRuleSummary() {
  const box = document.getElementById('alertRuleSummary');
  if (!box) return;
  const summary = alertRulesState.summary || {};
  const items = [
    ['watching', '监控中'],
    ['triggered', '已触发'],
    ['expired', '已过期'],
    ['disabled', '已停用'],
  ];
  box.innerHTML = items.map(item => '<div class="alert-summary-item ' + item[0] + '"><span>' + escapeHtml(item[1]) + '</span><strong>' + (Number(summary[item[0]]) || 0) + '</strong></div>').join('');
}

function renderAlertRuleCenter() {
  const list = document.getElementById('alertRuleCenterList');
  if (!list) return;
  renderAlertRuleSummary();
  document.querySelectorAll('.alert-center-filter').forEach(button => {
    button.classList.toggle('active', button.dataset.filter === alertRuleFilter);
  });
  const items = filteredAlertRules();
  renderAlertRuleBatchBar(items);
  const parts = [];
  if (activeUnifiedAlertRuleId === 'new') parts.push(buildUnifiedAlertRuleEditor());
  if (!items.length && activeUnifiedAlertRuleId !== 'new') {
    parts.push('<div class="alert-center-empty">当前筛选下暂无规则。新增规则后会在这里统一展示状态和触发结果。</div>');
  }
  items.forEach(rule => {
    const state = rule.state || {};
    const status = state.status || (rule.enabled === false ? 'disabled' : 'watching');
    const detailExpanded = activeAlertRuleDetailId === rule.id;
    const expanded = activeUnifiedAlertRuleId === rule.id || detailExpanded;
    const selected = selectedAlertRuleIds.includes(rule.id);
    const lastTriggered = state.last_triggered_at ? ' · 最近触发 ' + String(state.last_triggered_at).replace('T', ' ').slice(0, 16) : '';
    parts.push([
      '<div class="alert-center-rule kind-' + escapeHtml(rule.kind || '') + ' status-' + escapeHtml(status) + (expanded ? ' expanded' : '') + (selected ? ' selected' : '') + '">',
      '<span class="alert-center-rail" aria-hidden="true"></span>',
      '<div class="alert-center-rule-main">',
      '<div class="alert-center-rule-title"><label class="alert-center-select"><input type="checkbox" aria-label="选择规则 ' + escapeHtml(rule.name || '未命名规则') + '" onchange="toggleAlertRuleSelection(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ', this.checked)"' + (selected ? ' checked' : '') + '></label><span class="alert-center-kind">' + escapeHtml(alertRuleKindLabel(rule.kind)) + '</span><strong>' + escapeHtml(rule.name || '未命名规则') + '</strong></div>',
      '<div class="alert-center-rule-condition">' + escapeHtml(alertRuleConditionText(rule)) + '</div>',
      '<div class="alert-center-rule-meta">' + escapeHtml(alertRuleDeliveryText(rule) + ' · ' + alertRuleValidityText(rule) + lastTriggered) + '</div>',
      '</div>',
      '<div class="alert-center-rule-actions">',
      '<span class="alert-center-state ' + alertRuleStatusClass(status) + '">' + escapeHtml(alertRuleStatusLabel(status)) + '</span>',
      '<button class="btn-clear-sm" type="button" onclick="toggleAlertRuleDetail(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">' + (detailExpanded ? '收起' : '详情') + '</button>',
      '<button class="btn-clear-sm" type="button" onclick="editUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">编辑</button>',
      '<button class="btn-clear-sm" type="button" onclick="toggleUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ', ' + (rule.enabled === false ? 'true' : 'false') + ')">' + (rule.enabled === false ? '启用' : '停用') + '</button>',
      '<button class="btn-clear-sm" type="button" onclick="duplicateUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">复制</button>',
      state.triggered ? '<button class="btn-clear-sm" type="button" onclick="resetUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">重置</button>' : '',
      '<button class="btn-clear-sm" type="button" onclick="deleteUnifiedAlertRule(' + escapeHtml(JSON.stringify(String(rule.id || ''))) + ')">删除</button>',
      '</div>',
      activeUnifiedAlertRuleId === rule.id ? buildUnifiedAlertRuleEditor() : '',
      detailExpanded ? buildAlertRuleDetail(rule) : '',
      '</div>',
    ].join(''));
  });
  list.innerHTML = parts.join('');
}

function formatAlertRuleValue(value, unit) {
  if (value == null || value === '') return '未设置';
  return unit + Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatAlertEmailState(emailKey) {
  return appSettings[emailKey] === false ? '邮件关闭' : '邮件开启';
}

function setActiveAlertRule(type) {
  activeAlertRule = activeAlertRule === type ? null : type;
  renderAlertRules();
}

function buildThresholdRuleEditor(rule, value) {
  const inputValue = value == null ? '' : String(value);
  const mailChecked = appSettings[rule.emailKey] !== false ? ' checked' : '';
  return [
    '<div class="alert-rule-editor">',
    '<div class="alert-rule-fields">',
    '<div class="alert-rule-field">',
    '<label for="alertRuleValue_' + escapeHtml(rule.type) + '">触发价位</label>',
    '<input id="alertRuleValue_' + escapeHtml(rule.type) + '" type="number" step="0.01" value="' + escapeHtml(inputValue) + '" placeholder="输入价位">',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>触发时发送邮件</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="alertRuleEmail_' + escapeHtml(rule.type) + '"' + mailChecked + '><span class="slider"></span></label>',
    '</div>',
    '</div>',
    '<div class="alert-rule-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveThresholdRule(\'' + rule.type + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="clearThreshold(\'' + rule.type + '\')">停用预警</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'' + rule.type + '\')">放弃编辑</button>',
    '</div>',
    '</div>',
  ].join('');
}

function buildVolatilityRuleEditor() {
  const pct = volConfig.percent == null ? '2.0' : String(volConfig.percent);
  const minutes = volConfig.minutes || 10;
  const mailChecked = appSettings.email_volatility_enabled !== false ? ' checked' : '';
  return [
    '<div class="alert-rule-editor">',
    '<div class="alert-rule-fields">',
    '<div class="alert-rule-field">',
    '<label for="alertRuleVolPct">波动幅度</label>',
    '<input id="alertRuleVolPct" type="number" step="0.1" value="' + escapeHtml(pct) + '" placeholder="2.0">',
    '</div>',
    '<div class="alert-rule-field">',
    '<label for="alertRuleVolMin">观察分钟</label>',
    '<input id="alertRuleVolMin" type="number" step="1" value="' + escapeHtml(minutes) + '" placeholder="10">',
    '</div>',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>触发时发送邮件</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="alertRuleEmail_volatility"' + mailChecked + '><span class="slider"></span></label>',
    '</div>',
    '<div class="alert-rule-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveVolatilityRule()">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="clearVolatility()">停用预警</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'volatility\')">放弃编辑</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderAlertRules() {
  const box = document.getElementById('alertRulesList');
  if (!box) return;
  const unit = currentMode === 'usd' ? '$' : '¥';
  const modeLabel = currentMode === 'usd' ? 'USD/oz' : 'RMB/克';
  const ruleItems = ALERT_RULE_DEFS.map(rule => {
    const key = rule.type + '_' + currentMode;
    const value = allThresholds[key];
    const enabled = value != null;
    return {
      badgeClass: rule.badgeClass,
      title: rule.title,
      meta: rule.direction + ' ' + formatAlertRuleValue(value, unit) + ' · ' + modeLabel + ' · ' + formatAlertEmailState(rule.emailKey),
      state: enabled ? '已启用' : '未设置',
      enabled,
      type: rule.type,
      editor: activeAlertRule === rule.type ? buildThresholdRuleEditor(rule, value) : '',
      edit: "setActiveAlertRule('" + rule.type + "')",
      clear: "clearThreshold('" + rule.type + "')",
    };
  });
  const volEnabled = !!(volConfig.enabled && volConfig.percent != null);
  ruleItems.push({
    badgeClass: 'vol',
    title: '波动预警',
    meta: (volEnabled ? volConfig.minutes + '分钟内波动达到 ' + volConfig.percent + '%' : '未启用') + ' · ' + formatAlertEmailState('email_volatility_enabled'),
    state: volEnabled ? '已启用' : '已关闭',
    enabled: volEnabled,
    type: 'volatility',
    editor: activeAlertRule === 'volatility' ? buildVolatilityRuleEditor() : '',
    edit: "setActiveAlertRule('volatility')",
    clear: "clearVolatility()",
  });
  box.innerHTML = ruleItems.map(rule => [
    '<div class="alert-rule-item' + (activeAlertRule === rule.type ? ' expanded' : '') + '">',
    '<div class="alert-rule-main">',
    '<div class="alert-rule-title"><span class="level-badge ' + escapeHtml(rule.badgeClass) + '">' + escapeHtml(rule.title.replace('上涨', '').replace('下跌', '').replace('预警', '')) + '</span> ' + escapeHtml(rule.title) + '</div>',
    '<div class="alert-rule-meta">' + escapeHtml(rule.meta) + '</div>',
    '</div>',
    '<div class="alert-rule-actions">',
    '<span class="alert-rule-state ' + (rule.enabled ? 'on' : 'off') + '">' + escapeHtml(rule.state) + '</span>',
    '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="' + rule.edit + '">编辑</button>',
    '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="' + rule.clear + '">停用</button>',
    '</div>',
    rule.editor,
    '</div>',
  ].join('')).join('');
}

function updateThresholdInputs() {
  renderAlertRules();
}

function setThreshold(type) {
  const input = document.getElementById('alertRuleValue_' + type);
  const val = input ? input.value.trim() : '';
  socket.emit('set_threshold', { mode: currentMode, type, value: val === '' ? null : val });
}

function saveThresholdRule(type) {
  const rule = ALERT_RULE_DEFS.find(item => item.type === type);
  if (!rule) return;
  const input = document.getElementById('alertRuleValue_' + type);
  const emailInput = document.getElementById('alertRuleEmail_' + type);
  const val = input ? input.value.trim() : '';
  if (emailInput) updateEmailSwitch(rule.emailKey, emailInput.checked);
  socket.emit('set_threshold', { mode: currentMode, type, value: val === '' ? null : val });
}

function clearThreshold(type) {
  socket.emit('clear_threshold', { mode: currentMode, type });
}

function updateEmailSwitch(key, value) {
  const update = {};
  update[key] = value;
  socket.emit('update_settings', update);
  appSettings[key] = value;
  renderAlertRules();
}

// ========== 波动率 ==========
function setVolatility() {
  const pctEl = document.getElementById('alertRuleVolPct');
  const minEl = document.getElementById('alertRuleVolMin');
  const pct = pctEl ? (pctEl.value || '2.0') : String(volConfig.percent || '2.0');
  const min = minEl ? (minEl.value || '10') : String(volConfig.minutes || 10);
  const parsedPct = parseFloat(pct);
  const parsedMin = parseInt(min, 10);

  if (!Number.isFinite(parsedPct) || parsedPct <= 0 || !Number.isInteger(parsedMin) || parsedMin < 1) {
    alert('请输入有效的波动预警数字。');
    return;
  }

  volConfig = { percent: parsedPct, minutes: parsedMin, enabled: true };
  updateVolUI();
  socket.emit('set_volatility', { percent: pct, minutes: min, enabled: true });
}

function saveVolatilityRule() {
  const emailInput = document.getElementById('alertRuleEmail_volatility');
  setVolatility();
  if (emailInput) updateEmailSwitch('email_volatility_enabled', emailInput.checked);
}

function clearVolatility() {
  volConfig = { percent: null, minutes: 10, enabled: false };
  updateVolUI();
  socket.emit('set_volatility', { percent: null, minutes: 10, enabled: false });
}

function updateVolUI() {
  renderAlertRules();
}

// ========== 阈值接近提示 ==========
function checkThresholdProximity() {
  renderAlertRules();
}

// ========== 目标价观察 ==========
function normalizeWatchTargetItems(data) {
  if (Array.isArray(data)) return data;
  if (data && Array.isArray(data.items)) return data.items;
  return [];
}

function applyWatchTargets(data) {
  watchTargets = normalizeWatchTargetItems(data).map(item => Object.assign({}, item));
  renderWatchTargets();
}

function setWatchTargetStatus(message, type) {
  const status = document.getElementById('watchTargetStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'watch-target-status' + (type ? ' ' + type : '');
}

function setActiveWatchTarget(id) {
  activeWatchTargetId = activeWatchTargetId === id ? null : id;
  renderWatchTargets();
}

function watchTargetUnit(mode) {
  return mode === 'usd' ? '$' : '¥';
}

function watchTargetModeLabel(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function watchTargetDirectionLabel(direction) {
  return direction === 'rise_to' ? '上涨至' : '下跌至';
}

function watchTargetPrice(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return watchTargetUnit(mode) + number.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function watchTargetStateLabel(item) {
  if (item.triggered) return '已触发';
  if (item.enabled === false) return '已停用';
  return '观察中';
}

function watchTargetStateClass(item) {
  if (item.triggered) return 'on';
  if (item.enabled === false) return 'off';
  return 'on';
}

function buildWatchTargetEditor(item) {
  const isNew = !item || item.id === 'new';
  const target = item || { id: 'new', mode: currentMode, direction: 'fall_to', price: '', note: '', enabled: true };
  const id = isNew ? 'new' : target.id;
  const mode = target.mode || currentMode;
  const direction = target.direction || 'fall_to';
  const price = target.price == null ? '' : String(target.price);
  const note = target.note || '';
  const enabledChecked = target.enabled === false ? '' : ' checked';
  return [
    '<div class="watch-target-editor">',
    '<div class="watch-target-fields">',
    '<div class="watch-target-field">',
    '<label for="watchTargetMode_' + escapeHtml(id) + '">单位</label>',
    '<select id="watchTargetMode_' + escapeHtml(id) + '">',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="watch-target-field">',
    '<label for="watchTargetDirection_' + escapeHtml(id) + '">方向</label>',
    '<select id="watchTargetDirection_' + escapeHtml(id) + '">',
    '<option value="fall_to"' + (direction === 'fall_to' ? ' selected' : '') + '>下跌至</option>',
    '<option value="rise_to"' + (direction === 'rise_to' ? ' selected' : '') + '>上涨至</option>',
    '</select>',
    '</div>',
    '<div class="watch-target-field">',
    '<label for="watchTargetPrice_' + escapeHtml(id) + '">目标价</label>',
    '<input id="watchTargetPrice_' + escapeHtml(id) + '" type="number" step="0.01" value="' + escapeHtml(price) + '" placeholder="输入价格">',
    '</div>',
    '<div class="watch-target-field watch-target-note">',
    '<label for="watchTargetNote_' + escapeHtml(id) + '">备注</label>',
    '<input id="watchTargetNote_' + escapeHtml(id) + '" type="text" maxlength="200" value="' + escapeHtml(note) + '" placeholder="例如 预算观察价">',
    '</div>',
    '</div>',
    '<div class="alert-rule-mail">',
    '<span>启用观察</span>',
    '<label class="switch switch-sm"><input type="checkbox" id="watchTargetEnabled_' + escapeHtml(id) + '"' + enabledChecked + '><span class="slider"></span></label>',
    '</div>',
    '<div class="watch-target-editor-actions">',
    '<button class="btn-set" type="button" onclick="saveWatchTarget(\'' + escapeHtml(id) + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveWatchTarget(\'' + escapeHtml(id) + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderWatchTargets() {
  const box = document.getElementById('watchTargetList');
  if (!box) return;
  const items = [...watchTargets];
  const parts = [];
  if (activeWatchTargetId === 'new') {
    parts.push([
      '<div class="watch-target-item expanded">',
      '<div class="watch-target-main">',
      '<div class="watch-target-line">新增目标价</div>',
      '<div class="watch-target-meta">保存后开始观察</div>',
      '</div>',
      '<div class="watch-target-actions"><span class="alert-rule-state off">新建</span></div>',
      buildWatchTargetEditor({ id: 'new', mode: currentMode, direction: 'fall_to', price: '', note: '', enabled: true }),
      '</div>',
    ].join(''));
  }
  if (!items.length && activeWatchTargetId !== 'new') {
    parts.push('<div class="watch-target-empty">暂无目标价观察</div>');
  }
  parts.push(...items.map(item => {
    const cls = [
      'watch-target-item',
      activeWatchTargetId === item.id ? 'expanded' : '',
      item.triggered ? 'triggered' : '',
      item.enabled === false ? 'disabled' : '',
    ].filter(Boolean).join(' ');
    const triggerInfo = item.triggered && item.triggered_at
      ? ' · 触发 ' + String(item.triggered_at).replace('T', ' ')
      : '';
    const note = item.note ? ' · ' + item.note : '';
    return [
      '<div class="' + cls + '">',
      '<div class="watch-target-main">',
      '<div class="watch-target-line">' + escapeHtml(watchTargetDirectionLabel(item.direction)) + ' ' + escapeHtml(watchTargetPrice(item.price, item.mode)) + '</div>',
      '<div class="watch-target-meta">' + escapeHtml(watchTargetModeLabel(item.mode) + triggerInfo + note) + '</div>',
      '</div>',
      '<div class="watch-target-actions">',
      '<span class="alert-rule-state ' + watchTargetStateClass(item) + '">' + escapeHtml(watchTargetStateLabel(item)) + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="setActiveWatchTarget(\'' + escapeHtml(item.id) + '\')">编辑</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="toggleWatchTarget(\'' + escapeHtml(item.id) + '\', ' + (item.enabled === false ? 'true' : 'false') + ')">' + (item.enabled === false ? '启用' : '停用') + '</button>',
      item.triggered ? '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="resetWatchTarget(\'' + escapeHtml(item.id) + '\')">重置</button>' : '',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="deleteWatchTarget(\'' + escapeHtml(item.id) + '\')">删除</button>',
      '</div>',
      activeWatchTargetId === item.id ? buildWatchTargetEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function watchTargetInputValue(id, field) {
  const el = document.getElementById('watchTarget' + field + '_' + id);
  return el ? el.value : '';
}

function saveWatchTarget(id) {
  const isNew = id === 'new';
  const payload = {
    mode: watchTargetInputValue(id, 'Mode'),
    direction: watchTargetInputValue(id, 'Direction'),
    price: watchTargetInputValue(id, 'Price'),
    note: watchTargetInputValue(id, 'Note'),
    enabled: !!document.getElementById('watchTargetEnabled_' + id)?.checked,
  };
  if (!isNew) payload.id = id;
  const price = Number(payload.price);
  if (!Number.isFinite(price) || price <= 0) {
    setWatchTargetStatus('请输入有效的目标价格。', 'fail');
    return;
  }
  setWatchTargetStatus('正在保存观察项...', '');
  socket.emit('set_watch_target', payload);
  activeWatchTargetId = null;
}

function deleteWatchTarget(id) {
  setWatchTargetStatus('正在删除观察项...', '');
  socket.emit('delete_watch_target', { id });
  if (activeWatchTargetId === id) activeWatchTargetId = null;
}

function toggleWatchTarget(id, enabled) {
  setWatchTargetStatus(enabled ? '正在启用观察项...' : '正在停用观察项...', '');
  socket.emit('toggle_watch_target', { id, enabled });
}

function resetWatchTarget(id) {
  setWatchTargetStatus('正在重置触发状态...', '');
  socket.emit('reset_watch_target', { id });
}

function normalizePortfolioSummary(summary) {
  const base = {
    count: 0,
    valued: 0,
    cost: 0,
    cost_basis: 0,
    market_value: 0,
    pnl: 0,
    pnl_percent: 0,
    unrealized_pnl: 0,
    unrealized_pnl_percent: 0,
    realized_pnl: 0,
    total_pnl: 0,
    fees: 0,
    quantity: 0,
  };
  const source = summary && typeof summary === 'object' ? summary : {};
  return Object.keys(base).reduce((acc, key) => {
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
}

function normalizePortfolioReviewPoint(point) {
  const base = {
    trade_count: 0,
    buy_amount: 0,
    sell_amount: 0,
    fee: 0,
    realized_pnl: 0,
    cumulative_buy_amount: 0,
    cumulative_sell_amount: 0,
    cumulative_fee: 0,
    cumulative_realized_pnl: 0,
    net_invested: 0,
    quantity: 0,
    cost_basis: 0,
  };
  const source = point && typeof point === 'object' ? point : {};
  const normalized = Object.keys(base).reduce((acc, key) => {
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
  normalized.date = source.date || '';
  return normalized;
}

function normalizePortfolioReviewSummary(summary, mode) {
  const base = {
    mode,
    trade_count: 0,
    buy_count: 0,
    sell_count: 0,
    buy_amount: 0,
    sell_amount: 0,
    fee_total: 0,
    realized_pnl: 0,
    net_invested: 0,
    current_quantity: 0,
    cost_basis: 0,
    average_cost: null,
  };
  const source = summary && typeof summary === 'object' ? summary : {};
  const normalized = Object.keys(base).reduce((acc, key) => {
    if (key === 'mode') {
      acc.mode = source.mode === 'usd' ? 'usd' : mode;
      return acc;
    }
    const value = source[key];
    acc[key] = value == null || value === '' || !Number.isFinite(Number(value)) ? base[key] : Number(value);
    return acc;
  }, {});
  normalized.first_trade_date = source.first_trade_date || '';
  normalized.last_trade_date = source.last_trade_date || '';
  normalized.points = Array.isArray(source.points) ? source.points.map(normalizePortfolioReviewPoint) : [];
  return normalized;
}

function normalizePortfolioReview(review) {
  const source = review && typeof review === 'object' && !Array.isArray(review) ? review : {};
  return {
    rmb: normalizePortfolioReviewSummary(source.rmb, 'rmb'),
    usd: normalizePortfolioReviewSummary(source.usd, 'usd'),
  };
}

function normalizePortfolioAlert(alert) {
  const source = alert && typeof alert === 'object' && !Array.isArray(alert) ? alert : {};
  const triggered = source.triggered && typeof source.triggered === 'object' && !Array.isArray(source.triggered) ? source.triggered : {};
  return {
    id: source.id || '',
    position_id: source.position_id || '',
    enabled: source.enabled !== false,
    take_profit_price: source.take_profit_price == null ? '' : String(source.take_profit_price),
    stop_loss_price: source.stop_loss_price == null ? '' : String(source.stop_loss_price),
    profit_percent: source.profit_percent == null ? '' : String(source.profit_percent),
    loss_percent: source.loss_percent == null ? '' : String(source.loss_percent),
    near_cost_percent: source.near_cost_percent == null ? '' : String(source.near_cost_percent),
    note: source.note || '',
    status: source.status || '',
    triggered: {
      take_profit: !!triggered.take_profit,
      stop_loss: !!triggered.stop_loss,
      profit_percent: !!triggered.profit_percent,
      loss_percent: !!triggered.loss_percent,
      near_cost: !!triggered.near_cost,
    },
    last_triggered_at: source.last_triggered_at || '',
    last_trigger_price: source.last_trigger_price == null ? '' : String(source.last_trigger_price),
    last_trigger_condition: source.last_trigger_condition || '',
  };
}

function normalizePortfolioAlertsState(alerts) {
  const source = alerts && typeof alerts === 'object' && !Array.isArray(alerts) ? alerts : {};
  const items = Array.isArray(source.items) ? source.items.map(normalizePortfolioAlert).filter(item => item.position_id) : [];
  return {
    items,
    total: Number.isFinite(Number(source.total)) ? Number(source.total) : items.length,
    enabled: Number.isFinite(Number(source.enabled)) ? Number(source.enabled) : 0,
    triggered: Number.isFinite(Number(source.triggered)) ? Number(source.triggered) : 0,
  };
}

function normalizePortfolioImportBackup(data) {
  const source = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  return {
    available: source.available === true,
    kind: source.kind || 'transactions',
    batch_id: source.batch_id || '',
    imported_at: source.imported_at || '',
    count: Number.isFinite(Number(source.count)) ? Number(source.count) : 0,
    create: Number.isFinite(Number(source.create)) ? Number(source.create) : 0,
    overwrite: Number.isFinite(Number(source.overwrite)) ? Number(source.overwrite) : 0,
  };
}

function normalizePortfolioState(data) {
  const source = data && typeof data === 'object' && !Array.isArray(data) ? data : {};
  const items = Array.isArray(source.items)
    ? source.items.map(item => (item && typeof item === 'object') ? Object.assign({}, item) : null).filter(Boolean)
    : [];
  const transactions = Array.isArray(source.transactions)
    ? source.transactions.map(item => (item && typeof item === 'object') ? Object.assign({}, item) : null).filter(Boolean)
    : [];
  return {
    items,
    transactions,
    total: Number.isFinite(Number(source.total)) ? Number(source.total) : items.length,
    rmb_summary: normalizePortfolioSummary(source.rmb_summary),
    usd_summary: normalizePortfolioSummary(source.usd_summary),
    prices: source.prices && typeof source.prices === 'object' && !Array.isArray(source.prices) ? Object.assign({}, source.prices) : {},
    review: normalizePortfolioReview(source.review),
    alerts: normalizePortfolioAlertsState(source.alerts),
    import_backup: normalizePortfolioImportBackup(source.import_backup),
  };
}

function applyPortfolio(data) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  captureActivePortfolioAlertDraft();
  portfolioState = normalizePortfolioState(data);
  if (activePortfolioPositionId && activePortfolioPositionId !== 'new' && !portfolioState.items.some(item => item.id === activePortfolioPositionId)) {
    clearPortfolioDraft(activePortfolioPositionId);
    activePortfolioPositionId = null;
  }
  if (activePortfolioDetailId && !portfolioState.items.some(item => item.id === activePortfolioDetailId)) {
    activePortfolioDetailId = null;
  }
  if (activePortfolioAlertEditorId && !portfolioState.items.some(item => item.id === activePortfolioAlertEditorId)) {
    activePortfolioAlertEditorId = null;
  }
  if (activePortfolioTransactionId && activePortfolioTransactionId !== 'new' && !portfolioState.transactions.some(item => item.id === activePortfolioTransactionId)) {
    clearPortfolioTransactionDraft(activePortfolioTransactionId);
    activePortfolioTransactionId = null;
  }
  if (pendingPortfolioSave) {
    if (pendingPortfolioSave.kind === 'transaction') {
      clearPortfolioTransactionDraft(pendingPortfolioSave.id);
      if (activePortfolioTransactionId === pendingPortfolioSave.id) activePortfolioTransactionId = null;
    } else if (pendingPortfolioSave.kind === 'alert') {
      clearPortfolioAlertDraft(pendingPortfolioSave.id);
    } else if (pendingPortfolioSave.kind === 'position') {
      clearPortfolioDraft(pendingPortfolioSave.id);
      if (activePortfolioPositionId === pendingPortfolioSave.id) activePortfolioPositionId = null;
    }
    pendingPortfolioSave = null;
  }
  renderPortfolio();
  if (activeUnifiedAlertRuleId && alertRuleDraft && alertRuleDraft.kind === 'portfolio') {
    renderAlertRuleCenter();
  }
}

function setPortfolioStatus(message, type) {
  const status = document.getElementById('portfolioStatus');
  if (!status) return;
  status.textContent = message || '';
  status.className = 'portfolio-status' + (type ? ' ' + type : '');
}

function portfolioModeLabel(mode) {
  return mode === 'usd' ? 'USD/oz' : 'RMB/克';
}

function portfolioCurrency(mode) {
  return mode === 'usd' ? '$' : '¥';
}

function portfolioQuantityUnit(mode) {
  return mode === 'usd' ? 'oz' : '克';
}

function formatPortfolioNumber(value, digits) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const places = Number.isFinite(Number(digits)) ? Math.max(0, Number(digits)) : 2;
  return number.toLocaleString('en-US', { minimumFractionDigits: places, maximumFractionDigits: places });
}

function formatPortfolioMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  return portfolioCurrency(mode) + formatPortfolioNumber(number, 2);
}

function formatPortfolioSignedMoney(value, mode) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const prefix = number > 0 ? '+' : number < 0 ? '-' : '';
  return prefix + portfolioCurrency(mode) + formatPortfolioNumber(Math.abs(number), 2);
}

function formatPortfolioPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  const prefix = number > 0 ? '+' : '';
  return prefix + formatPortfolioNumber(number, 2) + '%';
}

function portfolioPnlClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return '';
  return number > 0 ? 'up' : 'down';
}

function portfolioStatusLabel(status) {
  return ({
    profit: '盈利',
    loss: '亏损',
    near_cost: '接近成本',
    target_hit: '触发预警',
    waiting_price: '等待行情',
    closed: '清仓',
    invalid_position: '需修正',
    valued: '已估值',
  })[status] || '未分类';
}

function portfolioStatusClass(status) {
  if (status === 'profit') return 'on';
  if (status === 'loss' || status === 'target_hit') return 'warn';
  return 'off';
}

function portfolioValuationLabel(item) {
  if (!item || item.valuation_status === 'invalid_position' || item.quantity == null) {
    return '持仓数据需修正';
  }
  if (item.valuation_status === 'closed') {
    return '已清仓';
  }
  if (item.valuation_status === 'waiting_price' || item.current_price == null) {
    return '等待行情';
  }
  const mode = item.mode || currentMode;
  return formatPortfolioMoney(item.market_value, mode);
}

function requestPortfolioRefresh() {
  if (!socket.connected) return;
  socket.emit('get_portfolio');
}

function portfolioDraftKey(id) {
  return String(id || 'new');
}

function portfolioBaseDraft(item) {
  const isNew = !item || item.id === 'new';
  const source = item || {};
  return {
    id: isNew ? 'new' : source.id,
    name: source.name || '',
    mode: source.mode || currentMode,
    entry_price: source.entry_price == null ? '' : String(source.entry_price),
    quantity: source.quantity == null ? '' : String(source.quantity),
    entry_date: source.entry_date || '',
    note: source.note || '',
  };
}

function portfolioDraftFor(item) {
  const base = portfolioBaseDraft(item);
  const draft = portfolioDrafts[portfolioDraftKey(base.id)] || {};
  return Object.assign({}, base, draft, { id: base.id });
}

function capturePortfolioDraft(id) {
  const key = portfolioDraftKey(id);
  if (!document.getElementById('portfolioName_' + key)) return;
  portfolioDrafts[key] = {
    name: portfolioInputValue(key, 'Name'),
    mode: portfolioInputValue(key, 'Mode') || currentMode,
    entry_price: portfolioInputValue(key, 'EntryPrice'),
    quantity: portfolioInputValue(key, 'Quantity'),
    entry_date: portfolioInputValue(key, 'EntryDate'),
    note: portfolioInputValue(key, 'Note'),
  };
}

function captureActivePortfolioDraft() {
  if (!activePortfolioPositionId) return;
  capturePortfolioDraft(activePortfolioPositionId);
}

function clearPortfolioDraft(id) {
  delete portfolioDrafts[portfolioDraftKey(id)];
}

function portfolioTransactionDraftKey(id) {
  return String(id || 'new');
}

function portfolioTransactionToday(now) {
  const date = now instanceof Date ? now : new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return year + '-' + month + '-' + day;
}

function defaultPortfolioTransactionPrice(mode) {
  const raw = latestData && mode === 'usd' ? latestData.usd : latestData && latestData.rmb;
  const number = Number(raw);
  return Number.isFinite(number) && number > 0 ? number.toFixed(2) : '';
}

function portfolioTransactionBaseDraft(item) {
  const isNew = !item || item.id === 'new';
  const source = item || {};
  const mode = source.mode || currentMode;
  const defaultPrice = isNew ? defaultPortfolioTransactionPrice(mode) : '';
  return {
    id: isNew ? 'new' : source.id,
    position_id: source.position_id || '',
    name: source.name || '',
    type: source.type || 'buy',
    mode: mode,
    price: source.price == null || (isNew && source.price === '') ? defaultPrice : String(source.price),
    quantity: source.quantity == null ? '' : String(source.quantity),
    fee: source.fee == null ? '0' : String(source.fee),
    trade_date: source.trade_date || (isNew ? portfolioTransactionToday() : ''),
    note: source.note || '',
  };
}

function portfolioTransactionDraftFor(item) {
  const base = portfolioTransactionBaseDraft(item);
  const draft = portfolioTransactionDrafts[portfolioTransactionDraftKey(base.id)] || {};
  return Object.assign({}, base, draft, { id: base.id });
}

function portfolioTransactionInputValue(id, field) {
  const el = document.getElementById('portfolioTransaction' + field + '_' + id);
  return el ? el.value : '';
}

function capturePortfolioTransactionDraft(id) {
  const key = portfolioTransactionDraftKey(id);
  if (!document.getElementById('portfolioTransactionName_' + key)) return;
  portfolioTransactionDrafts[key] = {
    position_id: portfolioTransactionInputValue(key, 'PositionId'),
    name: portfolioTransactionInputValue(key, 'Name'),
    type: portfolioTransactionInputValue(key, 'Type') || 'buy',
    mode: portfolioTransactionInputValue(key, 'Mode') || currentMode,
    price: portfolioTransactionInputValue(key, 'Price'),
    quantity: portfolioTransactionInputValue(key, 'Quantity'),
    fee: portfolioTransactionInputValue(key, 'Fee'),
    trade_date: portfolioTransactionInputValue(key, 'TradeDate'),
    note: portfolioTransactionInputValue(key, 'Note'),
  };
}

function captureActivePortfolioTransactionDraft() {
  if (!activePortfolioTransactionId) return;
  capturePortfolioTransactionDraft(activePortfolioTransactionId);
}

function clearPortfolioTransactionDraft(id) {
  delete portfolioTransactionDrafts[portfolioTransactionDraftKey(id)];
}

function portfolioAlertForPosition(positionId) {
  const alerts = portfolioState.alerts && Array.isArray(portfolioState.alerts.items) ? portfolioState.alerts.items : [];
  return alerts.find(item => item.position_id === positionId) || null;
}

function portfolioAlertDraftKey(positionId) {
  return String(positionId || '');
}

function portfolioAlertBaseDraft(position, alert) {
  const source = alert || {};
  return {
    id: source.id || '',
    position_id: position && position.id ? position.id : source.position_id || '',
    enabled: source.enabled !== false,
    take_profit_price: source.take_profit_price == null ? '' : String(source.take_profit_price || ''),
    stop_loss_price: source.stop_loss_price == null ? '' : String(source.stop_loss_price || ''),
    profit_percent: source.profit_percent == null ? '' : String(source.profit_percent || ''),
    loss_percent: source.loss_percent == null ? '' : String(source.loss_percent || ''),
    near_cost_percent: source.near_cost_percent == null ? '' : String(source.near_cost_percent || ''),
    note: source.note || '',
    status: source.status || 'empty',
  };
}

function portfolioAlertDraftFor(position, alert) {
  const base = portfolioAlertBaseDraft(position, alert);
  const draft = portfolioAlertDrafts[portfolioAlertDraftKey(base.position_id)] || {};
  return Object.assign({}, base, draft, { id: base.id, position_id: base.position_id, status: alert ? alert.status : base.status });
}

function portfolioAlertInputValue(positionId, field) {
  const el = document.getElementById('portfolioAlert' + field + '_' + positionId);
  return el ? el.value : '';
}

function capturePortfolioAlertDraft(positionId) {
  const key = portfolioAlertDraftKey(positionId);
  if (!key || !document.getElementById('portfolioAlertTakeProfit_' + key)) return;
  const existing = portfolioAlertForPosition(key);
  portfolioAlertDrafts[key] = {
    id: existing ? existing.id : '',
    position_id: key,
    enabled: portfolioAlertInputValue(key, 'Enabled') !== 'false',
    take_profit_price: portfolioAlertInputValue(key, 'TakeProfit'),
    stop_loss_price: portfolioAlertInputValue(key, 'StopLoss'),
    profit_percent: portfolioAlertInputValue(key, 'ProfitPercent'),
    loss_percent: portfolioAlertInputValue(key, 'LossPercent'),
    near_cost_percent: portfolioAlertInputValue(key, 'NearCostPercent'),
    note: portfolioAlertInputValue(key, 'Note'),
  };
}

function captureActivePortfolioAlertDraft() {
  if (!activePortfolioDetailId) return;
  capturePortfolioAlertDraft(activePortfolioDetailId);
}

function clearPortfolioAlertDraft(positionId) {
  delete portfolioAlertDrafts[portfolioAlertDraftKey(positionId)];
}

function renderPortfolioSummaryCard(title, mode, summary) {
  const state = normalizePortfolioSummary(summary);
  const valueClass = portfolioPnlClass(state.total_pnl || state.pnl);
  const titleText = title ? title + ' · ' + portfolioModeLabel(mode) : portfolioModeLabel(mode);
  const valueText = state.count === 0
    ? formatPortfolioMoney(0, mode)
    : formatPortfolioMoney(state.total_pnl || state.pnl, mode);
  const costMeta = state.count === 0
    ? '暂无持仓'
    : state.valued === 0
      ? '等待行情'
      : '市值 ' + formatPortfolioMoney(state.market_value, mode) + ' · 成本 ' + formatPortfolioMoney(state.cost_basis || state.cost, mode);
  const countMeta = '未实现 ' + formatPortfolioMoney(state.unrealized_pnl, mode) + ' · 已实现 ' + formatPortfolioMoney(state.realized_pnl, mode);
  return [
    '<div class="portfolio-summary-card">',
    '<div class="portfolio-summary-title">' + escapeHtml(titleText) + '</div>',
    '<div class="portfolio-summary-value ' + valueClass + '">' + escapeHtml(valueText) + '</div>',
    '<div class="portfolio-summary-meta">' + escapeHtml(costMeta) + '</div>',
    '<div class="portfolio-summary-meta ' + valueClass + '">' + escapeHtml(countMeta) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioSummary() {
  const box = document.getElementById('portfolioSummary');
  if (!box) return;
  box.innerHTML = [
    renderPortfolioSummaryCard('人民币持仓', 'rmb', portfolioState.rmb_summary),
    renderPortfolioSummaryCard('美元持仓', 'usd', portfolioState.usd_summary),
  ].join('');
}

function renderPortfolioTabs() {
  const box = document.getElementById('portfolioViewTabs');
  if (!box) return;
  Array.from(box.querySelectorAll('.portfolio-tab')).forEach(button => {
    const target = button.getAttribute('onclick') || '';
    const isActive = target.indexOf("'" + portfolioView + "'") >= 0;
    button.classList.toggle('active', isActive);
  });
}

function rightPanelMenuForButton(button) {
  if (!button || !button.closest) return null;
  if (button.id === 'portfolioToolsMoreButton') return document.getElementById('portfolioToolsMenu');
  if (button.id === 'alertLogMoreButton') return document.getElementById('alertLogMenu');
  const portfolioSelect = button.closest('.portfolio-select-wrap');
  if (portfolioSelect) return portfolioSelect.querySelector('.portfolio-select-menu');
  const sourceActions = button.closest('.source-health-actions');
  if (sourceActions) return sourceActions.querySelector('#sourceHealthMenu');
  const logActions = button.closest('.log-actions');
  if (logActions) return logActions.querySelector('.log-entry-menu');
  const portfolioDetailActions = button.closest('.portfolio-detail-actions');
  if (portfolioDetailActions) return portfolioDetailActions.querySelector('.portfolio-detail-action-menu');
  return null;
}

function closeRightPanelMenus(exceptMenu) {
  const menus = [
    document.getElementById('portfolioToolsMenu'),
    document.getElementById('sourceHealthMenu'),
    document.getElementById('alertLogMenu'),
    ...document.querySelectorAll('.portfolio-select-menu'),
    ...document.querySelectorAll('.log-entry-menu'),
    ...document.querySelectorAll('.portfolio-detail-action-menu'),
  ].filter(Boolean);
  menus.forEach(menu => {
    if (menu !== exceptMenu) menu.hidden = true;
  });
  document.querySelectorAll('#portfolioToolsMoreButton, #alertLogMoreButton, .portfolio-select-trigger, .source-health-action-trigger, .log-action-trigger, .portfolio-detail-action-trigger').forEach(button => {
    const controlledMenu = rightPanelMenuForButton(button);
    if (controlledMenu !== exceptMenu) button.setAttribute('aria-expanded', 'false');
  });
}

function isRightPanelMenuEventTarget(target) {
  return !!(target && target.closest && target.closest([
    '#portfolioToolsMoreButton',
    '#portfolioToolsMenu',
    '#alertLogMoreButton',
    '#alertLogMenu',
    '.portfolio-select-wrap',
    '.source-health-actions',
    '#sourceHealthMenu',
    '.log-actions',
    '.portfolio-detail-actions',
  ].join(', ')));
}

function closeRightPanelMenusOnOutsideClick(event) {
  if (isRightPanelMenuEventTarget(event.target)) return;
  closeRightPanelMenus();
}

document.addEventListener('click', closeRightPanelMenusOnOutsideClick);

function togglePortfolioToolsMenu() {
  const menu = document.getElementById('portfolioToolsMenu');
  const button = document.getElementById('portfolioToolsMoreButton');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}

function togglePortfolioDetailActionMenu(button) {
  const actions = button && button.closest ? button.closest('.portfolio-detail-actions') : null;
  const menu = actions ? actions.querySelector('.portfolio-detail-action-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function setPortfolioSearch(value) {
  portfolioSearch = String(value || '').trim();
  renderPortfolio();
}

const PORTFOLIO_POSITION_FILTER_OPTIONS = [
  { value: 'all', label: '全部持仓' },
  { value: 'rmb', label: '人民币' },
  { value: 'usd', label: '美元' },
  { value: 'profit', label: '盈利' },
  { value: 'loss', label: '亏损' },
  { value: 'near_cost', label: '接近成本' },
  { value: 'target_hit', label: '触发预警' },
  { value: 'valued', label: '已估值' },
  { value: 'waiting_price', label: '等待行情' },
  { value: 'closed', label: '清仓' },
];
const PORTFOLIO_POSITION_SORT_OPTIONS = [
  { value: 'recent', label: '最近交易' },
  { value: 'market_value', label: '市值' },
  { value: 'total_pnl', label: '总盈亏' },
  { value: 'unrealized_pnl', label: '未实现盈亏' },
  { value: 'quantity', label: '数量' },
  { value: 'name', label: '名称' },
];
const PORTFOLIO_TRANSACTION_TYPE_OPTIONS = [
  { value: 'all', label: '全部类型' },
  { value: 'buy', label: '买入' },
  { value: 'sell', label: '卖出' },
];
const PORTFOLIO_TRANSACTION_MODE_OPTIONS = [
  { value: 'all', label: '全部单位' },
  { value: 'rmb', label: 'RMB/克' },
  { value: 'usd', label: 'USD/oz' },
];
const PORTFOLIO_TRANSACTION_SORT_OPTIONS = [
  { value: 'date_desc', label: '交易日期倒序' },
  { value: 'date_asc', label: '交易日期正序' },
  { value: 'amount_desc', label: '成交金额优先' },
  { value: 'realized_desc', label: '已实现优先' },
  { value: 'name', label: '名称' },
];

function portfolioOptionValue(options, value, fallback) {
  return options.some(option => option.value === value) ? value : fallback;
}

function setPortfolioPositionFilter(value) {
  portfolioPositionFilter = portfolioOptionValue(PORTFOLIO_POSITION_FILTER_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioPositionSort(value) {
  portfolioPositionSort = portfolioOptionValue(PORTFOLIO_POSITION_SORT_OPTIONS, value, 'recent');
  renderPortfolio();
}

function setPortfolioTransactionTypeFilter(value) {
  portfolioTransactionTypeFilter = portfolioOptionValue(PORTFOLIO_TRANSACTION_TYPE_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioTransactionModeFilter(value) {
  portfolioTransactionModeFilter = portfolioOptionValue(PORTFOLIO_TRANSACTION_MODE_OPTIONS, value, 'all');
  renderPortfolio();
}

function setPortfolioTransactionSort(value) {
  portfolioTransactionSort = portfolioOptionValue(PORTFOLIO_TRANSACTION_SORT_OPTIONS, value, 'date_desc');
  renderPortfolio();
}

function escapeJsString(value) {
  return String(value ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\r/g, '\\r').replace(/\n/g, '\\n');
}

function togglePortfolioControlMenu(button) {
  const wrap = button && button.closest ? button.closest('.portfolio-select-wrap') : null;
  const menu = wrap ? wrap.querySelector('.portfolio-select-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function setPortfolioControlSelection(action, value) {
  closeRightPanelMenus();
  const handlers = {
    positionFilter: setPortfolioPositionFilter,
    positionSort: setPortfolioPositionSort,
    transactionType: setPortfolioTransactionTypeFilter,
    transactionMode: setPortfolioTransactionModeFilter,
    transactionSort: setPortfolioTransactionSort,
  };
  if (handlers[action]) handlers[action](value);
}

function renderPortfolioDropdownControl(className, label, current, options, action) {
  const selected = options.find(option => option.value === current) || options[0];
  const optionButtons = options.map(option => {
    const active = option.value === current;
    return [
      '<button class="portfolio-select-option' + (active ? ' active' : '') + '" type="button" data-value="' + escapeHtml(option.value) + '" aria-pressed="' + String(active) + '" onclick="setPortfolioControlSelection(\'' + escapeJsString(action) + '\', \'' + escapeJsString(option.value) + '\')">',
      escapeHtml(option.label),
      '</button>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-control ' + escapeHtml(className) + ' portfolio-select-control">',
    '<span>' + escapeHtml(label) + '</span>',
    '<div class="portfolio-select-wrap">',
    '<button class="portfolio-select-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="togglePortfolioControlMenu(this)">',
    '<span class="portfolio-select-value">' + escapeHtml(selected.label) + '</span>',
    '<span class="portfolio-select-arrow" aria-hidden="true"></span>',
    '</button>',
    '<div class="portfolio-select-menu" hidden>',
    optionButtons,
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioControls() {
  const box = document.getElementById('portfolioControls');
  if (!box) return;
  if (portfolioView === 'review') {
    box.innerHTML = [
      '<div class="portfolio-controls-note">交易复盘基于全部流水；持仓总收益按所选历史行情重估</div>',
      '<div class="portfolio-analytics-ranges">',
      [30, 90, 365].map(days => '<button class="btn-clear-sm' + (portfolioAnalyticsRange === days ? ' active' : '') + '" type="button" onclick="setPortfolioAnalyticsRange(' + days + ')">' + days + ' 日</button>').join(''),
      '<button class="btn-clear-sm" type="button" onclick="requestPortfolioAnalytics(true)">刷新</button>',
      '</div>',
    ].join('');
    return;
  }
  const search = [
    '<label class="portfolio-control portfolio-search">',
    '<span>搜索</span>',
    '<input type="search" value="' + escapeHtml(portfolioSearch) + '" placeholder="名称、备注、日期" oninput="setPortfolioSearch(this.value)">',
    '</label>',
  ].join('');
  if (portfolioView === 'transactions') {
    box.innerHTML = [
      search,
      renderPortfolioDropdownControl('portfolio-filter', '类型', portfolioTransactionTypeFilter, PORTFOLIO_TRANSACTION_TYPE_OPTIONS, 'transactionType'),
      renderPortfolioDropdownControl('portfolio-filter', '单位', portfolioTransactionModeFilter, PORTFOLIO_TRANSACTION_MODE_OPTIONS, 'transactionMode'),
      renderPortfolioDropdownControl('portfolio-sort', '排序', portfolioTransactionSort, PORTFOLIO_TRANSACTION_SORT_OPTIONS, 'transactionSort'),
    ].join('');
    return;
  }
  box.innerHTML = [
    search,
    renderPortfolioDropdownControl('portfolio-filter', '筛选', portfolioPositionFilter, PORTFOLIO_POSITION_FILTER_OPTIONS, 'positionFilter'),
    renderPortfolioDropdownControl('portfolio-sort', '排序', portfolioPositionSort, PORTFOLIO_POSITION_SORT_OPTIONS, 'positionSort'),
  ].join('');
}

function requestPortfolioAnalytics(force) {
  if (portfolioAnalyticsLoading) return;
  if (!force && portfolioAnalyticsState && Number(portfolioAnalyticsState.range_days) === portfolioAnalyticsRange) return;
  portfolioAnalyticsLoading = true;
  socket.emit('get_portfolio_analytics', { days: portfolioAnalyticsRange });
  if (portfolioView === 'review') renderPortfolio();
}

function setPortfolioAnalyticsRange(days) {
  const next = [30, 90, 365].includes(Number(days)) ? Number(days) : 90;
  if (portfolioAnalyticsRange === next && portfolioAnalyticsState) return;
  portfolioAnalyticsRange = next;
  portfolioAnalyticsState = null;
  renderPortfolio();
  requestPortfolioAnalytics(true);
}

function portfolioSearchMatches(textParts) {
  const query = portfolioSearch.trim().toLowerCase();
  if (!query) return true;
  return textParts.filter(Boolean).join(' ').toLowerCase().includes(query);
}

function portfolioSortableNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NEGATIVE_INFINITY;
}

function portfolioSortableDate(value) {
  return String(value || '');
}

function filteredPortfolioPositions() {
  const items = Array.isArray(portfolioState.items) ? portfolioState.items.slice() : [];
  const filtered = items.filter(item => {
    const mode = item.mode || 'rmb';
    const pnl = Number(item.total_pnl != null ? item.total_pnl : item.pnl);
    const portfolioStatus = item.portfolio_status || item.valuation_status || '';
    const valuationStatus = item.valuation_status || '';
    const matchesFilter = portfolioPositionFilter === 'all'
      || portfolioPositionFilter === mode
      || portfolioPositionFilter === portfolioStatus
      || portfolioPositionFilter === valuationStatus
      || (portfolioPositionFilter === 'profit' && Number.isFinite(pnl) && pnl > 0)
      || (portfolioPositionFilter === 'loss' && Number.isFinite(pnl) && pnl < 0);
    if (!matchesFilter) return false;
    return portfolioSearchMatches([
      item.id,
      item.name,
      item.note,
      portfolioModeLabel(mode),
      portfolioStatusLabel(portfolioStatus),
      portfolioValuationLabel(item),
      item.last_trade_date,
      item.entry_date,
    ]);
  });
  filtered.sort((left, right) => {
    if (portfolioPositionSort === 'name') return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
    if (portfolioPositionSort === 'market_value') return portfolioSortableNumber(right.market_value) - portfolioSortableNumber(left.market_value);
    if (portfolioPositionSort === 'total_pnl') {
      const rightPnl = right.total_pnl != null ? right.total_pnl : right.pnl;
      const leftPnl = left.total_pnl != null ? left.total_pnl : left.pnl;
      return portfolioSortableNumber(rightPnl) - portfolioSortableNumber(leftPnl);
    }
    if (portfolioPositionSort === 'unrealized_pnl') return portfolioSortableNumber(right.unrealized_pnl) - portfolioSortableNumber(left.unrealized_pnl);
    if (portfolioPositionSort === 'quantity') return portfolioSortableNumber(right.quantity) - portfolioSortableNumber(left.quantity);
    const dateCompare = portfolioSortableDate(right.last_trade_date || right.entry_date).localeCompare(portfolioSortableDate(left.last_trade_date || left.entry_date));
    return dateCompare || String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
  });
  return filtered;
}

function filteredPortfolioTransactions() {
  const transactions = Array.isArray(portfolioState.transactions) ? portfolioState.transactions.slice() : [];
  const filtered = transactions.filter(item => {
    const type = item.type === 'sell' ? 'sell' : 'buy';
    const mode = item.mode || 'rmb';
    if (portfolioTransactionTypeFilter !== 'all' && portfolioTransactionTypeFilter !== type) return false;
    if (portfolioTransactionModeFilter !== 'all' && portfolioTransactionModeFilter !== mode) return false;
    return portfolioSearchMatches([
      item.id,
      item.position_id,
      item.name,
      item.note,
      item.trade_date,
      type === 'sell' ? '卖出' : '买入',
      portfolioModeLabel(mode),
    ]);
  });
  filtered.sort((left, right) => {
    if (portfolioTransactionSort === 'name') return String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
    if (portfolioTransactionSort === 'date_asc') {
      return portfolioSortableDate(left.trade_date).localeCompare(portfolioSortableDate(right.trade_date)) || String(left.id || '').localeCompare(String(right.id || ''));
    }
    if (portfolioTransactionSort === 'amount_desc') {
      const rightAmount = (Number(right.price) || 0) * (Number(right.quantity) || 0) + (Number(right.fee) || 0);
      const leftAmount = (Number(left.price) || 0) * (Number(left.quantity) || 0) + (Number(left.fee) || 0);
      return rightAmount - leftAmount;
    }
    if (portfolioTransactionSort === 'realized_desc') return portfolioSortableNumber(right.realized_pnl) - portfolioSortableNumber(left.realized_pnl);
    return portfolioSortableDate(right.trade_date).localeCompare(portfolioSortableDate(left.trade_date)) || String(right.id || '').localeCompare(String(left.id || ''));
  });
  return filtered;
}

function buildPortfolioEditor(item) {
  const target = portfolioDraftFor(item);
  const id = target.id;
  const escapedId = escapeHtml(id);
  const draftInputAttr = ' oninput="capturePortfolioDraft(\'' + escapedId + '\')"';
  const draftChangeAttr = ' onchange="capturePortfolioDraft(\'' + escapedId + '\')"';
  const modeChangeAttr = ' onchange="capturePortfolioDraft(\'' + escapedId + '\'); renderPortfolio()"';
  const mode = target.mode || currentMode;
  const name = target.name || '';
  const entryPrice = target.entry_price == null ? '' : String(target.entry_price);
  const quantity = target.quantity == null ? '' : String(target.quantity);
  const entryDate = target.entry_date || '';
  const note = target.note || '';
  return [
    '<div class="portfolio-editor">',
    '<div class="portfolio-fields">',
    '<div class="portfolio-field portfolio-name">',
    '<label for="portfolioName_' + escapedId + '">名称</label>',
    '<input id="portfolioName_' + escapedId + '" type="text" maxlength="60" value="' + escapeHtml(name) + '" placeholder="例如 金条"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioMode_' + escapedId + '">单位</label>',
    '<select id="portfolioMode_' + escapedId + '"' + modeChangeAttr + '>',
    '<option value="rmb"' + (mode === 'rmb' ? ' selected' : '') + '>RMB/克</option>',
    '<option value="usd"' + (mode === 'usd' ? ' selected' : '') + '>USD/oz</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryPrice_' + escapedId + '">买入价</label>',
    '<input id="portfolioEntryPrice_' + escapedId + '" type="number" step="0.01" value="' + escapeHtml(entryPrice) + '" placeholder="输入价格"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioQuantity_' + escapedId + '">数量（' + escapeHtml(portfolioQuantityUnit(mode)) + '）</label>',
    '<input id="portfolioQuantity_' + escapedId + '" type="number" step="0.0001" value="' + escapeHtml(quantity) + '" placeholder="输入数量"' + draftInputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioEntryDate_' + escapedId + '">买入日期</label>',
    '<input id="portfolioEntryDate_' + escapedId + '" type="date" value="' + escapeHtml(entryDate) + '"' + draftChangeAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioNote_' + escapedId + '">备注</label>',
    '<textarea id="portfolioNote_' + escapedId + '" maxlength="200" rows="2" placeholder="例如 账户或来源"' + draftInputAttr + '>' + escapeHtml(note) + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-editor-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioPosition(\'' + escapedId + '\')">保存</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActivePortfolioPosition(\'' + escapedId + '\')">取消</button>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolio() {
  const detailItem = activePortfolioDetailItem();
  renderPortfolioHeaderChrome(detailItem);
  renderPortfolioSummary();
  renderPortfolioTabs();
  renderPortfolioControls();
  renderPortfolioImportBackup();
  const box = document.getElementById('portfolioList');
  if (!box) return;
  if (detailItem) {
    box.innerHTML = renderPortfolioPositionDetail(detailItem);
    return;
  }
  if (portfolioView === 'review') {
    renderPortfolioReview(box);
    return;
  }
  if (portfolioView === 'transactions') {
    renderPortfolioTransactions(box);
    return;
  }
  renderPortfolioPositions(box);
}

function activePortfolioDetailItem() {
  if (!activePortfolioDetailId) return null;
  return (portfolioState.items || []).find(item => item && item.id === activePortfolioDetailId) || null;
}

function closePortfolioDetail() {
  captureActivePortfolioAlertDraft();
  activePortfolioDetailId = null;
  activePortfolioAlertEditorId = null;
  portfolioDetailView = 'review';
  renderPortfolio();
}

function renderPortfolioHeaderChrome(detailItem) {
  const card = document.querySelector('.portfolio-card');
  if (!card) return;
  card.classList.toggle('portfolio-detail-mode', !!detailItem);
  const title = card.querySelector('.portfolio-head h3');
  if (title) title.textContent = detailItem ? '持仓详情 · 复盘' : '持仓';
  const primary = card.querySelector('.portfolio-primary-action');
  if (!primary) return;
  if (detailItem) {
    primary.textContent = '返回列表';
    primary.onclick = closePortfolioDetail;
  } else {
    primary.textContent = '新增流水';
    primary.onclick = () => setActivePortfolioTransaction('new');
  }
}

function portfolioReviewDateLabel(value) {
  return value && value !== '未标日期' ? value : '未标日期';
}

function renderPortfolioReviewMetric(label, value, extraClass) {
  return [
    '<div class="portfolio-review-metric">',
    '<div class="portfolio-review-metric-label">' + escapeHtml(label) + '</div>',
    '<div class="portfolio-review-metric-value ' + (extraClass || '') + '">' + escapeHtml(value) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewCard(mode, summary) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  const pnlClass = portfolioPnlClass(state.realized_pnl);
  const title = mode === 'usd' ? '美元复盘' : '人民币复盘';
  const dateText = state.trade_count ? '最近 ' + portfolioReviewDateLabel(state.last_trade_date) : '暂无交易';
  const quantityText = formatPortfolioNumber(state.current_quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode);
  const meta = state.trade_count
    ? state.trade_count + ' 笔 · 买入 ' + formatPortfolioMoney(state.buy_amount, mode) + ' · 卖出 ' + formatPortfolioMoney(state.sell_amount, mode)
    : '暂无流水';
  return [
    '<div class="portfolio-review-card">',
    '<div class="portfolio-review-title">' + escapeHtml(title + ' · ' + portfolioModeLabel(mode)) + '</div>',
    '<div class="portfolio-review-value">' + escapeHtml(formatPortfolioMoney(state.net_invested, mode)) + '</div>',
    '<div class="portfolio-review-meta">' + escapeHtml(meta) + '</div>',
    '<div class="portfolio-review-meta">' + escapeHtml(dateText) + '</div>',
    '<div class="portfolio-review-metrics">',
    renderPortfolioReviewMetric('已实现', formatPortfolioSignedMoney(state.realized_pnl, mode), pnlClass),
    renderPortfolioReviewMetric('手续费', formatPortfolioMoney(state.fee_total, mode), ''),
    renderPortfolioReviewMetric('持有数量', quantityText, ''),
    renderPortfolioReviewMetric('剩余成本', formatPortfolioMoney(state.cost_basis, mode), ''),
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewPoint(mode, point, maxNetInvested) {
  const item = normalizePortfolioReviewPoint(point);
  const ratio = maxNetInvested > 0 ? Math.min(100, Math.max(0, Math.abs(item.net_invested) / maxNetInvested * 100)) : 0;
  const pnlClass = portfolioPnlClass(item.cumulative_realized_pnl);
  return [
    '<div class="portfolio-review-point">',
    '<div class="portfolio-review-point-main">',
    '<div class="portfolio-review-point-date">' + escapeHtml(portfolioReviewDateLabel(item.date)) + '</div>',
    '<div class="portfolio-review-point-meta">' + escapeHtml(item.trade_count + ' 笔 · 当日买入 ' + formatPortfolioMoney(item.buy_amount, mode) + ' · 当日卖出 ' + formatPortfolioMoney(item.sell_amount, mode)) + '</div>',
    '</div>',
    '<div class="portfolio-review-point-side">',
    '<div class="portfolio-review-track"><span style="width:' + ratio.toFixed(2) + '%"></span></div>',
    '<div class="portfolio-review-point-meta">净投入 ' + escapeHtml(formatPortfolioMoney(item.net_invested, mode)) + ' · 已实现 <span class="' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(item.cumulative_realized_pnl, mode)) + '</span></div>',
    '<div class="portfolio-review-point-meta">持有 ' + escapeHtml(formatPortfolioNumber(item.quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode)) + ' · 成本 ' + escapeHtml(formatPortfolioMoney(item.cost_basis, mode)) + '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewCurve(mode, summary) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  const points = state.points.map(normalizePortfolioReviewPoint).filter(point => point.date);
  if (!points.length) return '';
  const values = points.map(point => Number(point.cumulative_realized_pnl) || 0);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const width = 240;
  const height = 88;
  const padding = 12;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const xy = values.map((value, index) => {
    const x = points.length === 1 ? width / 2 : padding + innerWidth * (index / (points.length - 1));
    const y = padding + innerHeight * (1 - ((value - minValue) / range));
    return {
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
      value,
      point: points[index],
    };
  });
  const zeroY = padding + innerHeight * (1 - ((0 - minValue) / range));
  const linePoints = xy.map(item => item.x + ',' + item.y).join(' ');
  const last = xy[xy.length - 1];
  const pnlClass = portfolioPnlClass(last.value);
  return [
    '<div class="portfolio-review-curve">',
    '<div class="portfolio-review-curve-head">',
    '<div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '已实现收益曲线') + '</div>',
    '<div class="portfolio-review-curve-value ' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(last.value, mode)) + '</div>',
    '</div>',
    '<svg class="portfolio-curve-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" aria-hidden="true">',
    '<line class="portfolio-curve-axis" x1="' + padding + '" y1="' + zeroY.toFixed(2) + '" x2="' + (width - padding) + '" y2="' + zeroY.toFixed(2) + '"></line>',
    '<polyline class="portfolio-curve-line" points="' + linePoints + '"></polyline>',
    xy.map(item => '<circle class="portfolio-curve-point" cx="' + item.x + '" cy="' + item.y + '" r="2.8"></circle>').join(''),
    '</svg>',
    '<div class="portfolio-review-curve-meta">' + escapeHtml(points[0].date + ' 至 ' + last.point.date + ' · ' + points.length + ' 个交易日') + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioReviewSection(mode, summary, maxNetInvested) {
  const state = normalizePortfolioReviewSummary(summary, mode);
  if (!state.points.length) return '';
  return [
    '<div class="portfolio-review-section">',
    '<div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '趋势') + '</div>',
    renderPortfolioReviewCurve(mode, state),
    '<div class="portfolio-review-points">',
    state.points.map(point => renderPortfolioReviewPoint(mode, point, maxNetInvested)).join(''),
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioPerformanceCurve(mode, performance) {
  const state = performance && typeof performance === 'object' ? performance : {};
  const points = Array.isArray(state.points) ? state.points.filter(point => point && Number.isFinite(Number(point.total_pnl))) : [];
  if (!points.length) {
    return '<div class="portfolio-review-section"><div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '持仓总收益曲线') + '</div><div class="portfolio-review-analytics-empty">当前区间没有可用于历史重估的行情与流水交集。</div></div>';
  }
  const values = points.map(point => Number(point.total_pnl) || 0);
  const minValue = Math.min(0, ...values);
  const maxValue = Math.max(0, ...values);
  const range = maxValue - minValue || 1;
  const width = 360;
  const height = 118;
  const padding = 14;
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  const xy = values.map((value, index) => {
    const x = points.length === 1 ? width / 2 : padding + innerWidth * (index / (points.length - 1));
    const y = padding + innerHeight * (1 - ((value - minValue) / range));
    return { x: Number(x.toFixed(2)), y: Number(y.toFixed(2)), value, point: points[index] };
  });
  const zeroY = padding + innerHeight * (1 - ((0 - minValue) / range));
  const last = points[points.length - 1];
  const summary = state.summary && typeof state.summary === 'object' ? state.summary : {};
  const pnlClass = portfolioPnlClass(last.total_pnl);
  const meta = [
    points[0].date + ' 至 ' + last.date,
    points.length + ' 个估值点',
    '最大回撤 ' + formatPortfolioSignedMoney(summary.max_drawdown, mode),
  ].join(' · ');
  return [
    '<div class="portfolio-review-section portfolio-performance-section">',
    '<div class="portfolio-review-curve-head">',
    '<div><div class="portfolio-review-section-title">' + escapeHtml((mode === 'usd' ? '美元' : '人民币') + '持仓总收益曲线') + '</div><div class="portfolio-review-curve-meta">总收益 = 已实现收益 + 按历史市价计算的未实现收益</div></div>',
    '<div class="portfolio-review-curve-value ' + pnlClass + '">' + escapeHtml(formatPortfolioSignedMoney(last.total_pnl, mode)) + '</div>',
    '</div>',
    '<svg class="portfolio-curve-svg portfolio-performance-svg" viewBox="0 0 ' + width + ' ' + height + '" preserveAspectRatio="none" aria-label="持仓总收益曲线">',
    '<line class="portfolio-curve-axis" x1="' + padding + '" y1="' + zeroY.toFixed(2) + '" x2="' + (width - padding) + '" y2="' + zeroY.toFixed(2) + '"></line>',
    '<polyline class="portfolio-curve-line" points="' + xy.map(item => item.x + ',' + item.y).join(' ') + '"></polyline>',
    '</svg>',
    '<div class="portfolio-performance-metrics">',
    renderPortfolioReviewMetric('未实现', formatPortfolioSignedMoney(last.unrealized_pnl, mode), portfolioPnlClass(last.unrealized_pnl)),
    renderPortfolioReviewMetric('已实现', formatPortfolioSignedMoney(last.realized_pnl, mode), portfolioPnlClass(last.realized_pnl)),
    renderPortfolioReviewMetric('市值', formatPortfolioMoney(last.market_value, mode), ''),
    renderPortfolioReviewMetric('收益率', formatPortfolioPercent(last.total_pnl_percent), pnlClass),
    '</div>',
    '<div class="portfolio-review-curve-meta">' + escapeHtml(meta) + '</div>',
    state.unknown_date_count ? '<div class="portfolio-review-analytics-note">有 ' + escapeHtml(String(state.unknown_date_count)) + ' 笔流水缺少可识别日期，未计入历史曲线。</div>' : '',
    '</div>',
  ].join('');
}

function portfolioAnalyticsRate(value) {
  return value == null || !Number.isFinite(Number(value)) ? '--' : Number(value).toFixed(1) + '%';
}

function renderAlertEffectiveness(effectiveness) {
  const state = effectiveness && typeof effectiveness === 'object' ? effectiveness : {};
  const total = Number(state.period_alerts || 0);
  const delivery = state.delivery && typeof state.delivery === 'object' ? state.delivery : {};
  const response = state.response && typeof state.response === 'object' ? state.response : {};
  const market = state.market_follow_through && typeof state.market_follow_through === 'object' ? state.market_follow_through : {};
  const items = Array.isArray(state.items) ? state.items.slice(0, 6) : [];
  if (!total) {
    return '<div class="portfolio-alert-effectiveness"><div class="portfolio-review-section-title">预警有效性</div><div class="portfolio-review-analytics-empty">最近 ' + escapeHtml(String(state.period_days || 30)) + ' 日没有可分析的预警记录。</div></div>';
  }
  const rows = items.map(item => {
    const direction = item.direction === 'down' ? '下行' : '上行';
    const outcome = item.follow_through ? '延续' : '未延续';
    const className = portfolioPnlClass(item.follow_through ? 1 : -1);
    return [
      '<div class="portfolio-effectiveness-row">',
      '<div><strong>' + escapeHtml(item.title || '预警') + '</strong><span>' + escapeHtml(String(item.timestamp || '').replace('T', ' ').slice(0, 16)) + ' · ' + direction + '</span></div>',
      '<div class="' + className + '">' + escapeHtml(outcome + ' ' + portfolioAnalyticsRate(item.final_signed_change_pct)) + '</div>',
      '</div>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-alert-effectiveness">',
    '<div class="portfolio-review-curve-head"><div><div class="portfolio-review-section-title">预警有效性</div><div class="portfolio-review-curve-meta">最近 ' + escapeHtml(String(state.period_days || 30)) + ' 日；行情延续按触发方向的 24 小时后变化统计</div></div></div>',
    '<div class="portfolio-effectiveness-grid">',
    renderPortfolioReviewMetric('预警数量', String(total), ''),
    renderPortfolioReviewMetric('通知送达率', portfolioAnalyticsRate(delivery.sent_rate), ''),
    renderPortfolioReviewMetric('已处理率', portfolioAnalyticsRate(response.handled_rate), ''),
    renderPortfolioReviewMetric('行情延续率', portfolioAnalyticsRate(market.rate), ''),
    '</div>',
    '<div class="portfolio-review-analytics-note">行情延续率仅描述预警触发后的价格路径，不代表预测准确率或投资建议。已评估 ' + escapeHtml(String(market.evaluated || 0)) + ' 条方向性预警。</div>',
    rows ? '<div class="portfolio-effectiveness-list">' + rows + '</div>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioAnalytics() {
  if (portfolioAnalyticsLoading && !portfolioAnalyticsState) {
    return '<div class="portfolio-review-analytics-loading">正在计算历史持仓收益与预警效果...</div>';
  }
  if (!portfolioAnalyticsState || Number(portfolioAnalyticsState.range_days) !== portfolioAnalyticsRange) {
    return '<div class="portfolio-review-analytics-empty">选择区间后可查看按历史市价重估的持仓总收益与预警效果。</div>';
  }
  const performance = portfolioAnalyticsState.performance && typeof portfolioAnalyticsState.performance === 'object' ? portfolioAnalyticsState.performance : {};
  return [
    '<div class="portfolio-performance-grid">',
    renderPortfolioPerformanceCurve('rmb', performance.rmb),
    renderPortfolioPerformanceCurve('usd', performance.usd),
    '</div>',
    renderAlertEffectiveness(portfolioAnalyticsState.alert_effectiveness),
  ].join('');
}

function renderPortfolioReview(box) {
  const review = normalizePortfolioReview(portfolioState.review);
  const totalTrades = review.rmb.trade_count + review.usd.trade_count;
  if (!totalTrades) {
    box.innerHTML = '<div class="portfolio-review">' + renderPortfolioAnalytics() + '<div class="portfolio-empty">暂无流水复盘数据</div></div>';
    return;
  }
  const maxNetInvested = Math.max(
    1,
    ...review.rmb.points.concat(review.usd.points).map(point => Math.abs(Number(point.net_invested) || 0))
  );
  box.innerHTML = [
    '<div class="portfolio-review">',
    '<div class="portfolio-review-grid">',
    renderPortfolioReviewCard('rmb', review.rmb),
    renderPortfolioReviewCard('usd', review.usd),
    '</div>',
    renderPortfolioAnalytics(),
    renderPortfolioReviewSection('rmb', review.rmb, maxNetInvested),
    renderPortfolioReviewSection('usd', review.usd, maxNetInvested),
    '</div>',
  ].join('');
}

function portfolioTransactionsForPosition(positionId) {
  return (Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [])
    .filter(item => item && item.position_id === positionId)
    .sort((left, right) => (
      portfolioReviewTimestampValue(right.trade_date || right.updated_at || right.created_at)
      - portfolioReviewTimestampValue(left.trade_date || left.updated_at || left.created_at)
    ));
}

function renderPortfolioDetailMetric(label, value, extraClass) {
  return [
    '<div class="portfolio-detail-metric">',
    '<div class="portfolio-detail-label">' + escapeHtml(label) + '</div>',
    '<div class="portfolio-detail-value ' + (extraClass || '') + '">' + escapeHtml(value) + '</div>',
    '</div>',
  ].join('');
}

function portfolioAlertStatusLabel(alert) {
  const status = alert && alert.status ? alert.status : 'empty';
  if (status === 'triggered') return '已触发';
  if (status === 'watching') return '监控中';
  if (status === 'disabled') return '已停用';
  return '未设置';
}

function portfolioAlertStatusClass(alert) {
  const status = alert && alert.status ? alert.status : 'empty';
  if (status === 'triggered') return 'on';
  if (status === 'watching') return 'on';
  return 'off';
}

function buildPortfolioAlertEditor(item) {
  const alert = portfolioAlertForPosition(item.id);
  const target = portfolioAlertDraftFor(item, alert);
  const positionId = escapeHtml(target.position_id);
  const inputAttr = ' oninput="capturePortfolioAlertDraft(\'' + positionId + '\')"';
  const changeAttr = ' onchange="capturePortfolioAlertDraft(\'' + positionId + '\')"';
  const resetButton = alert && alert.id
    ? '<button class="btn-clear-sm" type="button" onclick="resetPortfolioAlert(\'' + escapeHtml(alert.id) + '\')">重置</button>'
    : '';
  const deleteButton = alert && alert.id
    ? '<button class="btn-clear-sm" type="button" onclick="deletePortfolioAlert(\'' + escapeHtml(alert.id) + '\', \'' + positionId + '\')">清空</button>'
    : '';
  return [
    '<div class="portfolio-alert-editor">',
    '<div class="portfolio-alert-head">',
    '<div class="portfolio-detail-section-title">提醒设置</div>',
    '<span class="portfolio-alert-state ' + portfolioAlertStatusClass(alert) + '">' + escapeHtml(portfolioAlertStatusLabel(alert)) + '</span>',
    '</div>',
    '<div class="portfolio-alert-fields">',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertEnabled_' + positionId + '">状态</label>',
    '<select id="portfolioAlertEnabled_' + positionId + '"' + changeAttr + '>',
    '<option value="true"' + (target.enabled !== false ? ' selected' : '') + '>监控</option>',
    '<option value="false"' + (target.enabled === false ? ' selected' : '') + '>停用</option>',
    '</select>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertTakeProfit_' + positionId + '">止盈价</label>',
    '<input id="portfolioAlertTakeProfit_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.take_profit_price) + '" placeholder="例如 760"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertStopLoss_' + positionId + '">止损价</label>',
    '<input id="portfolioAlertStopLoss_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.stop_loss_price) + '" placeholder="例如 680"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertProfitPercent_' + positionId + '">浮盈比例（%）</label>',
    '<input id="portfolioAlertProfitPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.profit_percent) + '" placeholder="例如 8"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertLossPercent_' + positionId + '">浮亏比例（%）</label>',
    '<input id="portfolioAlertLossPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.loss_percent) + '" placeholder="例如 3"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field">',
    '<label for="portfolioAlertNearCostPercent_' + positionId + '">近成本（%）</label>',
    '<input id="portfolioAlertNearCostPercent_' + positionId + '" type="number" step="0.01" value="' + escapeHtml(target.near_cost_percent) + '" placeholder="例如 1"' + inputAttr + '>',
    '</div>',
    '<div class="portfolio-field portfolio-note">',
    '<label for="portfolioAlertNote_' + positionId + '">备注</label>',
    '<textarea id="portfolioAlertNote_' + positionId + '" maxlength="120" rows="2" placeholder="例如 止盈后分批卖出"' + inputAttr + '>' + escapeHtml(target.note) + '</textarea>',
    '</div>',
    '</div>',
    '<div class="portfolio-alert-actions">',
    '<button class="btn-set" type="button" onclick="savePortfolioAlert(\'' + positionId + '\')">保存提醒</button>',
    resetButton,
    deleteButton,
    '</div>',
    '</div>',
  ].join('');
}

function portfolioAlertThresholdText(label, value, mode, suffix) {
  if (value === null || value === undefined || value === '') return '';
  const number = Number(value);
  if (!Number.isFinite(number)) return '';
  const text = suffix ? formatPortfolioNumber(number, 2) + suffix : formatPortfolioMoney(number, mode);
  return label + ' ' + text;
}

function renderPortfolioAlertSummary(item, alert) {
  const mode = item.mode || 'rmb';
  const positionId = escapeHtml(item.id);
  const parts = [
    portfolioAlertThresholdText('止盈', alert && alert.take_profit_price, mode, ''),
    portfolioAlertThresholdText('止损', alert && alert.stop_loss_price, mode, ''),
    portfolioAlertThresholdText('浮盈', alert && alert.profit_percent, mode, '%'),
    portfolioAlertThresholdText('浮亏', alert && alert.loss_percent, mode, '%'),
    portfolioAlertThresholdText('近成本', alert && alert.near_cost_percent, mode, '%'),
  ].filter(Boolean);
  const stateText = portfolioAlertStatusLabel(alert);
  const summaryText = parts.length ? stateText + ' · ' + parts.join(' · ') : stateText + ' · 未设置价格条件';
  const buttonText = activePortfolioAlertEditorId === item.id ? '收起编辑' : '编辑提醒';
  return [
    '<div class="portfolio-alert-summary">',
    '<div class="portfolio-alert-summary-main">',
    '<span class="portfolio-alert-state ' + portfolioAlertStatusClass(alert) + '">' + escapeHtml(stateText) + '</span>',
    '<span class="portfolio-alert-summary-text">' + escapeHtml(summaryText) + '</span>',
    '</div>',
    '<div class="portfolio-alert-summary-actions">',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="togglePortfolioAlertEditor(\'' + positionId + '\')">' + buttonText + '</button>',
    '</div>',
    '</div>',
  ].join('');
}

function portfolioTransactionDisplay(transaction, fallbackMode) {
  const mode = transaction.mode || fallbackMode || 'rmb';
  const quantityDigits = mode === 'usd' ? 4 : 2;
  const typeText = transaction.type === 'sell' ? '卖出' : '买入';
  const typeClass = transaction.type === 'sell' ? 'sell' : 'buy';
  const amount = Number(transaction.price) * Number(transaction.quantity);
  const valueText = transaction.type === 'sell'
    ? '已实现 ' + formatPortfolioSignedMoney(transaction.realized_pnl, mode)
    : '成交 ' + formatPortfolioMoney(amount, mode);
  return {
    mode,
    quantityDigits,
    typeText,
    typeClass,
    valueText,
    quantityText: formatPortfolioNumber(transaction.quantity, quantityDigits) + ' ' + portfolioQuantityUnit(mode),
  };
}

function renderPortfolioDetailTransactionItem(item, transaction) {
  const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
  const metaParts = [
    transaction.trade_date || '未标日期',
    formatPortfolioMoney(transaction.price, display.mode),
    display.quantityText,
    Number(transaction.fee) > 0 ? '手续费 ' + formatPortfolioMoney(transaction.fee, display.mode) : '',
    transaction.note || '',
  ].filter(Boolean);
  return [
    '<div class="portfolio-detail-transaction">',
    '<div class="portfolio-detail-transaction-main">',
    '<div class="portfolio-detail-transaction-title"><span class="portfolio-transaction-type ' + display.typeClass + '">' + escapeHtml(display.typeText) + '</span>' + escapeHtml(transaction.name || item.name || '未命名流水') + '</div>',
    '<div class="portfolio-detail-transaction-meta">' + escapeHtml(metaParts.join(' · ')) + '</div>',
    '</div>',
    '<div class="portfolio-detail-transaction-value ' + portfolioPnlClass(transaction.realized_pnl) + '">' + escapeHtml(display.valueText) + '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailTransactionsList(item, transactions, limit) {
  const visibleTransactions = Number.isFinite(Number(limit)) ? transactions.slice(0, Number(limit)) : transactions;
  if (!transactions.length) return '<div class="portfolio-detail-empty">暂无关联流水</div>';
  return visibleTransactions.map(transaction => renderPortfolioDetailTransactionItem(item, transaction)).join('')
    + (transactions.length > visibleTransactions.length ? '<div class="portfolio-detail-more">还有 ' + escapeHtml(String(transactions.length - visibleTransactions.length)) + ' 条流水，可切换到流水页查看</div>' : '');
}

function renderPortfolioDetailActions(item) {
  const positionId = escapeHtml(item.id);
  return [
    '<span class="portfolio-detail-actions">',
    '<button class="btn-clear-sm btn-muted-sm portfolio-detail-action-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="togglePortfolioDetailActionMenu(this)">操作</button>',
    '<span class="portfolio-detail-action-menu" hidden>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'buy\')">新增买入</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'sell\')">新增卖出</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setActivePortfolioPosition(\'' + positionId + '\')">编辑持仓</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="openPortfolioAlertEditor(\'' + positionId + '\')">设置提醒</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setPortfolioView(\'transactions\')">查看全部流水</button>',
    '</span>',
    '</span>',
  ].join('');
}

function renderPortfolioDetailTabs(activeView) {
  const tabs = [
    ['overview', '概览'],
    ['transactions', '流水'],
    ['alert', '预警'],
    ['review', '复盘'],
  ];
  return '<div class="portfolio-detail-tabs">' + tabs.map(tab => (
    '<button class="portfolio-detail-tab' + (activeView === tab[0] ? ' active' : '') + '" type="button" onclick="setPortfolioDetailView(\'' + tab[0] + '\')">' + escapeHtml(tab[1]) + '</button>'
  )).join('') + '</div>';
}

function renderPortfolioDetailMetricGrid(item) {
  const mode = item.mode || 'rmb';
  const unrealizedPnl = item.unrealized_pnl != null ? item.unrealized_pnl : item.pnl;
  return [
    '<div class="portfolio-detail-grid">',
    renderPortfolioDetailMetric('平均成本', formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode), ''),
    renderPortfolioDetailMetric('市值', formatPortfolioMoney(item.market_value, mode), ''),
    renderPortfolioDetailMetric('未实现', formatPortfolioSignedMoney(unrealizedPnl, mode), portfolioPnlClass(unrealizedPnl)),
    renderPortfolioDetailMetric('已实现', formatPortfolioSignedMoney(item.realized_pnl, mode), portfolioPnlClass(item.realized_pnl)),
    '</div>',
  ].join('');
}

function renderPortfolioDetailOverview(item, alert, transactions) {
  return [
    '<div class="portfolio-detail-panel">',
    renderPortfolioDetailMetricGrid(item),
    renderPortfolioAlertSummary(item, alert),
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-transactions-head">',
    '<div class="portfolio-detail-section-title">最近流水</div>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="setPortfolioDetailView(\'transactions\')">查看全部</button>',
    '</div>',
    '<div class="portfolio-detail-transactions-list">',
    renderPortfolioDetailTransactionsList(item, transactions, 3),
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailTransactions(item, transactions) {
  return [
    '<div class="portfolio-detail-panel">',
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-transactions-head">',
    '<div class="portfolio-detail-section-title">关联流水</div>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">新增流水</button>',
    '</div>',
    '<div class="portfolio-detail-transactions-list">',
    renderPortfolioDetailTransactionsList(item, transactions),
    '</div>',
    '</div>',
    '</div>',
  ].join('');
}

function renderPortfolioDetailAlert(item, alert) {
  return [
    '<div class="portfolio-detail-panel">',
    renderPortfolioAlertSummary(item, alert),
    activePortfolioAlertEditorId === item.id ? buildPortfolioAlertEditor(item) : '',
    '</div>',
  ].join('');
}

function portfolioParseDate(value) {
  if (!value) return null;
  const parsed = new Date(String(value).replace(' ', 'T'));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function portfolioReviewTimestampValue(value) {
  const parsed = portfolioParseDate(value);
  return parsed ? parsed.getTime() : 0;
}

function portfolioAlertEntriesForPosition(item) {
  const tokens = [item && item.id, item && item.name]
    .map(value => String(value || '').trim().toLowerCase())
    .filter(Boolean);
  return alertEntries.filter(entry => {
    if (!entry || typeof entry !== 'object') return false;
    if (item && entry.position_id && entry.position_id === item.id) return true;
    const text = [
      entry.message,
      entry.title,
      entry.type,
      entry.mode,
      entry.handling_note,
      entry.watch_target_id,
      entry.source,
    ].join(' ').toLowerCase();
    return tokens.some(token => text.includes(token));
  });
}

function latestPortfolioRiskAnalysis() {
  const items = Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory.slice() : [];
  if (!items.length) return null;
  return items.sort((left, right) => portfolioReviewTimestampValue(left.analysis_time) - portfolioReviewTimestampValue(right.analysis_time))[items.length - 1];
}

function buildPortfolioReviewSummary(item, alert, transactions) {
  const now = Date.now();
  const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
  const recentTransactions = transactions.filter(transaction => {
    const date = portfolioParseDate(transaction.trade_date || transaction.updated_at || transaction.created_at);
    return date && date.getTime() >= sevenDaysAgo;
  });
  const matchedAlerts = portfolioAlertEntriesForPosition(item);
  const triggeredConditions = alert && alert.triggered && typeof alert.triggered === 'object'
    ? Object.keys(alert.triggered).filter(key => alert.triggered[key])
    : [];
  const triggeredCount = matchedAlerts.length + (alert && alert.status === 'triggered' && !matchedAlerts.length ? 1 : 0);
  const riskItems = Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory : [];
  const latestRisk = latestPortfolioRiskAnalysis();
  const riskLevel = latestRisk && latestRisk.structured ? (latestRisk.structured.risk_level || latestRisk.structured.overall_risk || '') : '';
  const quality = latestSourceHealthState && latestSourceHealthState.quality ? latestSourceHealthState.quality : null;
  return [
    {
      label: '近7日',
      value: recentTransactions.length + ' 笔',
      meta: transactions.length ? '共 ' + transactions.length + ' 笔流水' : '暂无流水',
    },
    {
      label: '触发预警',
      value: triggeredCount ? triggeredCount + ' 条' : '无触发',
      meta: triggeredConditions.length ? triggeredConditions.length + ' 个条件命中' : portfolioAlertStatusLabel(alert),
      className: triggeredCount ? 'up' : '',
    },
    {
      label: '风险分析',
      value: riskItems.length ? riskItems.length + ' 条' : '暂无分析',
      meta: riskLevel || (latestRisk ? '最近 ' + (latestRisk.analysis_time || '--') : '可从风险分析入口生成'),
    },
    {
      label: '数据质量',
      value: quality && quality.score != null ? quality.score + ' 分' : '--',
      meta: sourceQualityText(quality) || '等待数据源检查',
    },
  ];
}

function portfolioReviewTimelineEventLabel(type) {
  if (type === 'transaction') return '流水';
  if (type === 'alert') return '预警';
  if (type === 'risk') return '风险';
  if (type === 'quality') return '数据';
  return '线索';
}

function buildPortfolioReviewTimeline(item, alert, transactions) {
  const events = [];
  transactions.forEach(transaction => {
    const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
    events.push({
      type: 'transaction',
      time: transaction.trade_date || transaction.updated_at || transaction.created_at || '未标日期',
      sortTime: portfolioReviewTimestampValue(transaction.trade_date || transaction.updated_at || transaction.created_at),
      title: display.typeText + ' · ' + (transaction.name || item.name || '未命名流水'),
      text: [
        formatPortfolioMoney(transaction.price, display.mode),
        display.quantityText,
        display.valueText,
        Number(transaction.fee) > 0 ? '手续费 ' + formatPortfolioMoney(transaction.fee, display.mode) : '',
        transaction.note || '',
      ].filter(Boolean).join(' · '),
    });
  });
  if (alert) {
    const thresholds = [
      portfolioAlertThresholdText('止盈', alert.take_profit_price, item.mode || 'rmb', ''),
      portfolioAlertThresholdText('止损', alert.stop_loss_price, item.mode || 'rmb', ''),
      portfolioAlertThresholdText('浮盈', alert.profit_percent, item.mode || 'rmb', '%'),
      portfolioAlertThresholdText('浮亏', alert.loss_percent, item.mode || 'rmb', '%'),
      portfolioAlertThresholdText('近成本', alert.near_cost_percent, item.mode || 'rmb', '%'),
    ].filter(Boolean);
    events.push({
      type: 'alert',
      time: alert.last_triggered_at || '当前设置',
      sortTime: portfolioReviewTimestampValue(alert.last_triggered_at),
      title: portfolioAlertStatusLabel(alert) + ' · 持仓提醒',
      text: thresholds.length ? thresholds.join(' · ') : '未设置价格条件',
    });
  }
  portfolioAlertEntriesForPosition(item).slice(-5).forEach(entry => {
    events.push({
      type: 'alert',
      time: entry.timestamp || entry.time || '--',
      sortTime: portfolioReviewTimestampValue(entry.timestamp),
      title: alertLevelLabel(entry.type) + ' · 告警记录',
      text: entry.message || '达到预警条件',
    });
  });
  (Array.isArray(riskAnalysisHistory) ? riskAnalysisHistory.slice(-2) : []).forEach(entry => {
    const structured = entry.structured || {};
    const firstLine = String(entry.content || '').split('\n').find(Boolean) || '风险分析记录';
    events.push({
      type: 'risk',
      time: entry.analysis_time || '--',
      sortTime: portfolioReviewTimestampValue(entry.analysis_time),
      title: '风险分析' + (structured.risk_level ? ' · ' + structured.risk_level : ''),
      text: firstLine,
    });
  });
  const quality = latestSourceHealthState && latestSourceHealthState.quality ? latestSourceHealthState.quality : null;
  if (quality) {
    const reasons = Array.isArray(quality.reasons) ? quality.reasons.filter(Boolean).join('；') : '';
    events.push({
      type: 'quality',
      time: latestData && latestData.time ? latestData.time : '当前',
      sortTime: Date.now(),
      title: '行情质量 · ' + (quality.label || quality.level || '--'),
      text: quality.summary || reasons || sourceQualityText(quality),
    });
  }
  return events.sort((left, right) => right.sortTime - left.sortTime);
}

function renderPortfolioReviewSummaryStrip(summary) {
  return '<div class="portfolio-detail-review-summary">' + summary.map(item => [
    '<div class="portfolio-detail-review-stat">',
    '<div class="portfolio-detail-review-stat-label">' + escapeHtml(item.label) + '</div>',
    '<div class="portfolio-detail-review-stat-value ' + (item.className || '') + '">' + escapeHtml(item.value) + '</div>',
    '<div class="portfolio-detail-review-stat-meta">' + escapeHtml(item.meta) + '</div>',
    '</div>',
  ].join('')).join('') + '</div>';
}

function renderPortfolioReviewTimeline(events) {
  if (!events.length) return '<div class="portfolio-detail-empty">暂无复盘线索</div>';
  return [
    '<div class="portfolio-review-timeline">',
    events.map(event => [
      '<div class="portfolio-review-event">',
      '<div class="portfolio-review-event-time">' + escapeHtml(String(event.time || '--').replace('T', ' ').slice(0, 16)) + '</div>',
      '<div class="portfolio-review-event-main">',
      '<div class="portfolio-review-event-title"><span class="portfolio-review-event-type">' + escapeHtml(portfolioReviewTimelineEventLabel(event.type)) + '</span>' + escapeHtml(event.title || '复盘线索') + '</div>',
      '<div class="portfolio-review-event-text">' + escapeHtml(event.text || '暂无详情') + '</div>',
      '</div>',
      '</div>',
    ].join('')).join(''),
    '</div>',
  ].join('');
}

function renderPortfolioRelatedTransactionsTable(item, transactions) {
  if (!transactions.length) return '<div class="portfolio-detail-empty">暂无关联流水</div>';
  const rows = transactions.slice(0, 5).map(transaction => {
    const display = portfolioTransactionDisplay(transaction, item.mode || 'rmb');
    return [
      '<div class="portfolio-related-row">',
      '<span>' + escapeHtml(transaction.trade_date || '未标日期') + '</span>',
      '<span><span class="portfolio-transaction-type ' + display.typeClass + '">' + escapeHtml(display.typeText) + '</span></span>',
      '<span>' + escapeHtml(formatPortfolioMoney(transaction.price, display.mode)) + '</span>',
      '<span>' + escapeHtml(display.quantityText) + '</span>',
      '<span class="' + portfolioPnlClass(transaction.realized_pnl) + '">' + escapeHtml(display.valueText) + '</span>',
      '</div>',
    ].join('');
  }).join('');
  return [
    '<div class="portfolio-related-table">',
    '<div class="portfolio-related-row head"><span>日期</span><span>类型</span><span>成交价</span><span>数量</span><span>结果</span></div>',
    rows,
    transactions.length > 5 ? '<div class="portfolio-detail-more">还有 ' + escapeHtml(String(transactions.length - 5)) + ' 条流水</div>' : '',
    '</div>',
  ].join('');
}

function renderPortfolioPositionReview(item, alert, transactions) {
  const summary = buildPortfolioReviewSummary(item, alert, transactions);
  const events = buildPortfolioReviewTimeline(item, alert, transactions);
  const positionId = escapeHtml(item.id);
  return [
    '<div class="portfolio-detail-panel portfolio-detail-review-panel">',
    renderPortfolioReviewSummaryStrip(summary),
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-section-title">复盘线索</div>',
    renderPortfolioReviewTimeline(events),
    '</div>',
    '<div class="portfolio-detail-transactions">',
    '<div class="portfolio-detail-section-title">关联流水</div>',
    renderPortfolioRelatedTransactionsTable(item, transactions),
    '</div>',
    '<div class="portfolio-detail-action-row">',
    '<button class="btn-set" type="button" onclick="startPortfolioTransactionForPosition(\'' + positionId + '\', \'buy\')">新增流水</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="openPortfolioAlertEditor(\'' + positionId + '\')">设置提醒</button>',
    '<button class="btn-clear-sm btn-muted-sm" type="button" onclick="exportPortfolioPositionReview(\'' + positionId + '\')">导出复盘</button>',
    '</div>',
    '</div>',
  ].join('');
}

function portfolioReviewSafeFilename(value) {
  return String(value || 'position').trim().replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48) || 'position';
}

function portfolioPositionReviewMarkdown(item, alert, transactions) {
  const mode = item.mode || 'rmb';
  const summary = buildPortfolioReviewSummary(item, alert, transactions);
  const events = buildPortfolioReviewTimeline(item, alert, transactions);
  const totalPnl = item.total_pnl != null ? item.total_pnl : item.pnl;
  const lines = [
    '# 持仓复盘',
    '',
    '## 持仓',
    '- 名称：' + (item.name || '未命名持仓'),
    '- 单位：' + portfolioModeLabel(mode),
    '- 数量：' + formatPortfolioNumber(item.quantity, mode === 'usd' ? 4 : 2) + ' ' + portfolioQuantityUnit(mode),
    '- 当前价：' + (item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode)),
    '- 平均成本：' + formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode),
    '- 合计盈亏：' + formatPortfolioSignedMoney(totalPnl, mode),
    '',
    '## 摘要',
    ...summary.map(item => '- ' + item.label + '：' + item.value + '（' + item.meta + '）'),
    '',
    '## 复盘线索',
    ...(events.length ? events.map(event => '- ' + String(event.time || '--') + ' [' + portfolioReviewTimelineEventLabel(event.type) + '] ' + (event.title || '') + '：' + (event.text || '')) : ['- 暂无复盘线索']),
    '',
    '## 关联流水',
    ...(transactions.length ? transactions.map(transaction => {
      const display = portfolioTransactionDisplay(transaction, mode);
      return '- ' + (transaction.trade_date || '未标日期') + ' ' + display.typeText + ' ' + formatPortfolioMoney(transaction.price, display.mode) + ' × ' + display.quantityText + '，' + display.valueText;
    }) : ['- 暂无关联流水']),
  ];
  return lines.join('\n');
}

function exportPortfolioPositionReview(positionId) {
  const item = (portfolioState.items || []).find(entry => entry.id === positionId);
  if (!item) {
    setPortfolioStatus('未找到持仓，无法导出复盘。', 'fail');
    return;
  }
  const alert = portfolioAlertForPosition(item.id);
  const transactions = portfolioTransactionsForPosition(item.id);
  const filename = 'GoldMonitor-' + portfolioReviewSafeFilename(item.name || item.id) + '-review.md';
  downloadText(filename, portfolioPositionReviewMarkdown(item, alert, transactions), 'text/markdown;charset=utf-8');
  setPortfolioStatus('已导出当前持仓复盘。', 'ok');
}

function renderPortfolioPositionDetail(item) {
  const mode = item.mode || 'rmb';
  const quantityDigits = mode === 'usd' ? 4 : 2;
  const quantityText = formatPortfolioNumber(item.quantity, quantityDigits) + ' ' + portfolioQuantityUnit(mode);
  const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode);
  const totalPnl = item.total_pnl != null ? item.total_pnl : item.pnl;
  const pnlClass = portfolioPnlClass(totalPnl);
  const status = item.portfolio_status || item.valuation_status || '';
  const alert = portfolioAlertForPosition(item.id);
  const transactions = portfolioTransactionsForPosition(item.id);
  const activeView = ['overview', 'transactions', 'alert', 'review'].includes(portfolioDetailView) ? portfolioDetailView : 'review';
  const bodyHtml = activeView === 'overview'
    ? renderPortfolioDetailOverview(item, alert, transactions)
    : activeView === 'transactions'
      ? renderPortfolioDetailTransactions(item, transactions)
      : activeView === 'alert'
        ? renderPortfolioDetailAlert(item, alert)
        : renderPortfolioPositionReview(item, alert, transactions);
  return [
    '<div class="portfolio-detail">',
    '<div class="portfolio-detail-focus">',
    '<div class="portfolio-detail-focus-main">',
    '<div class="portfolio-detail-focus-head">',
    '<div class="portfolio-detail-focus-title">' + escapeHtml(item.name || '未命名持仓') + '</div>',
    '<span class="alert-rule-state ' + portfolioStatusClass(status) + '">' + escapeHtml(portfolioStatusLabel(status)) + '</span>',
    renderPortfolioDetailActions(item),
    '</div>',
    '<div class="portfolio-detail-focus-meta">' + escapeHtml([portfolioModeLabel(mode), quantityText, '当前价 ' + currentPrice, item.last_trade_date ? '最近 ' + item.last_trade_date : ''].filter(Boolean).join(' · ')) + '</div>',
    '</div>',
    '<div class="portfolio-detail-focus-value ' + pnlClass + '">',
    '<strong>' + escapeHtml(formatPortfolioSignedMoney(totalPnl, mode)) + '</strong>',
    '<span>合计盈亏</span>',
    '</div>',
    '</div>',
    renderPortfolioDetailTabs(activeView),
    bodyHtml,
    '</div>',
  ].join('');
}

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
      '<div class="portfolio-line"><span class="portfolio-transaction-type ' + typeClass + '">' + escapeHtml(typeText) + '</span> ' + escapeHtml(item.name || '未命名流水') + escapeHtml(realizedText) + '</div>',
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

// ========== 日志 ==========
function normalizeAlertEntry(entry) {
  const item = entry && typeof entry === 'object' ? { ...entry } : {};
  item.id = item.id || 'local-' + (item.timestamp || Date.now()) + '-' + Math.random().toString(16).slice(2);
  item.read = item.read === true;
  item.handled = item.handled === true;
  item.handled_at = item.handled_at ? String(item.handled_at) : '';
  item.handling_note = item.handling_note ? String(item.handling_note) : '';
  return item;
}

function setAlertEntries(items) {
  alertEntries = Array.isArray(items) ? items.slice(-50).map(normalizeAlertEntry) : [];
  updateAlertLogSummary();
  renderAlertLog();
}

function setAlertLogSearch(value) {
  alertLogSearch = (value || '').trim().toLowerCase();
  renderAlertLog();
}

function toggleAlertLogMenu() {
  const menu = document.getElementById('alertLogMenu');
  const button = document.getElementById('alertLogMoreButton');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}

function toggleSourceHealthMenu(button) {
  const menu = document.getElementById('sourceHealthMenu');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}

function toggleLogEntryMenu(button) {
  const actions = button && button.closest ? button.closest('.log-actions') : null;
  const menu = actions ? actions.querySelector('.log-entry-menu') : null;
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  button.setAttribute('aria-expanded', String(willOpen));
}

function updateAlertLogSummary() {
  const countEl = document.getElementById('alertUnreadCount');
  const unread = alertEntries.filter(entry => !entry.read).length;
  countEl.textContent = unread + ' 新';
  countEl.className = 'log-count' + (unread ? '' : ' empty');
}

function alertLogMatchesSearch(entry) {
  if (!alertLogSearch) return true;
  const haystack = [
    entry.time, entry.timestamp, entry.type, entry.mode, entry.message,
    entry.handling_note, entry.rule_id, entry.rule_name, entry.rule_kind,
    alertLevelLabel(entry.type), alertModeLabel(entry.mode),
  ].join(' ').toLowerCase();
  return haystack.includes(alertLogSearch);
}

function filterAlertLogByRule(id) {
  const ruleId = String(id || '');
  if (!ruleId) return;
  alertLogSearch = ruleId.toLowerCase();
  const input = document.getElementById('alertLogSearch');
  if (input) input.value = ruleId;
  renderAlertLog();
  const list = document.getElementById('logList');
  if (list) list.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function alertNotificationIssues(entry) {
  const summary = entry && entry.notification_summary;
  if (summary && typeof summary === 'object') {
    const status = summary.status || '';
    if (!['failed', 'partial', 'skipped'].includes(status)) return [];
    return [{
      status,
      label: summary.label || '通知',
      message: summary.message || '',
    }];
  }
  const items = Array.isArray(entry.notifications) ? entry.notifications : [];
  return items.filter(item => item && ['failed', 'skipped'].includes(item.status));
}

function alertNotificationDisplay(entry) {
  const summary = entry && entry.notification_summary;
  if (summary && typeof summary === 'object') {
    const status = summary.status || '';
    if (!status || ['none', 'disabled'].includes(status)) return [];
    return [{
      status,
      label: summary.label || '通知',
      message: summary.message || '',
    }];
  }
  const items = Array.isArray(entry && entry.notifications) ? entry.notifications : [];
  return items.filter(item => item && item.status && item.status !== 'disabled');
}

function renderNotificationBadges(entry) {
  const items = alertNotificationDisplay(entry);
  if (!items.length) return '';
  return '<span class="log-notify">' + items.map(item => {
    const status = item.status || '';
    const cls = ['sent', 'queued'].includes(status)
      ? 'ok'
      : (['failed', 'skipped', 'partial'].includes(status) ? 'fail' : (status === 'muted' ? 'muted' : (status === 'pending' ? 'pending' : '')));
    const label = item.label || item.channel || '通知';
    const message = item.message ? '：' + item.message : '';
    return '<span class="log-notify-badge ' + cls + '">' + escapeHtml(label + message) + '</span>';
  }).join('') + '</span>';
}

function renderLogActionButton(action, extraClass) {
  const classes = ['btn-clear-sm', action.buttonClass || 'btn-muted-sm', extraClass || ''].filter(Boolean).join(' ');
  const attrs = action.attrs || '';
  return '<button class="' + escapeHtml(classes) + '" type="button" onclick="' + action.onclick + '"' + attrs + '>' + escapeHtml(action.label) + '</button>';
}

function renderLogEntryActions(actions) {
  if (actions.length === 1) {
    return '<span class="log-actions">' + renderLogActionButton(actions[0], 'log-action-direct') + '</span>';
  }
  if (actions.length > 1) {
    return [
      '<span class="log-actions">',
      '<button class="btn-clear-sm btn-muted-sm log-action-trigger" type="button" aria-haspopup="true" aria-expanded="false" onclick="toggleLogEntryMenu(this)">操作</button>',
      '<span class="log-entry-menu" hidden>',
      actions.map(action => renderLogActionButton(action, '')).join(''),
      '</span>',
      '</span>',
    ].join('');
  }
  return '<span class="log-actions"></span>';
}

function buildLogEntry(entry) {
  const item = document.createElement('div');
  const encodedId = encodeURIComponent(String(entry.id || ''));
  const hasNotificationIssue = alertNotificationIssues(entry).length > 0;
  const logMessage = entry.message || '达到预警条件';
  const handlingNote = entry.handling_note ? '<span class="log-note">处理备注：' + escapeHtml(entry.handling_note) + '</span>' : '';
  const timelineAction = {
    label: '复盘',
    buttonClass: 'btn-muted-sm',
    onclick: "window.openAlertTimelineFromLog(decodeURIComponent('" + encodedId + "'))",
    attrs: ' data-log-timeline-id="' + encodedId + '"',
  };
  const actions = [
    { label: '分析', buttonClass: 'btn-risk-sm', onclick: "analyzeAlertFromLog(decodeURIComponent('" + encodedId + "'))" },
  ];
  if (entry.rule_id || entry.rule_kind) {
    actions.push(
      { label: '查看规则', buttonClass: 'btn-muted-sm', onclick: "viewAlertRuleFromLog(decodeURIComponent('" + encodedId + "'))" },
      { label: '复制规则', buttonClass: 'btn-muted-sm', onclick: "copyAlertRuleFromLog(decodeURIComponent('" + encodedId + "'))" },
    );
  }
  if (hasNotificationIssue) actions.push(
    { label: '重发通知', buttonClass: 'btn-muted-sm', onclick: "resendAlertNotification(decodeURIComponent('" + encodedId + "'))" },
  );
  item.className = [
    'log-item',
    entry.read ? 'read' : 'unread',
    entry.handled ? 'handled' : '',
  ].filter(Boolean).join(' ');
  item.innerHTML = [
    '<span class="log-unread-dot"></span>',
    '<span class="log-body">',
    '<span class="log-entry-head">',
    '<span class="log-line-head">',
    '<span class="log-time">' + escapeHtml(entry.time || entry.timestamp || '') + '</span>',
    '<span class="log-level ' + escapeHtml(entry.type || '') + '">' + escapeHtml(alertLevelLabel(entry.type)) + '</span>',
    '</span>',
    '<span class="log-action-row">' + renderLogActionButton(timelineAction, 'log-action-direct log-review-direct') + renderLogEntryActions(actions) + '</span>',
    '</span>',
    '<span class="log-meta">',
    '<span class="log-msg ' + escapeHtml(entry.type || '') + '" title="' + escapeHtml(logMessage) + '">' + escapeHtml(logMessage) + '</span>',
    handlingNote,
    renderNotificationBadges(entry),
    '</span>',
    '</span>',
  ].join('');
  return item;
}

function renderAlertLog() {
  const list = document.getElementById('logList');
  const items = alertEntries.filter(alertLogMatchesSearch);
  list.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'log-empty';
    empty.textContent = alertEntries.length ? '当前搜索暂无警报' : '暂无警报';
    list.appendChild(empty);
    return;
  }
  items.forEach(entry => list.appendChild(buildLogEntry(entry)));
  list.scrollTop = list.scrollHeight;
}

function addLogEntry(entry) {
  const normalized = normalizeAlertEntry(entry);
  alertEntries.push(normalized);
  while (alertEntries.length > 50) alertEntries.shift();
  updateAlertLogSummary();
  renderAlertLog();
}

function mergeAlertLogEntry(entry) {
  const normalized = normalizeAlertEntry(entry);
  const index = alertEntries.findIndex(item => item.id === normalized.id);
  if (index >= 0) alertEntries[index] = normalized;
  else alertEntries.push(normalized);
  updateAlertLogSummary();
  renderAlertLog();
}

function updateAlertStatus(id, patch) {
  const entry = alertEntries.find(item => item.id === id);
  if (entry) {
    Object.assign(entry, patch || {});
    updateAlertLogSummary();
    renderAlertLog();
  }
  socket.emit('update_alert_log_status', Object.assign({ id }, patch || {}));
}

function updateAlertHandling(id, handled) {
  const entry = alertEntries.find(item => item.id === id);
  const nextHandled = handled === true;
  let note = entry && entry.handling_note ? entry.handling_note : '';
  if (nextHandled) {
    const input = window.prompt('处理备注（可选）', note);
    if (input === null) return;
    note = input || '';
  } else {
    note = '';
  }
  if (entry) {
    entry.handled = nextHandled;
    entry.handled_at = nextHandled ? (entry.handled_at || new Date().toISOString().slice(0, 19)) : '';
    entry.handling_note = note;
    if (nextHandled) entry.read = true;
    updateAlertLogSummary();
    renderAlertLog();
  }
  socket.emit('update_alert_log_handling', { id, handled: nextHandled, note });
}

function analyzeAlertFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  activeAlert = entry;
  analyzeActiveAlert();
}

function scrollToAlertRuleCenter() {
  const center = document.getElementById('alertRuleCenterList');
  if (center) center.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function viewAlertRuleFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  const rule = entry.rule_id ? findUnifiedAlertRule(entry.rule_id) : null;
  if (rule) {
    editUnifiedAlertRule(rule.id);
    setAlertRuleCenterStatus('已定位到该警报对应的规则。', 'ok');
  } else {
    alertRuleFilter = 'all';
    activeUnifiedAlertRuleId = null;
    alertRuleDraft = null;
    renderAlertRuleCenter();
    setAlertRuleCenterStatus('原规则已不存在。当前警报保留了历史条件快照，可使用“复制规则”重新创建。', 'fail');
  }
  scrollToAlertRuleCenter();
}

function copyAlertRuleFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  const rule = entry.rule_id ? findUnifiedAlertRule(entry.rule_id) : null;
  if (rule) {
    duplicateUnifiedAlertRule(rule.id);
    scrollToAlertRuleCenter();
    return;
  }
  if (!entry.rule_kind || !entry.rule_condition) {
    setAlertRuleCenterStatus('该历史警报没有可复制的规则快照。', 'fail');
    scrollToAlertRuleCenter();
    return;
  }
  activeUnifiedAlertRuleId = 'new';
  alertRuleFilter = 'all';
  alertRuleDraft = cloneAlertRuleDraft(null);
  alertRuleDraft.kind = entry.rule_kind;
  alertRuleDraft.name = (entry.rule_name || '历史预警规则') + ' 副本';
  alertRuleDraft.scope = Object.assign(
    { mode: entry.mode || currentMode, position_id: entry.portfolio_position_id || null },
    entry.rule_scope || {},
  );
  alertRuleDraft.condition = Object.assign({}, entry.rule_condition || {});
  alertRuleDraft.delivery = { channels: 'inherit', cooldown_minutes: 'inherit' };
  alertRuleDraft.legacy = {};
  renderAlertRuleCenter();
  setAlertRuleCenterStatus('已从历史警报生成规则草稿，请确认后保存。', 'ok');
  scrollToAlertRuleCenter();
}

function openAlertTimelineFromLog(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  openEventTimelineAround(entry.timestamp || entry.time, 'alert', entry.id);
}

function handleAlertLogTimelineClick(event) {
  const button = event.target && event.target.closest ? event.target.closest('[data-log-timeline-id]') : null;
  if (!button) return;
  event.preventDefault();
  event.stopPropagation();
  openAlertTimelineFromLog(decodeURIComponent(button.getAttribute('data-log-timeline-id') || ''));
}

document.addEventListener('click', handleAlertLogTimelineClick, true);

function resendAlertNotification(id) {
  const status = document.getElementById('alertLogStatus');
  status.textContent = '正在重新提交通知...';
  status.className = 'log-status';
  socket.emit('resend_alert_notification', { id });
}

function exportAlertLog() {
  const status = document.getElementById('alertLogStatus');
  status.textContent = '正在导出警报记录...';
  status.className = 'log-status';
  socket.emit('export_alert_log');
}

function clearAlertLog() {
  if (!alertEntries.length) {
    const status = document.getElementById('alertLogStatus');
    status.textContent = '当前没有可清空的警报记录。';
    status.className = 'log-status';
    return;
  }
  if (!confirm('确定清空当前警报记录吗？')) return;
  socket.emit('clear_alert_log');
}

window.openEventTimelineAround = openEventTimelineAround;
window.openAlertTimelineFromLog = openAlertTimelineFromLog;
window.openRiskTimelineFromHistory = openRiskTimelineFromHistory;

// ========== 标题闪烁 ==========
let flashTimer = null;
function flashTitle(type) {
  if (flashTimer) clearTimeout(flashTimer);
  const orig = document.title, alertTitle = '['+type+'] 金价监控';
  let count = 0; document.title = alertTitle;
  flashTimer = setInterval(() => {
    document.title = count % 2 === 0 ? orig : alertTitle;
    count++;
    if (count >= 6) { clearInterval(flashTimer); flashTimer = null; document.title = orig; }
  }, 800);
}
