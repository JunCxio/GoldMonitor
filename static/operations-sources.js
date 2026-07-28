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
