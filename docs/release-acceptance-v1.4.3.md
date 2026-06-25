# GoldMonitor v1.4.3 发布验收记录

## 基础信息

- 验收日期：2026-06-25
- 版本号：`v1.4.3`
- 提交号：`cc9d0e15c007a77996ab0cfb3f1e6a90c0c6ee0e`
- Release 页面：https://github.com/JunCxio/GoldMonitor/releases/tag/v1.4.3
- Release workflow：https://github.com/JunCxio/GoldMonitor/actions/runs/28079236629

## Actions 结果

- Release workflow：成功。
- Release 状态：非 draft，非 prerelease。
- Release 资产：`GoldMonitorSetup.exe`、`GoldMonitor-macOS.dmg`、`version.json`。

## 本地检查结果

- `python -m pytest`：39 passed。
- `python -m py_compile app.py goldmonitor/*.py tests/*.py`：通过。
- `node --check static/app.js`：通过。
- `node --check static/app-shell.js`：通过。
- 脚本级回归检查：通过。
- `tests/port_selection_check.py`：通过。

当前 macOS 环境未安装 `pwsh` 或 `powershell`，因此 `tests/contract_checks.ps1` 未在本机运行；该检查已由 Release workflow 的 Windows job 覆盖。

## 线上清单检查

`version.json` 内容要点：

- `version`：`1.4.3`
- Windows URL：`https://github.com/JunCxio/GoldMonitor/releases/download/v1.4.3/GoldMonitorSetup.exe`
- Windows SHA256：`a8fbda013d83d25d7b187d0d965e4c41668066239fa323ca130bc0e0ac289e34`
- macOS URL：`https://github.com/JunCxio/GoldMonitor/releases/download/v1.4.3/GoldMonitor-macOS.dmg`
- macOS SHA256：`08c4f5dc06732fa400cca14126084d79b1438ee91a36aeff34e806a8900ae248`

下载 URL 检查：

- Windows 安装包 URL：HTTP 200，大小 `21024074` 字节。
- macOS DMG URL：HTTP 200，大小 `17006551` 字节。

## 下载资产校验

- `GoldMonitorSetup.exe`
  - 大小：`21024074` 字节。
  - SHA256：`a8fbda013d83d25d7b187d0d965e4c41668066239fa323ca130bc0e0ac289e34`
  - 文件类型：Windows PE GUI executable。
- `GoldMonitor-macOS.dmg`
  - 大小：`17006551` 字节。
  - SHA256：`08c4f5dc06732fa400cca14126084d79b1438ee91a36aeff34e806a8900ae248`
  - `hdiutil verify`：通过。

## macOS DMG 内容检查

- DMG 可只读挂载。
- 包含 `/GoldMonitor.app`。
- `CFBundleName`：`GoldMonitor`。
- `CFBundleShortVersionString`：`1.4.3`。
- 主可执行文件：`GoldMonitor.app/Contents/MacOS/GoldMonitor` 存在且可执行。

## 未覆盖项

- 当前环境无法运行 Windows 安装包，因此未执行 Windows 安装、启动和程序内更新冒烟测试。
- 当前验收未把发布版 macOS App 复制到“应用程序”目录启动，以避免改变本机应用状态；已完成 DMG 结构、版本和可执行文件检查。

## 结论

`v1.4.3` Release 的线上资产、版本清单、下载完整性和 macOS DMG 内容检查均通过。Windows 运行态冒烟测试需要在 Windows 环境补充执行。
