# GoldMonitor 开源基础设施设计

## 背景

GoldMonitor 已经作为免费项目公开源码，并具备 Windows、macOS 安装包、自动更新、行情监控、预警、持仓、复盘和风险分析等完整能力。当前仓库仍缺少开源许可证、贡献指南、安全策略、社区模板和 Pull Request 持续集成，因此外部使用者缺少明确的授权边界，贡献者也无法通过统一入口完成本地验证和提交检查。

本阶段采用“功能纵切式演进”路线中的第一个切片：先建立开源项目最小且完整的法律、协作和质量基础，不修改 GoldMonitor 的产品运行行为。

## 已确认决策

- 项目定位：面向公众、免费使用的开源项目。
- 演进原则：普通用户价值与开源维护体验平衡推进。
- 许可证：MIT License。
- 版权声明：`Copyright (c) 2026 JunCxio`。
- 支持平台：Windows 和 macOS。
- 本阶段不引入 CLA、DCO、账号体系、自动发布或产品功能改动。

## 目标

1. 让使用者获得明确的复制、修改和分发授权。
2. 让新贡献者能够仅根据仓库文档完成开发环境准备、本地检查和 Pull Request 提交。
3. 让每个 Pull Request 在 Windows 和 macOS 上执行与正式发布一致的质量检查。
4. 消除 README、Pull Request CI 和 Release 工作流之间重复维护测试命令的问题。
5. 为普通问题、功能建议和安全漏洞建立边界清晰的反馈入口。

## 非目标

- 不修改 `app.py`、前端页面、Socket.IO 契约、配置格式或本地数据。
- 不增加行情源、通知渠道、风险分析能力或其他产品功能。
- 不在 Pull Request 中构建或发布 Windows EXE、macOS DMG 和更新清单。
- 不引入账户、权限、远程写入、遥测或云服务。
- 不在本阶段拆分大型后端和前端文件。

## 交付组成

### 1. 开源授权

在仓库根目录新增 `LICENSE`，使用标准 MIT License 全文，版权声明固定为：

```text
Copyright (c) 2026 JunCxio
```

README 增加许可证入口，并明确项目在 MIT License 下发布。

### 2. 贡献指南

新增 `CONTRIBUTING.md`，至少包含：

- 支持的 Python 版本和 Windows、macOS 开发环境准备方式。
- 依赖安装、应用启动和统一检查命令。
- 建议从小范围、单一目标的变更开始，避免在一个 Pull Request 中混合功能、重构和无关格式化。
- 新增或修改行为时必须补充相应测试。
- Commit 使用中文 Conventional Commits，例如 `feat:`、`fix:`、`docs:`、`test:`、`refactor:`。
- Pull Request 需要说明目标、影响范围、验证证据、文档变化和隐私影响。
- 禁止提交 API Key、SMTP 授权码、Webhook URL、用户配置、诊断原文或其他敏感数据。

本阶段不要求贡献者签署 CLA 或在 Commit 中添加 DCO sign-off。

### 3. 安全策略

新增 `SECURITY.md`，规定：

- 安全漏洞通过 GitHub Security Advisory 的私密漏洞报告入口提交。
- 不在公开 Issue、Discussion、Pull Request 或日志中披露可利用细节、密钥和用户数据。
- 当前最新正式版本作为主要支持版本，历史版本不承诺安全补丁。
- 维护者不承诺固定响应时限，但会在可处理时确认报告并协调披露。

### 4. 社区行为规范

新增 `CODE_OF_CONDUCT.md`，采用 Contributor Covenant 2.1，要求讨论保持专业、尊重并聚焦项目问题。第一版将 GitHub Security Advisory 的私密报告入口同时作为行为准则举报渠道，举报标题必须注明“行为准则举报”；维护者不得公开举报者身份或原始举报内容。

### 5. Issue 与 Pull Request 模板

新增以下社区模板：

- `.github/ISSUE_TEMPLATE/bug_report.yml`：收集 GoldMonitor 版本、操作系统、问题描述、复现步骤、预期结果、实际结果和脱敏后的诊断信息。
- `.github/ISSUE_TEMPLATE/feature_request.yml`：收集用户问题、使用场景、期望结果、范围边界和替代方案，不要求提交者先设计实现。
- `.github/ISSUE_TEMPLATE/config.yml`：关闭空白 Issue，并提供私密安全报告入口。
- `.github/pull_request_template.md`：要求填写变更目标、影响范围、验证结果、文档变化、隐私安全检查和关联 Issue。

所有模板必须提醒提交者移除 API Key、SMTP 授权码、Webhook URL、本地路径中的个人信息以及完整诊断数据。

### 6. README 入口

README 增加简短的“参与贡献”“安全问题”和“许可证”章节，链接到对应文件。现有本地开发和测试说明保留，但标准验证入口统一指向 `scripts/run_checks.py`，详细规则放在 `CONTRIBUTING.md`，避免 README 继续膨胀。

## CI 架构

### 统一检查入口

新增 `scripts/run_checks.py` 作为跨平台检查编排器。该脚本只负责按顺序执行现有检查，不承载业务测试逻辑，也不修改源码或生成发布产物。

第一版检查清单必须覆盖当前 README、Windows Release 检查块和 macOS Release 检查块中全部命令的并集。只有完全相同的重复命令可以合并，不得在缺少等价验证证据时删除现有检查。

检查分为两类：

1. 通用检查：Python 语法编译、pytest 测试、Python 契约检查和前端静态资源契约检查。
2. 平台检查：Windows 执行现有 PowerShell 契约入口；macOS 执行当前 Release 工作流中的 macOS 检查集合。

脚本使用当前 Python 解释器调用子命令。任一子命令失败时返回非零退出码，并输出失败命令；未执行的发布和打包步骤不作为该脚本职责。

### Pull Request 工作流

新增 `.github/workflows/ci.yml`：

- 在 `pull_request` 和推送到 `main` 时触发。
- 使用 Python 3.12。
- 使用 `windows-latest` 和 `macos-latest` 矩阵，与正式支持平台一致。
- 安装 `requirements.txt` 中的平台适用依赖。
- 执行 `python scripts/run_checks.py`。
- 使用只读仓库权限，不配置发布权限和项目密钥。
- 为同一分支设置并发组，新提交到达时取消旧任务。
- Windows 和 macOS 任务独立运行；一个平台失败不会取消另一个平台，便于一次获得完整反馈。
- Pull Request 阶段不构建安装包，不上传 Release 资产。

### Release 工作流复用

保留 `.github/workflows/release.yml` 的标签触发、双平台构建、清单生成、发布和发布资产验收职责。Windows 和 macOS 构建任务中的重复检查命令改为调用 `python scripts/run_checks.py`。

Release 工作流在统一检查失败后必须停止对应平台构建，避免发布未通过 Pull Request 质量门槛的代码。

## 执行链路

### 本地贡献

```text
贡献者修改代码
  -> python scripts/run_checks.py
  -> 通用检查
  -> 当前平台检查
  -> 全部通过后提交 Pull Request
```

### Pull Request

```text
Pull Request 或 main 推送
  -> Windows / macOS 并行任务
  -> 安装依赖
  -> scripts/run_checks.py
  -> GitHub 汇总两个平台结果
  -> 全部通过后满足质量门槛
```

### 正式发布

```text
推送版本标签
  -> Windows / macOS 调用同一检查入口
  -> 构建安装包
  -> 生成更新清单
  -> 发布 Release
  -> 验收线上发布资产
```

## 异常与安全处理

- 测试或契约检查失败：统一检查脚本返回失败，Pull Request 或 Release 对应任务显示具体命令和输出。
- 单平台失败：保留另一平台的执行结果，不用一个失败掩盖另一个平台的问题。
- 依赖安装失败：CI 在检查前终止，不尝试降级、忽略或自动修改依赖范围。
- 外部服务不可用：检查集合不得依赖实时行情、GitHub Release、邮件、Webhook 或模型接口；相关行为必须使用模拟数据或现有测试替身。
- 安全报告误入公开 Issue：模板明确引导私密报告；维护者发现后应删除敏感内容并转入私密处理，不在公开讨论中继续复现。
- CI 权限：Pull Request 工作流仅使用 `contents: read`，不授予 Release 写入权限，不读取应用密钥和用户配置。

## 测试设计

新增 `tests/test_open_source_foundation.py`，验证：

- `LICENSE` 存在并包含 MIT 标准授权文本和确认的版权声明。
- `CONTRIBUTING.md`、`SECURITY.md`、`CODE_OF_CONDUCT.md` 和社区模板存在。
- README 包含许可证、贡献指南和安全策略入口。
- Pull Request 工作流包含 `pull_request`、`main` 推送、Windows/macOS 矩阵、只读权限和统一检查入口。
- Release 工作流调用统一检查入口，不再维护第二份完整检查清单。
- README、Windows Release 和 macOS Release 的现有检查均被统一入口覆盖。

新增 `tests/test_run_checks_script.py`，通过注入子进程执行器验证 `scripts/run_checks.py` 的命令顺序、平台分支、失败返回状态和失败命令输出，不在单元测试中重复执行完整测试套件。

工作流 YAML 的实际可执行性由 GitHub Actions 验证；本地测试只检查关键契约，不复制 GitHub Actions 的完整解析行为。

## 验收标准

1. GitHub 能识别仓库的 MIT License。
2. 版权声明为 `Copyright (c) 2026 JunCxio`。
3. 新贡献者可以仅根据 `CONTRIBUTING.md` 完成环境准备并运行统一检查。
4. Pull Request 自动在 Windows 和 macOS 上执行统一检查。
5. 本地、Pull Request 和 Release 使用同一检查入口。
6. 故意制造测试失败时，CI 能阻止质量检查通过并显示对应平台和失败命令。
7. README 可以直接进入许可证、贡献指南和安全策略。
8. Bug、功能建议、安全漏洞和 Pull Request 分别进入合适的模板或私密流程。
9. CI 不访问外部模型、通知服务、实时行情或用户数据。
10. 本阶段不改变 GoldMonitor 的运行行为、Socket.IO 契约、配置格式和安装包内容。

## 风险与取舍

- Windows 和 macOS 双平台 Pull Request 检查会增加执行时间，但能在合并前发现实际支持平台差异，优于只在发布标签阶段发现问题。
- 统一检查脚本增加一个维护入口，但它替代 README 和两个工作流中的重复命令，总体降低测试清单漂移风险。
- 本阶段不拆分 `app.py` 和 `static/app.js`，因此不会立即改善大型文件问题；后续功能切片必须在触及对应区域时同步抽取模块。
- MIT 允许第三方闭源使用和再分发，这是选择宽松许可证的明确结果。

## 后续阶段

本阶段完成后，下一条功能纵切建议为“首次使用向导”。该功能应同时抽离前端设置与引导状态，复用行情健康、通知测试和预警策略模板能力，但不属于本设计的实施范围。
