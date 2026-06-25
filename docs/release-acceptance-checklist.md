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
python -m pytest
python -m py_compile app.py goldmonitor/*.py tests/*.py
node --check static/app.js
node --check static/app-shell.js
```

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
- 配置导出和诊断报告导出可生成文件。
- 程序内更新检查能识别当前版本。

macOS DMG：

- DMG 可打开并显示 `GoldMonitor.app`。
- App 可复制到“应用程序”目录并启动。
- 菜单栏状态项可显示。
- 主窗口可打开、隐藏和恢复。
- 手动刷新行情能返回数据或明确的缓存/失败状态。
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
