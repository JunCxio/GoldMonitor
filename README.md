# GoldMonitor

GoldMonitor 是一个 Windows 桌面黄金价格监控工具，用于查看实时金价、设置风险提醒、接收邮件通知，并通过桌面悬浮条持续关注行情。

## 功能

- 实时获取 XAU/USD 与人民币克价，并展示数据源、更新时间、缓存状态和日内统计。
- 支持预警阈值、严重阈值和短时波动率提醒。
- 支持邮件通知，可分别控制关注、警告和波动提醒。
- 支持桌面悬浮金价条，显示涨跌颜色、更新时间和数据源状态。
- 支持风险分析助手，用户手动触发，避免后台自动消耗模型 token。
- 支持软件更新检查、安装包下载、SHA256 校验和自动启动安装器。

## 下载

最新安装包发布在 GitHub Releases：

```text
https://github.com/JunCxio/GoldMonitor/releases/latest
```

用户通常只需要下载 `GoldMonitorSetup.exe` 并运行安装。

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

程序会根据设置中的更新源定时自动检查新版本；发现可用更新后，会在主界面的更新按钮上显示状态。

## 本地开发

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
git tag v1.1.2
git push origin main
git push origin v1.1.2
```

GitHub Actions 会执行检查、构建安装包、生成 `version.json`，并把 `GoldMonitorSetup.exe` 与 `version.json` 上传到对应 Release。

如果 `CHANGELOG.md` 中缺少当前版本说明，发布流程会失败。
