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
let onboardingStep = 1;
let onboardingManual = false;
let onboardingAutoChecked = false;
let deepseekModelOptions = ['deepseek-v4-pro', 'deepseek-v4-flash', 'deepseek-chat', 'deepseek-reasoner'];
let dailyDigestStatusState = {};
