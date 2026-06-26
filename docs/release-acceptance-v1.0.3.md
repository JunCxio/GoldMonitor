# GoldMonitor v1.0.3 发布验收记录

## 基础信息

- 验收日期：2026-06-26
- 执行人：项目维护者
- 版本号：`v1.0.3`
- 提交号：`189b4f6702c0296fd0774e22adc87a026a6e7a68`
- Release 页面：https://github.com/JunCxio/GoldMonitor/releases/tag/v1.0.3
- Release workflow：https://github.com/JunCxio/GoldMonitor/actions/runs/28226194350

## Actions 结果

- Release workflow：成功。
- Release 状态：非 draft，非 prerelease。
- Release 资产：`GoldMonitorSetup.exe`、`GoldMonitor-macOS.dmg`、`version.json`。

## 本地检查结果

- `python -m py_compile app.py setup_gui.py tests/*.py scripts/verify_release_assets.py scripts/generate_release_manifest.py`：通过。
- `tests/frontend_asset_check.py`：通过。
- `node --check static/app.js`：通过。
- `git diff --check`：通过。
- `tests/risk_contract_check.py`：通过。
- `tests/engineering_foundation_check.py`：通过。
- `tests/test_storage_modules.py`：通过。
- `tests/test_portfolio_module.py`：20 passed。
- `tests/test_portfolio_alerts_module.py`：通过。
- `tests/test_portfolio_alerts_app.py`：通过。
- `tests/test_risk_analysis_module.py`：通过。
- `tests/test_market_data_module.py`：通过。
- `tests/test_settings_store_module.py`：通过。
- `tests/test_notifications_module.py`：通过。
- `tests/test_event_timeline_module.py`：通过。
- `tests/test_update_manager_module.py`：通过。
- `tests/test_platform_module.py`：通过。
- `tests/test_news_module.py`：通过。
- `tests/test_targets_module.py`：通过。
- `tests/test_support_files_module.py`：通过。
- `tests/test_desktop_ui_module.py`：通过。
- `tests/startup_contract_check.py`：通过。
- `tests/update_logic_check.py`：通过。
- `tests/gold_cache_check.py`：通过。
- `tests/price_fetch_with_cache_check.py`：通过。
- `tests/fetch_status_check.py`：通过。
- `tests/threshold_persistence_check.py`：通过。
- `tests/socket_connect_check.py`：通过。
- `tests/news_logic_check.py`：通过。
- `tests/forex_cache_check.py`：通过。
- `tests/port_selection_check.py`：通过。
- `tests/event_timeline_review_check.py`：通过。
- `tests/test_verify_release_assets_script.py`：3 passed。

当前 macOS 环境未安装 `pwsh` 或 `powershell`，因此 `tests/contract_checks.ps1` 未在本机运行；该检查由 Release workflow 的 Windows job 覆盖。

## 线上清单检查

`version.json` 内容要点：

- `version`：`1.0.3`
- Windows URL：`https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.3/GoldMonitorSetup.exe`
- Windows SHA256：`5c0e7ee599c8affddf883d0f706b772ef649d55a4710afc522d962f42f366a35`
- macOS URL：`https://github.com/JunCxio/GoldMonitor/releases/download/v1.0.3/GoldMonitor-macOS.dmg`
- macOS SHA256：`7fbc2db33a192d64239a6b6cfc25747ce8097608abf57e0d80d8493f5857a81a`

下载 URL 检查：

- Windows 安装包 URL：HTTP 200，大小 `21067842` 字节。
- macOS DMG URL：HTTP 200，大小 `17049609` 字节。
- `version.json`：HTTP 200，大小 `1129` 字节。

## 下载资产校验

- `GoldMonitorSetup.exe`
  - 大小：`21067842` 字节。
  - SHA256：`5c0e7ee599c8affddf883d0f706b772ef649d55a4710afc522d962f42f366a35`
- `GoldMonitor-macOS.dmg`
  - 大小：`17049609` 字节。
  - SHA256：`7fbc2db33a192d64239a6b6cfc25747ce8097608abf57e0d80d8493f5857a81a`

## 未覆盖项

- 当前环境无法运行 Windows 安装包，因此未执行 Windows 安装、启动和程序内更新冒烟测试。
- 当前验收未把发布版 macOS App 复制到“应用程序”目录启动，以避免改变本机应用状态。

## 结论

`v1.0.3` Release 的线上资产、版本清单、下载完整性和 SHA256 检查均通过。Windows 运行态冒烟测试需要在 Windows 环境补充执行。
