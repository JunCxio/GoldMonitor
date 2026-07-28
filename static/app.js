// ========== PWA Service Worker ==========
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
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

registerSettingsSocketHandlers(socket);

socket.on('threshold_error', data => alert(data.message));

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

// ========== 数据源菜单 ==========
function toggleSourceHealthMenu(button) {
  const menu = document.getElementById('sourceHealthMenu');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}
