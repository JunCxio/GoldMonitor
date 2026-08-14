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
  if (data.notification_retry_status) applyNotificationRetryStatus(data.notification_retry_status);
  if (data.background_task_status) applyBackgroundTaskStatus(data.background_task_status);
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
  requestTodayOverview(false);
});

socket.on('show_close_dialog', data => {
  openCloseDialog(data || {});
});

registerMarketDashboardSocketHandlers(socket);

registerTodayOverviewSocketHandlers(socket);

registerSettingsSocketHandlers(socket);

registerAlertRuleSocketHandlers(socket);

registerAlertConfigurationSocketHandlers(socket);

registerPortfolioSocketHandlers(socket);

registerOperationsSocketHandlers(socket);

registerPriceHistoryMaintenanceSocketHandlers(socket);

registerRiskAnalysisSocketHandlers(socket);

registerHistoryReviewSocketHandlers(socket);

registerAlertLogSocketHandlers(socket);
