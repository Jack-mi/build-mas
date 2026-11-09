# build-mas

### Build the workflow. Keep your coding agent.

**Design, build, and evolve agentic workflows with the Codex SDK, from the coding agent you already use.**

Bring a goal, a diagram, a failing trace, or an existing implementation. build-mas decides what should be an Agent, a Skill, a tool, or ordinary code, then turns those decisions into a runnable, verifiable system on the **Codex SDK**.

Use it inside **Codex, Claude Code, or OpenCode**, or directly from your terminal. Start from nothing, improve a working system, or rebuild a workflow from another framework. You do not have to start over just to ask for help.

build-mas is a workflow engineering assistant, delivered as a CLI and MCP service with optional host plugins. It helps you create or change your own workflow; it does not require a fixed Agent team or a new coding environment.

`0.2.0` · Codex SDK/runtime `0.167.0` · Local macOS acceptance tested

## Product Positioning

**The product is the ability to engineer an Agent system, not a particular Agent count, framework template, or packaging format.**

- **At any project stage:** call build-mas to inspect, design, build, edit, diagnose, migrate, refactor, or verify a workflow.
- **From your available material:** start with a goal, existing code, a document, an image, a diff, a trace, or selected task context; no complete specification is required upfront.
- **Use the smallest sufficient architecture:** choose one Agent when enough, multiple Agents when justified, reusable Skills for procedures, and deterministic tools or ordinary code where they fit.
- **Keep your host:** CLI, MCP, and thin plugins make the same capability available from Codex, Claude Code, OpenCode, or automation.
- **Own the result:** receive a standalone Codex SDK workflow and scoped, reviewable changes with verification evidence, not only design advice.

The current release uses Codex SDK for both construction and the target Agent runtime. An existing Codex SDK system is reused; a system built on another Agent runtime is migrated or rebuilt. Broad input support and flexible host integration do not imply an interchangeable target-runtime abstraction.

See [Product positioning and boundaries](docs/product-positioning.md) for the full definition and the distinction between product direction and currently implemented service forms.

## What You Can Do

| You bring | build-mas helps you |
| --- | --- |
| A rough goal or task-flow description | Choose the smallest useful architecture and build it |
| Code, documents, images, or a diagram | Recover the actual flow and produce an executable spec |
| A simple script or another Agent framework | Capture behavior, then rebuild on Codex SDK |
| An existing Codex SDK workflow | Reuse its runtime and make a scoped change |
| A diff, failing test, or execution trace | Diagnose the failing boundary and prepare a repair |
| An overcomplicated MAS | Compare against a single-Agent baseline and refactor |
| A prepared change | Inspect the exact diff, approve it, apply it, and verify it |

The same service handles analysis, planning, construction, migration, editing, diagnosis, refactoring, and verification. Follow-up requests retain the session and its versioned architecture.

## Two Services, One Clear Boundary

**build-mas is the builder. Your generated workflow is the product it builds.** Neither is limited to a Skill.

```text
Your terminal / Codex / Claude Code / OpenCode
                     |
              CLI or stdio MCP
                     |
                 build-mas
          architecture -> staged proposal
                     |
            exact review + approval
                     |
              standalone workflow
            library / CLI / task-level MCP
                     |
                 Codex SDK
```

- **Builder:** one shared construction service, first-class `build-mas` CLI and stdio MCP, with thin host adapters. Skills/plugins are optional ways to discover and invoke it, not its implementation.
- **Generated workflow:** a standalone Codex SDK package with library, `mas` CLI, and task-level MCP entrypoints. It does not import build-mas at runtime.
- **Optional target delivery:** plugins, HTTP endpoints, and resident workers can be requested. They are not default scaffold outputs or prebuilt hosting products in this release.
- **Host independence:** Claude Code and OpenCode invoke the same builder; their model/runtime does not replace Codex SDK inside the builder or target.

The target need not already have Codex SDK. The builder has its own isolated installation. Existing Codex SDK implementations are reused; other Agent runtimes are migrated or rebuilt with explicit behavior-preservation criteria.

## Quick Start

Install from source. This repository does not yet publish a PyPI release.

```sh
git clone https://github.com/Jack-mi/build-mas.git
cd build-mas
python3 scripts/bootstrap.py
export PATH="$HOME/.local/share/build-mas/venv/bin:$PATH"

build-mas --version
build-mas doctor --json
```

The current implementation requires Python 3.10+. The bootstrap installs the builder into `~/.local/share/build-mas/venv`, using `uv` when available or standard `venv`/`pip`. It does not install dependencies into your target project. For a custom location, pass `--environment` and use the executable path printed by the installer.

If authentication is missing, run `build-mas login` or `build-mas login --device` and complete the account interaction yourself. Existing selected Codex provider configuration/auth can be imported into a private runtime; build-mas never copies your entire `.codex` directory or asks for credentials in a prompt. Model availability depends on your account; no particular model is required by the quick start.

### Build, Review, Apply

Run from the project you want to work on:

```sh
build-mas build "Build a ticket-triage workflow. Use one Agent if sufficient." \
  --cwd "$PWD" --idempotency-key triage-v1 --json
```

The response supplies workspace, session, run, and proposal IDs. Substitute those IDs in subsequent commands:

```sh
build-mas read proposals prop_RETURNED_ID --limit 50000 --json
build-mas apply --proposal prop_RETURNED_ID --idempotency-key apply-v1
build-mas verify --workspace ws_RETURNED_ID --session ses_RETURNED_ID --json
```

**`invoke` and construction commands prepare changes; only `apply` writes target files.** Review every page of a large proposal using the returned `next_offset`. Interactive `apply` displays the proposal and requires an explicit `approve`. `--yes` is available for an already-reviewed local approval; it is not permission for a Coding Agent to approve on your behalf.

Offline checks run before approval. The approved candidate must pass its live checks and any required independent review before application. The applied files are checked again. Failed gates retain the candidate and evidence instead of claiming completion.

### Continue Anywhere In The Lifecycle

```sh
build-mas diagnose "Why did this handoff fail?" \
  --workspace ws_ID --session ses_ID --file traces/failed.json --json
build-mas edit "Fix only the failing adapter; keep the runtime" \
  --workspace ws_ID --session ses_ID --json
build-mas status --session ses_ID --json
build-mas recover --run run_ID --json
```

Use `analyze`, `review`, `explain`, or `plan` for inspection; `build`, `edit`, `migrate`, and `refactor` prepare scoped proposals. `invoke` chooses the operation from the request. `register` explicitly registers a project without changing it. Recovery checks ownership, original turns, and snapshots; unknown outcomes are not blindly replayed.

## Call It Through MCP

```sh
build-mas serve --transport stdio
# Expose approval-gated application when you need it:
build-mas serve --transport stdio --allow-apply
```

| Tool | Purpose |
| --- | --- |
| `buildmas_preflight` | Check SDK/runtime, account, and optional workspace readiness |
| `buildmas_invoke` | Analyze or prepare a workflow change from an IntakeEnvelope |
| `buildmas_verify` | Run the saved architecture's verification checks |
| `buildmas_status` | Inspect a session or run |
| `buildmas_read` | Read specs, exact proposal diffs, and bounded evidence pages |
| `buildmas_apply` | Apply an exact approved proposal; exposed only with `--allow-apply` |

Register the target with `build-mas register` and pass its workspace ID to MCP. `status/read` are ordinary tools, so basic use does not depend on MCP Resources support.

Use the **actual absolute executable path printed by bootstrap** in your client's MCP configuration, rather than assuming an interactive-shell PATH:

```json
{
  "mcpServers": {
    "buildmas": {
      "command": "/absolute/path/from/bootstrap/bin/build-mas",
      "args": ["serve", "--transport", "stdio", "--allow-apply"]
    }
  }
}
```

MCP application requires real human elicitation acceptance or a one-use approval issued locally after reviewing the full diff. If the client cannot display the approval, use `build-mas approve --proposal prop_ID --yes --json` locally and pass the returned approval fields with an `idempotency_key`. Missing, rejected, changed, expired, or consumed approvals cannot be bypassed through another adapter.

## Bring Your Own Coding Agent

The CLI/MCP service works without installing a host Skill. These adapters add convenient discovery and invocation instructions.

| Host | Integration |
| --- | --- |
| Codex | Compact local plugin in `adapters/codex`, with Skill + MCP launcher |
| Claude Code | Session plugin in `adapters/claude-code`, invoking the same private builder |
| OpenCode V2 | MCP configuration + instructions in `adapters/opencode` |
| Terminal / automation | Installed `build-mas` / `buildmas` executable and JSON output |

```sh
# From this repository, after installing the builder:
codex plugin marketplace add "$PWD"
codex plugin add build-mas@build-mas-local

# Or a session-only Claude Code adapter:
claude --plugin-dir "$PWD/adapters/claude-code"
```

For OpenCode V2, merge `adapters/opencode/opencode.jsonc` into your chosen project configuration and include its `build-mas-host.md` instructions. Replace the command with the installed absolute builder path. No separate JavaScript Agent runtime or UI plugin is needed.

Adapters do not rewrite global host settings. `BUILD_MAS_ENV` or `BUILD_MAS_PYTHON` selects a custom private builder for plugin launchers. Actual host loading and same-fixture calls are recorded in the acceptance evidence; this is not a claim about every future host version.

## Architecture That Can Be Checked

The versioned **ArchitectureSpec** is the executable contract, not just a diagram:

- **Single-Agent first:** `single_agent_sufficient` requires exactly one Agent. Multiple Agents need a reason and baseline comparison, not a fixed team template.
- **Explicit work packets:** typed input/output, dependencies, conditions, assertions, and integration rules; the host owns the scheduler and stopping conditions.
- **Skills where they belong:** reusable procedures are loaded through public `SkillInput`. Generation, discovery, loading, and asserted behavior have distinct evidence.
- **Narrow tools:** bounded `read_file`/`list_files`, Python CLI modules, and project-local Python stdio MCP servers run through a host-owned registry with schemas, OS sandbox, timeout, output limits, and actual call receipts. General shell is not a builtin tool.
- **Controls outside the model:** scope, budgets, concurrency, retries, snapshots, approval, and verification are enforced by code. A model verdict alone cannot make a failed run pass.

Codex SDK supplies threads, turns, structured results, and runtime capabilities. build-mas supplies workflow architecture, lifecycle, orchestration, and verification. The SDK is not the same thing as an interactive Codex client, and build-mas does not invent SDK methods such as `create_agent` or `register_tool`.

## Inputs Without A Forced Form

Use `--file`, `--image`, `--url`, or an IntakeEnvelope from `--input request.json` / `--input -`. Code, diffs, traces, failures, and selected conversation are provenance-labelled references, not execution authority. Full host chats are not copied automatically.

```sh
build-mas import /path/to/selected/architecture.docx --workspace ws_ID --json
build-mas invoke "Build from these notes" --workspace ws_ID --asset asset_ID --json
```

Local images enter supported SDK turns. DOCX uses bounded XML extraction; PDF uses sandboxed `pdftotext` or user-supplied extracted text/page images. Public HTTP(S) references are bounded, pin validated public addresses, and reject redirects, credentials, and private destinations. This does not imply native SDK support for every file type.

## Your Workflow Runs Independently

Install the generated project into its own environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/mas run --input request.json
.venv/bin/mas status --run-id latest
.venv/bin/mas verify --run-id latest
.venv/bin/mas serve
```

The generated MCP exposes `mas_run`, `mas_status`, `mas_read`, and `mas_verify` at the **task level**, not one public service per internal Agent. Its run state defaults outside the installed package, under `$XDG_STATE_HOME/codex-workflows` or `~/.local/state/codex-workflows`; use `--state-dir` or `WORKFLOW_STATE_DIR` to override it. Checkpoints bind the exact spec and input.

CI means **continuous integration**: an automated environment that reruns commands/tests when code changes. It can call the CLI; it is not another Agent or a mandatory service form.

## Safety, Evidence, And Honest Limits

| Boundary | Current behavior |
| --- | --- |
| Target writes | Exact proposal, scope, revision, snapshot, and one-use approval |
| Generated SDK configuration | Private `CODEX_HOME`; no inherited global MCP, plugins, or project trust |
| Project code execution | OS-sandboxed checks/tools; no environment-controlled sandbox bypass |
| Live generated checks | Execute verified package-owned templates; user tool implementations remain separately sandboxed |
| Existing-project verification | Use the owning project's local venv, or a portable explicit `verification.python` path; no automatic dependency install |
| Unknown / interrupted outcomes | Retained and reconciled; never automatically replayed as success |
| Builder state | Private state outside the target, default `~/.local/share/build-mas` or `BUILD_MAS_HOME` |
| Public evidence | Redacted command/results, hashes, and scoped trials; no credentials, provider config, or raw reasoning |

`completed` is distinct from verification `passed`. `approval_required`, `pending_live`, `partial`, `failed`, `blocked`, and `outcome_unknown` remain visible. CLI exit codes are 0 success, 1 failure/partial, 2 input/spec error, 3 approval needed, 4 environment unavailable, and 5 unknown outcome.

macOS is the commissioned platform. Linux bubblewrap support exists but end-to-end Linux commissioning is unverified; Windows verification fails closed. Remote HTTPS model checks use a request-scoped pinned CONNECT relay, but actual remote-model end-to-end remains unverified in the tested routed environment. Successful local-provider turns do not resolve an account preflight timeout: `doctor` can truthfully report `account_unverified`/exit 4.

Generation is stochastic and budgeted. Local tests, a tiny holdout, and captured migration contracts do not establish production reliability or original-runtime parity when the old framework could not be executed. External/destructive tools, multi-user hosting, automatic deployment, remote HTTP hosting, and resident workers are not enabled products in this release. State retention is manual.

The source is intended for public development. **No license has been selected yet**; do not assume a permissive open-source license, a PyPI release, or a published host marketplace package.

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e . pytest build
.venv/bin/pytest -q tests examples
.venv/bin/python scripts/export_schemas.py
.venv/bin/python -m build --wheel
```

| Start here | What it contains |
| --- | --- |
| [Product positioning](docs/product-positioning.md) | Core value, lifecycle, host integration, target output, and scope |
| [Architecture blueprint](docs/build-mas-codex-sdk-blueprint.md) | Product boundaries, SDK mapping, contracts, lifecycle |
| [Implementation ledger](docs/implementation-status.md) | Observed behavior, historical trials, remaining gaps |
| [Acceptance report](docs/acceptance-report.md) | Requirement mapping and measured local scope |
| [Release fix ledger](docs/release-fixes.md) | Review findings and their regression evidence |
| [Reference evaluations](docs/project-evaluations.md) | Architecture comparisons without universal MAS claims |
| `src/build_mas/schemas` | Exported public request/spec/result schemas |
| `examples/minimal_mas.py` | A read-only two-role teaching example, not the service runtime |

SDK-specific APIs are checked against the public pinned release and [official Codex SDK documentation](https://learn.chatgpt.com/docs/codex-sdk). Architecture decisions use [agents-best-practices](https://github.com/DenisSergeevitch/agents-best-practices); approval interactions apply the relevant [RICH confirmation guidance](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/confirm.zh-CN.md). Host/API references and verified revisions are recorded in the blueprint and ledger.
