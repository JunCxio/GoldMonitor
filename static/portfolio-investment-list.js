// ========== 定投计划列表 ==========
const PORTFOLIO_INVESTMENT_STATUS_FILTER_OPTIONS = [
  { value: 'all', label: '全部状态' },
  { value: 'running', label: '运行中' },
  { value: 'due', label: '待执行' },
  { value: 'attention', label: '需处理' },
  { value: 'paused', label: '已暂停' },
  { value: 'completed', label: '已完成' },
];
const PORTFOLIO_INVESTMENT_SORT_OPTIONS = [
  { value: 'priority', label: '状态优先' },
  { value: 'next_run', label: '下次执行' },
  { value: 'updated', label: '最近更新' },
  { value: 'invested', label: '累计投入' },
  { value: 'name', label: '名称' },
];
const PORTFOLIO_INVESTMENT_ARCHIVED_SORT_OPTIONS = [
  { value: 'priority', label: '最近归档' },
  { value: 'updated', label: '最近更新' },
  { value: 'invested', label: '累计投入' },
  { value: 'name', label: '名称' },
];

function portfolioInvestmentSortOptions() {
  return portfolioInvestmentListMode === 'archived'
    ? PORTFOLIO_INVESTMENT_ARCHIVED_SORT_OPTIONS
    : PORTFOLIO_INVESTMENT_SORT_OPTIONS;
}

function portfolioInvestmentFilterStatus(plan) {
  if (plan.archived_at) return 'archived';
  if (plan.status === 'completed') return 'completed';
  if (['error', 'waiting_price', 'orphaned'].includes(plan.last_result)) return 'attention';
  if (plan.status === 'due') return 'due';
  if (plan.enabled && ['active', 'pending_start'].includes(plan.status)) return 'running';
  return 'paused';
}

function setPortfolioInvestmentListMode(mode) {
  captureActivePortfolioInvestmentDraft();
  activePortfolioInvestmentPlanId = null;
  portfolioInvestmentListMode = mode === 'archived' ? 'archived' : 'active';
  portfolioInvestmentSort = portfolioOptionValue(
    portfolioInvestmentSortOptions(),
    portfolioInvestmentSort,
    'priority',
  );
  renderPortfolio();
}

function setPortfolioInvestmentStatusFilter(value) {
  captureActivePortfolioInvestmentDraft();
  portfolioInvestmentStatusFilter = portfolioOptionValue(
    PORTFOLIO_INVESTMENT_STATUS_FILTER_OPTIONS,
    value,
    'all',
  );
  activePortfolioInvestmentPlanId = null;
  renderPortfolio();
}

function setPortfolioInvestmentSort(value) {
  portfolioInvestmentSort = portfolioOptionValue(
    portfolioInvestmentSortOptions(),
    value,
    'priority',
  );
  renderPortfolio();
}

function filteredPortfolioInvestments() {
  const statusPriority = {
    attention: 0,
    due: 1,
    running: 2,
    paused: 3,
    completed: 4,
    archived: 5,
  };
  const filtered = portfolioInvestmentItems()
    .filter(item => portfolioInvestmentListMode === 'archived' ? Boolean(item.archived_at) : !item.archived_at)
    .filter(item => {
      if (portfolioInvestmentListMode === 'archived' || portfolioInvestmentStatusFilter === 'all') return true;
      return portfolioInvestmentFilterStatus(item) === portfolioInvestmentStatusFilter;
    })
    .filter(item => portfolioSearchMatches([
      item.name,
      item.position_name,
      item.mode,
      portfolioInvestmentFrequencyLabel(item),
      item.last_message,
      portfolioInvestmentStateLabel(item),
    ]));
  filtered.sort((left, right) => {
    const nameCompare = String(left.name || '').localeCompare(String(right.name || ''), 'zh-CN');
    if (portfolioInvestmentSort === 'name') return nameCompare;
    if (portfolioInvestmentSort === 'invested') {
      const rightInvested = Number((right.performance || {}).total_invested) || 0;
      const leftInvested = Number((left.performance || {}).total_invested) || 0;
      return rightInvested - leftInvested || nameCompare;
    }
    if (portfolioInvestmentSort === 'updated') {
      const updatedCompare = String(right.updated_at || right.created_at || '').localeCompare(String(left.updated_at || left.created_at || ''));
      return updatedCompare || nameCompare;
    }
    if (portfolioInvestmentSort === 'next_run') {
      const nextRunCompare = String(left.next_run_at || '9999').localeCompare(String(right.next_run_at || '9999'));
      return nextRunCompare || nameCompare;
    }
    if (portfolioInvestmentListMode === 'archived') {
      return String(right.archived_at || '').localeCompare(String(left.archived_at || '')) || nameCompare;
    }
    const priorityCompare = (statusPriority[portfolioInvestmentFilterStatus(left)] ?? 99) - (statusPriority[portfolioInvestmentFilterStatus(right)] ?? 99);
    const nextRunCompare = String(left.next_run_at || '9999').localeCompare(String(right.next_run_at || '9999'));
    return priorityCompare || nextRunCompare || nameCompare;
  });
  return filtered;
}
