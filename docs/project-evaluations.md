# codexwright 参考项目实现评估

评估日期：2026-11-08。

本文回答两个问题：这些项目实际上怎样工作；其中哪些机制值得进入 codexwright。目标不是选出另一个运行时，而是为 codexwright 形成一套可落地的架构与构建方法。

## 0. 目标、证据和边界

codexwright 的目标定位为：用户提供目标或已有实现，系统决定 Agent 划分、Skills、工具、CLI 与必要控制机制，并把决策落实为可运行、可验证的 Agentic workflow。

最新约束：

- 构建内核和生成的目标 workflow 只使用 Codex Python SDK 与宿主 Python，不引入 CrewAI、Claude Agent SDK 等其他 Agent runtime。
- codexwright 的产品形态不限于 Skill。独立 CLI、MCP、Codex / Claude Code / OpenCode 插件均可成为对外 Harness。
- 多种接入层共享同一构建内核；从其他客户端调用时，也不把架构决策或执行转交给该客户端的模型 runtime。
- 用户目标项目可能没有 Codex SDK 或使用其他 Agent 框架，本期统一新建/迁移为 Codex SDK；目标已经使用 Codex SDK 时才复用并局部修改。builder 自带所需 SDK，不依赖目标项目预装。

证据分为三类：

- **源码事实**：固定提交中的代码、配置、测试和目录结构。
- **公开声明**：官方文章或媒体描述的产品机制，不等于独立技术验证。
- **设计判断**：基于证据提出的 codexwright 方案，不冒充原项目已有能力。

固定研究基线：

| 项目 | 基线 | 证据范围 |
|---|---|---|
| revfactory/harness | `main@92d9f1b29e7af81acebf51a9fcd1832e739a1414`，插件版本 2.1.0 | Skill、模板、manifest、文档；无独立运行时代码 |
| CrewAI | `main@2fba413623a60d7a2f24a7d21685bbcd8dd45a4f`，版本 1.15.37 | Crew、Flow、AgentExecutor、工具、CLI、测试与 CI |
| Cresta Conductor | 2026-06-11 官方文章及后续官方材料；CMSWire 2026-10-30 报道 | 公开产品机制，无可审计 Conductor 源码 |
| claude-code-setup | `main@0412be76f50ab4f4f8abff3753efa9269fbbca5b`，插件版本 1.0.0 | 一个 Skill、五份 references、manifest、README |
| Codex Python SDK | `main@748ab55ca7de0b647d9a7a9d9a8e70e00f28666d` | 公开导出、API 文档、源码、示例、测试及官方 SDK 文档 |

## 1. revfactory/harness

### 1.1 实际实现逻辑

harness 不是 Python/TypeScript Agent 框架，也不是独立 CLI。它是一套 Claude Code 元 Skill、Markdown 模板和插件配置，核心为 `harness` 与 `evolve` 两个 Skill。

```text
一句话目标或现有 .claude 配置
  → 检查新建 / 扩展 / 维护意图
  → 分析领域、代码库和任务流
  → 选择 Workflow / 持久 Agent / 子 Agent
  → 选择 Pipeline、Fan-out、Expert Pool、Producer-Reviewer 等结构
  → 生成 Agent、Skill、编排 Skill、CLAUDE.md
  → 文件检查、Skill 触发测试、With/Without 对比、模拟执行
  → evolve 根据反馈做单项修改并复测
```

关键源码证据：

- [SKILL.md:21-52](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/harness/SKILL.md#L21-L52) 先审计现状，再进入新建、扩展或维护路径。
- [SKILL.md:54-96](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/harness/SKILL.md#L54-L96) 根据控制流选择执行模式，而不是直接按人数组队。
- [execution-modes.md:116-140](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/harness/references/execution-modes.md#L116-L140) 给出 Workflow、持久协作和一次性委托的决策树。
- [orchestrator-template.md:41-50](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/harness/references/orchestrator-template.md#L41-L50) 用 `_workspace`、`run_meta.json` 和 `resumeFromRunId` 描述恢复约定。
- [SKILL.md:312-355](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/harness/SKILL.md#L312-L355) 覆盖结构、引用、数据流、Skill 触发和 A/B 验证。
- [evolve/SKILL.md:54-89](https://github.com/revfactory/harness/blob/92d9f1b29e7af81acebf51a9fcd1832e739a1414/skills/evolve/SKILL.md#L54-L89) 要求反馈泛化、一次修改一项、保留原因并复测。

### 1.2 实现边界

- 仓库没有独立 `.py`、`.js`、`.ts`、`.sh` 可执行实现；Workflow 和 JavaScript 仅存在于 Markdown 示例。
- 没有自动测试、依赖清单或 CI。文档中的恢复、自动迁移、端到端生成和 A/B 效果没有本次运行证据。
- `_workspace`、hash 和 `run_meta.json` 是状态约定，不是带锁、原子提交、冲突解决和崩溃恢复的状态系统。
- v1 的作者测量不能证明当前 v2 的质量；提示词要求“盲评”也不等于访问隔离或独立 holdout。

### 1.3 应吸收的机制

1. **新建、扩展、维护三分入口**：与 codexwright 接受目标或已有实现高度一致。
2. **按控制流选择编排**：能写成代码的顺序、并行和循环由宿主控制；独立上下文或独立验收才引入新 Agent。
3. **Agent、Skill、编排职责分离**：Agent 决定谁执行，Skill 提供可复用方法，宿主编排决定数据流和完成条件。
4. **生产者与消费者联合验收**：检查跨 Agent handoff、CLI 输入输出和文件 schema 的两侧契约。
5. **Skill 触发与质量评测**：should-trigger、near-miss、With/Without、正常/失败路径、耗时和 token 都应进入 codexwright 测试体系。
6. **反馈形成回归**：一次只改一个变量，保留原因并复测，不把单次反馈直接堆成新提示词。

### 1.4 不应照搬

- 不复制 Claude 的 `.claude/agents`、`CLAUDE.md`、`Workflow`、`SendMessage`、`resumeFromRunId` 等运行时概念。
- 不采用团队优先的默认定位。单 Agent、单 Skill、无持久状态必须是正常结果。
- 不引入默认评委团、无限 Loop-until-dry 或失败后继续仍报完整成功。
- 不把 Markdown 模板、hash 冻结或模型 verdict 当成构建器、并发控制或最终验收。
- 不自动应用“演进”结果；候选修改需要独立回归和用户授权。

### 1.5 对 codexwright 的结论

harness 是四个参考项目中最接近 codexwright **构建方法论**的项目，但它不是可执行构建器。codexwright 应把其流程升级为版本化 `ArchitectureSpec`、真实工作包状态、宿主机械检查和可重放构建证据。

## 2. CrewAI

### 2.1 Crew 的真实调用链

```text
agents.yaml / tasks.yaml / Python 对象
  → @CrewBase 解析 Agent、Task、Tool 和输出模型引用
  → @crew 实例化 Crew
  → Crew.kickoff() / prepare_kickoff()
  → sequential 或 hierarchical Process
  → Crew._execute_tasks()
  → Task.execute_sync()/execute_async()
  → Agent.execute_task()
  → AgentExecutor.invoke()
  → 内部 Flow：plan、LLM、工具、观察、重规划、最终回答
  → TaskOutput、guardrail 与有限重试
  → CrewOutput、事件及 memory 后台写入
```

关键源码证据：

- [crew.py:1006](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/crew.py#L1006) 是 Crew 执行入口；Process 仅分 sequential 和 hierarchical。
- [crew.py:1586](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/crew.py#L1586) 负责任务循环、异步汇合和上下文传递。
- [agent_executor.py:203](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/agents/agent_executor.py#L203) 表明 AgentExecutor 自身也是 Flow。
- [task.py:1423](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/task.py#L1423) 实现 guardrail 失败后的有限重试。
- Crew 默认聚合之前的 raw output；最终结果取最后一个有效 Task 输出，不等于独立系统验收。

### 2.2 Flow 的真实调用链

```text
@start/@listen/@router 或 flow.yaml
  → FlowDefinition
  → Flow.kickoff()/kickoff_async()
  → 恢复状态、处理输入、执行 hooks
  → start methods 并行执行
  → 方法完成、输出与状态保存
  → router 顺序选择后续标签
  → listeners 并行 gather
  → 条件、循环、human feedback 或最终输出
```

- [flow_definition.py:653](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/flow/flow_definition.py#L653) 定义声明式 action 和路由规格。
- [runtime/__init__.py:2116](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/flow/runtime/__init__.py#L2116) 是同步/异步入口。
- [runtime/__init__.py:2924](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/flow/runtime/__init__.py#L2924) 处理方法执行、持久化和事件。
- [structured_tool.py:356](https://github.com/crewaiinc/crewai/blob/2fba413623a60d7a2f24a7d21685bbcd8dd45a4f/lib/crewai/src/crewai/tools/structured_tool.py#L356) 负责工具参数验证和调用。
- Flow 支持 CEL 和显式启用的 inline Python；后者源码明确说明不沙箱，不能进入 codexwright 默认路径。

### 2.3 应吸收的机制

1. **声明式规格**：用统一 `ArchitectureSpec` 描述 Agent、工作包、依赖、输出、权限和验证，先验证规格再生成代码。
2. **有界工作包**：每个 packet 具有 `id/objective/inputs/depends_on/output_schema/acceptance/budget`。
3. **显式控制平面**：保留依赖、条件、并行、join、retry、pause/resume、verify，不复制完整 Flow 框架。
4. **工具契约**：名称、输入输出 schema、风险、副作用、超时和实现引用必须明确；工具声明不授予权限。
5. **结构化规划**：planner 只提出 typed plan，宿主验证依赖、权限和验收，重规划产生新修订。
6. **输出后验证与有界修复**：失败反馈可送回构建者，但最终状态由真实测试和证据决定。
7. **CLI 闭环**：参考 create/run/test 的操作入口，但生成内容必须来自用户目标和仓库分析，而非固定 researcher/writer 模板。

### 2.4 不应照搬

- 不复制 `Flow → Crew → AgentExecutor Flow` 三层嵌套；codexwright 只保留“宿主工作流 + Codex 内层 Agent loop”两层。
- 不采用 manager 自由委托和隐式历史 raw output 拼接；路由由宿主校验，上游结果以显式 artifact 或 `ExternalMessage` 传递。
- 不复制多 provider LLM 抽象、统一 Memory、向量库、全局 singleton event bus、CEL、inline Python 和多套持久化机制。
- 不让最终 Task 输出或 LLM 评分自动等于构建成功。
- 不复制 CrewAI BaseTool/CrewStructuredTool 双重包装和静态脚手架。

### 2.5 测试证据与缺口

- 核心包和 CLI 有大量测试，CI 分片并使用 `--block-network` 与 VCR cassettes；Flow、guardrail、工具、事件和恢复均有专项覆盖。
- 本次只读审查未安装大型依赖集合，也未执行其完整测试、真实 LLM 或 CLI，因此不为当前 SHA 的全绿或生产稳定性背书。
- 文档中的 `crewai test` 默认次数和模型与当前代码存在漂移，进一步说明应以固定源码为准。

### 2.6 对 codexwright 的结论

CrewAI 的主要价值是**规格化、显式 Flow、工具契约和运行事件**。codexwright 只需要一个小型 DAG/状态机，不需要另一个 Agent runtime。

## 3. Cresta Conductor

### 3.1 证据口径

Cresta 没有公开 Conductor 的可审计源码。本节能确认的是官方公开产品流程，不能确认其规划循环、拓扑算法、热重载、根因定位准确率、RBAC、Secrets 或 rollback 的内部实现。

主要材料：

- [Conductor: The Agent for AI Agent Development](https://cresta.com/blog/cresta-conductor-the-agent-for-ai-agent-development)，2026-06-11。
- [End-to-End Self-Serve Model](https://cresta.com/blog/crestas-ai-agent-expertise-in-developers-hands-introducing-our-end-to-end-self-serve-model)，2026-10-29。
- [Cresta CLI](https://cresta.com/blog/introducing-the-cresta-cli-a-developer-surface-for-an-agent-operable-platform)，2026-08-27。
- [AI Agent Testing 2.0](https://cresta.com/blog/introducing-ai-agent-testing-2-0-confidence-at-launch-confidence-at-scale)，2026-06-04。
- [CMSWire 报道](https://www.cmswire.com/contact-center/cresta-opens-agent-platform-to-developer-selfservice/)，2026-10-30。

### 3.2 公开产品逻辑

```text
知识库、SOP、API、历史对话、升级规则
  → 追问范围、成功标准、受众和确定性边界
  → 可审查 Blueprint
  → 用户批准
  → Prompt、子 Agent 编排、工具、集成和自定义代码
  → 业务测试与模拟
  → 跨 Blueprint / Prompt / 工具 / 配置 / 代码定位根因
  → 修复并重跑
  → Git / PR / CI/CD / 受控发布
  → 生产信号进入下一轮回归
```

公开材料强调五个关键机制：

1. **Blueprint 是跨阶段单一事实源**：目标、范围、流程、测试和知识引用在写代码前接受审查。
2. **Prompt 与确定性代码分工**：账户查询、资格判断、记录更新等动作由代码承担。
3. **test → fail → diagnose → fix → rerun**：失败映射到具体层，修复后重跑，而非只重新生成。
4. **混合评估**：确定性评估器处理精确条件，LLM 评估器处理语义质量，并用人工标注校准。
5. **CLI 与修订证据**：结构化输出、退出码、稳定资源 ID、测试绑定修订，发布仍走 Git 和审批。

媒体所述“5x faster”等数字是厂商或客户案例声明，缺少任务样本、基线、统计方法和独立复现，不能转化为 codexwright 的收益承诺。

### 3.3 应吸收的机制

- 统一、版本化、可审批的 `ArchitectureSpec`，后续实现、测试、修复和验收都引用同一修订。
- 构建前记录事实、推断和缺失信息，只追问会阻塞安全下一步的问题。
- 调度、权限、结构化校验和最终验收由宿主代码负责，模型负责分析、生成和语义诊断。
- 保存 `来源证据 → 失败 → 根因 → 修复修订 → 回归测试 → 验证结果`。
- CLI 提供机器可读输出、稳定资源 ID、明确退出码和下一步提示；大 trace 落盘。
- 只有通过审查和回归的修复模式才沉淀为共享 Skill。

### 3.4 不应照搬

- 不复制 CX 专用的历史会话挖掘、Synthetic Customers、语音测试、CSAT 或完整联络中心平台。
- 不默认从自然语言直接生成多 Agent，不接受生成者自测即通过。
- 不把自动修复直接上线，不承诺通用热重载、渐进发布或 rollback。
- 不沿用其 Claude Agent SDK 实现栈。

### 3.5 对 codexwright 的结论

Cresta 最值得吸收的是**Blueprint 驱动的完整生命周期和证据闭环**，而不是 CX 功能或营销形式。其公开材料无法替代 codexwright 自己在规格、CLI、权限、测试和真实构建评测上的实现。

## 4. anthropics/claude-code-setup

### 4.1 实际实现逻辑

该插件是一个只读 Claude Code 自动化推荐器，没有 scripts、agents、commands、hooks 或测试实现。

```text
用户提出 Claude Code 配置或自动化需求
  → 宿主根据 description 加载 Skill
  → 模型按示例命令检测项目技术栈和 .claude 配置
  → 将信号映射到 MCP / Skills / Hooks / Subagents / Plugins
  → 按需读取 references
  → 每类输出 1–2 个限量建议及 Why / Install / Where / Invocation
  → 结束；用户另行要求实施
```

关键源码证据：

- [SKILL.md:1-17](https://github.com/anthropics/claude-plugins-official/blob/0412be76f50ab4f4f8abff3753efa9269fbbca5b/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md#L1-L17) 声明触发方式、工具和只读边界。
- [SKILL.md:32-63](https://github.com/anthropics/claude-plugins-official/blob/0412be76f50ab4f4f8abff3753efa9269fbbca5b/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md#L32-L63) 给出环境检测信号。
- [SKILL.md:153-212](https://github.com/anthropics/claude-plugins-official/blob/0412be76f50ab4f4f8abff3753efa9269fbbca5b/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md#L153-L212) 定义推荐报告。
- [SKILL.md:217-251](https://github.com/anthropics/claude-plugins-official/blob/0412be76f50ab4f4f8abff3753efa9269fbbca5b/plugins/claude-code-setup/skills/claude-automation-recommender/SKILL.md#L217-L251) 区分 MCP、Skill、Hook、Subagent 和 Plugin 的适用场景。
- [subagent-templates.md:151](https://github.com/anthropics/claude-plugins-official/blob/0412be76f50ab4f4f8abff3753efa9269fbbca5b/plugins/claude-code-setup/skills/claude-automation-recommender/references/subagent-templates.md#L151) 起是角色与工具权限模板，不是插件自身 Agent。

### 4.2 应吸收的机制

1. **环境证据驱动**：先形成 CodebaseProfile，再决定需要哪些机制。
2. **限量、可解释建议**：每项决策说明 Why，避免把所有可用框架和工具堆给用户。
3. **按机制分工**：重复流程归 Skill，外部能力归工具，确定性检查归脚本/宿主，独立上下文审查才考虑 Agent。
4. **最小权限角色**：审查只读，构建才可写，执行命令另设权限。
5. **验证靠近产物**：生成 Skill、工具或 workflow 时同时生成运行入口和验收检查。

### 4.3 不应照搬

- 不复制 `.claude`、`CLAUDE.md`、Claude Hook frontmatter、`context: fork`、`$ARGUMENTS` 和 Claude CLI 语法。
- 不把“代码库超过 500 文件”等单一规模信号当成新增 Agent 的充分理由。
- 不停留在只读建议；codexwright 必须继续完成规格、落地和验证。
- 不把 references 中的示例脚本当成可靠验证器；例如某些示例可能把失败命令转成文本后继续成功退出。

### 4.4 对 codexwright 的结论

它适合作为**环境检测和能力类型选择**的参考，不是 Agent 系统构建器。codexwright 应将其推荐链扩展为 `Evidence → ArchitectureSpec → Build → Run → Verification`。

## 5. Codex Python SDK 专项：能做什么，不能做什么

### 5.1 实际运行架构

官方 Python SDK 是嵌入 Python 应用的本地 Codex 控制库。发布包要求 Python 3.10+，自动安装匹配的 Codex CLI runtime；SDK 启动该 runtime 的 app-server，并通过 stdio JSON-RPC 通信。

```text
codexwright Python 宿主
  ├─ 接入层、操作路由、ArchitectureSpec、DAG、状态、权限、CLI、验证
  ├─ Codex / AsyncCodex
  │    └─ 随包 Codex CLI → codex app-server --listen stdio://
  ├─ Thread A：分析 / 架构
  ├─ Thread B：构建
  ├─ Thread C：独立验证
  └─ Turn 通知按 turn ID 路由，最终聚合为 TurnResult
```

官方定位：[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)、[固定 API Reference](https://github.com/openai/codex/blob/748ab55ca7de0b647d9a7a9d9a8e70e00f28666d/sdk/python/docs/api-reference.md)。

`Thread.run()` 是普通执行的便捷入口；需要进度、纠偏或中断时使用 `thread.turn()`，再调用 `stream()`、`steer()`、`interrupt()`。`TurnResult` 包含状态、错误、最终文本、items、耗时和 usage，不只是模型文本。

### 5.2 公开 SDK 能力矩阵

| 能力 | 公开 API | codexwright 用途 | 不能误解为 |
|---|---|---|---|
| 生命周期 | `Codex` / `AsyncCodex` | 同步构建、异步并行只读工作包 | 自动任务调度器 |
| 会话 | `thread_start/resume/fork/list/read/archive` | 角色隔离、连续访谈、候选修订 | 业务工作流数据库；fork 也不是 Git worktree |
| 执行 | `run()`、`turn()` | 执行一个或多个角色 Turn | 高层 Crew/Flow API |
| 活动控制 | `stream()`、`steer()`、`interrupt()` | 进度、纠偏、取消 | 中断后自动回滚副作用 |
| 结构化输出 | `output_schema`、`TurnResult` | 输出 ArchitectureSpec 和角色结果 | 业务正确性或验收通过 |
| 多模态输入 | `TextInput`、`ImageInput`、`LocalImageInput` | 文本、截图、架构图和本地材料 | 原生音频/视频输入或任意文件自动理解 |
| Skill 输入 | 文本 `$<skill-name>` + `SkillInput(name, path)` | 在指定 Turn 显式注入选定 Skill | 安装、发现、启用或验证 Skill |
| 资源引用 | `MentionInput(name, path)` | 附加资源引用 | 已验证支持所有资源类型 |
| 非可信输入 | `ExternalMessage` | 其他 Agent、工具和宿主上下文降权传递 | 用户授权、身份认证或双向 Agent 协议 |
| 文件权限 | `Sandbox.read_only/workspace_write/full_access` | 分析只读、构建限工作区 | 完整秘密、网络和外部副作用治理 |
| 审批模式 | `ApprovalMode.deny_all/auto_review` | 禁止升级或自动审查 | 人工审批；默认 auto_review 不是用户确认 |
| 模型配置 | `models()`、`model`、`effort`、`config` | 角色模型和推理配置 | 跨 provider 抽象或固定账号可用性 |
| 登录 | ChatGPT、device code、API key、account/logout | 初始化与账户检查 | 完整密钥管理产品 |
| 重试 | typed errors、`retry_on_overload` | 临时 overload 退避 | 所有构建节点都可安全重试 |
| 临时会话 | `ephemeral=True` | 一次性分析或实验 | 退出后还能 resume/list |
| 压缩 | `thread.compact()` | 长会话压缩 | 返回即表示压缩已完成 |
| 审计数据 | `items`、usage、duration、thread/turn ID | 宿主证据账本 | 自动跨工作包成本与验收账本 |

公开输入和类型以 [`openai_codex.__init__`](https://github.com/openai/codex/blob/748ab55ca7de0b647d9a7a9d9a8e70e00f28666d/sdk/python/src/openai_codex/__init__.py#L57-L95) 与 `openai_codex.types` 为边界。官方示例测试明确限制 examples 使用私有 `.client`、`.generated` 等模块；codexwright 应采用同样约束。

### 5.3 多 Agent 的真实实现方式

SDK 没有稳定的 `create_agent()`、`spawn_agent()`、`register_tool()`、`install_skill()`、`create_worktree()`、Crew、Flow 或通用 MAS API。

正确组合方式：

```text
ArchitectureSpec
  → 每个确有必要的新角色一个独立 Thread
  → 各自配置 instructions、model、effort、cwd、sandbox
  → Thread.run() 顺序执行，或 AsyncCodex + asyncio 执行独立工作包
  → output_schema 返回角色结果
  → 宿主验证、路由依赖、控制并发和汇总
  → 跨角色结果通过 ExternalMessage 降权传递
  → 独立 read_only verifier + 宿主机械检查
```

`AsyncCodex` 提供异步原语，不负责 DAG、共享状态、并发上限、总预算、失败传播和集成。`thread_resume()` 恢复对话上下文，不是工作流步骤重放；`thread_fork()` 不复制 Git 工作区。

### 5.4 必须由 codexwright 自己实现

- 任意阶段和任意材料形式的 Intake、访谈、操作路由与 ArchitectureSpec。
- 单 Agent 基线、Agent 拓扑、工作包 DAG、重试、幂等、检查点、总预算和恢复。
- 工具注册表、风险分类、参数 schema、CLI 适配器和权限决策。
- Skill 的生成、安装/发现、显式加载和行为验证。
- CLI/MCP/UI、用户审批、进度展示、worktree、测试执行和证据报告。
- Secrets、脱敏、数据出域、定时和事件触发。

### 5.5 SDK、Codex 客户端与 app-server 的区别

| 维度 | Python SDK | Codex CLI / Desktop / IDE | app-server |
|---|---|---|---|
| 定位 | 嵌入 Python 的控制库 | 面向人的完整交互产品 | 自定义富客户端的底层 JSON-RPC |
| UI | 无，宿主实现 | TUI、桌面 GUI、编辑器面板 | 无现成 UI |
| 编排 | Thread/Turn 原语 | 会话、原生 subagents、云交接 | 更丰富协议和实验能力 |
| Skills | `SkillInput` 显式注入 | 发现、安装、选择、管理 | skills/list、配置和通知等 RPC |
| 审批 | `deny_all/auto_review` | 人工提示、权限选择、auto-review UI | 审批请求/响应和实验人工 checkpoint |
| Worktree | 无公开 API | Desktop managed worktree / Handoff | 不应据此假设 Python 有封装 |
| 自动化 | 宿主自行实现 | Desktop/Web Scheduled 等产品体验 | 不是完整调度产品 |
| codexwright 用法 | **唯一 Agent 构建依赖** | 可选接入和人工验收界面 | 不直接依赖其实验 API |

以下能力不能从客户端或 app-server 反推为公开 Python SDK 能力：

- `dynamicTools`、原生 subagent 管理、skills/hooks/plugin 管理 RPC。
- managed worktree、Scheduled tasks、IDE selection、桌面文件产物和通知 UI。
- 公开人工审批 handler 或 `ApprovalMode.human`。
- 根据 generated schema 或私有 goal 操作推断出的高级生命周期 API。

官方分层参考：[App Server](https://learn.chatgpt.com/docs/app-server)、[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)、[Plugin packaging](https://developers.openai.com/plugins/build/plugins)。

### 5.6 对落地有直接影响的安全事实

1. **显式设置权限**：新 Thread 默认 `auto_review`，不是人工审批。codexwright 的分析和验证使用 `read_only + deny_all`；构建只在获得外部授权后使用 `workspace_write + deny_all`。
2. **deny_all 不是禁止所有操作**：它拒绝权限升级，sandbox 内已允许的操作仍可执行，因此外部入口仍需区分 plan、build 和 verify。
3. **公开 Python 层没有人工审批 UI**：人工确认由 codexwright 自己的 CLI/MCP/插件接入层完成，不依赖私有 `CodexClient.approval_handler`。
4. **完成不等于成功**：`TurnStatus.completed`、合法 JSON、模型 verdict 都不能替代测试、文件检查、退出码和证据。
5. **副作用不能靠 interrupt 回滚**：中断后仍需检查文件和外部状态。
6. **版本必须配对**：官方网页、main 源码和实际 PyPI 固定 runtime 可能存在版本差，应锁定发布 SDK 及其配套 runtime，不能混用任意本机 Codex。

### 5.7 仍需真实集成验证

- 发布 SDK 与固定 runtime、登录、账户和关闭行为。
- `deny_all` 在只读、工作区写入、网络和越界访问下的真实行为。
- resume/fork/ephemeral、parallel turns、steer/interrupt 和 compact 的状态一致性。
- 严格 schema、malformed 输出、failed/interrupted、usage 汇总。
- Skill 从生成到发现、显式注入和行为验证的完整链路。
- ExternalMessage 启动/加入 Turn 及伪造来源不提权。
- 宿主 DAG、部分失败、超时、幂等、总预算、恢复和假成功拒绝。

本次为固定源码和官方文档的静态审查，未运行真实账号、模型、审批或端到端构建。上述项目必须通过 codexwright 自己的真实集成测试，不能由参考项目测试代替。

## 6. 多 Harness 接入专项：CLI、MCP 与三类宿主插件

### 6.1 推荐服务形态

```text
独立 Python builder runtime
  ├─ CLI / MCP 两个基础入口
  ├─ Codex 薄接入包
  ├─ Claude Code 薄接入包
  └─ OpenCode 薄接入包或直接 MCP 配置
        ↓
同一 IntakeEnvelope / OperationRouter / ArchitectureSpec / VerificationReport
        ↓
公开 Codex Python SDK
```

builder 与 target 必须分离：builder 自己的隔离环境声明 `openai-codex` 和匹配 runtime；目标项目可以没有 SDK 或使用其他框架。插件首次 setup 只安装固定 codexwright 分发包到插件数据目录，不依赖目标仓库 venv，也不在每次调用时临时联网安装。

官方 SDK 依据：[Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)。

### 6.2 通用调用与写操作必须分开

用户可以在任意阶段以任意材料调用，但通用 `invoke(auto)` 只产生分析、诊断、SpecRevision 或 ApplyProposal，不直接修改目标工作区。`apply` 是唯一目标写入口。

```text
invoke: analyze / plan / build / edit / diagnose / migrate / refactor
  → 结构化结果或 ApplyProposal
apply: expected spec revision + workspace snapshot + proposal ID + idempotency key
  → 经外部授权后修改目标
verify: 执行声明的机械检查和独立 verifier
```

这保留了非线性使用方式，同时防止 auto 路由或宿主模型误判直接获得写权限。`unknown source_runtime + auto` 不得进入 apply。

### 6.3 各接入机制的真实边界

| 接入 | 官方机制 | codexwright 用法 | 主要限制 |
|---|---|---|---|
| Python CLI | PyPA `[project.scripts]` | CI、调试、脚本化、其他适配器的 canonical 入口 | 宿主 shell 审批不替代内核路径和命令控制 |
| MCP stdio | 宿主启动本地子进程，tools 结构化调用 | 多宿主共享同一 service | MCP 不是工作流状态机、沙箱或人工审批保证 |
| MCP HTTP | 独立远程服务 | 只有明确需要远程服务时增加 | 需另做 OAuth、多租户、远程工作区和凭证隔离 |
| Codex 插件 | `plugin.json`、Skills、`mcp.json`、可选 hooks | Skill 负责发现，MCP 负责真实调用 | IDE 与 Desktop 能力不同；local MCP 公共分发有限制 |
| Claude Code 插件 | `.claude-plugin/plugin.json`、Skills、`.mcp.json`、`bin/` | MCP 或独立 CLI 调用 Python 内核 | 插件进程可具有用户权限，不能把启动当沙箱 |
| OpenCode | 直接 MCP，或 V2 `Plugin.define` + `ctx.tool.transform` | 先复用 MCP；需要宿主 UI/权限时再写薄 V2 适配 | V1 custom-tool 与 V2 不可混用，默认权限需显式收紧 |

官方接入资料：

- [Plugin packaging](https://developers.openai.com/plugins/build/plugins)、[Codex MCP](https://learn.chatgpt.com/docs/extend/mcp)。
- [Claude plugin components](https://code.claude.com/docs/en/plugins/components)、[Claude plugin security](https://code.claude.com/docs/en/plugins/security)。
- [OpenCode plugins](https://opencode.ai/docs/plugins/)、[V2 server plugins](https://opencode.ai/docs/build/plugins/server/)、[V1→V2 migration](https://opencode.ai/docs/build/plugins/migrate-v1/)。
- [MCP stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio)、[MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools)。

### 6.4 MCP 合同

推荐窄工具：

| Tool | 作用 | 边界 |
|---|---|---|
| `codexwright_preflight` | 检查 builder、认证、状态目录和工作区 | 明确网络检查，不修改目标 |
| `codexwright_invoke` | 通用输入和操作路由 | 不写目标；可写内部 Session 并产生付费模型调用 |
| `codexwright_apply` | 应用指定提案 | 唯一目标写入口，要求 revision、snapshot 和幂等键 |
| `codexwright_verify` | 执行声明的验证 profile | 可运行受限测试和写 artifacts，不接受任意 shell |
| `codexwright_status` | 查询 Session/Run/preflight | 不调用模型，不修改目标 |
| `codexwright_read` | 有界读取 Spec、诊断、diff、验证报告 | Resources 不可用时的只读 fallback |

`readOnlyHint` 等 MCP 注解不是权限实现。analyze/plan 虽不修改目标，但会写内部 Session 并调用模型，不能简单标为完全只读。

MCP Resources 可作为可选优化，但不能成为唯一状态读取入口。Codex 当前公开 MCP 支持列表未声明 resources/prompts，必须保留 `status/read` tool fallback。核心运行状态也不能依赖所有宿主支持 MCP Tasks 或 subscriptions。

### 6.5 工作区、审批与恢复

- 模型传 `workspace_id`，服务端映射到预注册 canonical root；不能由模型直接指定任意写路径。
- `CODEXWRIGHT_HOME` 保存 Session、Spec、Run 和 artifacts，默认与目标仓库分离。
- `apply` 校验 `proposal_id + expected_spec_revision + expected_workspace_snapshot + idempotency_key`。
- `approval_reference` 只是证据引用，不能自证真人批准；宿主 tool policy 与 codexwright 服务端都要检查。
- Codex 可对 apply 配置 prompt 审批，Claude 可使用其专属用户交互元数据，OpenCode 使用权限配置或 V2 `ctx.permission.assert`；这些都不是跨宿主统一标准。
- spec revision 使用 compare-and-swap，外部修改返回 `stale_revision/workspace_conflict`，不能覆盖用户新改动。
- Run 状态增加 `waiting_input/waiting_approval/outcome_unknown`；断连或崩溃后先核对状态，不盲目重放。

### 6.6 必须实测后才能声明

- 目标无 SDK、无 Codex CLI、使用其他框架时，builder 仍能独立启动。
- 三类宿主安装、重载、stdio、依赖隔离、卸载和当前目录行为。
- invoke 不写目标，apply 在三类宿主都触发预期审批，拒绝后无修改。
- repo、图片、diff、trace、测试失败和对话引用的适配；不可访问时返回 `unsupported_input`。
- 同一 Session 多次调用、过期提案、并发 apply、幂等和崩溃恢复。
- 各宿主实际协商的 MCP 版本与功能，不默认使用新版 Resources、Tasks 或 subscriptions。
- 本地可加载不等于可公共分发；Codex Desktop-only、Claude marketplace、OpenCode 包分发分别核验。

本次未安装或运行三类宿主插件，所有跨宿主一致性均是待实测的落地方案，不是既有能力声明。

## 7. 跨项目能力取舍总表

| 能力 | 主要参考 | codexwright 决策 |
|---|---|---|
| 任意阶段 intake | harness、claude-code-setup、Cresta | IntakeEnvelope + Session，不强制用户改写模板 |
| 操作路由 | harness 新建/扩展/维护 | OperationRouter 支持 analyze/plan/build/edit/diagnose/migrate/refactor/verify |
| 架构事实源 | Cresta Blueprint、CrewAI 声明式规格 | 不可变 ArchitectureSpec revisions，构建与验证共同引用 |
| Agent 划分 | harness 控制流、CrewAI roles/tasks | 单 Thread 基线；独立工作、权限或验收才新增 Thread |
| 工作流 | CrewAI Flow | 宿主小型 DAG，显式依赖、join、budget 和失败状态 |
| Skills | harness、claude-code-setup | 渐进披露；generated/discovered/loaded/verified 分阶段验收 |
| 工具 | CrewAI schema、Cresta 确定性代码 | 窄 schema、风险与实现合同；CLI/MCP，不用实验 dynamicTools |
| 构建与修复 | Cresta | invoke 生成提案，apply 唯一写入；有界 diagnose/fix/rerun |
| 验证 | harness A/B、CrewAI guardrail、Cresta 混合评估 | 机械检查优先，独立 verifier 辅助，holdout 防过拟合 |
| 多 Harness | Cresta CLI、三类插件官方机制 | CLI/MCP 基础入口，Codex/Claude/OpenCode 薄适配 |
| runtime 迁移 | 用户新增约束 | none/codex_sdk/other/unknown；其他框架重建，Codex 项目复用 |
| 证据与状态 | harness workspace、CrewAI events、Cresta revisions | CODEXWRIGHT_HOME 下 Session/Spec/Run/artifacts，支持冲突和未知结果 |
