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
.\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller
```

macOS：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt pyinstaller
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

## 敏感信息

禁止提交或粘贴以下内容：

- API Key、SMTP 授权码和 Webhook URL。
- settings.json、系统凭据、用户持仓和风险分析历史。
- 未脱敏的诊断报告、日志和可识别个人身份的本地路径信息。

安全漏洞不要提交公开 Issue，请遵循 SECURITY.md。
