# GoldMonitor

GoldMonitor 是一个 Windows 桌面黄金价格监控工具，用于查看实时金价、设置风险提醒、接收邮件通知、手动生成风险分析，并通过桌面悬浮条持续关注行情。

## 主要功能

- 实时获取 XAU/USD、人民币克价和 USD/CNY 汇率，展示数据源、更新时间、缓存状态和日内统计。
- 支持上涨、下跌、关键价位和短时波动提醒，可分别控制弹窗、声音和邮件通知。
- 支持提醒冷却时间、静默时段、邮件标题模板和正文模板。
- 支持 Webhook 通知，可按预警级别控制是否发送。
- 支持桌面金价悬浮条，显示涨跌颜色、更新时间和数据源状态，并提供右键菜单。
- 支持风险分析助手，用户手动触发，避免后台自动消耗模型 token。
- 风险分析支持 DeepSeek 和 OpenAI 兼容接口，支持模型列表下拉、连接测试、分析深度、缓存、历史、复制和导出报告。
- 支持数据源健康面板，展示行情源、汇率源、缓存回退、失败原因和响应耗时。
- 支持本地价格历史 SQLite 持久化、历史复盘、图表事件标记和 CSV 导出。
- 支持配置导出、配置导入、恢复默认设置和诊断报告导出。
- 支持软件更新检查、下载进度、SHA256 校验、安装器启动和 GitHub Release 更新源。

## 下载

最新安装包发布在 GitHub Releases：

```text
https://github.com/JunCxio/GoldMonitor/releases/latest
```

用户通常只需要下载 `GoldMonitorSetup.exe` 并运行安装。安装包是按用户目录安装，不需要管理员权限。

## 更新源

程序默认内置 GitHub Release 更新源：

```text
https://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json
```

更新清单由 GitHub Actions 在发布时自动生成，包含：

- `version`：最新版本号。
- `url`：安装包下载地址。
- `sha256`：安装包 SHA256 校验值。
- `notes`：当前版本说明。

程序会根据设置中的更新源定时检查新版本；发现可用更新后，会在主界面的更新按钮上显示状态。更新安装完成后，安装器会自动重新打开程序。

## 本地数据

配置和运行数据默认保存在当前 Windows 用户的 `%APPDATA%\GoldMonitor` 目录，包括：

- `settings.json`：通用设置、邮件设置、风险分析设置和更新源。
- `thresholds.json`：价格阈值和波动提醒配置。
- `market_cache.json`：最近可用金价与汇率缓存。
- `price_history.json`：本地价格历史。
- `price_history.sqlite3`：本地价格历史主存储。
- `risk_analysis_history.json`：风险分析历史。
- `GoldMonitor.log`：运行日志。

重新安装程序通常不会删除这些配置。卸载或手动删除 `%APPDATA%\GoldMonitor` 后，本地配置和历史才会丢失。

## 本地开发

macOS 可双击根目录中的 `GoldMonitor.command` 启动浏览器模式，也可以在终端运行：

```bash
./scripts/start_mac.sh
```

脚本会创建 `.venv`，安装 Flask、Flask-SocketIO 和 requests，并把本地数据写入 `~/Library/Application Support/GoldMonitor`。macOS 启动方式不包含 Windows 托盘、桌面悬浮条、系统通知和安装器能力。

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller
```

运行静态与契约检查：

```powershell
.\.venv\Scripts\python.exe -m py_compile app.py setup_gui.py tests\risk_contract_check.py
powershell -NoProfile -ExecutionPolicy Bypass -File .\tests\contract_checks.ps1
.\.venv\Scripts\python.exe tests\risk_contract_check.py
```

完整检查：

```powershell
.\.venv\Scripts\python.exe tests\gold_cache_check.py
.\.venv\Scripts\python.exe tests\price_fetch_with_cache_check.py
.\.venv\Scripts\python.exe tests\fetch_status_check.py
.\.venv\Scripts\python.exe tests\threshold_persistence_check.py
.\.venv\Scripts\python.exe tests\socket_connect_check.py
.\.venv\Scripts\python.exe tests\news_logic_check.py
.\.venv\Scripts\python.exe tests\forex_cache_check.py
.\.venv\Scripts\python.exe tests\startup_contract_check.py
.\.venv\Scripts\python.exe tests\update_logic_check.py
.\.venv\Scripts\python.exe tests\port_selection_check.py
```

## 本地打包

```powershell
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm GoldMonitor.spec
.\.tools\InnoSetup6\ISCC.exe .\installer\GoldMonitor.iss
```

构建结果：

- 程序目录：`dist\GoldMonitor`
- 安装包：`release\GoldMonitorSetup.exe`

## 发布流程

发布前必须同步三处版本：

- `app.py` 中的 `APP_VERSION`
- `installer/GoldMonitor.iss` 中的 `MyAppVersion`
- `CHANGELOG.md` 中对应版本的变更内容

推送版本标签会触发 GitHub Actions 自动发布：

```powershell
git tag v1.2.2
git push origin main
git push origin v1.2.2
```

GitHub Actions 会执行检查、构建安装包、生成 `version.json`，并把 `GoldMonitorSetup.exe` 与 `version.json` 上传到对应 Release。

如果 `CHANGELOG.md` 中缺少当前版本说明，发布流程会失败。
