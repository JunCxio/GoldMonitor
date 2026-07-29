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
