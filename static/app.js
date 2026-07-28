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
const SETTINGS_TABS = ['general', 'email', 'webhook', 'digest', 'risk', 'ops'];
const SETTINGS_TAB_STORAGE_KEY = 'goldmonitor.settings.activeTab';
const SETTINGS_TAB_LABELS = {
  general: '通用设置',
  email: '邮件通知',
  webhook: 'Webhook',
  digest: '摘要通知',
  risk: '风险分析',
  ops: '运维与数据',
};
const SETTINGS_FIELD_IDS = [
  'setStartup', 'setStartupTray', 'setFloatingPrice', 'setFloatingDisplayMode',
  'setFloatingPreset', 'setFloatingOpacity', 'setFloatingSnapEdge', 'setFloatingAlwaysOnTop',
  'setCloseBehavior', 'setAlertSound', 'setAlertDialog', 'setAlertCooldownMinutes',
  'setAlertQuietStart', 'setAlertQuietEnd', 'setSmtpServer', 'setSmtpPort',
  'setSmtpEncryption', 'setSmtpSender', 'setSmtpPassword', 'clearSmtpPassword',
  'setSmtpRecipient', 'setEmailSubjectTemplate', 'setEmailBodyTemplate', 'setWebhookEnabled',
  'setWebhookUrl', 'setWebhookWarning', 'setWebhookCritical', 'setWebhookVolatility',
  'setDailyDigestEnabled', 'setDailyDigestTime', 'setDailyDigestEmail', 'setDailyDigestWebhook',
  'setRiskAssistantEnabled', 'setRiskAssistantProvider', 'setRiskAssistantDepth',
  'setDeepseekBaseUrl', 'setDeepseekModel', 'setDeepseekApiKey', 'clearDeepseekApiKey',
  'setOpenaiCompatibleBaseUrl', 'setOpenaiCompatibleModel', 'setOpenaiCompatibleApiKey',
  'clearOpenaiCompatibleApiKey', 'setRiskMaxTokens', 'setRiskCooldownSeconds',
  'setRiskCacheMinutes', 'setExportDir',
];
let settingsInitialSnapshot = '';
let settingsDirty = false;
let settingsLastFocused = null;
let activeSettingsTab = 'general';
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
let deepseekModelOptions = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'];
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
    setSettingsSaving(false);
    return;
  }
  applySettings(data || {});
  if (shouldClearProfileMatch) clearCurrentAlertProfileMatch();
  pendingSettingsSave = false;
  resetSettingsDirtySnapshot();
  showSettingsMessage('设置已保存并生效。', 'ok');
});

socket.on('settings_error', data => {
  if (settingsSaveTimer) {
    clearTimeout(settingsSaveTimer);
    settingsSaveTimer = null;
  }
  pendingSettingsSave = false;
  settingsSaveFailed = true;
  setSettingsDirty(true);
  showSettingsMessage(data.message || '设置保存失败。', 'error');
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

registerRiskAnalysisSocketHandlers(socket);

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

registerHistoryReviewSocketHandlers(socket);

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
  status.dataset.state = configured ? 'ok' : '';
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
    status.dataset.state = 'error';
    button.textContent = '取消删除';
    button.classList.add('marked');
    updateSettingsDirtyState();
    return;
  }
  status.textContent = button.dataset.defaultStatus || '';
  status.dataset.state = button.disabled ? '' : 'ok';
  button.textContent = button.dataset.defaultLabel || '删除已保存密钥';
  button.classList.remove('marked');
  updateSettingsDirtyState();
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
  status.className = 'setting-status setting-status-wide';
  if (ok === true) status.dataset.state = 'ok';
  else if (ok === false) status.dataset.state = 'error';
  else delete status.dataset.state;
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
    delete status.dataset.state;
    return;
  }
  const statusClass = data.ok ? 'ok' : 'fail';
  status.dataset.state = data.ok ? 'ok' : 'error';
  const actions = Array.isArray(data.actions) ? data.actions.map(exportDirActionButton).filter(Boolean) : [];
  status.innerHTML = [
    '<span class="export-dir-check ' + statusClass + '">' + escapeHtml(data.message || fallbackText || '') + '</span>',
    actions.length ? '<span class="export-dir-actions">' + actions.join('') + '</span>' : '',
  ].join('');
}

function clearSettingsMessage() {
  showSettingsMessage('', '');
}

function resetExportDirField() {
  const input = document.getElementById('setExportDir');
  if (!input) return;
  input.value = '';
  clearSettingsMessage();
  renderExportDirStatus(null, '保存后将使用默认导出目录：' + (appSettings.export_dir_default || appSettings.export_dir_effective || '未记录'));
  updateSettingsDirtyState();
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
      updateSettingsDirtyState();
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
  if (status) {
    status.textContent = '正在获取模型列表...';
    delete status.dataset.state;
  }
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

function settingsFieldElements() {
  return SETTINGS_FIELD_IDS.map(id => document.getElementById(id)).filter(Boolean);
}

function captureSettingsSnapshot() {
  const snapshot = {};
  settingsFieldElements().forEach(element => {
    snapshot[element.id] = element.type === 'checkbox' ? !!element.checked : element.value;
  });
  return JSON.stringify(snapshot);
}

function showSettingsMessage(message, state) {
  const element = document.getElementById('settingsMessage');
  if (!element) return;
  element.textContent = message || '';
  if (state) element.dataset.state = state;
  else delete element.dataset.state;
}

function setSettingsSaving(saving) {
  const button = document.getElementById('settingsSaveButton');
  if (!button) return;
  button.textContent = saving ? '正在保存' : '保存更改';
  button.disabled = !!saving || !settingsDirty;
}

function setSettingsDirty(dirty) {
  settingsDirty = !!dirty;
  const state = document.getElementById('settingsDirtyState');
  if (state) {
    state.textContent = settingsDirty ? '有未保存的更改' : '所有更改已保存';
    state.classList.toggle('changed', settingsDirty);
  }
  setSettingsSaving(pendingSettingsSave);
}

function updateSettingsDirtyState() {
  if (!settingsInitialSnapshot) return;
  setSettingsDirty(captureSettingsSnapshot() !== settingsInitialSnapshot);
}

function resetSettingsDirtySnapshot() {
  settingsInitialSnapshot = captureSettingsSnapshot();
  setSettingsDirty(false);
  hideSettingsDiscardPrompt();
}

function readStoredSettingsTab() {
  try {
    const stored = window.localStorage.getItem(SETTINGS_TAB_STORAGE_KEY) || '';
    return SETTINGS_TABS.includes(stored) ? stored : 'general';
  } catch (_error) {
    return 'general';
  }
}

function storeSettingsTab(tab) {
  try {
    window.localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, tab);
  } catch (_error) {
    // 本机浏览器禁用存储时，仅在当前会话中保留分页。
  }
}

function settingsTabForElement(element) {
  const panel = element && element.closest ? element.closest('[data-settings-panel]') : null;
  return panel ? panel.dataset.settingsPanel : 'general';
}

function clearSettingsValidation() {
  const modal = document.querySelector('.settings-primary-modal');
  if (!modal) return;
  modal.querySelectorAll('.invalid').forEach(element => element.classList.remove('invalid'));
  modal.querySelectorAll('[aria-invalid="true"]').forEach(element => {
    element.removeAttribute('aria-invalid');
    const describedBy = element.getAttribute('aria-describedby') || '';
    if (describedBy.endsWith('Error')) element.removeAttribute('aria-describedby');
  });
  modal.querySelectorAll('.setting-field-error').forEach(element => element.remove());
  modal.querySelectorAll('.settings-tab.has-error').forEach(element => element.classList.remove('has-error'));
}

function clearSettingsFieldError(element) {
  if (!element) return;
  element.classList.remove('invalid');
  const inlineCheck = element.closest('.inline-check');
  if (inlineCheck) inlineCheck.classList.remove('invalid');
  element.removeAttribute('aria-invalid');
  const error = document.getElementById(element.id + 'Error');
  if (error) error.remove();
  const tab = settingsTabForElement(element);
  const panel = document.querySelector('[data-settings-panel="' + tab + '"]');
  if (panel && !panel.querySelector('.setting-field-error')) {
    const tabButton = document.querySelector('[data-settings-tab="' + tab + '"]');
    if (tabButton) tabButton.classList.remove('has-error');
  }
}

function renderSettingsValidation(errors) {
  clearSettingsValidation();
  errors.forEach(error => {
    const element = document.getElementById(error.id);
    if (!element) return;
    const highlight = element.closest('.inline-check') || element;
    highlight.classList.add('invalid');
    element.setAttribute('aria-invalid', 'true');
    const row = element.closest('.setting-row');
    if (row && !document.getElementById(error.id + 'Error')) {
      const note = document.createElement('div');
      note.className = 'setting-field-error';
      note.id = error.id + 'Error';
      note.textContent = error.message;
      row.appendChild(note);
      element.setAttribute('aria-describedby', note.id);
    }
    const tabButton = document.querySelector('[data-settings-tab="' + error.tab + '"]');
    if (tabButton) tabButton.classList.add('has-error');
  });
}

function validateSettings() {
  const errors = [];
  const add = (id, message) => {
    const element = document.getElementById(id);
    if (!element) return;
    errors.push({ id, message, tab: settingsTabForElement(element) });
  };
  const validateNumber = (id, label, min, max) => {
    const element = document.getElementById(id);
    if (!element || element.value.trim() === '') return;
    const value = Number(element.value);
    if (!Number.isFinite(value) || value < min || value > max) add(id, label + '应在 ' + min + ' 到 ' + max + ' 之间。');
  };
  const validateTypedValue = (id, message) => {
    const element = document.getElementById(id);
    if (element && element.value.trim() && !element.validity.valid) add(id, message);
  };

  validateNumber('setFloatingOpacity', '悬浮条透明度', 50, 100);
  validateNumber('setAlertCooldownMinutes', '提醒冷却时间', 0, 240);
  validateNumber('setSmtpPort', 'SMTP 端口', 1, 65535);
  validateNumber('setRiskMaxTokens', '单次输出上限', 300, 4000);
  validateNumber('setRiskCooldownSeconds', '分析冷却时间', 0, 300);
  validateNumber('setRiskCacheMinutes', '重复分析缓存', 0, 60);
  validateTypedValue('setSmtpSender', '发件邮箱格式不正确。');
  validateTypedValue('setSmtpRecipient', '收件邮箱格式不正确。');
  validateTypedValue('setWebhookUrl', 'Webhook 地址格式不正确。');
  validateTypedValue('setDeepseekBaseUrl', 'DeepSeek API 地址格式不正确。');
  validateTypedValue('setOpenaiCompatibleBaseUrl', '兼容接口地址格式不正确。');

  const quietStart = document.getElementById('setAlertQuietStart').value;
  const quietEnd = document.getElementById('setAlertQuietEnd').value;
  if (!!quietStart !== !!quietEnd) add(quietStart ? 'setAlertQuietEnd' : 'setAlertQuietStart', '静默时段需要同时填写开始和结束时间。');

  if (document.getElementById('setWebhookEnabled').checked) {
    const webhookUrl = document.getElementById('setWebhookUrl').value.trim();
    if (!webhookUrl) add('setWebhookUrl', '启用 Webhook 前需要填写接收地址。');
    else if (!webhookUrl.toLowerCase().startsWith('https://')) add('setWebhookUrl', 'Webhook 地址必须使用 HTTPS。');
  }

  if (document.getElementById('setDailyDigestEnabled').checked) {
    if (!document.getElementById('setDailyDigestTime').value) add('setDailyDigestTime', '启用每日摘要前需要设置发送时间。');
    if (!document.getElementById('setDailyDigestEmail').checked && !document.getElementById('setDailyDigestWebhook').checked) {
      add('setDailyDigestEmail', '启用每日摘要前至少选择一个发送渠道。');
    }
  }

  if (document.getElementById('setRiskAssistantEnabled').checked) {
    const provider = document.getElementById('setRiskAssistantProvider').value;
    if (provider === 'deepseek') {
      if (!document.getElementById('setDeepseekBaseUrl').value.trim()) add('setDeepseekBaseUrl', '需要填写 DeepSeek API 地址。');
      if (!document.getElementById('setDeepseekModel').value) add('setDeepseekModel', '需要选择 DeepSeek 模型。');
    } else {
      if (!document.getElementById('setOpenaiCompatibleBaseUrl').value.trim()) add('setOpenaiCompatibleBaseUrl', '需要填写兼容接口地址。');
      if (!document.getElementById('setOpenaiCompatibleModel').value.trim()) add('setOpenaiCompatibleModel', '需要填写兼容模型名称。');
    }
  }

  renderSettingsValidation(errors);
  if (!errors.length) return true;
  const first = errors[0];
  switchSettingsTab(first.tab);
  showSettingsMessage(
    SETTINGS_TAB_LABELS[first.tab] + '有 ' + errors.filter(error => error.tab === first.tab).length + ' 项需要处理：' + first.message,
    'error'
  );
  window.requestAnimationFrame(() => {
    const element = document.getElementById(first.id);
    if (element) element.focus();
  });
  return false;
}

function handleSettingsFieldChange(event) {
  const target = event.target;
  if (!target || !SETTINGS_FIELD_IDS.includes(target.id)) return;
  clearSettingsFieldError(target);
  if (target.id === 'setDailyDigestEmail' || target.id === 'setDailyDigestWebhook') {
    clearSettingsFieldError(document.getElementById('setDailyDigestEmail'));
  }
  if (target.id === 'setAlertQuietStart' || target.id === 'setAlertQuietEnd') {
    clearSettingsFieldError(document.getElementById('setAlertQuietStart'));
    clearSettingsFieldError(document.getElementById('setAlertQuietEnd'));
  }
  const message = document.getElementById('settingsMessage');
  if (message && message.dataset.state === 'error') showSettingsMessage('', '');
  updateSettingsDirtyState();
}

function handleSettingsTabKeydown(event) {
  const current = event.target.closest && event.target.closest('.settings-tab');
  if (!current) return;
  const tabs = Array.from(document.querySelectorAll('.settings-tab'));
  const index = tabs.indexOf(current);
  if (index < 0) return;
  let nextIndex = index;
  if (event.key === 'ArrowDown' || event.key === 'ArrowRight') nextIndex = (index + 1) % tabs.length;
  else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') nextIndex = (index - 1 + tabs.length) % tabs.length;
  else if (event.key === 'Home') nextIndex = 0;
  else if (event.key === 'End') nextIndex = tabs.length - 1;
  else return;
  event.preventDefault();
  const next = tabs[nextIndex];
  switchSettingsTab(next.dataset.settingsTab);
  next.focus();
}

function switchSettingsTab(tab) {
  const nextTab = SETTINGS_TABS.includes(tab) ? tab : 'general';
  activeSettingsTab = nextTab;
  SETTINGS_TABS.forEach(name => {
    const active = nextTab === name;
    const suffix = name.charAt(0).toUpperCase() + name.slice(1);
    const tabButton = document.getElementById('settingsTab' + suffix);
    const panel = document.getElementById('settingsPanel' + suffix);
    tabButton.classList.toggle('active', active);
    tabButton.setAttribute('aria-selected', String(active));
    tabButton.tabIndex = active ? 0 : -1;
    panel.classList.toggle('active', active);
    panel.hidden = !active;
  });
  storeSettingsTab(nextTab);
  const activeButton = document.querySelector('[data-settings-tab="' + nextTab + '"]');
  if (activeButton) {
    window.requestAnimationFrame(() => activeButton.scrollIntoView({ block: 'nearest', inline: 'nearest' }));
  }
  const body = document.querySelector('#settingsBackdrop .settings-body');
  if (body) body.scrollTop = 0;
  if (nextTab === 'risk') refreshRiskModels();
  if (nextTab === 'digest') socket.emit('get_daily_digest_status');
}

function openSettings() {
  settingsLastFocused = document.activeElement;
  applySettings(appSettings);
  clearSettingsValidation();
  showSettingsMessage('', '');
  document.getElementById('settingsBackdrop').classList.add('show');
  switchSettingsTab(readStoredSettingsTab());
  resetSettingsDirtySnapshot();
  window.requestAnimationFrame(() => {
    const activeTab = document.querySelector('.settings-tab.active');
    if (activeTab) activeTab.focus();
  });
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
  if (settingsDirty || pendingSettingsSave) {
    showSettingsMessage('请先保存或放弃当前更改，再重新打开首次使用向导。', 'error');
    return;
  }
  closeSettings(true);
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

function hideSettingsDiscardPrompt() {
  const prompt = document.getElementById('settingsUnsavedConfirm');
  if (prompt) prompt.hidden = true;
}

function discardSettingsChanges() {
  closeSettings(true);
}

function settingsFocusableElements() {
  const modal = document.querySelector('.settings-primary-modal');
  if (!modal) return [];
  return Array.from(modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'))
    .filter(element => !element.hidden && element.offsetParent !== null);
}

function handleSettingsDialogKeydown(event) {
  const backdrop = document.getElementById('settingsBackdrop');
  if (!backdrop || !backdrop.classList.contains('show')) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    closeSettings();
    return;
  }
  if (event.key !== 'Tab') return;
  const focusable = settingsFocusableElements();
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function closeSettings(force) {
  const backdrop = document.getElementById('settingsBackdrop');
  if (!backdrop || !backdrop.classList.contains('show')) return;
  if (!force && pendingSettingsSave) {
    showSettingsMessage('设置正在保存，请等待后台确认。', '');
    return;
  }
  if (!force && settingsDirty) {
    const prompt = document.getElementById('settingsUnsavedConfirm');
    if (prompt) prompt.hidden = false;
    const discardButton = document.getElementById('settingsDiscardButton');
    if (discardButton) discardButton.focus();
    return;
  }
  backdrop.classList.remove('show');
  hideSettingsDiscardPrompt();
  clearSettingsValidation();
  settingsInitialSnapshot = '';
  settingsDirty = false;
  if (settingsLastFocused && typeof settingsLastFocused.focus === 'function') settingsLastFocused.focus();
  settingsLastFocused = null;
}

function onSettingsBackdrop(event) {
  if (event.target.id === 'settingsBackdrop') closeSettings();
}

function setupSettingsInteractions() {
  const backdrop = document.getElementById('settingsBackdrop');
  const tabs = document.querySelector('.settings-primary-modal .settings-tabs');
  if (backdrop) {
    backdrop.addEventListener('input', handleSettingsFieldChange);
    backdrop.addEventListener('change', handleSettingsFieldChange);
  }
  if (tabs) tabs.addEventListener('keydown', handleSettingsTabKeydown);
  document.addEventListener('keydown', handleSettingsDialogKeydown);
}

setupSettingsInteractions();

function saveSettings() {
  if (pendingSettingsSave) return;
  if (!settingsDirty) {
    showSettingsMessage('当前没有需要保存的更改。', '');
    return;
  }
  if (!validateSettings()) return;
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
  setSettingsSaving(true);
  showSettingsMessage('正在保存并应用设置...', '');
  socket.emit('update_settings', next);
  if (settingsSaveTimer) clearTimeout(settingsSaveTimer);
  settingsSaveTimer = setTimeout(() => {
    if (!pendingSettingsSave) return;
    pendingSettingsSave = false;
    settingsSaveFailed = true;
    setSettingsDirty(true);
    showSettingsMessage('保存失败：后台服务未响应，请退出托盘中的旧程序后重新打开最新版。', 'error');
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
