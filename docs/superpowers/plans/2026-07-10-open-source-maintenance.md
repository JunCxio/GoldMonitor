# GoldMonitor Open Source Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 升级 GitHub Actions、修正文档跟踪规则、配置 Dependabot、锁定 Windows/macOS Python 3.12 依赖，并在合并后启用 GitHub 安全设置与 `main` Ruleset。

**Architecture:** 继续以 `requirements.txt` 声明直接应用依赖，新增 `requirements-build.txt` 声明构建依赖，并用两份平台 constraints 固定完整解析结果。仓库级契约集中扩展 `tests/test_open_source_foundation.py`，CI、Release、README 和贡献指南共享同一依赖文件约定；GitHub 远端安全设置和 Ruleset 在代码 Pull Request 合并后配置并单独验收。

**Tech Stack:** Python 3.12、pytest、pip、uv 0.11.21、GitHub Actions、Dependabot、CodeQL default setup、GitHub Repository Rulesets。

---

## 实施前提

- 设计规格：`docs/superpowers/specs/2026-07-10-open-source-maintenance-design.md`
- 实施分支：`codex/open-source-maintenance`
- 隔离目录：`.worktrees/open-source-maintenance`
- 当前基线提交：`5725344 docs: 添加开源维护加固设计`
- 当前远端基线：`origin/main` 指向 `e96b32c`
- 当前统一检查入口：`python scripts/run_checks.py`
- 当前 GitHub CLI 未登录，远端设置和 Pull Request 操作优先使用已登录的 GitHub 浏览器会话；如果后续完成 `gh` 登录，可以使用等价 REST API。
- 主工作区中 8 个既有未跟踪文档不复制到隔离 worktree，不修改、不删除、不暂存。

## 文件结构

### 新增文件

- `.github/dependabot.yml`：每周检查 pip 和 GitHub Actions，分组普通版本更新。
- `requirements-build.txt`：声明 `pyinstaller>=6.0,<7.0`。
- `constraints/windows-py312.txt`：Windows、Python 3.12 的完整精确版本集合。
- `constraints/macos-py312.txt`：macOS、Python 3.12 的完整精确版本集合。

### 修改文件

- `.gitignore`：删除整体 `docs/` 忽略规则。
- `.github/workflows/ci.yml`：升级官方 Actions，并按矩阵使用平台 constraints。
- `.github/workflows/release.yml`：升级官方 Actions，并使用平台 constraints 与构建依赖文件。
- `tests/test_open_source_foundation.py`：增加仓库维护、Dependabot 和锁定依赖契约。
- `CONTRIBUTING.md`：记录可复现安装和 constraints 刷新命令。
- `README.md`：把开发环境安装命令切换为锁定依赖入口。

### 明确不修改

- `requirements.txt` 中现有直接依赖范围。
- `app.py`、`goldmonitor/`、`static/`、`templates/` 和用户数据格式。
- `scripts/run_checks.py` 的检查集合。
- Release 资产名称和构建步骤。
- 8 个实施前已经存在但未跟踪的 Markdown 文档。

## 执行环境准备

使用 `superpowers:using-git-worktrees` 创建隔离 worktree 后，在 worktree 根目录运行：

```bash
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python scripts/run_checks.py
```

Expected: 创建 Python 3.12 环境，按当前未锁定基线完成安装，统一检查全部通过；只允许既有 LibreSSL/urllib3 warning。基线失败时先按 systematic-debugging 查明原因，不进入 Task 1。

## Task 1: 升级 Actions 并修正文档跟踪规则

**Files:**
- Modify: `tests/test_open_source_foundation.py`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`
- Modify: `.gitignore`

- [ ] **Step 1: 添加失败的 Actions 与 `.gitignore` 契约测试**

在 `tests/test_open_source_foundation.py` 文件头增加 `import subprocess`，并在末尾追加：

```python
def test_workflows_use_node_24_action_versions():
    def action_versions(workflow, action):
        pattern = re.compile(
            rf"^[ \t]*(?:-[ \t]+)?uses:[ \t]*(?P<quote>[\"']?)"
            rf"{re.escape(action)}@(?P<version>[^\"'\s#]+)"
            r"(?P=quote)[ \t]*(?:#.*)?$",
            flags=re.MULTILINE,
        )
        return [
            match.group("version")
            for match in pattern.finditer(workflow)
        ]

    workflow = "\n".join(
        read_text(relative_path)
        for relative_path in (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
        )
    )
    expected_versions = {
        "actions/checkout": "v7",
        "actions/setup-python": "v6",
        "actions/upload-artifact": "v7",
        "actions/download-artifact": "v8",
        "softprops/action-gh-release": "v3",
    }

    for action, expected_version in expected_versions.items():
        versions = action_versions(workflow, action)

        assert versions
        assert set(versions) == {expected_version}


def test_docs_directory_is_not_ignored_by_repository_rules():
    ignore_result = subprocess.run(
        [
            "git",
            "-c",
            "core.excludesFile=/dev/null",
            "check-ignore",
            "--no-index",
            "docs/.contract-probe",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    ignore_rules = {
        line.strip()
        for line in read_text(".gitignore").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert ignore_result.returncode == 1, (
        "docs/.contract-probe is ignored by repository rules:\n"
        f"stdout: {ignore_result.stdout}\n"
        f"stderr: {ignore_result.stderr}"
    )
    assert ".DS_Store" in ignore_rules
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_workflows_use_node_24_action_versions \
  tests/test_open_source_foundation.py::test_docs_directory_is_not_ignored_by_repository_rules \
  -q
```

Expected: 1 failed、1 passed；Actions 契约发现 `checkout@v5`、`upload-artifact@v4`、`download-artifact@v4` 和 `action-gh-release@v2` 不符合稳定 Node.js 24 主版本映射，`setup-python@v6` 已符合要求，`.gitignore` 语义测试继续通过。

- [ ] **Step 3: 升级官方 Actions 主版本**

在 `.github/workflows/ci.yml` 和 `.github/workflows/release.yml` 中执行以下精确替换：

```text
actions/checkout@v5      -> actions/checkout@v7
actions/setup-python@v6  -> actions/setup-python@v6（保持）
actions/upload-artifact@v4       -> actions/upload-artifact@v7
actions/download-artifact@v4     -> actions/download-artifact@v8
softprops/action-gh-release@v2   -> softprops/action-gh-release@v3
```

上述五个版本均为 2026-07-10 通过各 Action 官方仓库 `action.yml` 确认的稳定 Node.js 24 主版本；不得保留 Node.js 20 Action 或新旧主版本混用。

- [ ] **Step 4: 删除整体文档忽略规则**

从 `.gitignore` 删除这一行：

```gitignore
docs/
```

保留全局规则：

```gitignore
.DS_Store
```

- [ ] **Step 5: 运行目标测试并确认通过**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_workflows_use_node_24_action_versions \
  tests/test_open_source_foundation.py::test_docs_directory_is_not_ignored_by_repository_rules \
  -q
```

Expected: 2 passed。

- [ ] **Step 6: 验证隔离 worktree 不包含主工作区既有文档**

Run:

```bash
git status --short
```

Expected: 只显示 Task 1 的 4 个已修改文件，不出现设计规格中列出的 8 个既有未跟踪文档。

- [ ] **Step 7: 提交 Task 1**

```bash
git add \
  .gitignore \
  .github/workflows/ci.yml \
  .github/workflows/release.yml \
  tests/test_open_source_foundation.py
git commit -m "ci: 升级 Actions 并修正文档跟踪"
```

## Task 2: 配置 Dependabot 周期更新

**Files:**
- Modify: `tests/test_open_source_foundation.py`
- Create: `.github/dependabot.yml`

- [ ] **Step 1: 添加失败的 Dependabot 契约测试**

在 `tests/test_open_source_foundation.py` 末尾追加：

```python
def test_dependabot_updates_python_and_actions_weekly():
    config = read_text(".github/dependabot.yml")

    assert "version: 2" in config
    assert 'package-ecosystem: "pip"' in config
    assert 'package-ecosystem: "github-actions"' in config
    assert config.count('interval: "weekly"') == 2
    assert config.count('target-branch: "main"') == 2
    assert config.count('applies-to: "version-updates"') == 2
    assert config.count('prefix: "chore"') == 2
    assert config.count('include: "scope"') == 2
```

- [ ] **Step 2: 运行测试并确认缺少配置文件**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_dependabot_updates_python_and_actions_weekly \
  -q
```

Expected: FAIL with `FileNotFoundError: .github/dependabot.yml`。

- [ ] **Step 3: 新增 Dependabot 配置**

创建 `.github/dependabot.yml`：

```yaml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/"
    schedule:
      interval: "weekly"
    target-branch: "main"
    open-pull-requests-limit: 5
    groups:
      python-dependencies:
        applies-to: "version-updates"
        patterns:
          - "*"
    commit-message:
      prefix: "chore"
      include: "scope"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    target-branch: "main"
    open-pull-requests-limit: 5
    groups:
      github-actions:
        applies-to: "version-updates"
        patterns:
          - "*"
    commit-message:
      prefix: "chore"
      include: "scope"
```

- [ ] **Step 4: 运行 Dependabot 契约测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_dependabot_updates_python_and_actions_weekly \
  -q
```

Expected: 1 passed。

- [ ] **Step 5: 提交 Task 2**

```bash
git add .github/dependabot.yml tests/test_open_source_foundation.py
git commit -m "ci: 配置 Dependabot 周期更新"
```

## Task 3: 锁定 Windows 与 macOS Python 依赖

**Files:**
- Modify: `tests/test_open_source_foundation.py`
- Create: `requirements-build.txt`
- Create: `constraints/windows-py312.txt`
- Create: `constraints/macos-py312.txt`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: 添加 constraints 读取辅助函数**

在 `tests/test_open_source_foundation.py` 的 `read_text` 后追加：

```python
def requirement_lines(relative_path):
    return [
        line.strip()
        for line in read_text(relative_path).splitlines()
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.lstrip().startswith("--")
    ]
```

- [ ] **Step 2: 添加失败的锁定依赖契约测试**

在 `tests/test_open_source_foundation.py` 末尾追加：

```python
def test_python_dependencies_are_locked_per_supported_platform():
    assert requirement_lines("requirements-build.txt") == [
        "pyinstaller>=6.0,<7.0"
    ]

    pinned_requirement = re.compile(
        r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^ ;]+(?:\s*;\s*.+)?$"
    )
    for relative_path in (
        "constraints/windows-py312.txt",
        "constraints/macos-py312.txt",
    ):
        lines = requirement_lines(relative_path)

        assert lines
        assert any(line.lower().startswith("pyinstaller==") for line in lines)
        assert all(pinned_requirement.fullmatch(line) for line in lines)


def test_ci_and_release_use_platform_constraints():
    ci = read_text(".github/workflows/ci.yml")
    release = read_text(".github/workflows/release.yml")

    assert "constraints/windows-py312.txt" in ci
    assert "constraints/macos-py312.txt" in ci
    assert (
        "pip install -r requirements.txt -c ${{ matrix.constraints }}" in ci
    )
    assert (
        "pip install -r requirements.txt -r requirements-build.txt "
        "-c constraints/windows-py312.txt"
    ) in release
    assert (
        "pip install -r requirements.txt -r requirements-build.txt "
        "-c constraints/macos-py312.txt"
    ) in release
    assert "pip install -r requirements.txt pyinstaller" not in release
```

- [ ] **Step 3: 运行测试并确认缺少依赖文件和工作流配置**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_python_dependencies_are_locked_per_supported_platform \
  tests/test_open_source_foundation.py::test_ci_and_release_use_platform_constraints \
  -q
```

Expected: 2 failed；首先因 `requirements-build.txt` 不存在失败。

- [ ] **Step 4: 声明构建依赖**

创建 `requirements-build.txt`：

```text
pyinstaller>=6.0,<7.0
```

- [ ] **Step 5: 使用 uv 0.11.21 生成双平台 constraints**

先确认生成器版本：

```bash
uv --version
```

Expected: `uv 0.11.21`。

Run:

```bash
mkdir -p constraints
uv pip compile \
  requirements.txt requirements-build.txt \
  --python-version 3.12 \
  --python-platform windows \
  --output-file constraints/windows-py312.txt
uv pip compile \
  requirements.txt requirements-build.txt \
  --python-version 3.12 \
  --python-platform macos \
  --output-file constraints/macos-py312.txt
```

Expected: 两个文件生成成功；非注释依赖均使用 `==`，两个文件均包含 `pyinstaller==`，Windows 文件包含 Windows 专属依赖，macOS 文件包含 PyObjC 依赖。

- [ ] **Step 6: 修改 CI 矩阵以选择平台 constraints**

把 `.github/workflows/ci.yml` 的矩阵从 `os` 列表改为：

```yaml
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: windows-latest
            constraints: constraints/windows-py312.txt
          - os: macos-latest
            constraints: constraints/macos-py312.txt
```

把 `Set up Python` 的缓存配置改为：

```yaml
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            requirements.txt
            ${{ matrix.constraints }}
```

把安装命令改为：

```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -c ${{ matrix.constraints }}
```

- [ ] **Step 7: 修改 Release 使用构建依赖和平台 constraints**

将 `.github/workflows/release.yml` 的 Windows 安装命令改为：

```yaml
      - name: Install Python dependencies
        shell: powershell
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-build.txt -c constraints/windows-py312.txt
```

将 macOS 安装命令改为：

```yaml
      - name: Install Python dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt -r requirements-build.txt -c constraints/macos-py312.txt
```

`publish-release` 和 `verify-release` 不安装应用依赖，保持原样。

- [ ] **Step 8: 运行锁定依赖契约测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_python_dependencies_are_locked_per_supported_platform \
  tests/test_open_source_foundation.py::test_ci_and_release_use_platform_constraints \
  -q
```

Expected: 2 passed。

- [ ] **Step 9: 验证 macOS constraints 可以完成解析安装**

Run:

```bash
uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -r requirements-build.txt \
  -c constraints/macos-py312.txt
```

Expected: 在 worktree 的已忽略 `.venv/` 中安装成功，无 resolution conflict。

- [ ] **Step 10: 提交 Task 3**

```bash
git add \
  requirements-build.txt \
  constraints/windows-py312.txt \
  constraints/macos-py312.txt \
  .github/workflows/ci.yml \
  .github/workflows/release.yml \
  tests/test_open_source_foundation.py
git commit -m "build: 锁定双平台 Python 依赖"
```

## Task 4: 同步贡献指南和 README

**Files:**
- Modify: `tests/test_open_source_foundation.py`
- Modify: `CONTRIBUTING.md`
- Modify: `README.md`

- [ ] **Step 1: 添加失败的依赖文档契约测试**

在 `tests/test_open_source_foundation.py` 末尾追加：

```python
def test_dependency_docs_use_reproducible_install_commands():
    contributing = read_text("CONTRIBUTING.md")
    readme = read_text("README.md")

    windows_install = (
        r".\.venv\Scripts\pip.exe install -r requirements.txt "
        r"-r requirements-build.txt -c constraints\windows-py312.txt"
    )
    macos_install = (
        ".venv/bin/pip install -r requirements.txt "
        "-r requirements-build.txt -c constraints/macos-py312.txt"
    )

    for document in (contributing, readme):
        assert windows_install in document
        assert macos_install in document
        assert "install -r requirements.txt pyinstaller" not in document

    assert "uv 0.11.21" in contributing
    assert "--python-platform windows" in contributing
    assert "--python-platform macos" in contributing
    assert "--upgrade-package <包名>" in contributing
```

- [ ] **Step 2: 运行测试并确认旧安装命令导致失败**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_dependency_docs_use_reproducible_install_commands \
  -q
```

Expected: 1 failed；README 和 CONTRIBUTING 仍直接安装未锁定的 `pyinstaller`。

- [ ] **Step 3: 更新 CONTRIBUTING 的环境安装命令**

将 Windows 命令改为：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-build.txt -c constraints\windows-py312.txt
```

将 macOS 命令改为：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-build.txt -c constraints/macos-py312.txt
```

- [ ] **Step 4: 在 CONTRIBUTING 增加 constraints 维护章节**

在“本地验证”之后增加：

````markdown
## 更新依赖锁定

项目使用 uv 0.11.21 为 Python 3.12 生成 Windows 和 macOS 两份 constraints；应用和 CI 仍使用 pip 安装依赖。

首次生成或保持当前版本集合：

```bash
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform windows --output-file constraints/windows-py312.txt
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform macos --output-file constraints/macos-py312.txt
```

全量升级时为两个命令增加 `--upgrade`。只升级一个包时，为两个命令增加 `--upgrade-package <包名>`。提交 constraints 更新的 Pull Request 时记录 `uv --version`，并确认 Windows、macOS 持续集成都通过。
````

- [ ] **Step 5: 更新 README 的开发环境安装命令**

把 README“本地开发”中的 Windows 命令改为：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt -r requirements-build.txt -c constraints\windows-py312.txt
```

把 macOS 命令改为：

```bash
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-build.txt -c constraints/macos-py312.txt
```

在命令后补充一句：

```markdown
上述命令使用当前平台的 Python 3.12 constraints，确保本地环境与 CI、Release 使用相同的依赖版本；constraints 更新规则参见 [贡献指南](CONTRIBUTING.md)。
```

- [ ] **Step 6: 运行依赖文档契约测试**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_open_source_foundation.py::test_dependency_docs_use_reproducible_install_commands \
  -q
```

Expected: 1 passed。

- [ ] **Step 7: 运行完整开源基础设施契约测试**

Run:

```bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
```

Expected: 全部通过。

- [ ] **Step 8: 提交 Task 4**

```bash
git add CONTRIBUTING.md README.md tests/test_open_source_foundation.py
git commit -m "docs: 补充可复现依赖说明"
```

## Task 5: 完成本地验证和代码审查

**Files:**
- Verify only; no expected source changes.

- [ ] **Step 1: 确认 Python 3.12 验证环境并重新应用 constraints**

Run:

```bash
./.venv/bin/python --version
uv pip install \
  --python .venv/bin/python \
  -r requirements.txt \
  -c constraints/macos-py312.txt
```

Expected: 输出 Python 3.12.x，并按 macOS constraints 完成无冲突安装。

- [ ] **Step 2: 运行仓库契约测试**

Run:

```bash
.venv/bin/python -m pytest tests/test_open_source_foundation.py -q
```

Expected: PASS，无失败。

- [ ] **Step 3: 运行完整统一检查**

Run:

```bash
.venv/bin/python scripts/run_checks.py
```

Expected: 所有语法检查、契约检查和 pytest 通过；只允许既有 LibreSSL/urllib3 warning。

- [ ] **Step 4: 检查工作流和差异格式**

Run:

```bash
git diff --check origin/main...HEAD
git status --short
git log --oneline --decorate origin/main..HEAD
```

Expected: `git diff --check` 无输出；工作区干净；日志包含设计、计划和 4 个实施提交。

- [ ] **Step 5: 进行规格符合性审查**

逐项核对：

```text
Actions: checkout@v7 / setup-python@v6 / upload-artifact@v7 / download-artifact@v8 / action-gh-release@v3
.gitignore: 不再包含 docs/
Dependabot: pip + github-actions，每周，普通更新分组，chore(deps)
Dependencies: requirements-build + Windows/macOS Python 3.12 constraints
CI/Release: 使用对应平台 constraints
Docs: 安装和刷新命令与工作流一致
Runtime: 无 app.py、goldmonitor/、static/、templates/ 变更
```

Expected: 全部符合，无范围外变更。

- [ ] **Step 6: 进行代码质量审查**

重点检查：

```text
测试是否会因注释或空行产生误判
constraints 是否全部为精确版本
CI matrix 是否仍产生 Checks (windows-latest) / Checks (macos-latest)
Release 是否仍保留 Windows/macOS 构建和发布资产步骤
Dependabot YAML 是否符合 GitHub schema
文档命令是否可以复制执行
```

Expected: 无阻塞问题；如发现问题，回到对应 Task 修正并重新运行 Step 2–4。

## Task 6: 推送 Pull Request 并完成双平台验收

**Files:**
- Remote Git branch and Pull Request only.

- [ ] **Step 1: 推送功能分支**

Run:

```bash
git push -u origin codex/open-source-maintenance
```

Expected: 远端分支创建成功。

- [ ] **Step 2: 创建 Pull Request**

使用已登录 GitHub 会话创建 Pull Request：

```text
Base: main
Compare: codex/open-source-maintenance
Title: ci: 加固开源维护与依赖供应链
```

Pull Request 描述：

```markdown
## 目标

升级 GitHub Actions，修正文档跟踪规则，启用 Dependabot 配置，并为 Windows/macOS 的 Python 3.12 环境增加版本级依赖锁定。

## 变更范围

- 所有 Node-based Actions 升级到 2026-07-10 官方稳定 Node.js 24 主版本：checkout@v7、setup-python@v6、upload-artifact@v7、download-artifact@v8、action-gh-release@v3
- 删除 `.gitignore` 中整体 `docs/` 规则
- 添加 pip 与 GitHub Actions 每周 Dependabot 更新
- 添加构建依赖声明和双平台 constraints
- CI、Release、README、贡献指南使用同一依赖约定

## 非目标

- 不修改产品运行行为、用户数据和接口契约
- 不处理安装包代码签名
- 不迁移到 pyproject.toml 或 uv.lock

## 验证

- `python -m pytest tests/test_open_source_foundation.py -q`
- `python scripts/run_checks.py`
- Windows/macOS GitHub Actions 检查

## 隐私与安全

不新增遥测、密钥、用户数据或运行时外部服务。远端安全设置和 main Ruleset 将在本 Pull Request 合并后启用。
```

- [ ] **Step 3: 等待双平台检查完成**

必须出现并通过：

```text
Checks (windows-latest)
Checks (macos-latest)
```

Expected: 两个检查均为 success；所有 Node-based Actions 均使用已确认的 Node.js 24 主版本，工作流不再出现 Node.js 20 弃用警告。

- [ ] **Step 4: 处理检查失败**

如任一平台失败：

1. 读取失败 job 的完整日志。
2. 先确定根因，不删除 constraints、不移除测试、不切回旧 Action。
3. 在功能分支修复并运行相应本地测试。
4. 使用中文 Conventional Commit 提交。
5. 推送并等待两个平台重新通过。

- [ ] **Step 5: 合并 Pull Request**

检查通过后使用 merge commit，Pull Request 标题保持：

```text
ci: 加固开源维护与依赖供应链
```

Expected: Pull Request 已合并，远端 `main` 保留设计、计划和各 Task 提交；本地主分支随后可以 `--ff-only` 同步。

## Task 7: 启用安全设置、CodeQL 和 main Ruleset

**Files:**
- GitHub repository settings only.

- [ ] **Step 1: 启用依赖安全功能**

在仓库 `Settings > Code security and analysis` 启用：

```text
Dependency graph
Dependabot alerts
Dependabot security updates
```

Expected: 三项均显示 Enabled；Private vulnerability reporting 保持 Enabled。

- [ ] **Step 2: 启用 CodeQL default setup**

在同一页面为 Code scanning 选择 `Set up > Default`，接受 GitHub 检测到的语言和默认查询套件。

Expected: CodeQL default setup 显示 Configured，首次分析进入 queued、in progress 或 completed 状态。

如果使用已认证 GitHub API，等价请求为：

```http
PATCH /repos/JunCxio/GoldMonitor/code-scanning/default-setup
Content-Type: application/json

{"state":"configured","query_suite":"default"}
```

- [ ] **Step 3: 读取实际 required check context**

从已合并 Pull Request 的 Checks 页面确认名称精确为：

```text
Checks (windows-latest)
Checks (macos-latest)
```

Expected: 名称与规则配置完全一致；如不同，使用实际 context，不猜测。

- [ ] **Step 4: 创建 `main` 分支 Ruleset**

在 `Settings > Rules > Rulesets` 创建 active branch ruleset：

```text
Name: Protect main
Target: Default branch / main
Enforcement: Active
Require a pull request before merging: Enabled
Required approvals: 0
Require status checks: Enabled
Strict branch update: Disabled
Required checks:
  - Checks (windows-latest)
  - Checks (macos-latest)
Block force pushes: Enabled
Restrict deletions: Enabled
Require signed commits: Disabled
Require linear history: Disabled
Require conversation resolution: Disabled
```

Bypass actor 只配置 Repository admin，模式选择 `For pull requests only`。不得选择 `Always allow`。

如果使用已认证 GitHub API，等价请求体为：

```json
{
  "name": "Protect main",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [
    {
      "actor_id": 5,
      "actor_type": "RepositoryRole",
      "bypass_mode": "pull_request"
    }
  ],
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "do_not_enforce_on_create": false,
        "required_status_checks": [
          {"context": "Checks (windows-latest)"},
          {"context": "Checks (macos-latest)"}
        ],
        "strict_required_status_checks_policy": false
      }
    }
  ]
}
```

- [ ] **Step 5: 验证远端设置**

重新打开安全设置和 Ruleset 详情，确认：

```text
Dependency graph: Enabled
Dependabot alerts: Enabled
Dependabot security updates: Enabled
Private vulnerability reporting: Enabled
CodeQL default setup: Configured
Protect main: Active
Pull request required: Yes, approvals 0
Required checks: Windows + macOS
Force push: Blocked
Deletion: Blocked
Admin bypass: Pull requests only
```

Expected: 所有状态与设计一致。

- [ ] **Step 6: 验证 Dependabot 配置已被默认分支识别**

打开仓库 Dependabot 页面，确认存在 `pip` 和 `github-actions` 两个 version update 配置，周期为 weekly。

Expected: 配置解析成功；若页面显示 YAML 错误，修复配置需通过新的 Pull Request，不直接推送 `main`。

## Task 8: 同步本地 main 并完成交付清理

**Files:**
- Local Git metadata and worktree only.

- [ ] **Step 1: 获取远端合并结果**

在主工作区运行：

```bash
git fetch origin
git merge --ff-only origin/main
```

Expected: 本地 `main` 快进到远端合并提交，不产生额外 merge commit。

- [ ] **Step 2: 验证主工作区状态**

Run:

```bash
git status --short --branch
```

Expected: `main` 与 `origin/main` 同步；只显示设计规格中列出的 8 个既有未跟踪 Markdown 文件，不出现本阶段生成的其他改动。

- [ ] **Step 3: 删除已合并功能分支和 worktree**

确认 Pull Request 已合并后：

```bash
git worktree remove .worktrees/open-source-maintenance
git branch -d codex/open-source-maintenance
git push origin --delete codex/open-source-maintenance
```

Expected: 隔离 worktree、本地功能分支和远端功能分支已删除；不得删除 8 个用户文档。

- [ ] **Step 4: 最终回归查询**

验证：

```text
远端 main 包含 Pull Request 合并提交
Windows/macOS CI 最近一次运行成功
CodeQL default setup 已配置
Dependabot 两个生态已识别
Protect main Ruleset 为 Active
本地 main 与 origin/main 同步
```

Expected: 全部满足，交付完成。
