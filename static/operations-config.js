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
