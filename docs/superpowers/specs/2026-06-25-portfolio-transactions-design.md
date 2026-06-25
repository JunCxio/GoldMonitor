# 持仓流水与已实现盈亏设计

## 背景

当前持仓模块已经支持维护单条持仓，并按实时 RMB/克或 USD/oz 行情计算成本、市值和浮动盈亏。这个模型适合最小可用版本，但无法表达追加买入、部分卖出、手续费和已实现盈亏。

本设计将持仓模块升级为“流水作为事实来源，持仓由流水派生”。后续所有持仓数量、平均成本、未实现盈亏和已实现盈亏都从交易流水计算得到。

## 目标

- 用户可以记录买入和卖出流水。
- 系统按移动加权平均成本计算当前持仓成本。
- 系统在卖出时计算已实现盈亏。
- 系统继续按 RMB/克和 USD/oz 分别计算，不做跨币种汇总换算。
- 旧的 `portfolio_positions.json` 持仓数据可以迁移为等价买入流水，不能丢失。
- 行情刷新时不能清空正在编辑的流水或持仓输入。
- 用户可以导出当前持仓汇总和流水明细。

## 非目标

- 不实现 FIFO、税务批次、IRR、回撤或收益曲线。
- 不做 RMB 与 USD 之间的汇率折算。
- 不支持自动同步券商、交易所或银行流水。
- 不支持云同步、多设备同步或账户体系。
- 不改变行情抓取、告警、新闻和风险分析模块。

## 核心决策

采用方案 A：流水作为事实来源，持仓由流水派生。

理由：

- 买入、卖出、手续费和备注都能保留为可追溯记录。
- 当前持仓、未实现盈亏、已实现盈亏可由同一套规则重算，避免持仓数量和卖出记录不一致。
- 后续增加图表、复盘、筛选、导出时可以直接复用流水数据。

成本计算采用移动加权平均成本。

理由：

- 当前产品按资产和币种汇总持仓，不强调逐笔税务批次。
- 计算规则简单，适合在现有 MVP 上迭代。
- 对用户而言，平均成本、剩余数量和已实现盈亏更容易理解。

## 数据模型

新增持久化文件：`portfolio_transactions.json`

使用现有版本化 JSON 契约：

```json
{
  "schema_version": 1,
  "items": []
}
```

流水字段：

- `id`：字符串，系统生成，流水唯一标识。
- `position_id`：字符串，持仓分组标识。同一个 `position_id` 下的流水合并为一条派生持仓。
- `name`：字符串，必填，最多 60 个字符。用于展示资产或持仓名称。
- `type`：字符串，`buy` 或 `sell`。
- `mode`：字符串，`rmb` 或 `usd`。
- `price`：数字，必填。`rmb` 表示 RMB/克，`usd` 表示 USD/oz。
- `quantity`：数字，必填。`rmb` 表示克数，`usd` 表示盎司数量。
- `fee`：数字，允许为 0。与 `mode` 对应的币种单位。
- `trade_date`：字符串，ISO 日期，允许为空。
- `note`：字符串，最多 200 个字符，允许为空。
- `created_at`：字符串，ISO 时间。
- `updated_at`：字符串，ISO 时间。

派生持仓字段不写入文件，在返回前计算：

- `id`：等于 `position_id`。
- `name`
- `mode`
- `quantity`
- `average_cost`
- `cost_basis`
- `current_price`
- `market_value`
- `unrealized_pnl`
- `unrealized_pnl_percent`
- `realized_pnl`
- `total_pnl`
- `fees`
- `last_trade_date`
- `valuation_status`

## 迁移策略

启动时读取新文件 `portfolio_transactions.json`。

- 如果新文件存在并包含有效流水，直接使用新文件。
- 如果新文件不存在或没有有效流水，则读取旧文件 `portfolio_positions.json`。
- 每条旧持仓迁移为一条 `buy` 流水：
  - `position_id` 使用旧持仓 `id`。
  - `name` 使用旧持仓 `name`。
  - `mode` 使用旧持仓 `mode`。
  - `price` 使用旧持仓 `entry_price`。
  - `quantity` 使用旧持仓 `quantity`。
  - `trade_date` 使用旧持仓 `entry_date`。
  - `note` 使用旧持仓 `note`。
  - `fee` 为 0。
- 迁移后写入 `portfolio_transactions.json`，不删除旧文件。
- 迁移只在新文件无有效流水时执行，避免重复生成流水。

## 计算规则

计算时按 `trade_date`、`created_at`、`id` 的顺序重放流水。日期为空的流水排在有日期流水之后，再按创建时间排序。

买入流水：

- `buy_cost = price * trade_quantity + fee`
- `next_cost_basis = current_cost_basis + buy_cost`
- `next_quantity = current_quantity + trade_quantity`
- `average_cost = next_cost_basis / next_quantity`
- `fees = current_fees + fee`

卖出流水：

- 保存前必须验证卖出数量不超过当前可卖数量。
- `cost_removed = average_cost * trade_quantity`
- `proceeds = price * trade_quantity - fee`
- `realized_pnl = current_realized_pnl + proceeds - cost_removed`
- `next_cost_basis = current_cost_basis - cost_removed`
- `next_quantity = current_quantity - trade_quantity`
- `fees = current_fees + fee`
- 如果剩余数量为 0，则 `cost_basis` 归零，`average_cost` 置空。

行情估值：

- `market_value = current_price * quantity`
- `unrealized_pnl = market_value - cost_basis`
- `unrealized_pnl_percent = unrealized_pnl / cost_basis * 100`
- `total_pnl = realized_pnl + unrealized_pnl`

当当前行情缺失时：

- 仍返回数量、平均成本、成本基数和已实现盈亏。
- `current_price`、`market_value`、`unrealized_pnl`、`unrealized_pnl_percent` 为空。
- `valuation_status` 为 `waiting_price`。

## 后端设计

在 `goldmonitor/portfolio.py` 中扩展或拆分以下职责：

- 规范化单条流水。
- 规范化流水列表。
- 从旧持仓构造迁移流水。
- 重放流水并派生持仓状态。
- 验证新增、编辑或删除后的流水集合是否有效。
- 本地 JSON 读写。
- 构建持仓汇总 CSV。
- 构建流水明细 CSV。

`app.py` 继续只做编排：

- 初始化和加载流水数据。
- 在行情更新后构建最新持仓状态。
- 处理 Socket 事件。
- 调用导出工具写入 CSV 文件。

## Socket 契约

保留事件：

- `get_portfolio`
  - 入参：无。
  - 出参：完整持仓状态。
- `export_portfolio`
  - 入参：`{ "kind": "positions" | "transactions" }`，缺省为 `positions`。
  - 行为：导出当前持仓汇总或流水明细。
  - 出参：导出路径、导出类型和条数。

新增事件：

- `save_portfolio_transaction`
  - 入参：单条流水字段。
  - 行为：新增或更新流水。
  - 出参：完整持仓状态。
- `delete_portfolio_transaction`
  - 入参：`{ "id": "..." }`
  - 行为：删除指定流水，并验证删除后的状态仍然有效。
  - 出参：完整持仓状态。

返回状态结构：

```json
{
  "items": [],
  "transactions": [],
  "total": 0,
  "rmb_summary": {},
  "usd_summary": {},
  "prices": {}
}
```

`items` 继续表示派生持仓，保留当前前端的主要读取入口。`transactions` 表示流水明细。

错误返回遵循现有 Socket 风格：

- `ok: false`
- `message`

## 前端设计

持仓区域增加分段视图：

- `持仓`：展示派生持仓和分币种汇总。
- `流水`：展示买入、卖出流水，支持新增、编辑和删除。

持仓视图展示：

- 名称。
- 单位模式。
- 当前数量。
- 平均成本。
- 当前价格。
- 市值。
- 未实现盈亏。
- 已实现盈亏。
- 总盈亏。

流水视图展示：

- 买入或卖出。
- 名称。
- 单位模式。
- 价格。
- 数量。
- 手续费。
- 交易日期。
- 备注。

输入体验要求：

- 行情刷新前先捕获当前编辑草稿，刷新后恢复到同一表单。
- 持仓编辑草稿和流水编辑草稿分开保存。
- 桌面端表单采用稳定网格布局，字段宽度足够展示常见价格、数量和备注内容。
- 移动端表单单列展示，输入框不截断关键数值。
- 保存成功后清理对应草稿；保存失败时保留用户输入。

## 导出设计

持仓汇总 CSV 字段：

- `id`
- `name`
- `mode`
- `quantity`
- `average_cost`
- `cost_basis`
- `current_price`
- `market_value`
- `unrealized_pnl`
- `unrealized_pnl_percent`
- `realized_pnl`
- `total_pnl`
- `fees`
- `last_trade_date`
- `valuation_status`

流水明细 CSV 字段：

- `id`
- `position_id`
- `name`
- `type`
- `mode`
- `price`
- `quantity`
- `fee`
- `trade_date`
- `realized_pnl`
- `note`
- `created_at`
- `updated_at`

导出文件保存到现有 `exports/` 目录：

- `portfolio-positions-YYYYMMDD-HHMMSS.csv`
- `portfolio-transactions-YYYYMMDD-HHMMSS.csv`

## 异常路径

- 新旧文件都不存在：返回空持仓和空流水。
- 新文件 JSON 损坏：返回空状态并记录日志，不阻断主程序启动。
- 旧持仓迁移中遇到非法记录：跳过非法记录，继续迁移其他记录。
- 非法类型、非法单位、非正价格或非正数量：拒绝保存。
- 手续费为负数：拒绝保存。
- 卖出数量超过当前可卖数量：拒绝保存，并返回明确提示。
- 编辑或删除流水导致任意时间点持仓数量为负：拒绝本次操作。
- 删除不存在的流水：返回当前状态，并提示未找到。
- 导出失败：返回失败消息，不改变内存状态。

## 调用方影响

- 现有 `get_portfolio` 调用方继续可从 `items` 读取派生持仓。
- 前端需要从单一持仓编辑器扩展为持仓视图和流水视图。
- 原 `save_portfolio_position` 和 `delete_portfolio_position` 可在实现期保留兼容入口，但新 UI 不再直接调用它们。
- `tests/test_portfolio_module.py` 需要覆盖流水规范化、迁移、成本计算、非法卖出和导出。
- `tests/frontend_asset_check.py` 需要覆盖新增事件名、视图挂载点和草稿保留逻辑。

## 验收标准

- 旧的 `portfolio_positions.json` 能迁移为买入流水，页面展示的数量、成本和浮动盈亏与迁移前一致。
- 新增买入后，剩余数量、成本基数和平均成本正确。
- 新增卖出后，剩余数量减少，已实现盈亏正确，未实现盈亏按剩余持仓计算。
- 卖出数量超过当前可卖数量时保存失败，页面保留输入内容。
- 行情刷新时，正在编辑的流水表单内容不会被清空。
- RMB/克和 USD/oz 独立计算，互不汇总换算。
- 持仓 CSV 和流水 CSV 均可导出，字段完整。
- 后端单元测试覆盖核心计算和异常路径。
- 前端静态检查覆盖新增事件和视图入口。

## 测试方案

后端测试：

- 流水规范化：必填字段、长度限制、非法类型、非法单位、非法数字。
- 旧持仓迁移：有效记录迁移，非法记录跳过，不重复迁移。
- 买入计算：多次买入后的移动加权平均成本。
- 卖出计算：部分卖出、清仓、手续费和已实现盈亏。
- 非法卖出：新增、编辑、删除导致负持仓时拒绝。
- 汇总计算：RMB 与 USD 分开汇总。
- CSV 导出：持仓汇总和流水明细字段完整。
- Store 行为：文件不存在、JSON 损坏、保存后可重新读取。

前端检查：

- `node --check static/app.js`。
- `tests/frontend_asset_check.py` 检查分段视图、流水事件名、导出入口和草稿函数。

## 发布说明草案

- 新增持仓流水，可记录买入、卖出、手续费和备注。
- 新增已实现盈亏，并按移动加权平均成本计算剩余持仓成本。
- 支持从旧持仓数据迁移为流水记录。
- 支持导出持仓汇总和流水明细。
