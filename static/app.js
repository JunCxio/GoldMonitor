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
const CHART_PERIODS = {
  realtime: { label: '价格走势', minutes: null, limit: 60, live: true },
  '1h': { label: '1小时走势', minutes: 60, limit: 360 },
  '4h': { label: '4小时走势', minutes: 240, limit: 720 },
  day: { label: '日内走势', minutes: 1440, limit: 1440 },
  '7d': { label: '7日走势', minutes: 10080, limit: 2000 },
  '5min': { label: '5分钟K线', minutes: null, limit: 96, kline: true },
};
const ALERT_RULE_DEFS = [
  { type: 'upper_warning', title: '上涨关注', direction: '高于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'upper_critical', title: '上涨警告', direction: '高于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
  { type: 'lower_warning', title: '下跌关注', direction: '低于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'lower_critical', title: '下跌警告', direction: '低于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
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
let watchTargets = [];
let portfolioState = { items: [], transactions: [], total: 0, rmb_summary: {}, usd_summary: {}, prices: {} };
let portfolioView = 'positions';
let activePortfolioPositionId = null;
let portfolioDrafts = {};
let activePortfolioTransactionId = null;
let portfolioTransactionDrafts = {};
let pendingPortfolioSave = null;
let activeWatchTargetId = null;
let historyView = 'prices';
let eventTimelineState = { events: [], summary: {}, filters: {}, range: {}, price_summary: {} };
let eventTimelineRange = 60;
let eventTimelineTypes = ['price_summary', 'alert', 'risk_analysis', 'news', 'data_status'];
let selectedTimelineEventId = null;
const EVENT_TIMELINE_TYPE_DEFS = [
  { type: 'price_summary', label: '价格摘要' },
  { type: 'alert', label: '预警' },
  { type: 'risk_analysis', label: '风险分析' },
  { type: 'news', label: '新闻' },
  { type: 'data_status', label: '数据状态' },
];
let appSettings = {
  platform: 'windows',
  platform_capabilities: {},
  startup_enabled: false,
  startup_to_tray: true,
  floating_price_enabled: true,
  floating_price_opacity: 94,
  floating_price_display_mode: 'rmb_usd',
  floating_price_preset: 'compact',
  floating_price_snap_edge: true,
  close_behavior: 'ask',
  close_remembered: false,
  alert_sound_enabled: true,
  alert_dialog_enabled: true,
  webhook_enabled: false,
  webhook_url: '',
  webhook_warning_enabled: true,
  webhook_critical_enabled: true,
  webhook_volatility_enabled: true,
  email_warning_enabled: true,
  email_critical_enabled: true,
  email_volatility_enabled: true,
  alert_cooldown_minutes: 30,
  alert_quiet_start: '',
  alert_quiet_end: '',
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
let autoUpdateTimer = null;
let lastAutoUpdateCheckAt = 0;
const AUTO_UPDATE_CHECK_INTERVAL_MS = 6 * 60 * 60 * 1000;
function autoUpdateIntervalMs() {
  return AUTO_UPDATE_CHECK_INTERVAL_MS;
}
let alertEntries = [];
let alertLogFilter = 'all';
let alertLogSearch = '';
let selectedAlertId = null;
let activeAlert = null;
let mergedAlertCount = 0;
let riskAnalysisRunning = false;
let riskAnalysisHistory = [];
let pendingRiskForceTrigger = null;
let deepseekModelOptions = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'];
let latestPriceHistoryState = { items: [], stats: {}, total: 0 };
let latestSourceHealthState = { items: [], summary: {} };
let latestSourceComparisonState = { items: [], summary: {}, status: 'insufficient' };

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

function chartHistoryLabel(item) {
  const raw = item.timestamp || item.time || '';
  if (!raw) return '--';
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) {
    const hhmm = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false });
    if (chartPeriod === '7d') {
      return (date.getMonth() + 1) + '/' + date.getDate() + ' ' + hhmm;
    }
    return hhmm;
  }
  return String(raw).replace('T', ' ').slice(0, chartPeriod === '7d' ? 16 : 8);
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
  const date = new Date(raw);
  if (!Number.isNaN(date.getTime())) {
    if (chartPeriod === '7d') {
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
  return text.slice(0, chartPeriod === '7d' ? 16 : 5);
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
  document.getElementById('thresholdUnit').textContent = isUsd ? '(USD/oz)' : '(RMB/克)';
  if (latestData) { updatePriceDisplay(latestData); updateDailyStats(latestData); }
  switchChartData();
  updateThresholdInputs();
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
    labels = klines5min.map(k => k.time);
    prices = klines5min.map(k => ({ y: k.close, o: k.open, h: k.high, l: k.low, c: k.close }));
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
  chart.update();
}

// ========== Socket.IO ==========
socket.on('connect', () => {
  document.getElementById('statusDot').classList.remove('disconnected');
  document.getElementById('statusText').textContent = '本地服务已连接';
  document.getElementById('priceRetry').textContent = '重新获取';
});
socket.on('disconnect', () => {
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
  applyWatchTargets(data.watch_targets || []);
  applyPortfolio(data.portfolio || {});
  if (data.settings) applySettings(data.settings);
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
  socket.emit('get_settings');
});

socket.on('price_update', data => {
  latestData = data;

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
    chart.update('none');
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

socket.on('alert_log_status_error', data => {
  const status = document.getElementById('alertLogStatus');
  status.textContent = (data && data.message) || '警报记录状态更新失败。';
  status.className = 'log-status fail';
});

socket.on('alert_notification_resent', data => {
  const status = document.getElementById('alertLogStatus');
  if (data && data.entry) mergeAlertLogEntry(data.entry);
  status.textContent = '通知已重新提交。';
  status.className = 'log-status ok';
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
});

socket.on('volatility_updated', data => {
  volConfig = {
    percent: data.percent != null ? data.percent : null,
    minutes: data.minutes || 10,
    enabled: !!data.enabled,
  };
  updateVolUI();
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
  setPortfolioStatus('持仓已更新。', 'ok');
});

socket.on('portfolio_error', data => {
  pendingPortfolioSave = null;
  setPortfolioStatus((data && data.message) || '持仓更新失败。', 'fail');
});

socket.on('portfolio_exported', data => {
  const count = data && Number.isFinite(Number(data.count)) ? Number(data.count) : portfolioState.total;
  const kindText = data && data.kind === 'transactions' ? '流水' : '持仓';
  setPortfolioStatus(data && data.saved_path ? '已导出' + kindText + ' ' + count + ' 条，保存至 ' + data.saved_path : kindText + '已导出。', 'ok');
});

socket.on('portfolio_export_error', data => {
  setPortfolioStatus((data && data.message) || '持仓导出失败。', 'fail');
});

socket.on('settings_updated', data => {
  applySettings(data || {});
  if (settingsSaveTimer) {
    clearTimeout(settingsSaveTimer);
    settingsSaveTimer = null;
  }
  if (settingsSaveFailed) {
    pendingSettingsSave = false;
    return;
  }
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
  if (data && data.snapshot) renderRiskSnapshot(data.snapshot);
  updateRiskButtonState();
});

socket.on('risk_analysis_cache_hit', data => {
  riskAnalysisRunning = false;
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
  openRiskAnalysis();
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
    setOpsStatus(data.message || '配置导出失败。', false);
    return;
  }
  if (data.saved_path) {
    setOpsStatus('配置已导出：' + data.saved_path, true);
    return;
  }
  if (!data.content) return;
  downloadText(data.filename || 'GoldMonitor-config.json', data.content, 'application/json;charset=utf-8');
  setOpsStatus('配置已导出，文件名：' + (data.filename || 'GoldMonitor-config.json') + '。', true);
});

socket.on('diagnostics_ready', data => {
  if (!data) return;
  if (data.ok === false) {
    setOpsStatus(data.message || '诊断报告导出失败。', false);
    return;
  }
  if (data.saved_path) {
    setOpsStatus('诊断报告已导出：' + data.saved_path, true);
    return;
  }
  if (!data.content) return;
  downloadText(data.filename || 'GoldMonitor-diagnostics.json', data.content, 'application/json;charset=utf-8');
  setOpsStatus('诊断报告已导出，文件名：' + (data.filename || 'GoldMonitor-diagnostics.json') + '。', true);
});

socket.on('exports_folder_opened', data => {
  setOpsStatus(data && data.message ? data.message : '已打开导出目录。', !!(data && data.ok));
});

socket.on('config_import_result', data => {
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

function renderSourceHealth(data) {
  latestSourceHealthState = data || { items: [], summary: {} };
  if (data && data.comparison) renderSourceComparison(data.comparison);
  const box = document.getElementById('sourceHealth');
  if (!box) return;
  const items = Array.isArray(data.items) ? data.items : [];
  const summary = data.summary || {};
  const head = box.querySelector('.source-health-head span');
  const list = box.querySelector('.source-health-list');
  head.textContent = '正常 ' + (summary.ok || 0) + ' · 异常 ' + (summary.failed || 0) + ' · 缓存 ' + (summary.cached || 0);
  if (!items.length) {
    list.innerHTML = '<div class="source-health-item"><span class="source-health-dot"></span><span class="source-health-name">等待数据源检查</span><span class="source-health-meta">--</span></div>';
    return;
  }
  list.innerHTML = items.map(item => {
    const cls = item.cached ? 'cached' : item.ok ? 'ok' : 'fail';
    const elapsed = item.elapsed_ms == null ? '--' : item.elapsed_ms + 'ms';
    const status = item.cached ? '缓存' : item.ok ? '正常' : '异常';
    const title = item.error ? item.error : status;
    return [
      '<div class="source-health-item" title="' + escapeHtml(title) + '">',
      '<span class="source-health-dot ' + cls + '"></span>',
      '<span class="source-health-name">' + escapeHtml(item.name || '--') + '</span>',
      '<span class="source-health-meta">' + escapeHtml(status + ' · ' + elapsed) + '</span>',
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
  eventTimelineRange = [60, 240, 1440, 10080].includes(minutes) ? minutes : 60;
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
  if (selectedTimelineEventId && !events.some(event => event.id === selectedTimelineEventId)) {
    selectedTimelineEventId = null;
  }
  setTimelineStatus('', '');
  renderEventTimeline();
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
    ['跳过', summary.skipped || 0],
    ['预警', byType.alert || 0],
    ['范围', range.minutes ? Math.round(Number(range.minutes) / 60) + 'h' : '--'],
  ];
  box.innerHTML = statItems.map(item => (
    '<div class="history-stat"><div class="history-stat-label">' + escapeHtml(item[0]) + '</div><div class="history-stat-value">' + escapeHtml(item[1]) + '</div></div>'
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
    '<span class="timeline-event-summary">' + escapeHtml(event.summary || '暂无详情') + '</span>',
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
    cells.push(detailCell('读取状态', payload.read ? '已读' : '未读'));
    cells.push(detailCell('处理状态', payload.acknowledged ? '已确认' : '未确认'));
    if (Array.isArray(payload.related_news) && payload.related_news.length) {
      extras += '<div class="timeline-detail-news">' + payload.related_news.slice(0, 3).map(item => (
        '<a href="' + escapeHtml(item.url || '#') + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(item.title || '相关新闻') + '</a>'
      )).join('') + '</div>';
    }
  } else if (event.type === 'risk_analysis') {
    const structured = payload.structured || {};
    const quality = payload.data_quality || {};
    cells.push(detailCell('模型', [payload.provider, payload.model].filter(Boolean).join(' / ')));
    cells.push(detailCell('可信度', quality.score == null ? '' : quality.score + '分'));
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
  }
  detail.innerHTML = [
    '<div class="timeline-detail-title">' + escapeHtml(event.title || timelineTypeLabel(event.type)) + '</div>',
    '<div class="timeline-detail-meta">' + escapeHtml(timelineEventTime(event.timestamp)) + ' · ' + escapeHtml(event.source || '--') + '</div>',
    '<div class="timeline-detail-summary">' + escapeHtml(payload.message || payload.content || event.summary || '暂无详情') + '</div>',
    '<div class="timeline-detail-grid">' + cells.join('') + '</div>',
    extras,
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

function exportConfig() {
  setOpsStatus('正在导出配置...', true);
  socket.emit('export_config');
}

function importConfig() {
  const text = document.getElementById('configImportText').value.trim();
  if (!text) {
    setOpsStatus('请先粘贴配置备份 JSON。', false);
    return;
  }
  setOpsStatus('正在导入配置...', true);
  socket.emit('import_config', { payload: text });
}

function exportDiagnostics() {
  setOpsStatus('正在生成诊断报告...', true);
  socket.emit('get_diagnostics');
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
    status.textContent = '正在测试当前模型...';
    status.className = 'model-test-status';
  }
  socket.emit('test_risk_model');
}

function switchSettingsTab(tab) {
  const tabs = ['general', 'email', 'webhook', 'risk', 'ops'];
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
}

function openSettings() {
  applySettings(appSettings);
  switchSettingsTab('general');
  document.getElementById('settingsMessage').textContent = '';
  document.getElementById('settingsBackdrop').classList.add('show');
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
function openRiskAnalysis() {
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

function updateRiskButtonState() {
  const runBtn = document.getElementById('riskRunButton');
  const openBtn = document.getElementById('riskAnalyzeButton');
  const forceBtn = document.getElementById('riskForceRunButton');
  const disabled = riskAnalysisRunning || !appSettings.risk_assistant_enabled || !!riskProviderErrorMessage();
  if (runBtn) {
    runBtn.disabled = disabled;
    runBtn.textContent = riskAnalysisRunning ? '分析中...' : '开始分析';
  }
  if (forceBtn) forceBtn.disabled = disabled;
  if (openBtn) openBtn.disabled = !appSettings.risk_assistant_enabled;
}

function requestRiskAnalysis(trigger, force) {
  if (riskAnalysisRunning) return;
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

function renderRiskSnapshot(snapshot) {
  const meta = document.getElementById('riskMeta');
  if (!snapshot) {
    meta.innerHTML = '';
    meta.classList.remove('show');
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
  if (snapshot.data_quality) items.push('可信度 ' + snapshot.data_quality.score + '分/' + snapshot.data_quality.level);
  if (snapshot.sample_warning) items.push(snapshot.sample_warning);
  meta.innerHTML = items.map(item => '<span>' + escapeHtml(item) + '</span>').join('');
  meta.classList.add('show');
  renderRiskQuality(snapshot.data_quality || null);
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
  el.innerHTML = [
    '<div class="risk-block-title">数据可信度</div>',
    '<div class="risk-quality-score">' + escapeHtml(quality.score == null ? '--' : quality.score) + '</div>',
    '<div class="risk-quality-level">等级 ' + escapeHtml(quality.level || '--') + '</div>',
    '<div class="risk-quality-summary">' + escapeHtml(quality.summary || '暂无说明') + '</div>',
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
  renderRiskHistory();
}

function renderRiskHistory() {
  const list = document.getElementById('riskHistoryList');
  const clearBtn = document.getElementById('riskClearHistoryButton');
  if (clearBtn) clearBtn.disabled = riskAnalysisHistory.length === 0;
  if (!riskAnalysisHistory.length) {
    list.innerHTML = '<div class="risk-history-empty">暂无历史记录</div>';
    return;
  }
  list.innerHTML = riskAnalysisHistory.map((item, index) => {
    const firstLine = String(item.content || '').split('\n').find(Boolean) || '历史分析';
    const quality = item.snapshot && item.snapshot.data_quality ? ' · 可信度 ' + item.snapshot.data_quality.score + '分' : '';
    return [
      '<button class="risk-history-item" type="button" onclick="openRiskHistoryItem(' + index + ')">',
      '<div class="risk-history-time">' + escapeHtml(item.analysis_time || '--') + escapeHtml(quality) + '</div>',
      '<div class="risk-history-text">' + escapeHtml(firstLine) + '</div>',
      '</button>',
    ].join('');
  }).join('');
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

function clearRiskHistory() {
  if (riskAnalysisRunning) return;
  socket.emit('clear_risk_analysis_history');
}

function currentRiskReportMarkdown() {
  const result = document.getElementById('riskResult').textContent || '';
  const meta = Array.from(document.querySelectorAll('#riskMeta span')).map(item => item.textContent).join('\n');
  const parts = ['# 风险分析报告'];
  if (meta) parts.push('', '## 数据快照', meta);
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

function checkUpdate() {
  requestUpdateCheck(false);
}

function requestUpdateCheck(silent) {
  pendingUpdateInfo = null;
  document.getElementById('updateButton').classList.remove('update-ready');
  document.getElementById('installUpdateButton').disabled = true;
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
  const message = data.message || (ok ? '行情数据正常' : '行情数据获取失败');
  retry.textContent = data.reconnect ? '重新连接' : '重新获取';
  stale.textContent = message;
  retry.disabled = data.retryable === false;

  if (ok) {
    stale.classList.remove('show');
    retry.classList.remove('show');
    return;
  }

  stale.classList.add('show');
  if (data.retryable !== false) retry.classList.add('show');
  else retry.classList.remove('show');
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
  document.getElementById('alertBackdrop').classList.remove('show');
  activeAlert = null;
  mergedAlertCount = 0;
  openRiskAnalysis();
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
  if (price == null) { priceEl.textContent = '--'; document.title = BASE_TITLE; return; }

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
    '<button class="btn-clear-sm" type="button" onclick="clearThreshold(\'' + rule.type + '\')">关闭</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'' + rule.type + '\')">取消</button>',
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
    '<button class="btn-clear-sm" type="button" onclick="clearVolatility()">关闭</button>',
    '<button class="btn-clear-sm" type="button" onclick="setActiveAlertRule(\'volatility\')">取消</button>',
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
    '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="' + rule.clear + '">关闭</button>',
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
  };
}

function applyPortfolio(data) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  portfolioState = normalizePortfolioState(data);
  if (activePortfolioPositionId && activePortfolioPositionId !== 'new' && !portfolioState.items.some(item => item.id === activePortfolioPositionId)) {
    clearPortfolioDraft(activePortfolioPositionId);
    activePortfolioPositionId = null;
  }
  if (activePortfolioTransactionId && activePortfolioTransactionId !== 'new' && !portfolioState.transactions.some(item => item.id === activePortfolioTransactionId)) {
    clearPortfolioTransactionDraft(activePortfolioTransactionId);
    activePortfolioTransactionId = null;
  }
  if (pendingPortfolioSave) {
    if (pendingPortfolioSave.kind === 'transaction') {
      clearPortfolioTransactionDraft(pendingPortfolioSave.id);
      if (activePortfolioTransactionId === pendingPortfolioSave.id) activePortfolioTransactionId = null;
    } else if (pendingPortfolioSave.kind === 'position') {
      clearPortfolioDraft(pendingPortfolioSave.id);
      if (activePortfolioPositionId === pendingPortfolioSave.id) activePortfolioPositionId = null;
    }
    pendingPortfolioSave = null;
  }
  renderPortfolio();
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

function portfolioTransactionBaseDraft(item) {
  const isNew = !item || item.id === 'new';
  const source = item || {};
  return {
    id: isNew ? 'new' : source.id,
    position_id: source.position_id || '',
    name: source.name || '',
    type: source.type || 'buy',
    mode: source.mode || currentMode,
    price: source.price == null ? '' : String(source.price),
    quantity: source.quantity == null ? '' : String(source.quantity),
    fee: source.fee == null ? '0' : String(source.fee),
    trade_date: source.trade_date || '',
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
  renderPortfolioSummary();
  renderPortfolioTabs();
  const box = document.getElementById('portfolioList');
  if (!box) return;
  if (portfolioView === 'transactions') {
    renderPortfolioTransactions(box);
    return;
  }
  renderPortfolioPositions(box);
}

function renderPortfolioPositions(box) {
  const items = Array.isArray(portfolioState.items) ? portfolioState.items : [];
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
    parts.push('<div class="portfolio-empty">暂无持仓</div>');
  }
  parts.push(...items.map(item => {
    const cls = [
      'portfolio-item',
      activePortfolioPositionId === item.id ? 'expanded' : '',
    ].filter(Boolean).join(' ');
    const mode = item.mode || 'rmb';
    const quantity = formatPortfolioNumber(item.quantity, 2);
    const unit = portfolioQuantityUnit(mode);
    const averageCost = formatPortfolioMoney(item.average_cost != null ? item.average_cost : item.entry_price, mode);
    const currentPrice = item.current_price == null ? '等待行情' : formatPortfolioMoney(item.current_price, mode);
    const valuationLabel = portfolioValuationLabel(item);
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
      '<span class="alert-rule-state ' + (item.valuation_status === 'valued' ? 'on' : 'off') + '">' + escapeHtml(item.valuation_status === 'valued' ? '已估值' : item.valuation_status === 'closed' ? '清仓' : '等待') + '</span>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'buy\')">买入</button>',
      '<button class="btn-clear-sm alert-rule-edit" type="button" onclick="startPortfolioTransactionForPosition(\'' + escapeHtml(item.id) + '\', \'sell\')">卖出</button>',
      '</div>',
      activePortfolioPositionId === item.id ? buildPortfolioEditor(item) : '',
      '</div>',
    ].join('');
  }));
  box.innerHTML = parts.join('');
}

function renderPortfolioTransactions(box) {
  const transactions = Array.isArray(portfolioState.transactions) ? portfolioState.transactions : [];
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
    parts.push('<div class="portfolio-empty">暂无流水</div>');
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
  if (nameInput && !nameInput.value) nameInput.value = item.name || '';
  if (modeInput) modeInput.value = item.mode || currentMode;
  capturePortfolioTransactionDraft(id);
}

function setPortfolioView(view) {
  captureActivePortfolioDraft();
  captureActivePortfolioTransactionDraft();
  portfolioView = view === 'transactions' ? 'transactions' : 'positions';
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
  const defaults = item ? {
    position_id: item.id,
    name: item.name || '',
    type: type === 'sell' ? 'sell' : 'buy',
    mode: item.mode || currentMode,
    price: '',
    quantity: '',
    fee: '0',
    trade_date: '',
    note: '',
  } : { type: type === 'sell' ? 'sell' : 'buy', mode: currentMode, fee: '0' };
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
  if (activePortfolioPositionId === id) activePortfolioPositionId = null;
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
  const exportKind = kind === 'transactions' ? 'transactions' : 'positions';
  setPortfolioStatus(exportKind === 'transactions' ? '正在导出流水...' : '正在导出持仓...', '');
  socket.emit('export_portfolio', { kind: exportKind });
}

// ========== 日志 ==========
function normalizeAlertEntry(entry) {
  const item = entry && typeof entry === 'object' ? { ...entry } : {};
  item.id = item.id || 'local-' + (item.timestamp || Date.now()) + '-' + Math.random().toString(16).slice(2);
  item.read = item.read === true;
  item.acknowledged = item.acknowledged === true;
  if (item.acknowledged) item.read = true;
  return item;
}

function setAlertEntries(items) {
  alertEntries = Array.isArray(items) ? items.slice(-50).map(normalizeAlertEntry) : [];
  if (selectedAlertId && !alertEntries.some(entry => entry.id === selectedAlertId)) selectedAlertId = null;
  updateAlertLogSummary();
  renderAlertDetail();
  renderAlertLog();
}

function setAlertLogFilter(value) {
  alertLogFilter = value || 'all';
  renderAlertLog();
}

function setAlertLogSearch(value) {
  alertLogSearch = (value || '').trim().toLowerCase();
  renderAlertLog();
}

function updateAlertLogSummary() {
  const countEl = document.getElementById('alertUnreadCount');
  const unread = alertEntries.filter(entry => !entry.read).length;
  countEl.textContent = unread + ' 未读';
  countEl.className = 'log-count' + (unread ? '' : ' empty');
}

function alertLogMatchesFilter(entry) {
  if (alertLogFilter === 'unread') return !entry.read;
  if (alertLogFilter === 'pending') return !entry.acknowledged;
  if (alertLogFilter === 'all') return true;
  return (entry.type || '') === alertLogFilter;
}

function alertLogMatchesSearch(entry) {
  if (!alertLogSearch) return true;
  const haystack = [
    entry.time, entry.timestamp, entry.type, entry.mode, entry.message,
    alertLevelLabel(entry.type), alertModeLabel(entry.mode),
  ].join(' ').toLowerCase();
  return haystack.includes(alertLogSearch);
}

function alertStatusLabel(entry) {
  if (entry.acknowledged) return '已确认';
  if (entry.read) return '已读';
  return '未读';
}

function renderNotificationBadges(entry) {
  const items = Array.isArray(entry.notifications) ? entry.notifications : [];
  if (!items.length) return '';
  return '<span class="log-notify">' + items.map(item => {
    const status = item.status || '';
    const cls = status === 'queued' ? 'ok' : (status === 'skipped' ? 'fail' : (status === 'muted' ? 'muted' : ''));
    const label = item.label || item.channel || '通知';
    const message = item.message ? '：' + item.message : '';
    return '<span class="log-notify-badge ' + cls + '">' + escapeHtml(label + message) + '</span>';
  }).join('') + '</span>';
}

function buildLogEntry(entry) {
  const button = document.createElement('button');
  const selected = selectedAlertId === entry.id;
  button.type = 'button';
  button.className = [
    'log-item',
    entry.read ? 'read' : 'unread',
    entry.acknowledged ? 'acknowledged' : '',
    selected ? 'active' : '',
  ].filter(Boolean).join(' ');
  button.onclick = () => selectAlertEntry(entry.id);
  const stateBadge = entry.acknowledged
    ? '<span class="log-state-badge ack">已确认</span>'
    : (entry.read ? '<span class="log-state-badge">已读</span>' : '<span class="log-state-badge unread">未读</span>');
  button.innerHTML = [
    '<span class="log-unread-dot"></span>',
    '<span class="log-meta">',
    '<span class="log-time">' + escapeHtml(entry.time || '') + '</span>',
    '<span class="log-msg ' + escapeHtml(entry.type || '') + '">' + escapeHtml(entry.message || '') + renderNotificationBadges(entry) + '</span>',
    '</span>',
    '<span class="log-state">' + stateBadge + '</span>',
  ].join('');
  return button;
}

function renderAlertLog() {
  const list = document.getElementById('logList');
  const items = alertEntries.filter(entry => alertLogMatchesFilter(entry) && alertLogMatchesSearch(entry));
  list.innerHTML = '';
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'log-empty';
    empty.textContent = alertEntries.length ? '当前条件暂无警报' : '暂无警报';
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
  selectedAlertId = normalized.id;
  updateAlertLogSummary();
  renderAlertDetail();
  renderAlertLog();
}

function mergeAlertLogEntry(entry) {
  const normalized = normalizeAlertEntry(entry);
  const index = alertEntries.findIndex(item => item.id === normalized.id);
  if (index >= 0) alertEntries[index] = normalized;
  else alertEntries.push(normalized);
  updateAlertLogSummary();
  renderAlertDetail();
  renderAlertLog();
}

function findSelectedAlert() {
  return alertEntries.find(entry => entry.id === selectedAlertId) || null;
}

function selectAlertEntry(id) {
  selectedAlertId = id;
  const entry = findSelectedAlert();
  if (entry && !entry.read) updateAlertStatus(entry.id, { read: true });
  renderAlertDetail();
  renderAlertLog();
}

function updateAlertStatus(id, patch) {
  const entry = alertEntries.find(item => item.id === id);
  if (entry) {
    Object.assign(entry, patch || {});
    if (entry.acknowledged) entry.read = true;
    updateAlertLogSummary();
    renderAlertDetail();
    renderAlertLog();
  }
  socket.emit('update_alert_log_status', Object.assign({ id }, patch || {}));
}

function acknowledgeAlert(id) {
  updateAlertStatus(id, { read: true, acknowledged: true });
}

function analyzeAlertFromDetail(id) {
  const entry = alertEntries.find(item => item.id === id);
  if (!entry) return;
  activeAlert = entry;
  analyzeActiveAlert();
}

function resendAlertNotification(id) {
  const status = document.getElementById('alertLogStatus');
  status.textContent = '正在重新提交通知...';
  status.className = 'log-status';
  socket.emit('resend_alert_notification', { id });
}

function renderAlertDetail() {
  const detail = document.getElementById('alertDetail');
  if (!detail) return;
  const entry = findSelectedAlert();
  if (!entry) {
    detail.innerHTML = '<div class="alert-detail-empty">选择一条警报查看详情</div>';
    return;
  }
  const notifications = renderNotificationBadges(entry);
  detail.innerHTML = [
    '<div class="alert-detail-head">',
    '<div>',
    '<div class="alert-detail-title">' + escapeHtml(alertLevelLabel(entry.type)) + '</div>',
    '<div class="alert-detail-time">' + escapeHtml(entry.timestamp || entry.time || '--') + '</div>',
    '</div>',
    '<span class="log-state-badge ' + (!entry.read ? 'unread' : (entry.acknowledged ? 'ack' : '')) + '">' + escapeHtml(alertStatusLabel(entry)) + '</span>',
    '</div>',
    '<div class="alert-detail-message">' + escapeHtml(entry.message || '达到预警条件') + '</div>',
    notifications,
    '<div class="alert-detail-grid">',
    '<div class="alert-detail-cell"><span>类型</span><strong>' + escapeHtml(alertLevelLabel(entry.type)) + '</strong></div>',
    '<div class="alert-detail-cell"><span>品种</span><strong>' + escapeHtml(alertModeLabel(entry.mode)) + '</strong></div>',
    '<div class="alert-detail-cell"><span>读取状态</span><strong>' + escapeHtml(entry.read ? '已读' : '未读') + '</strong></div>',
    '<div class="alert-detail-cell"><span>处理状态</span><strong>' + escapeHtml(entry.acknowledged ? '已确认' : '未确认') + '</strong></div>',
    '</div>',
    '<div class="alert-detail-actions">',
    entry.read ? '' : '<button class="btn-clear-sm" type="button" onclick="updateAlertStatus(\'' + escapeHtml(entry.id) + '\', { read: true })">标为已读</button>',
    entry.acknowledged ? '' : '<button class="btn-clear-sm" type="button" onclick="acknowledgeAlert(\'' + escapeHtml(entry.id) + '\')">确认</button>',
    '<button class="btn-clear-sm" type="button" onclick="resendAlertNotification(\'' + escapeHtml(entry.id) + '\')">重发通知</button>',
    '<button class="btn-clear-sm" type="button" onclick="analyzeAlertFromDetail(\'' + escapeHtml(entry.id) + '\')">风险分析</button>',
    '</div>',
  ].join('');
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
