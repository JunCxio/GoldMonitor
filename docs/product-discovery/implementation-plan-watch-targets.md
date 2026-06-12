# 目标价观察清单实现方案

## 目标

实现第一版目标价观察清单，让用户可以维护多个关注价位，并在价格达到目标时触发现有告警链路。

本方案只覆盖 MVP：

- 新增、编辑、删除观察项。
- 支持启用、停用、重置触发状态。
- 支持 RMB/克 和 USD/oz。
- 支持上涨至目标价、下跌至目标价。
- 支持备注。
- 本地持久化。
- 触发后进入现有警报记录和通知链路。

## 现有链路

### 入口

- 前端主页面：`templates/index.html`
- 后端 Socket.IO：`app.py`
- 价格刷新：`fetch_price_once`
- 固定阈值检查：`_check_thresholds`
- 波动提醒检查：`_check_volatility`
- 告警分发：`emit_alert`
- 告警记录：`alert_log` 和 `alert_log.sqlite3`

### 已有状态

- `price_usd`
- `price_rmb`
- `thresholds`
- `volatility_config`
- `alert_log`

### 已有持久化

- `settings.json`
- `thresholds.json`
- `price_history.sqlite3`
- `alert_log.sqlite3`
- `risk_analysis_history.json`

## 新增数据结构

### 文件路径

```python
WATCH_TARGETS_PATH = os.path.join(APPDATA_DIR, "watch_targets.json")
```

### 运行时状态

```python
watch_targets = []
```

### 单条观察项

```json
{
  "id": "target-1f2e3d4c",
  "mode": "rmb",
  "direction": "fall_to",
  "price": 688.0,
  "note": "预算观察价",
  "enabled": true,
  "triggered": false,
  "created_at": "2026-06-12T10:00:00",
  "updated_at": "2026-06-12T10:00:00",
  "triggered_at": "",
  "last_trigger_price": null
}
```

### 字段约束

- `id`：字符串。新增时由后端生成。
- `mode`：只能是 `rmb` 或 `usd`。
- `direction`：只能是 `rise_to` 或 `fall_to`。
- `price`：大于 0 的有限数字。
- `note`：字符串，建议截断到 200 字以内。
- `enabled`：布尔值。
- `triggered`：布尔值。
- `created_at`、`updated_at`、`triggered_at`：ISO 时间字符串。
- `last_trigger_price`：数字或 `null`。

## 后端函数

### 归一化

```python
normalize_watch_target(item, existing=None)
```

职责：

- 校验并清洗字段。
- 新增时生成 id 和时间。
- 编辑时保留 `created_at`。
- 价格或方向变化时重置触发状态。

异常：

- 无效单位、方向、价格时抛出 `ValueError`。

### 读取

```python
load_watch_targets()
```

职责：

- 文件不存在时返回空列表。
- 文件格式异常时记录日志并返回空列表。
- 逐条归一化，跳过无效项。

### 保存

```python
save_watch_targets(items=None)
```

职责：

- 写入 `watch_targets.json`。
- 使用临时文件再替换，避免写入中断导致文件损坏。
- 返回归一化后的列表。

异常：

- 目录不可写时抛出 `OSError`，由 Socket.IO 事件转成前端错误。

### 快照

```python
get_watch_targets_state()
```

职责：

- 返回前端可直接渲染的观察清单。
- 未来可扩展统计字段，如启用数量、已触发数量。

### 新增或编辑

```python
upsert_watch_target(data)
```

职责：

- 有 id 时编辑。
- 无 id 时新增。
- 保存并返回最新清单。

### 删除

```python
delete_watch_target(target_id)
```

职责：

- 删除指定观察项。
- 不存在时返回失败。

### 启停

```python
toggle_watch_target(target_id, enabled)
```

职责：

- 修改启用状态。
- 停用不清除触发状态。

### 重置触发状态

```python
reset_watch_target(target_id)
```

职责：

- 将 `triggered` 改为 `False`。
- 清空 `triggered_at` 和 `last_trigger_price`。

### 触发检查

```python
check_watch_targets(now_str)
```

职责：

- 检查所有启用且未触发的观察项。
- 按 `mode` 选择 `price_rmb` 或 `price_usd`。
- 达到条件时调用 `emit_alert`。
- 更新观察项触发状态并保存。
- 推送 `watch_targets_updated`。

触发条件：

- `rise_to`：当前价格 >= 目标价。
- `fall_to`：当前价格 <= 目标价。

## Socket.IO 契约

### 初始化

`init_state` 增加：

```json
{
  "watch_targets": []
}
```

### 设置观察项

事件：

```text
set_watch_target
```

请求：

```json
{
  "id": "target-1f2e3d4c",
  "mode": "rmb",
  "direction": "fall_to",
  "price": "688",
  "note": "预算观察价",
  "enabled": true
}
```

成功推送：

```text
watch_targets_updated
```

失败推送：

```text
watch_target_error
```

### 删除观察项

事件：

```text
delete_watch_target
```

请求：

```json
{
  "id": "target-1f2e3d4c"
}
```

### 启停观察项

事件：

```text
toggle_watch_target
```

请求：

```json
{
  "id": "target-1f2e3d4c",
  "enabled": false
}
```

### 重置观察项

事件：

```text
reset_watch_target
```

请求：

```json
{
  "id": "target-1f2e3d4c"
}
```

## 前端实现

### 入口

在右侧预警区域增加“目标价观察”分组。

建议位置：

- `threshold-card` 内部，在 `alertRulesList` 下方。
- 或新增同级小区域，避免与警报记录混在一起。

### 前端状态

```javascript
let watchTargets = [];
let activeWatchTargetId = null;
```

### 前端函数

- `renderWatchTargets()`
- `setActiveWatchTarget(id)`
- `saveWatchTarget(id)`
- `deleteWatchTarget(id)`
- `toggleWatchTarget(id, enabled)`
- `resetWatchTarget(id)`
- `formatWatchTargetDirection(direction)`
- `formatWatchTargetState(item)`

### Socket 监听

- `watch_targets_updated`
- `watch_target_error`

### UI 状态

- 空状态：暂无观察目标。
- 启用：正常显示。
- 停用：弱化显示。
- 已触发：显示触发时间和触发价格。
- 编辑中：展开表单。

## 持久化与导出

### 必做

- `watch_targets.json` 保存和读取。
- 程序启动时加载。
- 配置目录不可写时前端报错。

### 建议做

- 诊断报告增加：
  - 文件路径。
  - 观察项总数。
  - 启用数量。
  - 已触发数量。

### 暂不做

- 配置导出导入是否包含观察清单。

原因：观察清单更接近运行数据还是用户配置，需要在实现前确认。第一版可以先放入诊断报告，后续再决定是否进入配置备份。

## 异常路径

- 请求不是对象：返回“观察项格式无效”。
- id 不存在：返回“未找到观察项”。
- mode 非法：返回“观察单位无效”。
- direction 非法：返回“观察方向无效”。
- price 非法：返回“请输入有效的目标价格”。
- 配置目录不可写：返回“观察清单保存失败，请检查配置目录权限”。
- 当前价格为空：跳过触发，不报错。
- 文件损坏：记录日志，启动时返回空清单。
- 已触发观察项：不重复触发。
- 停用观察项：不触发。

## 调用方影响

### 对现有阈值功能

不修改现有 `thresholds` 数据结构。

### 对告警记录

复用 `emit_alert` 和 `save_alert_log_entry`。新增告警字段应保持兼容：

```json
{
  "source": "watch_target",
  "watch_target_id": "target-1f2e3d4c"
}
```

现有前端如果不识别这些字段，也应正常显示消息。

### 对风险分析

不自动触发风险分析。用户仍可从警报详情手动触发。

### 对通知渠道

复用现有邮件、Webhook、系统弹窗和声音设置。不为单条观察项新增独立通知配置。

## 测试计划

### 后端契约测试

建议新增：

```text
tests/watch_targets_check.py
```

覆盖：

- 保存和读取观察项。
- 无效 mode、direction、price。
- 新增、编辑、删除。
- 启用、停用、重置。
- 触发上涨目标。
- 触发下跌目标。
- 已触发不重复触发。
- 停用不触发。
- 触发后写入告警记录。
- 不自动调用风险分析。

### 静态契约测试

可在 `tests/contract_checks.ps1` 中补充：

- `WATCH_TARGETS_PATH`
- `load_watch_targets`
- `save_watch_targets`
- `check_watch_targets`
- `renderWatchTargets`

### 手动验证

1. 启动应用。
2. 新增 RMB 下跌目标价。
3. 模拟或等待价格达到目标。
4. 确认警报记录出现观察清单提醒。
5. 停用观察项后确认不再触发。
6. 重置触发状态后确认可再次触发。
7. 重启应用后确认观察清单仍存在。

## 开发顺序

1. 新增后端模型和持久化。
2. 新增 Socket.IO 管理事件。
3. 接入价格刷新触发链路。
4. 新增后端契约测试。
5. 新增前端清单 UI。
6. 更新诊断报告。
7. 更新 README 和 CHANGELOG。

## 不做事项

- 不做账号体系。
- 不做云同步。
- 不做自动交易。
- 不做交易建议。
- 不做自动风险分析。
- 不做多品种扩展。
- 不重构现有阈值模型。
