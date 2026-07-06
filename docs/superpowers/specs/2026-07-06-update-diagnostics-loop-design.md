# 更新状态与诊断闭环设计

## 背景

`v1.0.2` 已经补齐风险分析失败诊断和诊断摘要复制能力，但更新检查仍主要集中在顶部更新弹窗里。用户在遇到更新失败、网络异常、版本不确定时，需要在更新弹窗和运维设置之间切换，排障路径不够集中。

本轮目标是在不改变发布流程和更新源安全边界的前提下，把“检查更新、查看状态、复制诊断”收拢到设置页运维区，形成一个可复用的更新排障入口。

## 目标

- 在“设置 > 运维”中展示更新状态摘要。
- 用户能在运维区直接触发更新检查。
- 用户能从运维区打开现有更新弹窗执行安装流程。
- 更新检查失败时，运维区显示失败原因，并提供复制诊断入口。
- 运维区状态与现有更新弹窗使用同一份 `update_status` 数据，避免两个入口显示不一致。

## 非目标

- 不改 GitHub Release 发布流程。
- 不增加可配置更新源。
- 不向前端暴露下载地址、SHA256 或安装包本地路径。
- 不重写更新弹窗和安装流程。
- 不增加后台持久化表或新的配置文件。

## 用户入口

### 设置页运维区

在现有“导出配置 / 导入配置 / 诊断报告 / 导出目录 / 恢复默认设置”附近新增一行“更新状态”。

该区域展示：

- 当前版本
- 最新版本
- 最近检查时间
- 状态文本
- 失败原因或提示说明

操作按钮：

- `检查更新`：复用现有 `check_update` socket 事件。
- `打开更新`：打开现有更新弹窗；若已有可用版本，用户继续使用现有安装按钮。
- `复制诊断`：复用现有 `copyDiagnostics()`，复制完整诊断摘要。

### 现有更新弹窗

保留现有弹窗结构和安装流程。弹窗仍用于查看更新说明、安装进度和执行安装。

## 状态设计

前端新增一个轻量状态对象，例如：

```javascript
let opsUpdateStatus = null;
```

来源：

- `update_status` socket 事件。
- 前端主动点击“检查更新”时先进入本地检查中状态。
- 页面加载后的自动检查也应更新该状态。

状态字段使用后端已有 `update_status` payload：

- `state`
- `message`
- `current_version`
- `latest_version`
- `checked_at`
- `notes`
- `progress_percent`

前端只渲染允许展示的字段，不依赖 `url`、`sha256`、`manifest_url` 等后端安装元数据。

## 数据流

1. 用户打开设置页运维区。
2. 前端渲染最近一次 `opsUpdateStatus`；如果没有状态，显示“尚未检查更新”。
3. 用户点击“检查更新”。
4. 前端设置运维区为“正在检查更新...”，调用 `socket.emit('check_update')`。
5. 后端执行现有 `get_update_status()`。
6. 后端通过现有 `update_status` 事件返回状态。
7. 前端 `applyUpdateStatus(data)` 继续更新原更新弹窗，同时调用新的运维区渲染函数。
8. 如果失败，用户可以点击“复制诊断”，复制包含更新状态的诊断摘要。

## 后端契约

后端优先复用现有能力：

- `get_update_status()`
- `@socketio.on("check_update")`
- `update_status` 事件
- `build_diagnostics_clipboard_text()`

需要补充：

- 诊断摘要中加入“更新状态”小节，包含当前版本、最新版本、检查状态、检查时间和失败原因。
- 后端新增一个运行时最近更新状态，例如 `last_update_status`，由 `get_update_status()` 或 `check_update` 完成后更新。
- `last_update_status` 不持久化，不进入用户配置，不影响启动速度；进程重启后显示为“尚未检查更新”。
- `build_diagnostics_clipboard_text()` 从 `last_update_status` 读取最近一次更新状态；没有状态时只展示当前版本和“尚未检查更新”。

`build_diagnostics_report()` 可包含同一份脱敏后的 `last_update_status`，但仍不得包含下载 URL、SHA256、manifest URL 或本地安装包路径。

## 前端契约

新增函数：

- `renderOpsUpdateStatus(data)`
- `checkUpdateFromOps()`
- `openUpdateFromOps()`

修改点：

- `applyUpdateStatus(data)` 在更新弹窗状态后，同步调用 `renderOpsUpdateStatus(data)`。
- `requestUpdateCheck(silent)` 触发检查中状态时，也更新运维区。
- 设置页运维区模板新增 `id="opsUpdateStatus"`、`id="opsUpdateMeta"` 和操作按钮。

交互要求：

- `检查更新` 按钮可重复点击，但点击后先显示检查中。
- `打开更新` 始终打开现有更新弹窗，不单独实现安装。
- `复制诊断` 与诊断报告区域使用同一个复制函数，避免两套剪贴板逻辑。

## 异常路径

- 更新检查失败：显示后端 `message`，同时保留“复制诊断”按钮。
- 网络受限或 GitHub 不可达：显示失败消息，不暴露内部 URL。
- 后端返回未知状态：显示“更新状态未知”，按钮仍可继续检查。
- 自动检查静默触发：不弹出更新弹窗，但运维区更新最近状态。

## 测试计划

### 前端契约测试

更新 `tests/frontend_asset_check.py`：

- 模板包含运维区更新状态元素。
- JS 包含 `renderOpsUpdateStatus`、`checkUpdateFromOps`、`openUpdateFromOps`。
- `applyUpdateStatus(data)` 同步调用运维区渲染。
- 运维区复用 `copyDiagnostics()`。

### 后端契约测试

更新 `tests/update_logic_check.py` 或 `tests/risk_contract_check.py`：

- 诊断复制摘要包含“更新状态”。
- 摘要不包含下载 URL、SHA256 或 manifest URL。
- `get_update_status()` 给前端的普通状态仍不暴露安装元数据。

### 验收命令

- `.venv/bin/python tests/frontend_asset_check.py`
- `.venv/bin/python tests/update_logic_check.py`
- `.venv/bin/python tests/risk_contract_check.py`
- `node --check static/app.js`
- `.venv/bin/python -m pytest`
- `git diff --check`

## 验收标准

- 设置页运维区能看到当前版本、最新版本、最近检查时间和状态。
- 点击“检查更新”后，运维区和更新弹窗状态一致。
- 更新检查失败时，运维区显示失败原因，并可复制诊断。
- 有新版本时，运维区可以打开现有更新弹窗继续安装。
- 诊断摘要包含更新状态，但不泄露下载地址、SHA256 或更新源地址。
- 原有自动更新、手动更新和安装流程保持可用。
