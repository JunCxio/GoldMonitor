# GoldMonitor

<p align="center">
  <img src="static/icon-256.png" width="104" alt="GoldMonitor 图标">
</p>

<p align="center">本地优先的黄金行情监控、风险预警与持仓复盘桌面工具。</p>

<p align="center">
  <a href="https://github.com/JunCxio/GoldMonitor/releases/latest">下载最新版本</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="docs/quick-start.md">首次使用指南</a> ·
  <a href="CONTRIBUTING.md">参与贡献</a> ·
  <a href="https://github.com/JunCxio/GoldMonitor/issues/new/choose">提交反馈</a>
</p>

<p align="center">
  <a href="https://github.com/JunCxio/GoldMonitor/releases"><img src="https://img.shields.io/github/v/release/JunCxio/GoldMonitor?display_name=tag&label=Release" alt="最新发布版本"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/JunCxio/GoldMonitor?label=License" alt="MIT License"></a>
  <a href="https://github.com/JunCxio/GoldMonitor/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/JunCxio/GoldMonitor/ci.yml?branch=main&label=CI" alt="持续集成状态"></a>
</p>

GoldMonitor 面向希望在本机持续观察金价、管理持仓并复盘交易决策的用户。数据和配置默认保存在本地；风险分析仅在用户手动触发时调用已配置的模型服务。

![GoldMonitor 功能一览](docs/images/feature-overview.svg)

## 适合的使用场景

- 需要同时查看国际金价、人民币克价与 USD/CNY 汇率，并掌握数据来源和更新时间。
- 希望按价格、短时波动或目标价接收桌面、邮件或 Webhook 提醒。
- 需要在本地维护黄金持仓、流水、风险分析历史和复盘记录。
- 希望使用免费、可审查、可自行构建的桌面工具，而不是把配置和历史上传到云端。

## 主要功能

- 实时获取 XAU/USD、人民币克价和 USD/CNY 汇率，展示数据源、更新时间、缓存状态和日内统计。
- 提供统一预警中心，在同一列表维护价格、波动、目标价和持仓规则；支持名称搜索、状态筛选、批量启停/重置/删除，并集中查看监控中、已触发、已过期和已停用状态。
- 每条规则可设置生效时间、失效时间、独立冷却时间和通知渠道；渠道可继承全局设置、指定本机/邮件/Webhook，或仅记录不发送。
- 规则详情提供运行诊断和单规则最近 30 天触发复盘，展示当前值、距触发差距、数据阻塞原因、实际通知渠道、送达率、处理率和 24 小时后行情延续率。
- 新建或编辑价格、波动、目标价和持仓规则时，可运行 7 天、30 天或 90 天历史模拟。持仓规则会使用本地流水与历史行情还原估值，并在交易日期或历史覆盖不足时明确拒绝生成不可靠结果。
- 支持预警策略模板，可保存价格阈值、波动提醒、冷却、静默和通知级别，并按场景一键切换。
- 支持持仓看板，可维护人民币克价和国际金价持仓，展示成本、市值、浮动盈亏，并导出 CSV。
- 支持按每天、每周、每月或每年设置人民币与美元固定金额定投计划，可选开始日期、结束日期和目标期数，并按执行时通过质量门禁的实时行情生成本地买入流水；缓存、过期或异常行情不会用于自动或手动执行。达到目标期数后自动完成。可预览未来 5 个执行日期、目标总预算、剩余投入和预计完成日期，并在定投概览中对照近 30 天实际投入、近 6 个月投入趋势、近 90 天执行稳定性与未来 30 天计划投入。未来投入可通过资金日历按日期查看人民币、美元资金需求和当天涉及的计划，也可按计划查看预计期数、单期金额和首末执行日期。支持按状态筛选和按执行时间、更新时间、累计投入或名称排序，临时跳过当前期次、复制计划、归档计划，并在单个计划详情中查看近 90 天按时、补执行和手动执行情况、计划买入金额与包含手续费的实际支出对照、累计绩效与最近执行记录，以及导出该计划的全部执行记录。单个计划可运行 7 天、30 天或 90 天历史模拟，按计划期次匹配邻近本地行情样本，明确展示行情覆盖率、采样间隔、缺失期次、估算投入、均价、市值和盈亏。模拟结果不写入持仓或流水，不代表真实成交、滑点或历史真实收益；覆盖不足时不会使用当前价格补齐。投入对照反映本地流水中的手续费与数量舍入差额，不代表真实成交滑点；缺少计划金额的旧流水不会计入。应用关闭期间只补最近一期，不连接交易平台或执行真实下单。
- 警报记录会显示邮件和 Webhook 的最终投递状态，区分发送中、已送达和失败；可对失败通知重发，并记录有限重试次数与完成时间。
- 警报记录支持本地保存、新警报计数、通知异常重发、搜索筛选、CSV 导出到固定导出目录和一键清空。
- 支持提醒冷却时间、静默时段、邮件标题模板和正文模板。
- 支持 Webhook 通知，可按预警级别控制是否发送。
- 支持本地每日摘要调度，可按设定时间通过邮件或 Webhook 汇总最近 24 小时的价格、预警、风险分析、新闻、复盘笔记、数据质量、持仓和定投计划；程序当天晚启动时会补发，摘要不会自动调用模型。
- 新安装会显示四步首次使用向导，集中说明本地存储、行情状态、桌面行为和本机预警设置；完成后可从运维设置重新打开。
- 支持桌面金价悬浮条，显示涨跌颜色、更新时间和数据源状态，并提供右键菜单。
- macOS 桌面版支持菜单栏金价、菜单栏打开主窗口、刷新行情、风险分析、通知中心提醒和系统提示音。
- 支持风险分析助手，用户手动触发，避免后台自动消耗模型 token。
- 风险分析支持 DeepSeek 和 OpenAI 兼容接口，支持模型列表下拉、连接测试、分析深度、缓存、历史、复制和导出报告。
- 可从本地风险分析历史选择两条结果并排比较；对比选择不持久化，且不会新增模型调用。
- 金价与汇率请求通过统一的行情源适配器接口组织。可在详情面板启停、排序和单独探测现有 4 个金价源与 3 个汇率源，每类至少保留一个启用源。
- 支持数据源滚动健康指标，保留最近 50 次探测的成功率、缓存率、平均/中位延迟、连续失败和最近恢复时间，并在本地持久化。
- 行情质量使用可解释的连续评分，综合实时取数、缓存回退、当前主源滚动成功率、连续失败、数据新鲜度和跨源价差，页面会显示逐项扣分依据。缓存行情可继续用于界面查看，但不会写入新历史、触发预警或生成定投流水。
- 行情观测会区分来源时间与本机接收时间，并随警报和定投流水保存质量快照，便于复盘当时使用的数据来源、缓存状态和阻塞原因。
- 运维页提供行情可信度诊断视图，集中显示历史入库、预警判断和定投执行门禁，金价与汇率的来源时效、缓存状态，以及本次运行期间合并后的质量事件和数据源滚动健康指标。
- Chart.js 和 Socket.IO Client 使用仓库内固定版本，主界面启动和运行不依赖公共 CDN。
- 支持本地价格历史分层留存：原始行情保留 24 小时，1 分钟保留 30 天，5 分钟保留 90 天，1 小时保留 2 年，日线长期保留；查询会按时间范围自动选择粒度。
- 历史数据维护页按原始、1 分钟、5 分钟、1 小时和日线分别展示记录数、采样间隔、保留策略、实际覆盖区间及当前差异状态。
- 后台每 6 小时执行一次只读历史数据检查，发现数据库完整性、无效明细、汇总差异或可补记录时会在运维任务中提示；连续 3 次异常后发送本机通知并进入今日概览的“运维”分类。数据修复仍需用户查看预览并明确确认；可清理无法参与计算的无效明细，重建时会清理可还原范围内的多余汇总并保留范围外的长期数据，未知粒度汇总不会自动删除；修复完成后会立即复检后台任务并刷新今日概览状态。
- 支持历史复盘、事件时间轴、30 日与 90 日图表、图表事件标记、CSV 导出和本地复盘报告导出。
- 持仓复盘包含按历史行情重放流水生成的总收益曲线、已实现收益曲线、未实现收益、收益率和最大回撤，并分别统计通知送达率、确认/处理率及 24 小时后行情延续率。行情延续率不等同于预测准确率或投资建议。
- 支持在事件时间轴新增、编辑和删除本地复盘笔记，可独立记录或关联具体事件，并随现有复盘报告一并导出。
- 支持配置导出、配置导入、恢复默认设置、诊断报告导出和自定义导出目录；配置备份使用 schema v1，包含统一预警规则并兼容无版本字段的旧版 v0 备份。
- 诊断报告包含历史数据库完整性、无效明细、汇总差异、JSON 可补记录和最近修复恢复点状态，复制诊断摘要时可直接查看主要问题。
- 支持创建和恢复完整本地数据归档。归档覆盖设置、密钥、持仓、流水、预警、复盘、缓存、滚动指标及 SQLite 数据库，恢复前校验版本、文件清单、大小、SHA-256、JSON 和 SQLite 完整性，失败时自动回滚。
- 支持软件更新检查、下载进度、SHA256 校验、安装器启动和内置 GitHub Release 官方更新源。

## 扩展边界

当前版本聚焦本地黄金行情监控、持仓管理、提醒通知和复盘分析。多品种贵金属、更多通知渠道、局域网只读面板和云同步属于后续扩展方向，启动前需先满足 `docs/product-discovery/extension-readiness-checklist.md` 中的模块边界、数据能力、核心闭环和行情可信度前置条件。

行情源适配器是内部扩展接口，用于统一数据源元数据、请求结果和健康状态目录。用户只能管理项目内置数据源的启停和顺序，不能修改请求 URL；金价和汇率分类均不允许全部停用。新增或替换数据源仍需通过解析、排序、缓存、滚动指标和质量评分契约验证。

## 快速开始

最新安装包发布在 GitHub Releases：

```text
https://github.com/JunCxio/GoldMonitor/releases/latest
```

Windows 用户通常只需要下载 `GoldMonitorSetup.exe` 并运行安装。安装包是按用户目录安装，不需要管理员权限。

macOS 用户可下载 `GoldMonitor-macOS.dmg`，打开后把 `GoldMonitor.app` 拖入“应用程序”目录即可安装。macOS 版会在菜单栏显示状态项，关闭主窗口后仍可从菜单栏恢复。

首次使用、预警设置、通知测试和隐私注意事项参见 [首次使用指南](docs/quick-start.md)。

## 更新源

程序内置 GitHub Release 官方更新源，普通用户无需在设置页查看或修改具体地址。

更新清单由 GitHub Actions 在发布时自动生成，包含：

- `version`：最新版本号。
- `url`：安装包下载地址。
- `sha256`：安装包 SHA256 校验值。
- `notes`：当前版本说明。

程序会按内置更新源每 6 小时检查一次新版本；发现可用更新后，会在主界面的更新按钮上显示状态。更新安装完成后，安装器会自动重新打开程序。旧版本本地配置中保存过的 `update_manifest_url` 和 `update_auto_check_interval_hours` 会被忽略并在下次保存设置时移除。

## 本地数据

配置和运行数据默认保存在以下目录：

- Windows：`%APPDATA%\GoldMonitor`
- macOS：`~/Library/Application Support/GoldMonitor`

其中包括：

- `settings.json`：通用设置、邮件通知、Webhook 通知、风险分析设置和内置数据源启停/排序配置。
- `alert_rules.json`：统一预警规则，是价格、波动、目标价和持仓提醒的唯一事实来源，包含有效期、冷却、通知渠道及触发状态。
- `alert_profiles.json`：预警策略模板，保存价格阈值、波动提醒和提醒行为白名单，不包含 SMTP、Webhook URL 或密钥。
- `portfolio_positions.json`：本地持仓记录。
- `portfolio_transactions.json`：本地持仓流水；定投生成的流水包含执行时行情来源、源时间、接收时间、缓存状态和质量快照。
- `portfolio_investment_plans.json`：本地持仓定投计划。
- `portfolio_import_backup.json`：最近一次持仓流水导入的可撤销备份。
- `market_cache.json`：最近可用金价与汇率缓存。
- `source_metrics.json`：版本化数据源滚动指标，默认每个数据源保留最近 50 次探测。
- `price_history.json`：本地价格历史。
- `price_history.sqlite3`：本地价格历史主存储。
- `price_history.repair-backup.sqlite3`：最近一次历史数据修复前的 SQLite 恢复点；下一次成功修复时覆盖，执行恢复后移除。
- `alert_log.sqlite3`：本地警报记录主存储。
- `risk_analysis_history.json`：风险分析历史。
- `review_notes.json`：本地复盘笔记，最多保存 500 条；单条标题最多 80 个字符、正文最多 2000 个字符，可选关联时间轴事件。
- `daily_digest_state.json`：每日摘要最近执行与发送状态，用于避免同一天重复发送；手动测试发送不会占用当天的计划发送资格。
- `exports/`：默认导出目录，可在设置页修改。桌面版支持通过系统目录选择器设置路径，浏览器模式可手动输入路径；保存导出目录时会检查目录是否可写。配置备份、诊断报告和复盘报告会保存到当前导出目录。复盘报告基于本地历史、警报、风险分析历史、复盘笔记、新闻缓存和数据状态生成，不会自动调用模型。
- `GoldMonitor.log`：运行日志。

从 1.0.7 或更早版本升级时，程序会读取 `thresholds.json`、`watch_targets.json` 和 `portfolio_alerts.json` 并一次性迁移到 `alert_rules.json`。迁移完成后，旧文件仅作为迁移来源保留，不再接收新的规则写入。

运维设置中的“完整数据归档”会备份上述可恢复状态和 SQLite 数据库，但不包含更新安装包、普通导出产物、运行日志或临时的历史修复恢复点。完整归档包含密钥原文等敏感信息，应作为本机敏感备份保管；普通配置备份仍不包含密钥原文。完整归档恢复成功后会清理本机已有的历史修复恢复点，避免将旧恢复点应用到新恢复的数据上。

完整数据归档的创建和恢复会与历史数据写入、诊断及修复互斥执行，避免归档中的 JSON 与 SQLite 历史状态来自不同写入阶段，或恢复过程被后台行情写入覆盖。

历史数据维护中的修复操作必须先查看影响范围并确认。预览令牌仅对当前连接和当前操作生效，有效期为 5 分钟且只能使用一次；预览会绑定数据库和 JSON 归档的数据状态，即使记录数量和预计影响不变，只要确认前实际内容发生变化，旧预览也会被拒绝，需重新预览后执行。

历史数据修复的成功和失败结果会显示在运维页“最近操作记录”中。执行失败后旧预览会立即关闭并自动刷新诊断，避免重复提交已经失效的确认令牌。

清理无效明细、重建汇总或同步 JSON 前会自动创建一个数据库恢复点。运维页可预览并恢复最近一次修复前的 SQLite 明细和汇总；恢复不会修改 JSON 历史归档，完成后恢复点会被消费。

SMTP 授权码、DeepSeek API Key 和 OpenAI 兼容接口 API Key 会优先保存到系统凭据存储：

- Windows：Credential Manager。
- macOS：Keychain。

配置备份不包含敏感字段，也不包含“已配置”或掩码值等状态衍生字段；诊断报告只包含敏感字段的配置状态，不包含原文密钥。旧版本中已经写入 `settings.json` 的敏感字段会在下次保存设置时迁移到系统凭据存储。

配置备份当前使用 schema v1。无 `schema_version` 字段的旧备份按 v0 处理，导入预检会明确提示并在确认导入时迁移；高于当前支持版本或版本字段非法的备份会在预检阶段被拒绝，不会写入配置。

重新安装程序通常不会删除这些配置。卸载或手动删除 `%APPDATA%\GoldMonitor` 后，本地配置和历史才会丢失。

## 本地开发

macOS 可双击根目录中的 `GoldMonitor.command` 启动浏览器模式，也可以在终端运行：

```bash
./scripts/start_mac.sh
```

脚本会创建 `.venv`，安装 Flask、Flask-SocketIO 和 requests，并把本地数据写入 `~/Library/Application Support/GoldMonitor`。源码目录下的 macOS 启动方式默认使用浏览器模式；Release 中的 `.app` 会以桌面窗口启动。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-build.txt -c constraints\windows-py312.txt
```

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-build.txt -c constraints/macos-py312.txt
```

上述命令使用当前平台的 Python 3.12 constraints，确保本地与 CI/Release 的依赖版本一致。依赖锁定更新规则参见 [贡献指南](CONTRIBUTING.md#更新依赖锁定)。

运行完整检查：

Windows：

```powershell
.\.venv\Scripts\python.exe scripts\run_checks.py
```

macOS：

```bash
.venv/bin/python scripts/run_checks.py
```

该入口会执行 Python 语法检查、现有契约检查和完整 pytest；Windows 还会执行 PowerShell 契约检查。贡献要求参见 [贡献指南](CONTRIBUTING.md)。

## 本地打包

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm GoldMonitor.spec
.\.tools\InnoSetup6\ISCC.exe .\installer\GoldMonitor.iss
```

```bash
PYTHON_BIN=.venv/bin/python ./scripts/build_macos_dmg.sh
```

构建结果：

- Windows 程序目录：`dist\GoldMonitor`
- Windows 安装包：`release\GoldMonitorSetup.exe`
- macOS 安装包：`release\GoldMonitor-macOS.dmg`

## 发布流程

发布前必须同步三处版本：

- `goldmonitor/application.py` 中的 `APP_VERSION`
- `installer/GoldMonitor.iss` 中的 `MyAppVersion`
- `CHANGELOG.md` 中对应版本的变更内容

推送版本标签会触发 GitHub Actions 自动发布：

```powershell
git tag v1.0.0
git push origin main
git push origin v1.0.0
```

GitHub Actions 会执行检查、构建 Windows EXE 和 macOS DMG、生成 `version.json`，并把 `GoldMonitorSetup.exe`、`GoldMonitor-macOS.dmg` 与 `version.json` 上传到对应 Release。

发布完成后，GitHub Actions 会继续运行发布资产验收，自动下载 `version.json`、Windows 安装包和 macOS DMG，并校验版本、下载地址和 SHA256。

如果 `CHANGELOG.md` 中缺少当前版本说明，发布流程会失败。

## 参与贡献

开发环境、测试要求、Commit 和 Pull Request 规范参见 [贡献指南](CONTRIBUTING.md)。

## 安全问题

安全漏洞不要提交公开 Issue，请按照 [安全策略](SECURITY.md) 使用私密报告入口。

## 许可证

GoldMonitor 使用 [MIT License](LICENSE) 发布。
