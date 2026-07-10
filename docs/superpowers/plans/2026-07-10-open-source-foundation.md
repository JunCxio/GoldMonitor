# GoldMonitor Open Source Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox - [ ] syntax for tracking.

**Goal:** 为 GoldMonitor 增加 MIT 开源授权、社区协作文件、统一检查入口和 Windows/macOS Pull Request 持续集成，同时保持产品运行行为不变。

**Architecture:** 用 tests/test_open_source_foundation.py 约束仓库级文档和工作流契约，用 scripts/run_checks.py 编排现有检查命令。Pull Request 和 Release 工作流都调用同一编排器，社区文档与模板只提供协作入口，不进入应用运行时。

**Tech Stack:** Python 3.12、pytest、GitHub Actions、GitHub Issue Forms、Markdown、PowerShell。

---

## 实施前提

- 规格来源：docs/superpowers/specs/2026-07-10-open-source-foundation-design.md
- 当前基线：.venv/bin/python -m pytest -q 为 149 passed。
- 当前支持平台：Windows、macOS。
- 当前 Release 检查定义位置：
  - .github/workflows/release.yml:34-67
  - .github/workflows/release.yml:110-141
- 当前 README 检查说明位置：README.md:105-159。
- docs/ 被 .gitignore 忽略，提交本计划或后续规格文件时必须对明确文件使用 git add -f，不修改 .gitignore。

## 文件结构

### 新增文件

- LICENSE：标准 MIT License，版权主体为 JunCxio。
- CONTRIBUTING.md：开发环境、检查命令、提交规范、Pull Request 和敏感信息要求。
- SECURITY.md：支持版本、私密漏洞报告和披露边界。
- CODE_OF_CONDUCT.md：基于 Contributor Covenant 2.1 的社区行为规范。
- .github/ISSUE_TEMPLATE/bug_report.yml：结构化 Bug 报告。
- .github/ISSUE_TEMPLATE/feature_request.yml：结构化功能建议。
- .github/ISSUE_TEMPLATE/config.yml：关闭空白 Issue，提供私密安全报告入口。
- .github/pull_request_template.md：Pull Request 自检模板。
- .github/workflows/ci.yml：Windows/macOS Pull Request 与 main 分支检查。
- scripts/run_checks.py：唯一的跨平台检查编排入口。
- tests/test_open_source_foundation.py：许可证、社区文件、模板和工作流契约。
- tests/test_run_checks_script.py：检查编排器的命令、平台分支和失败行为测试。

### 修改文件

- README.md:105-159：把重复检查清单替换为统一入口。
- README.md:198 之后：增加参与贡献、安全问题和许可证入口。
- .github/workflows/release.yml:34-67：Windows Release 改用统一检查入口。
- .github/workflows/release.yml:110-141：macOS Release 改用统一检查入口。

### 明确不修改

- app.py
- templates/index.html
- static/app.js
- static/app.css
- goldmonitor/ 下的运行时模块
- 配置文件格式、Socket.IO 事件和安装包构建步骤

## Task 1: 添加 MIT 许可证契约

**Files:**
- Create: tests/test_open_source_foundation.py
- Create: LICENSE
- Modify: README.md:198 之后

- [ ] **Step 1: 编写失败的许可证测试**

创建 tests/test_open_source_foundation.py：

~~~python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_text(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_repository_uses_confirmed_mit_license():
    license_path = ROOT / "LICENSE"

    assert license_path.exists()
    text = license_path.read_text(encoding="utf-8")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 JunCxio" in text
    assert "Permission is hereby granted, free of charge" in text
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in text


def test_readme_declares_mit_license():
    readme = read_text("README.md")

    assert "## 许可证" in readme
    assert "[MIT License](LICENSE)" in readme
~~~

- [ ] **Step 2: 运行测试并确认失败**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: FAIL，原因是 LICENSE 不存在，README 尚未声明 MIT License。

- [ ] **Step 3: 新增标准 MIT License**

创建 LICENSE，内容必须完整：

~~~text
MIT License

Copyright (c) 2026 JunCxio

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
~~~

- [ ] **Step 4: 在 README 末尾增加许可证章节**

追加：

~~~markdown
## 许可证

GoldMonitor 使用 [MIT License](LICENSE) 发布。
~~~

- [ ] **Step 5: 运行许可证测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: 2 passed。

- [ ] **Step 6: 提交许可证**

~~~bash
git add LICENSE README.md tests/test_open_source_foundation.py
git commit -m "docs: 添加 MIT 开源许可证"
~~~

## Task 2: 建立统一检查编排器

**Files:**
- Create: tests/test_run_checks_script.py
- Create: scripts/run_checks.py

- [ ] **Step 1: 编写检查命令和失败行为测试**

创建 tests/test_run_checks_script.py：

~~~python
import sys
from types import SimpleNamespace


def test_build_check_commands_preserves_existing_release_checks():
    from scripts.run_checks import build_check_commands

    commands = build_check_commands("darwin")

    assert commands[0][:3] == [sys.executable, "-m", "py_compile"]
    assert [sys.executable, "tests/risk_contract_check.py"] in commands
    assert [sys.executable, "tests/gold_cache_check.py"] in commands
    assert [sys.executable, "tests/engineering_foundation_check.py"] in commands
    assert [sys.executable, "tests/alert_log_ui_contract_check.py"] in commands
    assert [sys.executable, "tests/frontend_asset_check.py"] in commands
    assert commands[-2] == [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_single_instance_app.py",
        "tests/test_update_app.py",
        "tests/test_verify_release_assets_script.py",
    ]
    assert commands[-1] == [sys.executable, "-m", "pytest", "-q"]


def test_windows_commands_include_existing_powershell_contract():
    from scripts.run_checks import build_check_commands

    windows_commands = build_check_commands("win32")
    macos_commands = build_check_commands("darwin")
    powershell_command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "tests/contract_checks.ps1",
    ]

    assert powershell_command in windows_commands
    assert powershell_command not in macos_commands


def test_run_checks_stops_at_first_failure_and_reports_command(capsys):
    from scripts.run_checks import run_checks

    commands = [
        ["python", "first.py"],
        ["python", "second.py"],
        ["python", "third.py"],
    ]
    calls = []

    def fake_runner(command, cwd, check):
        calls.append((command, cwd, check))
        return SimpleNamespace(returncode=9 if command[-1] == "second.py" else 0)

    exit_code = run_checks(commands=commands, runner=fake_runner)
    captured = capsys.readouterr()

    assert exit_code == 9
    assert [item[0] for item in calls] == commands[:2]
    assert "检查失败 (9)" in captured.err
    assert "python second.py" in captured.err


def test_run_checks_returns_zero_after_all_commands_pass():
    from scripts.run_checks import run_checks

    calls = []

    def fake_runner(command, cwd, check):
        calls.append(command)
        return SimpleNamespace(returncode=0)

    exit_code = run_checks(
        commands=[["python", "first.py"], ["python", "second.py"]],
        runner=fake_runner,
    )

    assert exit_code == 0
    assert len(calls) == 2
~~~

- [ ] **Step 2: 运行测试并确认失败**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_run_checks_script.py -q
~~~

Expected: FAIL with ModuleNotFoundError: No module named 'scripts.run_checks'。

- [ ] **Step 3: 实现跨平台检查入口**

创建 scripts/run_checks.py：

~~~python
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

COMPILE_TARGETS = (
    "app.py",
    "setup_gui.py",
    "tests/risk_contract_check.py",
    "tests/update_logic_check.py",
    "tests/startup_contract_check.py",
    "tests/frontend_asset_check.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_portfolio_module.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_market_data_module.py",
    "tests/test_settings_store_module.py",
    "tests/test_notifications_module.py",
    "tests/test_event_timeline_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_platform_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/test_verify_release_assets_script.py",
    "tests/test_open_source_foundation.py",
    "tests/test_run_checks_script.py",
    "scripts/verify_release_assets.py",
    "scripts/run_checks.py",
)

PYTHON_CHECKS = (
    "tests/risk_contract_check.py",
    "tests/gold_cache_check.py",
    "tests/price_fetch_with_cache_check.py",
    "tests/fetch_status_check.py",
    "tests/threshold_persistence_check.py",
    "tests/socket_connect_check.py",
    "tests/news_logic_check.py",
    "tests/forex_cache_check.py",
    "tests/startup_contract_check.py",
    "tests/update_logic_check.py",
    "tests/port_selection_check.py",
    "tests/event_timeline_review_check.py",
    "tests/engineering_foundation_check.py",
    "tests/test_storage_modules.py",
    "tests/test_portfolio_module.py",
    "tests/test_risk_analysis_module.py",
    "tests/test_market_data_module.py",
    "tests/test_settings_store_module.py",
    "tests/test_notifications_module.py",
    "tests/test_event_timeline_module.py",
    "tests/test_update_manager_module.py",
    "tests/test_platform_module.py",
    "tests/test_news_module.py",
    "tests/test_targets_module.py",
    "tests/test_support_files_module.py",
    "tests/test_desktop_ui_module.py",
    "tests/alert_log_ui_contract_check.py",
    "tests/frontend_asset_check.py",
)

RELEASE_PYTEST_TARGETS = (
    "tests/test_single_instance_app.py",
    "tests/test_update_app.py",
    "tests/test_verify_release_assets_script.py",
)

WINDOWS_CONTRACT_COMMAND = (
    "powershell",
    "-NoProfile",
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "tests/contract_checks.ps1",
)


def build_check_commands(platform_name=None):
    platform_name = platform_name or sys.platform
    commands = [
        [sys.executable, "-m", "py_compile", *COMPILE_TARGETS],
    ]
    if str(platform_name).lower().startswith("win"):
        commands.append(list(WINDOWS_CONTRACT_COMMAND))
    commands.extend([sys.executable, path] for path in PYTHON_CHECKS)
    commands.append([
        sys.executable,
        "-m",
        "pytest",
        *RELEASE_PYTEST_TARGETS,
    ])
    commands.append([sys.executable, "-m", "pytest", "-q"])
    return commands


def command_text(command):
    return subprocess.list2cmdline([str(part) for part in command])


def run_checks(commands=None, runner=None):
    commands = build_check_commands() if commands is None else commands
    runner = runner or subprocess.run
    for command in commands:
        display = command_text(command)
        print(f"$ {display}", flush=True)
        result = runner(command, cwd=ROOT, check=False)
        if result.returncode:
            print(
                f"检查失败 ({result.returncode}): {display}",
                file=sys.stderr,
                flush=True,
            )
            return result.returncode or 1
    print("GoldMonitor checks passed.", flush=True)
    return 0


def main():
    return run_checks()


if __name__ == "__main__":
    raise SystemExit(main())
~~~

- [ ] **Step 4: 运行编排器单元测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_run_checks_script.py -q
~~~

Expected: 4 passed。

- [ ] **Step 5: 运行真实统一检查**

Run:

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

Expected:

- 所有现有 Python 脚本检查通过。
- macOS 不执行 PowerShell 契约。
- 显式 Release pytest 集合通过。
- 最后的完整 pytest 通过，测试数量为 155 项。
- 末行输出 GoldMonitor checks passed.

- [ ] **Step 6: 提交统一检查入口**

~~~bash
git add scripts/run_checks.py tests/test_run_checks_script.py
git commit -m "test: 统一项目检查入口"
~~~

## Task 3: 添加跨平台 Pull Request CI

**Files:**
- Modify: tests/test_open_source_foundation.py
- Create: .github/workflows/ci.yml
- Modify: .github/workflows/release.yml:34-67
- Modify: .github/workflows/release.yml:110-141

- [ ] **Step 1: 增加工作流契约测试**

追加到 tests/test_open_source_foundation.py：

~~~python
def test_pull_request_ci_runs_supported_platform_checks():
    workflow = read_text(".github/workflows/ci.yml")

    assert "pull_request:" in workflow
    assert 'branches: ["main"]' in workflow
    assert "contents: read" in workflow
    assert "fail-fast: false" in workflow
    assert "windows-latest" in workflow
    assert "macos-latest" in workflow
    assert 'python-version: "3.12"' in workflow
    assert "python scripts/run_checks.py" in workflow
    assert "cancel-in-progress: true" in workflow
    assert "upload-artifact" not in workflow
    assert "softprops/action-gh-release" not in workflow


def test_release_workflow_reuses_unified_check_entry():
    workflow = read_text(".github/workflows/release.yml")

    assert workflow.count("python scripts/run_checks.py") == 2
    assert "python -m py_compile app.py" not in workflow
    assert "python tests/risk_contract_check.py" not in workflow
    assert "python tests/frontend_asset_check.py" not in workflow
    assert "pyinstaller --clean --noconfirm GoldMonitor.spec" in workflow
    assert "PYTHON_BIN=python scripts/build_macos_dmg.sh" in workflow
~~~

- [ ] **Step 2: 运行工作流契约测试并确认失败**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: FAIL，原因是 .github/workflows/ci.yml 不存在，Release 仍包含重复检查命令。

- [ ] **Step 3: 新增 Pull Request CI**

创建 .github/workflows/ci.yml：

~~~yaml
name: CI

on:
  pull_request:
  push:
    branches: ["main"]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true

jobs:
  checks:
    name: Checks (${{ matrix.os }})
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30
    strategy:
      fail-fast: false
      matrix:
        os:
          - windows-latest
          - macos-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run checks
        run: python scripts/run_checks.py
~~~

- [ ] **Step 4: 收敛 Windows Release 检查块**

将 .github/workflows/release.yml:34-67 替换为：

~~~yaml
      - name: Run checks
        shell: powershell
        run: python scripts/run_checks.py
~~~

保留后续 Windows 应用构建、Inno Setup 构建和上传步骤不变。

- [ ] **Step 5: 收敛 macOS Release 检查块**

将 .github/workflows/release.yml:110-141 替换为：

~~~yaml
      - name: Run checks
        run: python scripts/run_checks.py
~~~

保留后续 DMG 构建、上传、发布和发布资产验收步骤不变。

- [ ] **Step 6: 运行工作流契约测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: 4 passed。

- [ ] **Step 7: 运行完整统一检查**

Run:

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

Expected: GoldMonitor checks passed.

- [ ] **Step 8: 提交 CI**

~~~bash
git add .github/workflows/ci.yml .github/workflows/release.yml tests/test_open_source_foundation.py
git commit -m "ci: 添加跨平台拉取请求检查"
~~~

## Task 4: 添加贡献、安全与社区行为文档

**Files:**
- Modify: tests/test_open_source_foundation.py
- Create: CONTRIBUTING.md
- Create: SECURITY.md
- Create: CODE_OF_CONDUCT.md

- [ ] **Step 1: 增加社区文档契约测试**

追加到 tests/test_open_source_foundation.py：

~~~python
def test_community_docs_define_contribution_and_private_reporting():
    contributing = read_text("CONTRIBUTING.md")
    security = read_text("SECURITY.md")
    conduct = read_text("CODE_OF_CONDUCT.md")

    assert "python scripts/run_checks.py" in contributing
    assert "Conventional Commits" in contributing
    assert "API Key" in contributing
    assert "SMTP 授权码" in contributing
    assert "Webhook URL" in contributing
    assert "security/advisories/new" in security
    assert "公开 Issue" in security
    assert "Contributor Covenant 2.1" in conduct
    assert "行为准则举报" in conduct
    assert "security/advisories/new" in conduct
~~~

- [ ] **Step 2: 运行测试并确认失败**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: FAIL，原因是三个社区文档不存在。

- [ ] **Step 3: 创建贡献指南**

创建 CONTRIBUTING.md：

~~~~markdown
# 参与贡献

感谢你改进 GoldMonitor。请保持变更目标单一、可验证，并避免在同一个 Pull Request 中混合功能、重构和无关格式化。

## 支持环境

- Python 3.12
- Windows 10/11
- macOS

GoldMonitor 当前不承诺 Linux 桌面运行兼容性。

## 准备开发环境

Windows：

~~~powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt pyinstaller
~~~

macOS：

~~~bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pyinstaller
~~~

## 本地验证

提交前运行：

Windows：

~~~powershell
.\.venv\Scripts\python.exe scripts\run_checks.py
~~~

macOS：

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

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

Commit 信息保持简洁、专业，不添加生成工具或额外署名声明。

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
- 未脱敏的诊断报告、日志和本地路径个人信息。

安全漏洞不要提交公开 Issue，请遵循 SECURITY.md。
~~~~

- [ ] **Step 4: 创建安全策略**

创建 SECURITY.md：

~~~markdown
# 安全策略

## 支持版本

GoldMonitor 当前只为最新正式版本处理安全问题。历史版本不承诺安全补丁。

## 私密报告

请通过 GitHub 的私密漏洞报告入口提交：

https://github.com/JunCxio/GoldMonitor/security/advisories/new

报告应包含受影响版本、操作系统、影响说明、最小复现步骤和建议修复方向。提交前删除 API Key、SMTP 授权码、Webhook URL、用户数据和无关诊断内容。

## 禁止公开披露

不要在公开 Issue、Discussion、Pull Request 或日志中发布：

- 可直接利用的漏洞细节。
- 密钥、授权码或访问令牌。
- 用户配置、持仓、风险分析和本地文件。

如果安全内容误发到公开区域，维护者应先删除敏感内容，再转入私密渠道处理。

## 处理方式

维护者不承诺固定响应时限。报告确认后，维护者会评估影响、协调修复和披露时间。在修复发布前，请不要公开漏洞细节。
~~~

- [ ] **Step 5: 创建社区行为准则**

创建 CODE_OF_CONDUCT.md：

~~~markdown
# 社区行为准则

本行为准则基于 Contributor Covenant 2.1。

## 我们的承诺

参与者和维护者应共同营造开放、友好、尊重且不骚扰他人的社区，不因年龄、体型、残障、族群、性别特征、性别认同、经验水平、教育程度、社会经济状况、国籍、外貌、种族、宗教或性取向而区别对待。

## 可接受行为

- 使用专业、尊重且聚焦问题的表达。
- 接受建设性反馈并对错误负责。
- 优先考虑项目和社区的整体利益。
- 尊重不同经验、观点和使用场景。

## 不可接受行为

- 人身攻击、侮辱、威胁、骚扰或歧视。
- 发布他人的私人信息或敏感数据。
- 持续偏离技术主题、恶意消耗维护资源。
- 其他在专业协作环境中不适当的行为。

## 适用范围

本准则适用于仓库、Issue、Pull Request、Discussion、Release 反馈以及代表 GoldMonitor 参与的其他公开空间。

## 举报

行为准则举报通过以下私密入口提交，标题注明“行为准则举报”：

https://github.com/JunCxio/GoldMonitor/security/advisories/new

维护者不得公开举报者身份或原始举报内容。明显滥用举报渠道的行为也可能受到限制。

## 执行

维护者可根据行为的性质和影响采取说明纠正、正式警告、临时限制或永久限制。执行决定应说明违反的规则和预期改正方式。

## 来源

本准则基于 Contributor Covenant 2.1：

https://www.contributor-covenant.org/version/2/1/code_of_conduct/
~~~

- [ ] **Step 6: 运行社区文档测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: 5 passed。

- [ ] **Step 7: 提交社区文档**

~~~bash
git add CONTRIBUTING.md SECURITY.md CODE_OF_CONDUCT.md tests/test_open_source_foundation.py
git commit -m "docs: 补充开源协作与安全规范"
~~~

## Task 5: 添加 Issue、Pull Request 模板并收敛 README

**Files:**
- Modify: tests/test_open_source_foundation.py
- Create: .github/ISSUE_TEMPLATE/bug_report.yml
- Create: .github/ISSUE_TEMPLATE/feature_request.yml
- Create: .github/ISSUE_TEMPLATE/config.yml
- Create: .github/pull_request_template.md
- Modify: README.md:105-159
- Modify: README.md:198 之后

- [ ] **Step 1: 增加模板和 README 契约测试**

追加到 tests/test_open_source_foundation.py：

~~~python
def test_issue_and_pull_request_templates_route_reports_safely():
    bug = read_text(".github/ISSUE_TEMPLATE/bug_report.yml")
    feature = read_text(".github/ISSUE_TEMPLATE/feature_request.yml")
    config = read_text(".github/ISSUE_TEMPLATE/config.yml")
    pull_request = read_text(".github/pull_request_template.md")
    combined = "\n".join((bug, feature, config, pull_request))

    assert "blank_issues_enabled: false" in config
    assert "security/advisories/new" in config
    assert "API Key" in combined
    assert "SMTP 授权码" in combined
    assert "Webhook URL" in combined
    assert "复现步骤" in bug
    assert "用户问题" in feature
    assert "验证结果" in pull_request
    assert "隐私" in pull_request


def test_readme_uses_canonical_contribution_and_security_entries():
    readme = read_text("README.md")

    assert "python scripts/run_checks.py" in readme
    assert "[贡献指南](CONTRIBUTING.md)" in readme
    assert "[安全策略](SECURITY.md)" in readme
    assert "[MIT License](LICENSE)" in readme
    assert "tests\\gold_cache_check.py" not in readme
    assert "tests/gold_cache_check.py" not in readme
~~~

- [ ] **Step 2: 运行测试并确认失败**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
~~~

Expected: FAIL，原因是模板不存在，README 仍维护长检查清单。

- [ ] **Step 3: 创建 Bug Issue Form**

创建 .github/ISSUE_TEMPLATE/bug_report.yml：

~~~yaml
name: Bug 报告
description: 报告可复现的 GoldMonitor 缺陷
title: "[Bug] "
labels:
  - bug
body:
  - type: markdown
    attributes:
      value: |
        请先删除 API Key、SMTP 授权码、Webhook URL、用户数据和本地路径中的个人信息。安全漏洞请使用私密报告入口，不要提交公开 Issue。
  - type: input
    id: version
    attributes:
      label: GoldMonitor 版本
      placeholder: 例如 1.0.5
    validations:
      required: true
  - type: dropdown
    id: operating-system
    attributes:
      label: 操作系统
      options:
        - Windows 10
        - Windows 11
        - macOS
    validations:
      required: true
  - type: textarea
    id: problem
    attributes:
      label: 问题描述
      description: 说明问题以及它对使用造成的影响。
    validations:
      required: true
  - type: textarea
    id: reproduction
    attributes:
      label: 复现步骤
      description: 提供能够稳定复现问题的最小步骤。
      placeholder: |
        1. 打开……
        2. 配置……
        3. 出现……
    validations:
      required: true
  - type: textarea
    id: expected
    attributes:
      label: 预期结果
    validations:
      required: true
  - type: textarea
    id: actual
    attributes:
      label: 实际结果
    validations:
      required: true
  - type: textarea
    id: diagnostics
    attributes:
      label: 脱敏后的诊断信息
      description: 只粘贴与问题有关且已删除敏感内容的摘要。
      render: shell
  - type: checkboxes
    id: privacy
    attributes:
      label: 隐私确认
      options:
        - label: 我已删除 API Key、SMTP 授权码、Webhook URL、用户数据和个人路径信息。
          required: true
        - label: 这不是需要私密处理的安全漏洞。
          required: true
~~~

- [ ] **Step 4: 创建功能建议 Issue Form**

创建 .github/ISSUE_TEMPLATE/feature_request.yml：

~~~yaml
name: 功能建议
description: 描述用户问题、使用场景和期望结果
title: "[Feature] "
labels:
  - enhancement
body:
  - type: markdown
    attributes:
      value: |
        请从用户问题和使用场景开始，不要求先设计技术实现。不要提交 API Key、SMTP 授权码、Webhook URL 或用户数据。
  - type: textarea
    id: user-problem
    attributes:
      label: 用户问题
      description: 当前什么事情难以完成，或者容易出错？
    validations:
      required: true
  - type: textarea
    id: scenario
    attributes:
      label: 使用场景
      description: 谁会在什么情况下使用这项能力？
    validations:
      required: true
  - type: textarea
    id: outcome
    attributes:
      label: 期望结果
      description: 完成后用户应获得什么可验证结果？
    validations:
      required: true
  - type: textarea
    id: scope
    attributes:
      label: 范围边界
      description: 哪些行为不应包含在第一版中？
  - type: textarea
    id: alternatives
    attributes:
      label: 当前替代方案
      description: 目前如何绕过或解决这个问题？
  - type: checkboxes
    id: privacy
    attributes:
      label: 隐私确认
      options:
        - label: 内容不包含 API Key、SMTP 授权码、Webhook URL 或用户数据。
          required: true
~~~

- [ ] **Step 5: 创建 Issue 配置**

创建 .github/ISSUE_TEMPLATE/config.yml：

~~~yaml
blank_issues_enabled: false
contact_links:
  - name: 安全漏洞私密报告
    url: https://github.com/JunCxio/GoldMonitor/security/advisories/new
    about: 不要公开披露漏洞细节、密钥或用户数据。
~~~

- [ ] **Step 6: 创建 Pull Request 模板**

创建 .github/pull_request_template.md：

~~~markdown
## 变更目标

说明本 Pull Request 解决的用户问题或工程问题。

## 变更范围

- 包含：
- 不包含：

## 验证结果

列出已执行命令和结果：

- [ ] python scripts/run_checks.py

## 影响检查

- [ ] 已补充或更新相关测试。
- [ ] 已更新与实际行为相关的文档。
- [ ] 已检查配置、持久化和 Socket.IO 契约影响。
- [ ] 未提交 API Key、SMTP 授权码、Webhook URL、用户数据或未脱敏诊断信息。
- [ ] 前端文本未使用 Emoji。

## 关联 Issue

填写 Issue 编号；没有关联 Issue 时说明原因。
~~~

- [ ] **Step 7: 用统一入口替换 README 的长检查清单**

将 README.md:105-159 的“运行静态与契约检查”和“完整检查”替换为：

~~~~markdown
运行完整检查：

Windows：

~~~powershell
.\.venv\Scripts\python.exe scripts\run_checks.py
~~~

macOS：

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

该入口会执行 Python 语法检查、现有契约检查和完整 pytest；Windows 还会执行 PowerShell 契约检查。贡献要求参见 [贡献指南](CONTRIBUTING.md)。
~~~~

- [ ] **Step 8: 在 README 末尾补齐社区入口**

保证 README 末尾包含且只包含一组以下章节：

~~~markdown
## 参与贡献

开发环境、测试要求、Commit 和 Pull Request 规范参见 [贡献指南](CONTRIBUTING.md)。

## 安全问题

安全漏洞不要提交公开 Issue，请按照 [安全策略](SECURITY.md) 使用私密报告入口。

## 许可证

GoldMonitor 使用 [MIT License](LICENSE) 发布。
~~~

- [ ] **Step 9: 运行开源基础设施测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py tests/test_run_checks_script.py -q
~~~

Expected: 11 passed。

- [ ] **Step 10: 运行完整统一检查**

Run:

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

Expected: GoldMonitor checks passed.

- [ ] **Step 11: 提交社区模板和 README**

~~~bash
git add .github/ISSUE_TEMPLATE .github/pull_request_template.md README.md tests/test_open_source_foundation.py
git commit -m "docs: 完善开源社区协作入口"
~~~

## Task 6: 完成最终验证和远端启用清单

**Files:**
- Verify only; no planned source changes

- [ ] **Step 1: 运行目标测试**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py tests/test_run_checks_script.py -q
~~~

Expected: 11 passed。

- [ ] **Step 2: 运行完整检查**

Run:

~~~bash
.venv/bin/python scripts/run_checks.py
~~~

Expected:

- 所有现有脚本检查通过。
- 完整 pytest 通过，测试数量不少于 160 项。
- 末行输出 GoldMonitor checks passed.

- [ ] **Step 3: 检查变更边界**

Run:

~~~bash
git diff --check
git status --short
git log -5 --oneline
~~~

Expected:

- git diff --check 无输出。
- 工作区没有未提交变更。
- 最近提交依次覆盖许可证、统一检查入口、CI、社区规范和社区模板。
- app.py、templates/index.html、static/app.js、static/app.css 和 goldmonitor/ 没有变更。

- [ ] **Step 4: 检查 GitHub 工作流静态契约**

Run:

~~~bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py::test_pull_request_ci_runs_supported_platform_checks tests/test_open_source_foundation.py::test_release_workflow_reuses_unified_check_entry -q
~~~

Expected: 2 passed。

- [ ] **Step 5: 记录需要远端授权的仓库设置**

本地实现完成后，不自动执行以下远端操作：

1. 将本地提交推送到 GitHub。
2. 在仓库 Settings > Security > Code security and analysis 中启用 Private vulnerability reporting。
3. 观察首个 Pull Request 的 Windows 和 macOS Checks 均通过。

执行这些远端操作前必须获得用户明确授权。启用后验证以下地址可用于私密报告：

~~~text
https://github.com/JunCxio/GoldMonitor/security/advisories/new
~~~

## 规格覆盖自检

- MIT License 与版权主体：Task 1。
- 本地、Pull Request、Release 统一检查入口：Task 2、Task 3。
- Windows/macOS 并行且 fail-fast 关闭：Task 3。
- CI 只读、不发布资产：Task 3 的工作流内容和契约测试。
- CONTRIBUTING、SECURITY、CODE_OF_CONDUCT：Task 4。
- Bug、功能建议、Pull Request 和安全入口：Task 5。
- README 收敛与社区入口：Task 5。
- 故障返回、失败命令输出和完整验证：Task 2、Task 6。
- 不修改产品运行行为：文件结构约束和 Task 6 变更边界检查。
