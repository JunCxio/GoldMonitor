// ========== 行情展示状态 ==========
const BASE_TITLE = '金价监控';
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

let historyUsd = { labels: [], prices: [] };
let historyRmb = { labels: [], prices: [] };
let klines5min = [];
let chartHistoryState = { period: null, items: [] };
let chartEvents = [];
let latestData = null;

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

function applyMarketInitialState(data) {
  const history = Array.isArray(data.history) ? data.history : [];
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
    time: history.length ? history[history.length - 1].time : '--',
    daily: data.daily || {},
  };
  historyUsd = { labels: [], prices: [] };
  historyRmb = { labels: [], prices: [] };
  history.forEach(item => {
    historyUsd.labels.push(item.time); historyUsd.prices.push(item.usd);
    historyRmb.labels.push(item.time); historyRmb.prices.push(item.rmb);
  });
  klines5min = Array.isArray(data.klines_5min) ? data.klines_5min : [];
}

function registerMarketDashboardSocketHandlers(socketClient) {
  socketClient.on('price_update', data => {
    latestData = data;
    applyMarketObservationState(data);
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

  socketClient.on('fetch_error', data => applyFetchStatus(data || { ok:false, message:'行情数据获取失败', retryable:true }));
  socketClient.on('fetch_status', data => applyFetchStatus(data || {}));
}

function applyFetchStatus(data) {
  applyMarketObservationState(data);
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

function toggleSourceHealthMenu(button) {
  const menu = document.getElementById('sourceHealthMenu');
  if (!menu) return;
  const willOpen = menu.hidden;
  closeRightPanelMenus(menu);
  menu.hidden = !willOpen;
  if (button) button.setAttribute('aria-expanded', String(willOpen));
}
