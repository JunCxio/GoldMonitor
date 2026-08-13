# 发布验收清单

本文档用于每次版本发布后的验收。执行前确认当前版本号已经在 `app.py`、`installer/GoldMonitor.iss` 和 `CHANGELOG.md` 中同步，并已推送对应 `vX.Y.Z` 标签。

## 1. 基础信息

- 版本号：`vX.Y.Z`
- 提交号：发布标签指向的 commit。
- Release 页面：`https://github.com/JunCxio/GoldMonitor/releases/tag/vX.Y.Z`
- Actions 页面：对应 Release workflow run。

## 2. 本地发布前检查

在推送标签前运行：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/goldmonitor-pycache .venv/bin/python scripts/run_checks.py
```

Windows 使用 `\.venv\Scripts\python.exe scripts\run_checks.py`。该入口包含 Python 语法、脚本契约、完整 pytest 和平台专项检查；仍可按下列命令单独定位失败。

继续运行项目脚本级回归：

```bash
python tests/frontend_asset_check.py
python tests/engineering_foundation_check.py
python tests/risk_contract_check.py
python tests/event_timeline_review_check.py
python tests/startup_contract_check.py
python tests/socket_connect_check.py
python tests/threshold_persistence_check.py
python tests/gold_cache_check.py
python tests/forex_cache_check.py
python tests/price_fetch_with_cache_check.py
python tests/fetch_status_check.py
python tests/news_logic_check.py
python tests/update_logic_check.py
python tests/watch_targets_check.py
python tests/port_selection_check.py
```

Windows 环境还需要运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\contract_checks.ps1
```

## 3. GitHub Actions 检查

- Release workflow 已由版本标签触发。
- Windows job 成功完成。
- macOS job 成功完成。
- publish-release job 成功完成。
- verify-release job 成功完成。
- Release 不是 draft，也不是 prerelease。

## 4. Release 资产检查

Release 必须包含以下资产：

- `GoldMonitorSetup.exe`
- `GoldMonitor-macOS.dmg`
- `version.json`

下载 `version.json` 并确认：

- `version` 等于当前版本号。
- 顶层 `url` 指向 Windows 安装包。
- 顶层 `sha256` 等于 Windows 安装包 SHA256。
- `downloads.windows.url` 指向 `GoldMonitorSetup.exe`。
- `downloads.windows.sha256` 与 Windows 安装包实际 SHA256 一致。
- `downloads.macos.url` 指向 `GoldMonitor-macOS.dmg`。
- `downloads.macos.sha256` 与 macOS DMG 实际 SHA256 一致。
- `notes` 与 `CHANGELOG.md` 当前版本内容一致或语义一致。

可自动化部分由 Release workflow 的 verify-release job 执行，也可以手动运行：

```bash
python scripts/verify_release_assets.py --tag vX.Y.Z --repository JunCxio/GoldMonitor
```

## 5. 下载与完整性检查

下载两个安装包到临时目录并计算 SHA256：

```bash
shasum -a 256 GoldMonitorSetup.exe
shasum -a 256 GoldMonitor-macOS.dmg
```

检查文件类型：

```bash
file GoldMonitorSetup.exe GoldMonitor-macOS.dmg version.json
```

macOS 环境检查 DMG：

```bash
hdiutil verify GoldMonitor-macOS.dmg
hdiutil attach -readonly -nobrowse -mountpoint /tmp/goldmonitor-dmg GoldMonitor-macOS.dmg
/usr/libexec/PlistBuddy -c Print:CFBundleShortVersionString /tmp/goldmonitor-dmg/GoldMonitor.app/Contents/Info.plist
test -x /tmp/goldmonitor-dmg/GoldMonitor.app/Contents/MacOS/GoldMonitor
hdiutil detach /tmp/goldmonitor-dmg
```

## 6. 平台冒烟测试

Windows 安装包：

- 安装包可启动，无管理员权限要求异常。
- 安装后程序可启动主窗口。
- 设置页可打开并保存基础设置。
- 手动刷新行情能返回数据或明确的缓存/失败状态。
- 数据源详情能显示当前主源、滚动成功率、延迟和质量扣分依据。
- 数据源启停和排序在刷新后生效，金价源或汇率源不能全部停用；单源探测和恢复默认可用。
- 历史图表可切换 30 日、90 日范围，长时间范围不会强制读取全部原始点。
- 预警中心可新增价格、波动、目标价和持仓规则，类型筛选、状态汇总、复制、启停、重置和删除均可用。
- 规则名称搜索、状态筛选、当前结果全选及批量启用、停用、重置和删除均可用；包含失效规则编号时不会部分保存。
- 规则详情能显示当前值、目标值、距触发差距和等待原因，并能加载最近 30 天触发、送达、处理及行情延续复盘。
- 新建或编辑价格、波动、目标价和持仓规则时，可运行 7 天、30 天、90 天历史模拟并显示命中、有效触发、后续命中或冷却抑制、数据覆盖和时段分布；持仓流水缺少交易日期时拒绝生成不可靠结果。
- 单规则有效期、冷却时间和通知渠道可保存并在刷新后恢复；“仅记录”不会发送本机、邮件或 Webhook 通知。
- 从 1.0.7 数据目录升级时，旧阈值、观察目标和持仓提醒只迁移一次，后续规则写入 `alert_rules.json`。
- 警报记录可查看关联规则；规则删除后可从历史快照生成复制草稿。
- 持仓复盘可查看总收益曲线、已实现收益曲线和预警有效性。
- 持仓定投可创建每天、每周、每月和每年计划；每周计划可选择星期一至星期日，并支持人民币与美元固定金额、手续费、关联已有持仓或首次执行创建持仓。
- 定投计划可编辑、暂停、重新启用、立即执行和删除；立即执行后仅生成带“定投”来源标识的本地买入流水，不触发真实交易。
- 定投计划可复制为名称带“副本”且默认暂停的新草稿；复制本身不保存计划、不生成流水，确认修改后才可保存。
- 定投计划可选开始日期和结束日期；开始前不执行，结束后补完范围内最后一期并显示已完成，两个日期留空时保持长期有效。
- 定投计划可跳过当前期次；确认后不生成持仓流水，计划保持启用并推进到下一期，重复提交旧期次时必须拒绝。
- 定投计划首次执行后可查看累计投入、手续费、执行次数、累计数量、定投均价、当前市值、盈亏和最近 10 条执行记录；普通手动流水不计入计划绩效。
- 单个定投计划可将全部执行记录导出为 CSV；导出内容只包含该计划生成的定投买入流水，并显示实际保存路径。
- 无有效行情时计划显示等待行情，删除关联持仓时自动暂停；应用关闭期间只补最近一期，重新启用后不补停用期间的历史期次。
- 今日概览可查看到期或异常计划及当日执行结果，并可跳转到对应计划；每日摘要预览包含计划汇总、下一次计划、最近执行和异常计划。
- 新安装可完成或暂不设置首次使用向导，完成后不会重复自动弹出。
- 完整数据归档可创建、预检并恢复；篡改文件或哈希时必须拒绝恢复。
- 配置导出和诊断报告导出可生成文件。
- 程序内更新检查能识别当前版本。

macOS DMG：

- DMG 可打开并显示 `GoldMonitor.app`。
- App 可复制到“应用程序”目录并启动。
- 菜单栏状态项可显示。
- 主窗口可打开、隐藏和恢复。
- 手动刷新行情能返回数据或明确的缓存/失败状态。
- 数据源详情能显示当前主源、滚动成功率、延迟和质量扣分依据。
- 数据源启停和排序在刷新后生效，金价源或汇率源不能全部停用；单源探测和恢复默认可用。
- 历史图表可切换 30 日、90 日范围，长时间范围不会强制读取全部原始点。
- 预警中心可新增价格、波动、目标价和持仓规则，类型筛选、状态汇总、复制、启停、重置和删除均可用。
- 规则名称搜索、状态筛选、当前结果全选及批量启用、停用、重置和删除均可用；包含失效规则编号时不会部分保存。
- 规则详情能显示当前值、目标值、距触发差距和等待原因，并能加载最近 30 天触发、送达、处理及行情延续复盘。
- 新建或编辑价格、波动、目标价和持仓规则时，可运行 7 天、30 天、90 天历史模拟并显示命中、有效触发、后续命中或冷却抑制、数据覆盖和时段分布；持仓流水缺少交易日期时拒绝生成不可靠结果。
- 单规则有效期、冷却时间和通知渠道可保存并在刷新后恢复；“仅记录”不会发送本机、邮件或 Webhook 通知。
- 从 1.0.7 数据目录升级时，旧阈值、观察目标和持仓提醒只迁移一次，后续规则写入 `alert_rules.json`。
- 警报记录可查看关联规则；规则删除后可从历史快照生成复制草稿。
- 持仓复盘可查看总收益曲线、已实现收益曲线和预警有效性。
- 持仓定投可创建每天、每周、每月和每年计划；每周计划可选择星期一至星期日，并支持人民币与美元固定金额、手续费、关联已有持仓或首次执行创建持仓。
- 定投计划可编辑、暂停、重新启用、立即执行和删除；立即执行后仅生成带“定投”来源标识的本地买入流水，不触发真实交易。
- 定投计划可复制为名称带“副本”且默认暂停的新草稿；复制本身不保存计划、不生成流水，确认修改后才可保存。
- 定投计划可选开始日期和结束日期；开始前不执行，结束后补完范围内最后一期并显示已完成，两个日期留空时保持长期有效。
- 定投计划可跳过当前期次；确认后不生成持仓流水，计划保持启用并推进到下一期，重复提交旧期次时必须拒绝。
- 定投计划首次执行后可查看累计投入、手续费、执行次数、累计数量、定投均价、当前市值、盈亏和最近 10 条执行记录；普通手动流水不计入计划绩效。
- 单个定投计划可将全部执行记录导出为 CSV；导出内容只包含该计划生成的定投买入流水，并显示实际保存路径。
- 无有效行情时计划显示等待行情，删除关联持仓时自动暂停；应用关闭期间只补最近一期，重新启用后不补停用期间的历史期次。
- 今日概览可查看到期或异常计划及当日执行结果，并可跳转到对应计划；每日摘要预览包含计划汇总、下一次计划、最近执行和异常计划。
- 新安装可完成或暂不设置首次使用向导，完成后不会重复自动弹出。
- 完整数据归档可创建、预检并恢复；篡改文件或哈希时必须拒绝恢复。
- 配置导出和诊断报告导出可生成文件。
- 程序内更新检查能识别当前版本。

## 7. 回滚准备

- 保留上一版本 Release。
- 确认上一版本 `version.json` 可下载。
- 如发现阻断问题，优先发布补丁版本，不覆盖已发布标签。
- 如需要撤回当前版本，在 Release 页面标记说明，并保留问题记录。

## 8. 验收记录

每次发布后记录：

- 验收日期。
- 执行人。
- 版本号和提交号。
- Release workflow 结果。
- 下载资产大小与 SHA256。
- 平台冒烟结果。
- 未覆盖项和原因。
- 后续修复项。
