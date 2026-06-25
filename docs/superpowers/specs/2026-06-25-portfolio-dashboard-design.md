# 持仓 / 成本价 / 盈亏看板 MVP 设计

## 背景

GoldMonitor 已具备实时金价、人民币克价、USD/CNY 汇率、历史价格、导出、设置和本地持久化能力。下一步增加持仓看板，让用户在查看金价时直接了解自己的持仓成本、当前市值和浮动盈亏。

本设计只覆盖 MVP，不引入完整投资账本、自动交易、税费核算或收益曲线。

## 目标

- 用户可以维护多个黄金相关持仓。
- 系统根据当前行情计算每条持仓的成本、市值、浮动盈亏和盈亏比例。
- 系统按人民币持仓和美元持仓分别展示汇总成本、市值和盈亏。
- 持仓数据保存在本地，重启后仍可读取。
- 用户可以导出持仓 CSV。
- 当前行情缺失时，仍允许新增、编辑、删除持仓，并明确显示估值不可用。

## 非目标

- 不支持买入、卖出流水账。
- 不支持手续费、税费、点差和汇率锁定。
- 不支持收益曲线、回撤、IRR 或复盘分析。
- 不支持持仓盈亏提醒。
- 不支持云同步或多设备同步。

## 用户场景

- 用户持有实物黄金，想输入克重和买入克价，查看当前盈亏。
- 用户持有按国际金价计价的资产，想输入盎司数量和买入美元价格，查看当前盈亏。
- 用户有多笔持仓，想看总成本、总市值和总浮动盈亏。
- 用户希望导出持仓明细用于手工记录。

## 数据模型

新增文件：`portfolio_positions.json`

使用现有版本化 JSON 契约：

```json
{
  "schema_version": 1,
  "items": []
}
```

持仓字段：

- `id`：字符串，系统生成。
- `name`：字符串，必填，最多 60 个字符。
- `mode`：字符串，`rmb` 或 `usd`。
- `entry_price`：数字，必填，买入价。
- `quantity`：数字，必填。`rmb` 表示克数，`usd` 表示盎司数量。
- `entry_date`：字符串，ISO 日期，允许为空。
- `note`：字符串，最多 200 个字符，允许为空。
- `created_at`：字符串，ISO 时间。
- `updated_at`：字符串，ISO 时间。

派生字段不写入文件，在读取或返回前计算：

- `current_price`
- `cost`
- `market_value`
- `pnl`
- `pnl_percent`
- `valuation_status`

## 计算规则

人民币克价持仓：

- `cost = entry_price * quantity`
- `market_value = price_rmb * quantity`
- `pnl = market_value - cost`
- `pnl_percent = pnl / cost * 100`

国际金价持仓：

- `cost = entry_price * quantity`
- `market_value = price_usd * quantity`
- `pnl = market_value - cost`
- `pnl_percent = pnl / cost * 100`

当当前价格不存在、成本不大于 0 或数量不大于 0 时：

- 不计算盈亏。
- `valuation_status` 设为 `waiting_price` 或 `invalid_position`。
- 前端显示“等待行情”或“持仓数据需修正”。

MVP 不做 USD 持仓到人民币的汇总换算；汇总按币种分开：

- `rmb_summary`
- `usd_summary`

## 后端设计

新增模块：`goldmonitor/portfolio.py`

职责：

- 规范化单条持仓。
- 规范化持仓列表。
- 计算单条持仓估值。
- 计算分币种汇总。
- 本地 JSON 读写。
- 构建 CSV 导出内容。

`app.py` 只保留编排函数：

- `_portfolio_store()`
- `load_portfolio_positions()`
- `save_portfolio_positions()`
- `build_portfolio_state()`
- `upsert_portfolio_position()`
- `delete_portfolio_position()`
- `build_portfolio_csv()`

## Socket 事件

新增事件：

- `get_portfolio`
  - 入参：无。
  - 出参：完整持仓状态。
- `save_portfolio_position`
  - 入参：单条持仓字段。
  - 行为：新增或更新持仓。
  - 出参：完整持仓状态。
- `delete_portfolio_position`
  - 入参：`{ "id": "..." }`
  - 行为：删除指定持仓。
  - 出参：完整持仓状态。
- `export_portfolio`
  - 入参：无。
  - 行为：保存 CSV 到现有导出目录。
  - 出参：导出路径和条数。

错误返回遵循现有 Socket 风格：

- `ok: false`
- `message`

## 前端设计

在现有界面中新增“持仓”视图或区域，MVP 采用当前应用已有密度和控件风格，不做独立落地页。

主要区域：

- 汇总条：人民币持仓和美元持仓分别展示总成本、总市值、浮动盈亏。
- 持仓列表：展示名称、模式、买入价、数量、当前价、市值、盈亏、买入日期。
- 编辑表单：新增和编辑复用同一表单。
- 操作按钮：保存、删除、导出 CSV。

行情缺失时：

- 列表仍显示成本和数量。
- 当前价、市值、盈亏显示等待状态。
- 新增、编辑、删除不受影响。

## 导出设计

CSV 字段：

- `id`
- `name`
- `mode`
- `entry_price`
- `quantity`
- `entry_date`
- `current_price`
- `cost`
- `market_value`
- `pnl`
- `pnl_percent`
- `valuation_status`
- `note`

导出文件保存到现有 `exports/` 目录，文件名形如：

```text
portfolio-YYYYMMDD-HHMMSS.csv
```

## 异常路径

- 文件不存在：返回空持仓列表。
- JSON 损坏：返回空列表，不阻断主程序启动。
- 非法数字：规范化为无效持仓，不参与估值。
- 删除不存在的持仓：返回当前状态，并给出未找到提示。
- 导出失败：返回失败消息，不影响内存状态。

## 测试方案

新增测试：

- `tests/test_portfolio_module.py`
  - 持仓规范化。
  - 盈亏计算。
  - 人民币和美元分组汇总。
  - JSON 持久化。
  - CSV 导出。
- 脚本级检查：
  - 确认新增模块被 `py_compile` 覆盖。
  - 确认 README 和 Release workflow 检查列表包含新增测试。

如实现涉及前端：

- 更新 `tests/frontend_asset_check.py`，确认新增持仓视图挂载点和事件名存在。
- 继续运行 `node --check static/app.js`。

## 兼容与迁移

这是新增数据文件，不需要迁移旧数据。配置导出和诊断报告可以在后续版本纳入持仓文件元数据；MVP 不把持仓合入配置备份，避免用户误以为备份只包含设置。

## 发布说明

CHANGELOG 可描述为：

- 新增持仓看板，可维护黄金持仓并查看当前市值和浮动盈亏。
- 支持人民币克价和国际金价两种持仓模式。
- 支持持仓 CSV 导出。
