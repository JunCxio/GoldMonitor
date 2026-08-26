(function () {
  'use strict';

  const statusLabels = {
    watching: '监控中',
    triggered: '已触发',
    waiting_data: '等待数据',
    scheduled: '待生效',
    expired: '已过期',
    disabled: '已停用',
    orphaned: '关联失效',
  };
  const kindLabels = {
    price_threshold: '价格',
    volatility: '波动',
    watch_target: '目标价',
    portfolio: '持仓',
  };
  const levelLabels = { critical: '关键', warning: '预警', volatility: '波动', info: '信息' };

  function text(id, value) {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  }

  function formatNumber(value, digits) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '--';
    return number.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function formatTime(value) {
    if (!value) return '时间未记录';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value).replace('T', ' ');
    return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
  }

  function renderChange(id, current, previous) {
    const element = document.getElementById(id);
    if (!element) return;
    const now = Number(current);
    const before = Number(previous);
    element.className = '';
    if (!Number.isFinite(now) || !Number.isFinite(before) || before === 0) {
      element.textContent = '暂无可比数据';
      return;
    }
    const change = (now - before) / before * 100;
    element.textContent = (change > 0 ? '+' : '') + change.toFixed(2) + '% 较上次';
    if (change > 0) element.className = 'up';
    if (change < 0) element.className = 'down';
  }

  function renderQuality(quality) {
    const state = quality || {};
    const score = Number(state.score);
    const safeScore = Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : 0;
    text('qualityScore', Number.isFinite(score) ? String(Math.round(score)) : '--');
    text('qualityLabel', state.label || '等待有效行情');
    const blockers = Array.isArray(state.blockers) ? state.blockers.filter(Boolean) : [];
    text('qualityReason', blockers.length ? blockers.join('；') : '当前未发现影响业务判断的质量问题。');
    const marker = document.getElementById('qualityMarker');
    if (marker) marker.style.left = safeScore + '%';
    const strip = document.getElementById('qualityStrip');
    if (strip) strip.dataset.level = state.level || 'unavailable';
  }

  function renderRules(rules) {
    const state = rules || {};
    const summary = state.summary || {};
    text('ruleTotal', (Number(state.total) || 0) + ' 条规则');
    const cards = [
      ['监控中', summary.watching],
      ['已触发', summary.triggered],
      ['等待数据', summary.waiting_data],
      ['未运行', (Number(summary.disabled) || 0) + (Number(summary.expired) || 0) + (Number(summary.orphaned) || 0)],
    ];
    const summaryElement = document.getElementById('ruleSummary');
    if (summaryElement) {
      summaryElement.replaceChildren(...cards.map(item => {
        const card = document.createElement('div');
        card.className = 'status-card';
        const label = document.createElement('span');
        label.textContent = item[0];
        const value = document.createElement('strong');
        value.textContent = Number(item[1]) || 0;
        card.append(label, value);
        return card;
      }));
    }
    const list = document.getElementById('ruleList');
    if (!list) return;
    const items = Array.isArray(state.items) ? state.items : [];
    if (!items.length) {
      list.innerHTML = '<p class="empty-state">尚无规则数据。</p>';
      return;
    }
    list.replaceChildren(...items.map(item => {
      const row = document.createElement('article');
      row.className = 'rule-item';
      const copy = document.createElement('div');
      const title = document.createElement('h3');
      title.textContent = item.name || '未命名规则';
      const detail = document.createElement('p');
      const mode = item.mode === 'usd' ? '美元' : item.mode === 'rmb' ? '人民币' : '';
      const target = item.target == null ? '' : ' · 目标 ' + formatNumber(item.target, 2);
      detail.textContent = (kindLabels[item.kind] || '规则') + (mode ? ' · ' + mode : '') + target;
      copy.append(title, detail);
      const pill = document.createElement('span');
      pill.className = 'status-pill ' + (item.status || '');
      pill.textContent = statusLabels[item.status] || item.status || '未知';
      row.append(copy, pill);
      return row;
    }));
  }

  function renderAlerts(items) {
    const list = document.getElementById('alertList');
    if (!list) return;
    if (!Array.isArray(items) || !items.length) {
      list.innerHTML = '<p class="empty-state">尚无警报记录。</p>';
      return;
    }
    list.replaceChildren(...items.map(item => {
      const row = document.createElement('article');
      row.className = 'alert-item';
      const copy = document.createElement('div');
      const title = document.createElement('h3');
      title.textContent = item.title || '金价预警';
      const message = document.createElement('p');
      message.textContent = item.message || '未记录详情';
      const meta = document.createElement('div');
      meta.className = 'alert-meta';
      const time = document.createElement('span');
      time.textContent = formatTime(item.timestamp || item.time);
      const handled = document.createElement('span');
      handled.textContent = item.handled ? '已处理' : item.acknowledged ? '已确认' : '待处理';
      meta.append(time, handled);
      copy.append(title, message, meta);
      const level = document.createElement('span');
      level.className = 'alert-level ' + (item.type || 'warning');
      level.textContent = levelLabels[item.type] || '预警';
      row.append(copy, level);
      return row;
    }));
  }

  function render(data) {
    const market = data.market || {};
    text('priceRmb', formatNumber(market.rmb, 2));
    text('priceUsd', formatNumber(market.usd, 2));
    text('rateValue', formatNumber(market.rate, 4));
    text('rateSource', (market.rate_source || '汇率来源未记录') + (market.rate_cached ? ' · 缓存' : ''));
    text('updatedAt', '面板刷新 ' + formatTime(data.generated_at));
    renderChange('changeRmb', market.rmb, market.previous_rmb);
    renderChange('changeUsd', market.usd, market.previous_usd);
    renderQuality(data.quality);
    renderRules(data.rules);
    renderAlerts(data.alerts);
  }

  async function refresh() {
    const indicator = document.getElementById('connectionState');
    try {
      const response = await fetch('/api/dashboard', { credentials: 'same-origin', cache: 'no-store' });
      if (response.status === 401) {
        window.location.replace('/');
        return;
      }
      if (!response.ok) throw new Error('request failed');
      render(await response.json());
      if (indicator) {
        indicator.className = 'connection-state online';
        indicator.lastChild.textContent = '已连接';
      }
    } catch (_error) {
      if (indicator) {
        indicator.className = 'connection-state error';
        indicator.lastChild.textContent = '连接中断';
      }
    }
  }

  refresh();
  window.setInterval(refresh, 10000);
}());
