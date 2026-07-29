function registerAlertRuleSocketHandlers(socket) {
  socket.on('alert_rules_updated', data => {
    applyAlertRulesState(data || {});
  });

  socket.on('alert_rule_saved', () => {
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
}
