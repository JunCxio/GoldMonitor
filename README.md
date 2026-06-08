# GoldMonitor

GoldMonitor 是一个 Windows 桌面黄金价格监控工具，支持实时行情、阈值提醒、邮件通知、桌面悬浮金价、风险分析助手和软件更新。

## 下载

最新安装包发布在 GitHub Releases：

https://github.com/JunCxio/GoldMonitor/releases/latest

## 更新源

程序默认使用以下更新清单地址：

```text
https://github.com/JunCxio/GoldMonitor/releases/latest/download/version.json
```

清单由 GitHub Actions 在发布时自动生成，包含版本号、安装包下载地址和 SHA256 校验值。

## 本地构建

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm GoldMonitor.spec
.\.tools\InnoSetup6\ISCC.exe .\installer\GoldMonitor.iss
```

构建结果：

- 程序目录：`dist\GoldMonitor`
- 安装包：`release\GoldMonitorSetup.exe`

## 发布

推送版本标签会触发自动发布流程：

```powershell
git tag v1.1.1
git push origin main
git push origin v1.1.1
```

GitHub Actions 会生成 `GoldMonitorSetup.exe` 和 `version.json`，并上传到对应 Release。
