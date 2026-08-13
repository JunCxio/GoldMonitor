const SOCKET_ACCESS_TOKEN = document.querySelector('meta[name="goldmonitor-socket-token"]')?.getAttribute('content') || '';
const socket = io(window.GoldMonitorShell.withSocketDefaults({
  auth: { token: SOCKET_ACCESS_TOKEN },
}));

const PORTFOLIO_TRANSACTION_IMPORT_FIELDS = ['id', 'position_id', 'type', 'name', 'mode', 'price', 'quantity', 'fee', 'trade_date', 'note'];
const PORTFOLIO_TRANSACTION_IMPORT_REQUIRED_FIELDS = ['name', 'type', 'mode', 'price', 'quantity'];

let portfolioState = { items: [], transactions: [], total: 0, rmb_summary: {}, usd_summary: {}, prices: {}, review: { rmb: {}, usd: {} }, alerts: { items: [], total: 0, enabled: 0, triggered: 0 }, investment_plans: { items: [], summary: { total: 0, enabled: 0, due: 0, attention: 0 }, updated_at: '' }, import_backup: { available: false } };
let portfolioAnalyticsState = null;
let portfolioAnalyticsRange = 90;
let portfolioAnalyticsLoading = false;
let portfolioView = 'positions';
let portfolioDetailView = 'review';
let portfolioSearch = '';
let portfolioPositionFilter = 'all';
let portfolioPositionSort = 'recent';
let portfolioTransactionTypeFilter = 'all';
let portfolioTransactionModeFilter = 'all';
let portfolioTransactionSort = 'date_desc';
let activePortfolioPositionId = null;
let activePortfolioDetailId = null;
let activePortfolioAlertEditorId = null;
let portfolioDrafts = {};
let activePortfolioTransactionId = null;
let portfolioTransactionDrafts = {};
let activePortfolioInvestmentPlanId = null;
let portfolioInvestmentDrafts = {};
let portfolioInvestmentDraftNotice = '';
let portfolioInvestmentSchedulePreviews = {};
let portfolioInvestmentSchedulePreviewSeq = 0;
let portfolioInvestmentListMode = 'active';
let portfolioAlertDrafts = {};
let pendingPortfolioSave = null;
let pendingPortfolioImportMessage = '';
let pendingPortfolioUndoMessage = '';
let portfolioImportPreview = null;
let portfolioImportPreviewRequestSeq = 0;

let appSettings = {
  onboarding_started: false,
  onboarding_completed: false,
  onboarding_version: 1,
  onboarding_completed_at: '',
  platform: 'windows',
  platform_capabilities: {},
  startup_enabled: false,
  startup_to_tray: true,
  floating_price_enabled: true,
  floating_price_windows_mode: 'floating',
  floating_price_taskbar_target: 'auto',
  floating_price_opacity: 94,
  floating_price_display_mode: 'rmb_usd',
  floating_price_preset: 'compact',
  floating_price_snap_edge: true,
  floating_price_always_on_top: false,
  floating_price_hide_on_fullscreen: true,
  floating_price_lock_position: false,
  taskbar_price_state: {},
  close_behavior: 'ask',
  close_remembered: false,
  alert_sound_enabled: true,
  alert_dialog_enabled: true,
  webhook_enabled: false,
  webhook_url: '',
  webhook_warning_enabled: true,
  webhook_critical_enabled: true,
  webhook_volatility_enabled: true,
  daily_digest_enabled: false,
  daily_digest_time: '20:00',
  daily_digest_email_enabled: true,
  daily_digest_webhook_enabled: false,
  email_warning_enabled: true,
  email_critical_enabled: true,
  email_volatility_enabled: true,
  alert_cooldown_minutes: 30,
  alert_quiet_start: '',
  alert_quiet_end: '',
  export_dir: '',
  export_dir_default: '',
  export_dir_effective: '',
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
