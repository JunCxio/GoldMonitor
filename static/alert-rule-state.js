// ========== 统一预警中心 ==========
const ALERT_RULE_DEFS = [
  { type: 'upper_warning', title: '上涨关注', direction: '高于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'upper_critical', title: '上涨警告', direction: '高于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
  { type: 'lower_warning', title: '下跌关注', direction: '低于或等于', emailKey: 'email_warning_enabled', badgeClass: 'warn' },
  { type: 'lower_critical', title: '下跌警告', direction: '低于或等于', emailKey: 'email_critical_enabled', badgeClass: 'crit' },
];

let allThresholds = {};
let volConfig = { percent: null, minutes: 10, enabled: false };
let activeAlertRule = null;
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
