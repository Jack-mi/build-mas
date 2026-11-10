# codexwright FDE positioning

User-confirmed direction for promotional material, 2026-11-09.

## Audience

Forward Deployed Engineers (FDEs) and other engineers who already have a
codebase, business requirements, data, tools, or model access, but do not know
how to turn those pieces into an Agent Workflow.

The user's problem is not choosing an Agent count or learning the builder's
internal modules. Their problem is getting from an existing project to a
workflow that can operate automatically.

## Core promise

Latest clarification: the most direct promotional description is **one-click
generation of multi-agent-system Agentic Workflows**. Titles and covers should
make that outcome immediately obvious rather than using abstract phrases such
as "automatic operation" alone. The primary starting point is the user's
**existing task**: codexwright turns that task into a Workflow in one click. A
codebase can be useful input, but it is not a required premise for the message.

codexwright helps people build Agent Workflows from their existing projects and
varied requirements. The resulting workflow should support the appropriate mix
of:

- Automatic operation: the workflow runs the task rather than requiring the
  user to manually coordinate every step.
- Control or self-decision: people can control critical decisions where needed,
  while the workflow can make task-level decisions where that is appropriate.
- Continuous evolution: feedback, diagnosis, editing, refactoring, and
  migration allow the workflow to improve without starting over each time.

Self-evolution is a product direction supported by iterative engineering; it
does not mean unsupervised self-modification is already a shipped capability.
Automatic operation also does not imply that this release provides hosted,
resident, or durable background execution.

## Product stage

codexwright is built for FDEs and is under active construction. The repository
and source are public. Do not call it legally open-source until a license has
been selected.

## Copy rules

- Explain concretely how user needs are met: start from the user's task and
  business rules; clarify the desired result; break the work into executable
  steps; connect the selected data, tools, models, and existing code; assign
  task-level judgment and human control where appropriate; then use runs,
  feedback, and failures to improve the workflow. Describe these outcomes in
  user-facing language rather than listing internal modules.
- Where useful, include one clearly hypothetical task example and show what
  the user provides, what the generated workflow handles, and what the user can
  adjust after seeing a run.
- Lead with the FDE's existing codebase and the outcome they want.
- Spend most of the copy on automatic operation, control or self-decision, and
  continuous evolution.
- Lead with one-click generation of multi-agent-system Agentic Workflows.
  Do not lead with single-Agent-first, approvals, invoke/read/apply/verify,
  internal schemas, or implementation modules.
- Do not use robotic transitions such as "边界也得讲清" or "现状也讲清楚".
- For Xiaohongshu titles, prefer short, concrete wording within the platform's
  20-character title limit. Titles should be eye-catching to people with AI
  workflow development needs, without unsupported guarantees or fake urgency.
- Do not claim production reliability, autonomous self-modification, a PyPI
  release, hosted execution, or a selected open-source license.
