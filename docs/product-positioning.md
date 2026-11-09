# Product Positioning

Current definition: 2026-11-09. This document describes the agreed product and
distinguishes it from the service forms implemented in version 0.4.0.

## One-Sentence Definition

**build-mas is an architecture and construction assistant that users can call
from their existing coding agent or automation to build and evolve runnable,
verifiable agentic workflows on the Codex SDK.**

Its subject is the user's Agent system. Its job is to understand the work,
choose the architecture, implement the change, and produce evidence that the
result meets the declared requirements.

## The Core Job

1. Understand the goal or recover the actual flow from an existing implementation.
2. Choose the smallest sufficient mix of Agents, Skills, tools, and ordinary code.
3. Define context, inputs/outputs, orchestration, service interfaces, and controls.
4. Build or change the system within a reviewable scope.
5. Verify behavior, preserve failures, and support the next iteration.

Architecture advice without an implementation is useful for an analysis request,
but it is not completion of a construction request. File generation alone is
also insufficient: required verification and explicit approval gates must pass.

## How Users Work With It

Users can invoke build-mas at any stage: exploration, design, implementation,
debugging, evaluation, maintenance, or refactoring. They need not already have
a formal task flow, a multi-Agent system, or the Codex SDK installed in the
target project.

Inputs can include a natural-language goal, selected code or project files,
documents, images, diagrams, diffs, failed tests, traces, URLs, structured data,
or selected host conversation. The current material adapters normalize and
bound these inputs; arbitrary file formats and automatic full-chat access are
not promised.

The interaction can be conversational or an explicit MCP operation. A
session preserves the workspace, versioned ArchitectureSpec, and run history,
so a later request can change one part rather than restart the entire build.

## Three Distinct Layers

| Layer | Responsibility | Current implementation |
| --- | --- | --- |
| Host integration | Make the capability available where the user works | Skill + stdio MCP, Codex/Claude Code plugins, OpenCode V2 MCP/instructions; no builder CLI or hooks |
| Construction core | Architecture, proposals, approval, editing, and verification | One shared BuildService using the Codex SDK |
| User's target system | Perform the user's domain task independently | Standalone Codex SDK workflow with library, CLI, and task-level MCP |

The builder itself is an MCP service, not a Skill-only package. A Skill or
plugin is a thin discovery/invocation adapter, not a duplicate builder or an
alternative target Agent runtime.

Generated systems expose the workflow as a task-level service. Internal Agents
do not each need a public endpoint. Plugins, HTTP, and resident services are
optional delivery requirements; this release does not supply a prebuilt hosted
or always-on service platform.

## Architecture And Migration Policy

- One Agent is the baseline. Multiple Agents require a concrete reason and comparison.
- Skills hold reusable procedures; tools and scripts implement bounded operations.
- The host enforces permissions, schemas, state, budgets, orchestration, and acceptance.
- No prior implementation means a new Codex SDK workflow.
- Another Agent runtime means behavior capture followed by migration or rebuild.
- An existing Codex SDK workflow is reused and edited within scope.
- An unknown runtime is inspected before choosing a migration path.

Host flexibility does not mean runtime interchangeability. Codex, Claude Code,
and OpenCode can all invoke build-mas; the current builder and target Agent
runtime remain Codex SDK. The implementation language is an installation/API
detail, not the product category.

## What The Product Is Not

- A mandatory multi-Agent team generator or a fixed workflow collection.
- A teaching-only plugin or a wrapper that merely forwards prompts to the SDK.
- A replacement for the user's coding agent or a new editor they must adopt.
- A provider-neutral Agent runtime, a hosted MAS platform, or an enterprise control plane.
- An autonomous publisher that commits, pushes, deploys, or sends externally by default.

## Current Boundaries

The implemented core uses typed specs, private staging, exact proposals,
one-use approval, scoped application, deterministic checks, and live SDK
verification. `invoke` does not write the target; `apply` is its write boundary.
Incomplete, failed, and unknown outcomes remain visible.

Local macOS acceptance is recorded. Linux/Windows end-to-end commissioning,
actual remote-model connectivity, and production reliability are not established
by those trials. No license, PyPI release, or hosted-service release is implied
by the public repository.

The product definition guides future extensions; it does not turn optional
interfaces or unverified deployment targets into shipped features.

## Owning Sources

The current implementation is defined by `service.py`, `router.py`,
`contracts.py`, the MCP entrypoint, and the generated templates under
`src/build_mas`. The [architecture blueprint](build-mas-codex-sdk-blueprint.md)
and [implementation ledger](implementation-status.md) provide technical scope
and recorded evidence.

This separation of core objects from integration forms follows the relevant
product-structure guidance in *The Product Philosophy Behind WeChat*.
[RICH intention guidance](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/define-intention-type.zh-CN.md)
supports distinct consultation/execution intents and context-appropriate entry
forms. These are design references, not claims of user research or implementation
APIs. Codex-specific capability boundaries follow the
[official SDK documentation](https://learn.chatgpt.com/docs/codex-sdk).
