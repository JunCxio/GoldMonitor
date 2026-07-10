# GoldMonitor 开源维护与供应链加固设计

## 背景

GoldMonitor 已完成 MIT 许可证、贡献指南、安全策略、社区模板、Windows/macOS 持续集成和统一检查入口建设。当前仓库已经适合公开使用和接受贡献，但仍存在五类维护风险：GitHub Actions 运行时即将弃用、`docs/` 新文件会被错误忽略、`main` 可以绕过 Pull Request 与持续集成、依赖与代码安全检查未自动化、CI 和 Release 每次安装的传递依赖版本不固定。

本阶段只完善仓库治理、供应链安全和构建可复现性，不改变 GoldMonitor 的产品功能、运行时数据、接口契约或安装包交互。

## 已确认决策

- 项目继续以 MIT License 免费开源。
- 功能价值与维护成本保持平衡，优先采用 GitHub 原生能力和现有 pip 安装链路。
- GitHub Actions 升级到 Node.js 24 对应的官方主版本。
- 删除 `.gitignore` 中对整个 `docs/` 目录的忽略。
- `main` 通过仓库 Ruleset 保护，但不要求人工审批，适配单人维护。
- 启用 Dependency graph、Dependabot alerts、Dependabot security updates 和 CodeQL default setup。
- 保留 `requirements.txt` 作为直接依赖声明，增加 Windows/macOS 两份 Python 3.12 constraints 固定完整依赖解析结果。

## 目标

1. 消除 GitHub Actions 的 Node.js 20 弃用警告。
2. 确保新增公开文档默认进入 Git 变更集。
3. 让 `main` 的常规变更必须经过 Pull Request 和双平台持续集成。
4. 自动发现依赖漏洞、依赖新版本和可由 CodeQL 识别的代码安全问题。
5. 让同一提交在每个受支持平台的 CI、Release 中重复安装该平台相同的已锁定依赖版本。
6. 控制自动化产生的 Pull Request 数量，避免增加不必要的维护负担。

## 非目标

- 不修改 `app.py`、前端资源、Socket.IO 事件、配置格式或本地持久化数据。
- 不新增产品功能、遥测、账号体系、远程服务或运行时网络依赖。
- 不在本阶段处理 Windows 代码签名和 macOS Developer ID 签名、公证。
- 不要求 Commit 签名、线性历史、人工审批、CLA 或 DCO。
- 不迁移到 `pyproject.toml`、Poetry、PDM 或 `uv.lock`。
- 不要求普通使用者或 CI 改用 uv 安装依赖；uv 只作为维护者生成 constraints 的工具。
- 不保证不同操作系统安装完全相同的包集合；平台专属依赖分别锁定。

## 仓库文件设计

### 1. GitHub Actions 版本

修改 `.github/workflows/ci.yml` 和 `.github/workflows/release.yml`：

- `actions/checkout@v4` 升级为 `actions/checkout@v5`。
- `actions/setup-python@v5` 升级为 `actions/setup-python@v6`。
- 已使用当前稳定主版本的 `actions/upload-artifact@v4`、`actions/download-artifact@v4` 和 `softprops/action-gh-release@v2` 保持不变。

官方 Action 使用主版本标签，由 Dependabot 后续跟踪新主版本。本阶段不改为 Commit SHA 固定，以减少官方 Action 日常补丁升级的维护成本。

### 2. 文档跟踪规则

从 `.gitignore` 删除单独的 `docs/` 规则。现有 `.DS_Store` 全局规则继续忽略文档目录中的系统文件；不增加 `!docs/**` 等反向规则，因为根级 `docs/` 忽略被删除后不再需要例外配置。

当前主工作区已有 8 个因该规则而未被跟踪的 Markdown 文件：

- `docs/product-discovery/PRD-event-timeline-review-report.md`
- `docs/product-discovery/WWA-event-timeline-review-report.md`
- `docs/product-discovery/acceptance-criteria-event-timeline-review-report.md`
- `docs/product-discovery/implementation-plan-event-timeline-review-report.md`
- `docs/product-discovery/user-stories-event-timeline-review-report.md`
- `docs/superpowers/plans/2026-06-30-portfolio-import-safety.md`
- `docs/superpowers/plans/2026-07-02-portfolio-review-detail.md`
- `docs/superpowers/plans/2026-07-09-alert-profiles.md`

这些文件属于实施前已经存在的用户文件，不在本阶段自动修改、删除或提交。实施时使用隔离 worktree，并只按明确路径暂存本阶段文件。合并后它们会按修正规则正常显示为未跟踪文件，最终报告必须单独列明，不得把它们描述为本阶段遗留变更或通过新增仓库忽略规则再次隐藏。

### 3. Dependabot 配置

新增 `.github/dependabot.yml`：

- `pip`：每周检查一次，目录为仓库根目录，目标分支为 `main`。
- `github-actions`：每周检查一次，目录为仓库根目录，目标分支为 `main`。
- 同一生态的非安全版本更新按组提交，减少 Pull Request 数量。
- 保留 Dependabot 安全更新的独立可追踪性，不将安全修复与普通升级混在同一变更中。
- Commit 配置使用 `prefix: "chore"` 和 `include: "scope"`，生成符合项目规范的 `chore(deps):`，不添加任何署名或生成声明。

### 4. 可复现 Python 依赖

保留 `requirements.txt` 作为开发者可读的直接依赖声明和平台 marker 来源，新增：

- `requirements-build.txt`
- `constraints/windows-py312.txt`
- `constraints/macos-py312.txt`

`requirements-build.txt` 声明 `pyinstaller>=6.0,<7.0`，使 Release 构建依赖不再隐藏在工作流命令中，同时避免未经验证的下一主版本进入构建。两份 constraints 必须包含对应平台在 Python 3.12 下解析出的全部直接依赖和传递依赖，并使用精确版本 `==`。平台专属包只进入对应文件。`pyinstaller` 也必须被 constraints 固定，避免应用依赖已锁定但打包器仍漂移。

不启用 `--require-hashes`。哈希锁定可以进一步固定分发文件，但会显著增加 Windows/macOS 不同 wheel、源代码包和 Dependabot 更新的维护成本；本阶段先保证版本级可复现。

CI 安装方式调整为：

```text
Windows -> pip install -r requirements.txt -c constraints/windows-py312.txt
macOS   -> pip install -r requirements.txt -c constraints/macos-py312.txt
```

Release 使用 `requirements.txt`、`requirements-build.txt` 和对应 constraints 安装完整构建环境。开发者仍可直接安装 `requirements.txt`；需要复现 CI 或 Release 环境时，按 `CONTRIBUTING.md` 增加当前平台 constraints 和构建依赖文件。

constraints 首次使用已验证的 uv 0.11.21 pip-compatible 编译器生成，但安装端仍使用 pip：

```text
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform windows --output-file constraints/windows-py312.txt
uv pip compile requirements.txt requirements-build.txt --python-version 3.12 --python-platform macos --output-file constraints/macos-py312.txt
```

生成命令写入 `CONTRIBUTING.md`，输出文件保留生成器头部和依赖来源注释，便于审阅。采用显式 `windows`、`macos` 目标，而不是在本机 `pip freeze`，避免把维护者当前虚拟环境和架构状态带入锁定文件。维护者升级 uv 后刷新 constraints 时，Pull Request 必须记录实际 `uv --version`，便于解释解析结果变化。

constraints 更新规则：

1. 只接受能够在对应 GitHub Actions 平台完整安装并通过 `scripts/run_checks.py` 的版本集合。
2. 直接依赖范围仍在 `requirements.txt` 维护；constraints 不取代需求声明。
3. 首次生成使用上述命令；全量更新时增加 `--upgrade`，单包更新时增加 `--upgrade-package <包名>`，避免普通依赖 Pull Request 无意刷新全部传递依赖。
4. Dependabot 提交依赖更新后，维护者按更新范围刷新两份 constraints；双平台 CI 是合并门槛。若直接依赖与 constraints 不一致，安装步骤必须失败，不允许忽略 constraints 或回退到未锁定安装。
5. Python 小版本保持 3.12；升级 Python 版本时必须重新生成两份 constraints，而不是继续复用旧文件。

README 和 `CONTRIBUTING.md` 只补充必要安装说明，不重复列出完整锁定版本。

## GitHub 远端设置设计

### 1. 主分支 Ruleset

为 `main` 创建一个启用状态的分支 Ruleset：

- 目标仅为默认分支 `main`。
- 常规变更必须通过 Pull Request 合并。
- 人工批准数为 0，允许单人维护者在检查通过后合并自己的 Pull Request。
- 必须通过 `Checks (windows-latest)` 和 `Checks (macos-latest)`。
- 不强制 Pull Request 在合并前再次更新到最新 `main`，避免低并发单人维护场景产生无价值的重复 CI；若后续并发贡献增加，再单独评估严格更新策略或 merge queue。
- 禁止强制推送和删除 `main`。
- 仓库管理员保留 `pull_request` 模式的紧急 bypass，只能在 Pull Request 合并时绕过检查，不能直接推送 `main`；bypass 用于 GitHub 检查故障或规则配置错误，不作为日常开发路径。
- 不额外要求签名 Commit、线性历史或对话全部解决。

Ruleset 在本阶段代码 Pull Request 合并后再启用。这样既能使用现有流程完成首次加固，又能确保后续变更受新规则约束。

### 2. 依赖与代码安全

通过 GitHub 仓库设置启用：

- Dependency graph。
- Dependabot alerts。
- Dependabot security updates。
- CodeQL default setup。

CodeQL 使用 GitHub 自动识别的仓库语言和默认查询套件，不新增自维护 CodeQL workflow。默认设置由 GitHub 维护，适合当前仓库规模；若后续需要自定义查询、构建步骤或扫描排除项，再单独设计 advanced setup。

Private vulnerability reporting 已启用，本阶段只验证其状态，不重复修改。

## 执行顺序

```text
创建功能分支和隔离 worktree
  -> 先写仓库契约测试
  -> 升级 Actions、修正 .gitignore、添加 Dependabot 与 constraints
  -> 更新 CI、Release 和贡献文档
  -> 本地测试与静态检查
  -> 推送 Pull Request，等待 Windows/macOS 检查通过
  -> 合并代码变更
  -> 启用 GitHub 安全设置和 CodeQL default setup
  -> 创建并启用 main Ruleset
  -> 读取 GitHub 设置与检查状态做最终验收
```

远端设置放在代码合并后执行，因为 required status check 名称必须已经稳定存在，且 Dependabot 配置需要先进入默认分支。

## 异常处理

- Action 主版本不存在或工作流无法加载：Pull Request 检查失败，停止合并，不保留新旧版本混用作为兜底。
- constraints 与 `requirements.txt` 冲突：依赖安装失败，修正锁定文件后重新运行；禁止移除 `-c` 临时绕过。
- 某个平台无可用 wheel：确认该依赖是否应存在于该平台；不能通过删除测试或静默跳过解决。
- Dependabot 配置无效：GitHub 不会创建更新任务，必须从 Dependabot 页面或 API 确认配置解析成功。
- CodeQL default setup 不支持当前仓库状态：保留其他安全功能，记录 GitHub 返回的具体原因，不自动切换到自维护 advanced workflow。
- Ruleset 所需检查名称不匹配：先从已完成的 CI run 读取实际 check context，再创建或修正规则，避免合并永久阻塞。
- GitHub API 或权限不足：不在本地伪造成功；保留已完成的仓库变更并明确报告未完成的远端设置。

## 测试与验证

仓库级契约测试覆盖：

- CI 和 Release 只使用 `actions/checkout@v5`、`actions/setup-python@v6`。
- `.gitignore` 不再忽略 `docs/`。
- `.github/dependabot.yml` 同时配置 `pip` 和 `github-actions` 的每周检查。
- Windows/macOS constraints 文件存在，非注释依赖均为精确版本或合规平台 marker。
- CI 和 Release 根据操作系统使用正确 constraints。
- `requirements-build.txt` 将 `pyinstaller` 限制在 6.x，Release 的实际版本继续受 constraints 精确限制。
- README 与 `CONTRIBUTING.md` 的可复现安装说明与工作流一致。

执行验证包括：

1. 运行新增或修改的仓库契约测试。
2. 运行 `python scripts/run_checks.py`。
3. 在 Pull Request 中确认 Windows 和 macOS 两个检查均通过。
4. 合并后通过 GitHub API 或设置页面确认四项安全功能状态。
5. 确认 CodeQL default setup 已启用并出现首次分析状态。
6. 读取 Ruleset，确认目标、Pull Request 要求、两个 required checks、禁止强推/删除和管理员 bypass 与设计一致。
7. 使用只读请求确认远端 `main` 包含已合并提交；隔离 worktree 无未提交变更，主工作区只允许出现上述 8 个实施前已存在、现已正常显式呈现的未跟踪文档。

GitHub 远端设置无法由 pytest 可靠模拟，因此以 API 返回和 GitHub 实际检查结果为验收证据，不增加依赖个人令牌的本地测试。

## 验收标准

1. GitHub Actions 不再报告 checkout/setup-python 的 Node.js 20 弃用警告。
2. 新建 `docs/` 下文件时，`git status` 能显示该文件。
3. `main` 的常规推送不能绕过 Pull Request，强推和删除被禁止。
4. Pull Request 必须通过 Windows 和 macOS 检查，且不要求第二名维护者批准。
5. Dependency graph、Dependabot alerts、Dependabot security updates 和 CodeQL default setup 均已启用。
6. Dependabot 每周检查 Python 与 GitHub Actions 依赖，并按生态合并普通版本更新。
7. CI 与 Release 在 Windows/macOS 使用各自的 Python 3.12 constraints，所有应用和构建依赖版本均被精确固定。
8. 本地完整检查与 Pull Request 双平台检查通过。
9. 本阶段不改变应用运行行为、用户数据、接口契约和发布资产名称。

## 风险与取舍

- 两份 constraints 比单一锁文件多一个维护点，但能明确反映 Windows 与 macOS 的平台依赖差异，并保持现有 pip 工作流不迁移。
- 不启用哈希锁定，不能固定同版本下的具体分发文件；换取 Dependabot 和跨平台 wheel 更新的可维护性。
- 0 人工审批降低了多人复核强度，但双平台检查仍是强制门槛，符合当前单人维护实际。
- `pull_request` 模式的管理员 bypass 是恢复手段而不是质量豁免；它允许紧急合并，但不会恢复直接推送 `main` 的能力。
- CodeQL default setup 可维护性高，但自定义能力有限；当前阶段没有证据需要 advanced setup。
