# 参与贡献

感谢你改进 GoldMonitor。请保持变更目标单一、可验证，并避免在同一个 Pull Request 中混合功能、重构和无关格式化。

## 支持环境

- Python 3.12
- Windows 10/11
- macOS

GoldMonitor 当前不承诺 Linux 桌面运行兼容性。

## 准备开发环境

Windows：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-build.txt -c constraints\windows-py312.txt
```

macOS：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-build.txt -c constraints/macos-py312.txt
```

## 启动应用

本地开发建议使用 Web 模式，便于直接查看日志和调试页面。

Windows：

```powershell
.\.venv\Scripts\python.exe app.py --web
```

macOS：

```bash
.venv/bin/python app.py --web
```

## 本地验证

提交前运行：

Windows：

```powershell
.\.venv\Scripts\python.exe scripts\run_checks.py
```

macOS：

```bash
.venv/bin/python scripts/run_checks.py
```

该命令执行 Python 语法检查、现有契约检查和完整 pytest。Windows 还会执行 tests/contract_checks.ps1。

## 更新依赖锁定

项目使用 uv 0.11.21 为 Python 3.12 分别生成 Windows 和 macOS constraints；开发环境及 CI/Release 仍使用 pip 安装依赖。

```bash
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform windows --output-file constraints/windows-py312.txt
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform macos --output-file constraints/macos-py312.txt
```

全量升级依赖时，在上述命令末尾增加 `--upgrade`；只升级单个包时，增加 `--upgrade-package <包名>`。提交 Pull Request 时记录 `uv --version` 的输出，并确保 Windows 和 macOS 的 CI 均通过。

## 变更要求

- 修改行为时增加或更新测试。
- 保持现有 Socket.IO 事件、配置结构和本地数据兼容，除非变更目标明确要求修改契约。
- 不为了单个功能进行无关的大范围重构。
- 文档必须与实际行为一致。
- 前端文本不得使用 Emoji，图形使用项目图标或 SVG。

## Commit 规范

使用中文 Conventional Commits：

- feat: 新增功能
- fix: 修复缺陷
- docs: 修改文档
- test: 修改测试或检查
- refactor: 不改变行为的重构
- ci: 修改持续集成
- chore: 维护性变更

Commit 信息保持简洁、专业，不添加生成工具署名或其他额外署名声明。

## Pull Request

Pull Request 需要说明：

- 用户问题或工程问题。
- 变更范围和明确的非目标。
- 已执行的验证命令与结果。
- 对文档、配置、持久化和隐私的影响。
- 关联 Issue；没有关联 Issue 时说明原因。

PR 的 Windows 和 macOS 基础检查全部通过后，CI 会继续生成 Windows 测试安装包。在 PR 的检查详情中打开最新 `CI` 运行记录，从页面底部的 `Artifacts` 下载 `windows-pr-<PR 编号>`。压缩包内包含 `GoldMonitorSetup.exe`，产物保留 7 天，仅用于测试，未进行代码签名。

## 敏感信息

禁止提交或粘贴以下内容：

- API Key、SMTP 授权码和 Webhook URL。
- settings.json、系统凭据、用户持仓和风险分析历史。
- 未脱敏的诊断报告、日志和可识别个人身份的本地路径信息。

安全漏洞不要提交公开 Issue，请遵循 SECURITY.md。
