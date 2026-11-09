# build-mas 完整落地方案（Codex Python SDK）

版本：方案基线 2026-11-08。本文不包含排期。

参考项目实现、源码证据和 SDK 能力边界见 [project-evaluations.md](./project-evaluations.md)。

## 1. 最终产品判断

build-mas 不是一个 Skill，也不是另一个 CrewAI。

它是一个**可持续嵌入用户 Coding Agent 工作过程的 Agent 系统架构与构建内核**：

- 用户可以在构思、设计、编码、调试、评测、重构等任意阶段调用。
- 输入可以是自然语言、仓库、文件、图片、diff、测试失败、trace、URL、结构化数据或宿主对话中选定的上下文。
- 用户可以要求分析、规划、构建、局部编辑、诊断、调整、重构或验证自己的 Agentic workflow / MAS。
- 构建内核和目标 workflow 的 Agent runtime 只使用 Codex Python SDK。
- CLI、MCP、Codex 插件、Claude Code 插件、OpenCode 插件都是对外 Harness；Skill 只是某些接入层的薄入口。

核心架构结论：

```text
一个构建内核 + 一个版本化 ArchitectureSpec + 多种薄接入层
模型负责分析、生成和语义诊断
宿主 Python 负责路由、权限、调度、状态、集成和最终验收
Codex 负责每个 Agent 内层的模型—工具—沙箱循环
```

## 2. 产品边界

### 2.1 必须实现

1. 从目标或已有实现恢复真实任务流、数据流、权限和完成条件。
2. 决定是否需要多个 Agent，以及每个 Agent 的上下文、输入输出、Skills、工具和权限。
3. 决定目标系统需要哪些 Skills、工具、CLI、MCP 或其他调用界面。
4. 生成或修改可运行的 Codex Python SDK 项目。
5. 执行确定性验证，必要时增加独立 Codex verifier，交付证据。
6. 允许跨多次调用延续同一工作区、ArchitectureSpec 和验证历史。
7. 通过 CLI、MCP 和不同 Coding Agent 插件提供同一能力。
8. 识别目标项目当前 runtime；无实现或其他 Agent 框架统一新建/迁移到 Codex SDK，已是 Codex SDK 时复用现有实现。

### 2.2 明确不做

- 不引入 CrewAI、Claude Agent SDK、OpenAI Agents SDK 或 OpenCode 自有 Agent runtime。
- 不直接调用 app-server 实验 JSON-RPC，不把 generated schema 当公开 Python API。
- 不默认多 Agent，不复制 Crew/Flow/AgentExecutor 三层运行时。
- 不做通用模型 provider 抽象、统一向量 Memory、远程 Skill registry 或企业部署控制面。
- 不自动 commit、push、发布、部署或修改外部系统。
- 不把 `TurnStatus.completed`、合法 JSON 或 verifier 的 `passed` 单独当作构建成功。
- 不在最终目标系统中保留其他 Agent runtime；迁移期间保留旧实现仅用于对照和回退。

## 3. 总体架构

```text
用户 / CI / 用户的 Coding Agent
  │
  ├─ 独立 CLI
  ├─ MCP clients
  ├─ Codex plugin
  ├─ Claude Code plugin
  └─ OpenCode plugin
        │  薄接入：规范化输入、展示结果、宿主审批
        ▼
IntakeEnvelope + OperationRouter
        ▼
Session / Workspace / Spec revisions / RunState
        ▼
invoke（分析、规划、诊断、变更提案）
        ▼
build-mas Core
  ├─ Discovery & CodebaseProfile
  ├─ ArchitectureSpec & policy validation
  ├─ Build / Edit / Refactor DAG
  ├─ Tool / Skill / Interface planner
  ├─ Deterministic verifier
  └─ Evidence and trace store
        ▼
apply（唯一目标写入口）/ verify（受控执行）
        ▼
公开 openai_codex / openai_codex.types
        ▼
Codex CLI runtime / app-server（仅由 SDK 内部管理）
        ▼
分析、构建、诊断、独立验证 Threads
```

接入层不得各自实现一套架构逻辑。Claude Code 或 OpenCode 的宿主模型只负责调用 build-mas 和转述结果，不代替 Codex SDK 做 build-mas 的架构决策或执行。

## 4. 任意阶段、任意材料的统一入口

### 4.1 IntakeEnvelope

所有接入层先把输入规范化为同一合同：

```json
{
  "request_id": "req_...",
  "idempotency_key": "caller_stable_key",
  "session_id": "ses_optional",
  "operation": "auto",
  "goal": "用户的原始请求",
  "workspace_id": "ws_pre_registered",
  "spec_ref": null,
  "inputs": [
    {
      "kind": "text|path|image|diff|trace|url|artifact|conversation",
      "content_or_ref": "...",
      "media_type": "text/plain",
      "source": "user|workspace|host|external",
      "trust": "user|workspace_untrusted|external_untrusted"
    }
  ],
  "constraints": {
    "allowed_operations": [],
    "allowed_write_roots": [],
    "forbidden_actions": [],
    "max_repairs": 2
  }
}
```

约束：

- 宿主对话默认只传当前请求所需片段，不自动复制完整历史。
- `workspace_id` 由服务端映射到预注册 canonical root；模型不能直接通过任意路径获得写权限。
- repo、网页、trace、测试输出、其他 Agent 结论均为非可信数据，不能提升为授权。
- SDK 原生支持的文本和图片直接进入 Turn；其他材料先落为带路径和 media type 的 artifact，不把“任意形式”误述为 SDK 原生支持任意模态。
- 未提供 `session_id` 时创建新会话并返回；后续调用显式复用。

### 4.2 OperationRouter

支持操作：

| 操作 | 典型请求 | 默认权限 | 结果 |
|---|---|---|---|
| `analyze/review` | 看看当前架构、审计这个 MAS | read-only | 现状、问题、证据 |
| `plan` | 根据目标设计 workflow | read-only + run artifact | ArchitectureSpec 新修订 |
| `build` | 从零搭建这个系统 | invoke 阶段不写目标 | ApplyProposal 与验证计划 |
| `edit` | 增加一个工具、Skill 或 verifier | invoke 阶段不写目标 | 最小变更提案 |
| `diagnose` | 为什么这个 handoff/test 失败 | 先 read-only | 最早失败边界与修复建议 |
| `migrate` | 把现有 CrewAI/其他 MAS 迁到 Codex SDK | 先 read-only | 迁移提案与对等验证计划 |
| `refactor` | 把多 Agent 合并、重排 Flow | invoke 阶段不写目标 | 新 spec 和重构提案 |
| `verify` | 验证当前实现 | 执行声明的检查，不改源码 | VerificationReport |
| `apply` | 应用 build/edit/migrate/refactor 提案 | 明确授权后 workspace-write | 目标修改与回归证据 |

`auto` 路由规则：

1. 先识别用户意图、当前阶段、已有 spec 和工作区状态。
2. 分析、解释、审查请求不能被扩展成写操作。
3. `invoke(auto)` 只产生分析、诊断、SpecRevision 或 ApplyProposal，不直接修改目标；所有目标修改统一经过 `apply`。
4. 已有 Codex SDK 实现默认做最小变更；已有非 Codex runtime 进入 `migrate`，最终重建为 Codex SDK，而不是继续叠加旧框架。
5. 修改后自动执行相关验证；验证失败进入有界诊断/修复，不无限重试。

## 5. ArchitectureSpec：唯一的跨阶段事实源

采用 JSON 作为机器交换格式，UI 可渲染为 Markdown。所有字段带 `schema_version` 和单调递增 `revision`。

```text
ArchitectureSpec
├─ objective / inputs / outputs / done_conditions
├─ mode: new | adapt | migrate | refactor | diagnose
├─ runtime: source=none|codex_sdk|other|unknown、target=codex_sdk、migration_ref
├─ workspace: cwd、base_revision、preexisting_changes_ref、write_roots
├─ evidence[]: source、path/URI、observed/inferred/missing
├─ baseline: single_agent_sufficient、comparison、reason
├─ agents[]
│  └─ id、purpose、instructions_ref、thread_strategy、skills、tools、sandbox、budget
├─ skills[]
│  └─ name、trigger、procedure、references、scripts、lifecycle、eval_cases
├─ tools[]
│  └─ name、kind、input/output schema、implementation、risk、side_effect、timeout、approval
├─ interfaces[]
│  └─ type: cli|mcp|plugin|library、entrypoint、commands/tools、host
├─ work_packets[]
│  └─ id、agent、depends_on、input_refs、output_schema、acceptance、retry、timeout
├─ orchestration: sequential|parallel|iterative、join、integration、max_parallel
├─ state: artifacts、resume、retention、idempotency
├─ controls: write_roots、forbidden_actions、approval_gates、budgets、trust_boundaries
├─ verification: artifact_checks、command_checks、semantic_checks、eval_cases
└─ deferred[]: 被刻意排除的机制及原因
```

关键规则：

- spec 是 build-mas 自有合同，不是 Codex SDK 提供的模型。
- planner 只能提出 spec；宿主验证 schema、引用、DAG、权限、验收和路径后才能使用。
- `apply` 绑定 `proposal_id + spec_sha256 + expected_workspace_snapshot + idempotency_key`；spec、工作区或目标范围发生实质变化时必须重新授权。
- spec 中的工具、Skills 和接口声明不会自行安装、注册或授权。
- 失败修复也更新 spec 或实现修订，保证需求、代码、测试和证据可关联。

## 6. Runtime、Agent、Skills、工具与接口的决策规则

### 6.1 Source runtime 与迁移

| 检测结果 | 路径 | 最终要求 |
|---|---|---|
| 无现有实现 | 新建 Codex SDK 项目 | 声明 `openai-codex` 依赖，生成运行与验证入口 |
| 已是 Codex SDK | 复用并做用户要求的局部修改 | 不重建、不切换，保留有效合同 |
| 简单自实现或其他 Agent 框架 | 先提取行为合同，再 `migrate/rebuild` | 最终只保留 Codex SDK Agent runtime |
| 无法确认 | 只读检查入口、依赖、import 和调用链 | 仍不明确时只问一个阻塞性问题 |

非 Codex 迁移步骤：

```text
识别旧 Agent / Task / Flow / 工具 / 状态 / 权限
  → 记录输入输出、外部集成、错误和副作用合同
  → 生成 source_runtime=other、target_runtime=codex_sdk 的 ArchitectureSpec
  → 用公开 Codex SDK 重建目标 workflow
  → 用固定 fixtures 做行为对等、权限和失败路径验证
  → 新实现通过后再由用户批准移除旧 runtime 与依赖
```

迁移期间旧实现可用于对照和回退，但不与 Codex runtime 混合执行。完成迁移必须证明目标代码不再 import 旧 Agent 框架、依赖清单不再需要旧 runtime、真实 workflow 由 Codex SDK 跑通。外部业务 API 可以保持不变，不能用“对等”之名保留旧 Agent runtime。旧系统无法安全运行时，使用已有输出和行为合同做回归，并明确未覆盖项，不能声称已证明完全对等。

### 6.2 Agent

默认一个 Thread 多个 Turn。只有以下情况才新增 Thread：

- 工作可以独立分派，并行有实际收益。
- 需要独立上下文，避免不同角色相互污染。
- 需要不同 sandbox、工具或数据范围。
- 独立验收有可证明的价值。

不因为“角色听起来不同”“文件很多”“用户提到 MAS”就拆分。协调器默认是宿主 Python，不再创建一个拥有自由分派权的 manager Agent。

### 6.3 Skills

Skill 只承载可复用程序性知识：

- 重复工作流、领域方法、模板、检查清单和按需 references。
- 一次性任务说明不生成 Skill。
- 确定性重复逻辑放脚本或宿主代码，不靠提示词重复生成。
- 采用渐进披露，不在初始上下文加载所有 Skill 正文。

生命周期必须分别验证：

```text
generated → discovered/installed → explicitly loaded → behavior verified
```

显式调用时按官方合同在文本中包含 `$<skill-name>`，并同时传入对应 `SkillInput`。这只覆盖显式加载的一部分，不证明安装或行为正确。

### 6.4 工具

工具用于实时数据或受控动作，至少包含输入输出 schema、风险、副作用、超时和权限。

可选实现：

- Codex 内置文件/shell 能力。
- 目标项目中的窄 Python CLI 适配器。
- 确有需要时的配置化 MCP。

公开 Python SDK 没有稳定动态工具注册 API；不使用 app-server experimental `dynamicTools`。工具发现、MCP 描述和 Skill 声明均不增加权限。

### 6.5 CLI / MCP / Plugin

- 需要人或 CI 重跑、调试、审计时生成 CLI。
- 需要让其他 Coding Agent 直接调用时提供 MCP。
- 需要嵌入 Codex、Claude Code 或 OpenCode 的产品体验时提供薄插件。
- 不需要所有目标系统都同时具备三种接口；由 ArchitectureSpec 按用户场景决定。

## 7. 构建、修改与验证闭环

```text
IntakeEnvelope
  → 工作区和已有 spec 快照
  → read-only Discovery / CodebaseProfile
  → source runtime 判定：reuse / new / migrate
  → ArchitectureSpec 新修订
  → ApplyProposal（build/edit/migrate/refactor）
  → 宿主规格与权限检查
  → apply + 外部用户授权（唯一目标写通道）
  → Codex workspace-write Build/Edit/Refactor
  → 宿主确定性检查
  → 独立 read-only Codex verifier（需要时）
  → 有界 diagnose → fix → rerun
  → OperationResult + VerificationReport + Evidence Manifest
```

### 7.1 工作包

每个工作包定义输入、输出 schema、依赖、验收、超时和重试。独立只读工作包可用 `AsyncCodex + asyncio` 并行；默认串行构建。

并行写入不是首版默认能力。确需并行写时，必须由宿主创建隔离 Git worktree、指定唯一集成者、检查冲突并重新运行完整验证；`thread_fork()` 不能替代 worktree。

### 7.2 上下文传递

- 同一角色连续工作：同一 Thread 多个 Turn。
- 不同角色：独立 Thread，只传必要 artifact。
- 其他 Agent、工具、宿主对话和外部文档：使用 `ExternalMessage`。
- 不把上游 raw outputs 全部隐式拼入下游。

### 7.3 有界修复

- 默认最多两次针对同一失败的修复。
- 修复必须针对最早失败边界：spec、Skill、工具、权限、代码、测试或验收器本身。
- 每次修复保存 diff 和原因，重跑原失败用例及相关回归。
- 仍失败则返回 `failed` 或 `blocked`，保留部分产物，不包装为成功。

### 7.4 验收顺序

1. 检查 Turn 状态、错误和非空输出。
2. 解析并验证结构化结果。
3. 检查要求产物存在、路径在范围内、schema 合法。
4. 实际执行声明的测试、import、CLI smoke 和最小 Codex smoke。
5. 检查命令真实运行、退出码、关键输出和覆盖范围。
6. 需要语义复核时，由独立 read-only verifier 检查证据。
7. 宿主合并所有结果，保留未覆盖项和不确定性。

最终状态至少区分 `passed / partial / failed / blocked`。关键工作包缺失、检查未运行、Turn interrupted/failed 或证据为空时不能 `passed`。

## 8. 对外 Harness 设计

### 8.1 统一 OperationResult

所有接口返回同一逻辑结果：

```text
status: completed | partial | failed | blocked | approval_required | outcome_unknown
operation / session_id / spec_revision / run_id
summary
changed_files[]
artifacts[]
checks[]: name、status、exit_code、evidence_ref
verification: not_run | passed | partial | failed | blocked
assumptions[] / unresolved[]
next_safe_action
usage / duration
```

MCP 返回 16 KiB 内的结构化摘要、检查状态统计和详情引用；完整 spec/check/run/events 使用 read 分页。Skill/插件只提供调用指导和展示。builder 从 0.3.0 起不再提供 CLI；生成工作流自身的 CLI 保留。

`completed` 只表示请求的操作已完成；是否经过验证必须另看 `verification`。build/apply 只有在必需检查通过后才可以声明“可运行、已验证”。

0.4.0 MCP 的公开 ApplyRequest 仅包含：

```text
proposal_id
idempotency_key
```

内部 ApplyRequest 仍携带 workspace、revision、snapshot 和 approval reference，由服务端在完整真人审批后绑定，宿主模型不得提供这些内部字段。

`approval_reference` 只关联审批证据，本身不证明真人批准；真实授权由宿主 tool policy 和 build-mas 服务端共同检查。

### 8.2 MCP 进程入口（0.4.0）

唯一 builder 进程入口是私有解释器执行 `python -m build_mas.mcp_server`，不接受操作子命令。bootstrap 仅安装环境，不承担工作流操作。`BUILD_MAS_HOME` 选择状态目录，`BUILD_MAS_MODEL` 可选模型，`BUILD_MAS_ALLOW_APPLY=1` 仅暴露审批后的应用工具，不授予批准。

Skill 引导宿主先预检、注册用户指定绝对目录，再将 goal、operation、inputs、session_id、idempotency_key 传给 `buildmas_invoke`。`auto` 或显式操作在同一个共享服务中路由，不复制架构/构建逻辑。大结果通过 `buildmas_read` 分页。

`buildmas_apply` 按页显示完整 diff，最后一页要求真人明确批准并绑定原提案 hash、revision、snapshot；中途拒绝、无 elicitation 或提案变化都不会写入目标。没有 `--yes`、终端审批或 Hook 绕过。身份登录走用户独占 URL elicitation；既有选定 provider 配置仍隔离继承。

### 8.3 MCP

工具集：

| Tool | 用途 | 副作用 |
|---|---|---|
| `buildmas_preflight` | 检查 builder、认证、状态目录和工作区 | 明确网络检查，不修改目标 |
| `buildmas_register` | 注册用户指定绝对项目路径并返回 workspace_id | 写私有注册记录，不修改项目文件 |
| `buildmas_import` | 导入用户选定附件，返回资产 ID | 私有资产副本和记录，复用路径/大小/秘密检查 |
| `buildmas_login` | URL elicitation 中由用户完成 SDK 登录 | 私有登录态，失败或拒绝取消，不把凭据输出给模型 |
| `buildmas_recover` | 核对原运行和快照，恢复保留候选 | 写私有恢复状态，不盲目重放目标写入 |
| `buildmas_invoke` | 通用 IntakeEnvelope + auto/显式操作 | 不写目标；可写内部 Session 并调用付费模型 |
| `buildmas_apply` | 应用指定 build/edit/migrate/refactor 提案 | 唯一目标写入口，要求 revision、snapshot、幂等键和授权 |
| `buildmas_verify` | 执行声明的测试和验证 | 可运行受限进程和写 artifacts，不改源码 |
| `buildmas_status` | 查询 session/run/preflight | 不调用模型，不修改目标 |
| `buildmas_read` | 有界读取 Spec、诊断、diff、验证报告 | Resources 不可用时的只读 fallback |

资源：

```text
buildmas://sessions/{session_id}/spec/{revision}
buildmas://runs/{run_id}
buildmas://artifacts/{artifact_id}
```

MCP 注解不是权限实现。analyze/plan 虽然不修改目标，但会写内部 Session 并产生模型调用，不能简单标为完全只读。`apply` 必须在 server policy 中显式开启，并由宿主客户端的用户审批和 build-mas 外部授权门共同放行；`invoke(auto)` 不能直接进入 apply。

Resources 只是可选优化，不能成为唯一读取方式。Codex 等未声明支持 MCP Resources 的宿主统一使用 `buildmas_status/read`；核心状态不依赖 MCP Tasks 或 subscriptions。基础实现使用本地 stdio，远程 HTTP 需要另行解决 OAuth、多租户和远程工作区。

### 8.4 Codex / Claude Code / OpenCode 插件

三类插件都复用同一 MCP server：

- manifest 只声明 Skill/MCP 和必要展示信息，不增加 Hook。
- Skill 只说明何时调用 `preflight/register/import/login/invoke/apply/verify/status/read/recover`、怎样传当前材料、怎样呈现 spec 和证据。
- 不在插件提示词中复制架构规则、DAG、验证器或修复逻辑。
- 插件安装、Skill 发现、MCP 可用和实际调用分别做 smoke test。
- 各宿主的审批 UI 只作为外部授权来源之一，不被解释为 Codex SDK 的人工审批 API。
- OpenCode 基础接入直接复用 MCP；只有确需宿主 UI 或权限集成时才增加 V2 薄插件，不维护第二套 JS 核心。

### 8.5 Builder 与 target runtime 的安装和预检

用户的目标项目没有 Codex SDK，不妨碍其使用 build-mas：

- build-mas 自身 Python 包显式声明 `openai-codex` 依赖，安装 MCP 服务时同时安装匹配的 Codex runtime；移除 builder CLI 不移除 SDK 依赖的 Codex 可执行 runtime。
- builder runtime 与目标项目环境分离；不能把目标项目尚未安装 SDK 当成无法运行 builder 的理由。
- 目标项目的新建/迁移由 build-mas 写入自己的 `pyproject.toml` 和锁定依赖，构建后在其隔离环境中验证。
- `buildmas_preflight` 检查 builder SDK、配套 runtime、账户可用性和目标 source runtime；只返回状态，不泄露凭据。
- SDK 或认证缺失时返回 `blocked/runtime_unavailable` 和明确修复路径，不能静默回退到宿主 Coding Agent 的模型或旧 Agent 框架。

## 9. 状态、证据和安全

### 9.1 工作区与运行状态

```text
$BUILD_MAS_HOME/
  workspaces/{workspace_id}/workspace.json
  sessions/{session_id}/session.json
  specs/{workspace_id}/{revision}.json
  runs/{run_id}/
    manifest.json
    events.jsonl
    artifacts/
    verification.json
```

`BUILD_MAS_HOME` 默认与目标仓库分离；只有用户明确要求时才把 spec 或报告导出到目标项目。`manifest` 至少记录：

- spec hash、workspace baseline、用户已有改动快照。
- 操作、proposal/apply ID、工作包状态、thread/turn ID、model/effort/sandbox。
- 输入输出 artifact、文件变更、命令、退出码、错误和重试。
- token usage、耗时、审批、最终状态和未覆盖项。

运行状态用临时文件写入后原子替换；spec revision 使用 compare-and-swap。过期 revision 返回 `stale_revision`，外部工作区变化返回 `workspace_conflict`。thread resume 只恢复 Codex 对话，build-mas 的 DAG 和验收状态以自有 manifest 为准。

### 9.2 权限分层

| 阶段 | Codex sandbox | ApprovalMode | 外部控制 |
|---|---|---|---|
| analyze/plan/diagnose | `read_only` | `deny_all` | 不写目标源码 |
| apply | `workspace_write` | `deny_all` | 准确 proposal、spec、路径、snapshot 和范围授权 |
| verify 语义复核 | `read_only` | `deny_all` | 独立 Thread |
| 部署、发送、commit/push | 不由核心执行 | 不适用 | 默认禁止，留给单独授权流程 |

`deny_all` 只拒绝权限升级，不禁止 sandbox 内操作。`auto_review` 不是人工审批，不能替代 build-mas 的外部用户授权。

### 9.3 确定性命令

- spec 保存逻辑检查类型，不让模型提供任意 shell 字符串。
- 宿主将 `unittest/pytest/import/cli-smoke/codex-smoke` 映射为受控 argv。
- 固定 cwd、timeout、输出上限和秘密清洗后的环境。
- 验证前解析路径和符号链接；拒绝越界路径、凭据文件和未声明命令。
- 测试进程与外部部署分离，超时不确定结果先查询状态，不盲目重试。

### 9.4 数据和信任

- 工作区文档、网页、trace、其他 Agent 输出均为非可信输入。
- 外部内容不能选择权限、扩大写路径或批准自己的动作。
- secrets 不写入 spec、trace、MCP resource 或最终报告。
- 用户已有 dirty changes 不清空、不回滚；最终 diff 必须检查无关变更和秘密。
- Run 状态包括 `queued/running/waiting_input/waiting_approval/succeeded/partial/failed/blocked/cancelled/outcome_unknown`；断连或崩溃后先核对工作区和 Codex turn，不盲目重放。

## 10. Codex SDK 使用约束

只允许导入公开 `openai_codex` 和 `openai_codex.types`。锁定发布 SDK 及其配套 runtime；自定义 `codex_bin` 必须单独做兼容验证。

| 场景 | SDK 用法 |
|---|---|
| 只读分析 | `Codex/AsyncCodex + thread_start(read_only, deny_all)` |
| 结构化 spec | `thread.run(..., output_schema=...)`，宿主再次验证 |
| 连续访谈/修复 | 同一 Thread 多个 `run()` |
| 独立角色 | 新 `thread_start()`，各自 instructions/model/sandbox |
| 独立只读并行 | `AsyncCodex` + 有界 `asyncio` |
| 非可信结果 | `ExternalMessage` 作为完整 input |
| 构建 | 授权后 `thread_start(workspace_write, deny_all)` |
| 进度/取消 | 需要时 `turn()` + `stream()/steer()/interrupt()` |
| 恢复对话 | `thread_resume()`，业务恢复仍读 RunState |
| 候选探索 | `thread_fork()`，不使用它模拟 Git worktree |
| Skill 显式加载 | 文本中的 `$<skill-name>` + `SkillInput`，另做发现和行为验证 |
| 观测 | 汇总 `TurnResult.items/usage/duration/status` |

不调用私有 `.client`、`.generated`、私有 goal 操作或 app-server experimental dynamicTools/subagents/hooks。`output_schema` 不替代业务校验，`interrupt()` 不回滚副作用。

## 11. 仓库与模块落地

```text
build-mas/
  pyproject.toml
  src/build_mas/
    contracts.py      # Envelope、Spec、Run、ApplyRequest、Result、错误
    service.py        # 所有接口共享的唯一应用服务
    router.py         # source_runtime + operation + effect 路由
    runtime.py        # 唯一允许 import openai_codex 的边界
    target.py         # 目标检测、局部修改和迁移实现
    preflight.py      # builder/target 检查
    store.py          # Session、revision、幂等和运行记录
    workspace.py      # 工作区、快照、锁和 artifacts
    verify.py         # 确定性检查、独立 verifier、证据汇总
    cli.py            # invoke/apply/plan/build/verify/status/doctor/serve
    mcp_server.py     # 薄 MCP 适配
  schemas/
    architecture-spec.schema.json
    operation-result.schema.json
    verification-report.schema.json
  adapters/
    codex/            # plugin.json + mcp.json + 薄 Skill
    claude-code/      # .claude-plugin + .mcp.json + 薄 Skill
    opencode/         # MCP 配置；按需增加 V2 薄插件
  examples/
    single_agent.py
    minimal_mas.py
  tests/
    unit/
    fixtures/
    integration/
    e2e/
  docs/
```

`service.py` 是所有接入层的唯一调用入口，`runtime.py` 是唯一 Codex SDK 适配边界。概念组件不等于继续增加框架层；DAG、policy 和 CLI 不为“未来扩展”另建抽象。

现有 `skills/build-mas/SKILL.md` 迁移为 Codex 接入层的薄使用说明；核心规则进入版本化 contracts、references 和可执行代码。现有 `minimal_mas.py` 保留为有界双角色示例，不再承担产品主入口。现有 Codex manifest 迁入 `adapters/codex/` 时，必须同步更新 `.agents/plugins/marketplace.json` 的 source path 并验证旧安装迁移。

## 12. 测试与评测体系

### 12.1 单元与合同测试

- Intake 各输入类型、session 复用、操作路由和 read-only 请求不写入。
- invoke(auto) 不产生目标修改；apply 的 proposal、snapshot、幂等和过期拒绝。
- spec schema、未知引用、循环依赖、缺失验收、非法 sandbox、越权工具。
- spec hash、工作区 baseline、过期授权、dirty worktree 和路径逃逸。
- DAG join、条件、重试、部分失败、超时、取消和恢复。
- FakeCodex 的 completed/failed/interrupted/malformed/empty evidence。
- MCP/CLI 参数、结构化输出、退出码和副作用门。

### 12.2 真实 SDK 集成测试

- 发布 SDK 与固定 runtime、登录、关闭、model 可用性。
- `read_only/workspace_write + deny_all` 的实际行为。
- `output_schema`、SkillInput、ExternalMessage、resume/fork/ephemeral。
- 多 Thread 并行、steer/interrupt、usage、compact。
- 验证真实文件和进程状态，不只检查 SDK 返回文本。

### 12.3 端到端产品用例

1. 一句话目标生成单 Agent + CLI 的可运行 workflow。
2. 从文档和架构图生成带 Skill 的单 Agent 系统。
3. 改造已有 Codex 项目，保持公共合同并增加工具或验证。
4. 简单任务保持单 Agent，不制造 MAS。
5. 独立资料簇确需并行时生成有界 worker + verifier。
6. 根据测试失败完成 diagnose → edit → rerun。
7. 将不必要 MAS 重构为单 Thread，并证明回归通过。
8. 通过 CLI、MCP 和三类宿主插件调用同一 fixture，结果合同一致；Resources 不可用时 read fallback 完整。
9. 跨多次调用延续 session，后续编辑使用最新 spec 和已有证据。
10. 将其他 Agent 框架 fixture 迁移为 Codex SDK，验证输入输出、错误、权限和副作用对等，并移除旧 runtime。
11. 对已是 Codex SDK 的 fixture 执行局部调整，证明没有发生不必要重建。
12. 在目标项目未预装 SDK 的环境中，由 builder 自带 runtime 完成迁移，并在目标隔离环境安装后验证。

### 12.4 对抗与假成功

- repo/网页/trace 中的 prompt injection 和伪造授权。
- `.env`、token、私钥、路径逃逸和未声明网络访问。
- 空证据、伪造 passed、未运行测试、非法 verdict、部分工作包失败。
- stale spec、过期审批、并发写冲突、晚到结果和重复执行。
- MCP 客户端未批准时，build 不得写入。
- MCP 客户端未批准时，apply 不得写入；断开后的 `outcome_unknown` 不得当成失败或成功盲重试。

### 12.5 架构收益评测

同任务比较：

- 直接使用单 Codex Thread。
- build-mas 生成的单 Agent 系统。
- 简单并行 workers。
- workers + independent verifier。

同时衡量任务成功率、证据质量、token、延迟、失败率和人工介入。调参集、验证集和最终 holdout 分离；只有独立分工或独立验收有实际收益时才允许多 Agent 成为推荐架构。

## 13. 无排期的实施顺序与完成门

### A. 合同与内核骨架

交付：IntakeEnvelope、OperationRouter、ArchitectureSpec、RunState、OperationResult、CLI `invoke/apply/status/doctor`、公开 SDK 白名单检查。

完成门：任意输入能形成可审计请求；invoke/review 不写目标；apply 拒绝过期提案和冲突工作区；非法 spec 在执行前失败。

### B. 单 Agent 新建与验证闭环

交付：Discovery、spec 生成、workspace-write build、确定性检查、CLI `plan/build/verify`、证据 manifest。

完成门：空目录生成单 Agent Codex SDK 项目，真实 CLI 和最小 Codex smoke 通过，失败不能报成功。

### C. 已有项目编辑、诊断与重构

交付：CodebaseProfile、source runtime 路由、最小变更、非 Codex 迁移、spec 修订、两次内有界修复、session 续用。

完成门：Codex fixture 保持公共合同完成 edit/refactor；非 Codex fixture 通过对等迁移验证并移除旧 runtime；用户已有改动不受影响；回归证据绑定准确修订。

### D. 有界 MAS 与 Skills/工具规划

交付：多 Thread DAG、ExternalMessage、独立 verifier、Skill 生命周期检查、工具注册表。

完成门：并行/verifier 在对照评测中有收益；部分失败、恶意 handoff 和假成功均安全终止。

### E. MCP 与多宿主插件

交付：MCP tools/read fallback、可选 resources、Codex/Claude Code/OpenCode 薄插件、宿主审批和安装说明。

完成门：同一 fixture 经 CLI、MCP 和三类插件调用得到一致 spec 与验证结果；未批准 build 无法写入；安装和 Skill/MCP 加载经真实客户端验证。

### F. 评测与演进

交付：端到端任务集、对抗集、对照实验、失败到回归的溯源、候选 Skill 晋升规则。

完成门：公开示例之外的 holdout 证明构建成功率和架构选择；每次自动修复都有 diff、重跑证据和回退路径。

## 14. 从参考项目整合的最终清单

| 来源 | 吸收 | 不吸收 |
|---|---|---|
| harness | 新建/扩展/维护、控制流决策、Agent/Skill 分工、Skill eval、反馈回归 | Claude runtime、模板即实现、团队优先、无限循环 |
| CrewAI | 声明式 spec、工作包、显式 DAG、工具合同、CLI 和运行事件 | 三层编排、manager 自由委托、隐式上下文、多 provider 和统一 Memory |
| Cresta | 可审批 Blueprint、Prompt/代码分工、诊断修复闭环、证据和 CLI 契约 | CX 专用平台、未验证热重载/发布承诺、生成者自测 |
| claude-code-setup | 环境检测、限量可解释建议、机制分工、最小权限 | 只读推荐终点、Claude 配置和 Hook 语法 |
| Codex SDK | Thread/Turn、结构化输出、沙箱、ExternalMessage、SkillInput、异步原语和 usage | 虚构 MAS API、实验 app-server 依赖、auto_review 当人工审批 |

最终要建设的不是这些项目的合集，而是一个以 **ArchitectureSpec、OperationRouter、Codex Threads、宿主控制面和证据验收**为核心的新产品。

无论用户从空白项目、简单自实现、其他 MAS 还是已有 Codex SDK 项目进入，最终目标都统一为可运行、可验证的 Codex SDK 系统；差别只在复用、局部修改或迁移重建路径。
