# build-mas X / Hacker News drafts

Based on local `main` at `5aa55b7` (`0.2.0`), reviewed on 2026-11-09.
These are drafts only; nothing has been posted.

## Positioning

Core message:

> Build the workflow. Keep your coding agent.

build-mas is a workflow engineering assistant for Codex SDK, not a fixed
multi-agent team generator. Its strongest differentiators are:

- Start from a goal, existing code, documents, images, diffs, or failing traces.
- Prefer one Agent; add Skills, tools, or Agents only when justified.
- Review an exact proposal before `apply` can write target files.
- Produce a standalone Codex SDK workflow and verification evidence.
- Invoke the same builder through CLI/MCP from Codex, Claude Code, or OpenCode.

Do not call it production-proven, PyPI-published, hosted, or open-source. The
repository is public, but no license has been selected. Current acceptance is
local macOS acceptance, not a production reliability benchmark.

## X series

Post these separately rather than all at once. Each stands alone; the launch,
standalone-output, and feedback posts are the best starting set.

### X1 - Launch

```text
I built build-mas: engineer agent workflows from your coding agent.

Turn goals, code, diagrams, or traces into Codex SDK workflows with reviewable diffs, approval gates, and verification.

CLI + MCP for Codex, Claude Code, and OpenCode.

https://github.com/Jack-mi/build-mas
```

### X2 - Single-Agent first

```text
Multi-agent should be a justified architecture, not the default template.

build-mas starts with one Agent. It adds Skills, tools, or more Agents only when the task needs them, and asks for a baseline comparison before adding complexity.

https://github.com/Jack-mi/build-mas
```

### X3 - Approval boundary

```text
Agent builders often stop at scaffolding.

build-mas separates:
- invoke: analyze and stage a proposal
- read: inspect the exact diff
- apply: write after approval
- verify: check the applied result

A model saying "done" is not the acceptance gate.
```

### X4 - Improve an existing system

```text
You shouldn't have to rebuild your agent system just to improve it.

build-mas can start from existing code, a diff, a trace, or a failed test. Existing Codex SDK systems are edited in scope; other runtimes are migrated with explicit behavior criteria.
```

### X5 - Standalone output

```text
What does build-mas produce?

A standalone Codex SDK workflow with library, CLI, and task-level MCP entrypoints. It does not import build-mas at runtime.

The builder is the tool. Your workflow is the product.

https://github.com/Jack-mi/build-mas
```

### X6 - Keep your host

```text
Keep the coding agent you already use.

build-mas exposes the same builder through CLI and stdio MCP, with thin adapters for Codex, Claude Code, and OpenCode. Skills and plugins help you invoke it; they are not another agent runtime.
```

### X7 - Controls outside the model

```text
Agent workflow controls belong outside the model.

build-mas uses typed work packets, scoped tools, budgets, retries, snapshots, one-use approvals, and verification. Failed, partial, blocked, and unknown outcomes stay visible.
```

### X8 - Transparent release status

```text
build-mas 0.2.0 is public for feedback.

Tested locally on macOS. Source and installed-wheel acceptance each record 108 tests + 6 example subtests passing.

Not yet on PyPI; no license selected; production reliability is not claimed.

https://github.com/Jack-mi/build-mas
```

### X9 - Feedback

```text
What is the most painful part of building agent workflows today?

1. Choosing the architecture
2. Integrating tools and Skills
3. Debugging handoffs
4. Verifying that the result actually works

I'm building build-mas around these problems:
https://github.com/Jack-mi/build-mas
```

## Hacker News

Use one Show HN submission, not a sequence of near-duplicate launches. The
alternative titles are options for the same submission, not separate posts.

### Recommended title

```text
Show HN: Build-mas, an approval-gated Codex SDK workflow builder
```

URL:

```text
https://github.com/Jack-mi/build-mas
```

### Alternative titles

```text
Show HN: Build-mas, single-Agent-first workflow engineering for Codex SDK
Show HN: Build-mas, build and verify Agent workflows from your coding agent
```

### First comment

```text
Hi HN - I built build-mas because I wanted help engineering Agent workflows without adopting another fixed multi-agent framework.

It accepts a goal, existing code, documents/images, a diff, or a failing trace. It chooses one Agent by default, adds Skills/tools/Agents only when justified, and stages an exact proposal. Nothing writes to the target until the proposal is reviewed and approved.

The result is a standalone Codex SDK package with library, CLI, and task-level MCP interfaces. It does not import build-mas at runtime. The builder itself is available through CLI and stdio MCP, with thin adapters for Codex, Claude Code, and OpenCode.

Current acceptance includes real SDK runs for Skills, CLI tools, and project MCP tools. Source and installed-wheel suites each pass 108 tests + 6 example subtests. This is local macOS acceptance, not a production reliability claim.

Current limits: remote-model end-to-end remains unverified in the test environment, and there is no PyPI or hosted release. No license has been selected yet.

I would especially like feedback on the approval/verification model and whether the generated workflow boundary makes sense.
```

### Short answers for likely comments

**Why not just prompt Codex to build the workflow?**

```text
You still use Codex for construction. build-mas adds a persistent architecture contract, lifecycle operations, exact staged diffs, one-use approval, scoped application, and verification evidence around that work. It is aimed at repeated construction and evolution, not replacing the model with templates.
```

**Why is single-Agent-first a feature?**

```text
Extra Agents add handoffs, context, cost, and failure modes. Sometimes independent contexts or verification justify them; often they do not. build-mas makes one Agent the baseline and requires a concrete reason and comparison before adding more.
```

**Does Claude Code or OpenCode replace the Codex runtime?**

```text
No. They are alternative hosts for invoking the same builder. The current builder and generated target workflow both use Codex SDK. Host flexibility is not a provider-neutral runtime abstraction.
```

**Is this a no-code workflow builder?**

```text
No. It is a coding-agent-accessible engineering tool that produces a real Python/Codex SDK project. The point is not to hide code; it is to make architecture, changes, approval, and verification explicit.
```

## Before posting

- Recheck the README if installation, licensing, platform support, or release status changes.
- Post X1 first; use X2-X7 as standalone follow-ups, then X8/X9 when feedback is useful.
- On HN, answer technical questions directly and keep failures and limits visible.
- Do not use the historical single-run latency/token measurements as a general benchmark.
