# Implementation Acceptance Ledger

Historical goal: implement the complete agreed blueprint, including the user's source-runtime and multi-harness corrections. The earlier release request authorized that release's commit/push/publication; it does not authorize publishing subsequent changes. Version 0.3.0 retired the builder CLI. Version 0.4.0 hardened Skill + MCP contracts, approval/retry, protocol compatibility, bounded output and stage recovery without paid/remote services. Version 0.4.1 added indexed material retrieval, result-only paging, early scope validation and separated usage/progress signals. See [feedback acceptance](mcp-0.4.1-feedback.md) and [historical 0.4.0 acceptance](mcp-0.4-acceptance.md) for their distinct evidence and limits. Version 0.5.0 renames the project and public contract to codexwright.

## Current Product Definition

The [product positioning](product-positioning.md) defines codexwright as an
architecture and construction assistant for building and evolving Codex SDK
workflows from an existing coding agent or automation. MCP is the builder service
form; Skills/plugins are thin adapters, and generated workflows retain their CLI. Single-Agent-first, flexible lifecycle
inputs, exact reviewable changes, and verification remain the core boundaries.
The README is English-only; implementation language appears only where needed
for installation or technical compatibility.


## 0.5.0 Codexwright Rename

The distribution, Python import package, plugin, Skills, MCP server/tools/resources and host configuration now use `codexwright`. Version 0.5.0 is a public-contract migration, not a claim that historical 0.2-0.4 evidence tested the new identifiers. Existing builder state remains reachable through the legacy state-directory and `BUILD_MAS_HOME` fallbacks. See [the rename and migration guide](codexwright-migration.md).

Source and independent installed-wheel suites each pass 180 tests, one skipped test and six example subtests. The clean wheel contains no old Python package. Independent stdio discovery reports ten `codexwright_*` tools and two `codexwright://` resource templates; bootstrap, launcher, local-link and brand-asset checks pass. Evidence is in `acceptance-evidence/codexwright-0.5-rename.json`. Fresh host UI commissioning and live model behavior were not repeated.

## 0.3.0 MCP-Only Migration

The builder command module and console scripts are removed. The standalone MCP module and all host launchers use the private Python interpreter directly. Registration, selected attachment import, secure URL login and retained-run recovery have MCP tools. Application reviews every diff page through human form elicitation and stops without a supporting client; there is no CLI or Hook approval bypass. Builder state and generated workflow interfaces are retained. Commercialization is a document-only proposal, not shipped payment or remote-hosting code. Current migration acceptance is recorded separately in `mcp-only-acceptance.md`; the following 0.2.0 trials are historical.

## Historical 0.2.0 Release Revalidation: 2026-11-09

The 2026-11-08 trials below are historical. The full review found and fixed gaps
after those trials; they do not independently establish current release safety.
See [the release fix ledger](release-fixes.md) and the distinct `release-*.json`
records for current tests, installed acceptance, and real SDK receipts.

- Generated SDK configuration is private and excludes inherited MCP/project trust.
- Tools always get their own sandbox; environment flags and a partial inherited-policy proof cannot bypass it.
- Verified package-owned templates run live checks without importing target code in the verifier process. Project CLI/MCP implementations execute in a separate sandbox; other candidate checks remain sandboxed. Structural failure blocks candidate execution.
- The owning target environment is used for existing-project deterministic checks, including apply staging. Frozen generated harness checks use the trusted builder interpreter, never target venv startup code. Target dependencies are not silently installed.
- Generated CLI/MCP state is external to site-packages, with private atomic checkpoints and structured MCP results.
- Bounded builtin, Python CLI, and local Python stdio MCP tool bindings all have actual smoke/runtime receipts. PDF extraction is bounded while reading, including timeout/process-group cleanup; exact executable dependencies are discovered without a Homebrew-prefix grant.
- Public evidence is sanitized with `scripts/redact_evidence.py`; machine-path placeholders and omitted PATH values are presentation redaction, not runtime bindings. Original failures and historical measurement scope are preserved.
- Source and independent installed-wheel final suites each pass 108 tests + 6 example subtests. The installed builder recovers an unchanged fresh candidate after fixing Python-file import checks, applies it with all required live/offline gates passed, and preserves the original user file. Failed earlier construction trials remain separate records; the recovered success is not a holdout.
- Implementation commit `00e75e6ebea431b7e7fb3e2e6e8167b32dc6580a` identifies the release after the authorized history cleanup. Runtime/source file trees are unchanged by that cleanup; public verification is recorded separately from later README/positioning edits.

### Remaining Deployment Boundaries

Only macOS is commissioned. Linux/Windows end-to-end, actual remote-model
connectivity, production reliability, and missing original-framework parity
remain unverified. No license, PyPI release, hosted service, or public host
marketplace package is claimed.

## Scope

The Python core, strict schemas, state/revisions, snapshots, approvals, input normalization, Codex runtime, generated workflows, migration, verification, CLI, stdio MCP, adapters, fixtures, and docs must all agree. The original read-only example remains supported.

## Milestones

- [x] A: contracts, workspace registration, revisions, routing, invoke/apply/status/doctor.
- [x] B: real SDK construction, generated standalone library/CLI/MCP, deterministic evidence.
- [x] C: existing Codex reuse, non-Codex migration, parity gates, bounded repair, session continuation.
- [x] D: bounded DAG, handoff trust, Skills/tools, verifier, failure/timeout/retry/budget tests.
- [x] E: CLI and MCP equivalence, Codex/Claude/OpenCode adapters, bootstrap and approval tests.
- [x] F: real integrations, holdout/parity cases, baseline measurements, final requirement audit and final network/package revalidation within the documented local macOS scope.

## Authoritative Baselines

- Repository initially contains only the 0.1.3 Skill and read-only example plus the agreed blueprint. Existing README/docs changes are preserved.
- Architecture guidance: agents-best-practices `da245f8cbfc4c358e8c3cde61dbb703bd40292bc`, version 1.18.0, verified upstream 2026-11-08.
- Official SDK source: `748ab55ca7de0b647d9a7a9d9a8e70e00f28666d`. Implementation pins published `openai-codex==0.167.0` and its matching runtime, checked separately against installed public signatures.
- Interaction guidance: RICH confirmation and generation-state sources at Ant Design X `8b76d6a22067945c5d224c02ee1448dfb30144ff`; only visible operations/states are exposed, not hidden reasoning.
- Product method: Simple and Usable / transfer-strategy; share complexity in the core rather than duplicating it in host adapters. Security and user control are not removed.

## Evidence

This ledger is updated with actual commands and results. A checked box requires scoped runtime or test evidence, not a source-text assertion.

### Historical Local Trials: 2026-11-08

- Earlier `pytest -q tests --disable-warnings`: 62 passing tests after recovery, exact approval, JSON-to-CLI registry, strict read-only permissions and contract-boundaries changes; superseded by the final full-suite record below.
- Fresh construction `buildmas-final-build-6ael2lb2`: `run_dc0fd7771c3158368ca7a7a1` prepares one agent without changing `keep.txt`; approved `run_7c6047b93b44444a52287b3f` completes with real SDK CLI and offline checks. Installed standalone package imports and `mas --help` pass in a separate target venv.
- Existing Codex local edit: `run_0bd724c90c3d13810b0d2b0d` changes only `legacy_api.py` and `tests/test_legacy_api.py`; no runtime rebuild or unrelated file change.
- Non-Codex migration `buildmas-migrate-current-8co183xt`: approved `run_c4ec83e5faabec93d10a8d95` passes golden/error/permission and live SDK checks; old runtime/dependency retired. A narrow non-agent adapter preserves captured Python exceptions. CrewAI was not installed/executed: evidence establishes golden/contract rebuild agreement, not proven old-runtime execution parity.
- Document + generated diagram `buildmas-doc-image-skill-v2-inlz1peb`: `run_655e64a0895bd91cbbbe2cdc` applies with real SkillInput and asserted triage output; document extraction and registered image reach the SDK without rewriting the user's material.
- Skill + CLI tool `buildmas-skill-tool-current-zhb9vltl/evidence11`: actual SkillInput, scoped MCP-to-CLI registry call and strict output assertion pass; tool arguments/schema, one-use authority and OS sandbox tested independently. Later frozen-template and network regression checks also pass.
- Diagnose -> local edit -> regression `buildmas-diagnose-regression-nkrdoyut`: diagnosis `run_26d5166ea91fecd0f0c4c937` identifies discarded adapter output; approved `run_a2fd3a31eb037b69c412b012` edits only `legacy_api.py` and passes original failing test.
- Three-agent independent join `buildmas-mas-architecture-aocugefs`: approved `run_3296f63537ed92376e1672a4` completes with actual SDK workers/verifier, fixed template, strict read-only/source-isolation configuration, mutation tests, CLI/MCP checks and independent frozen-candidate review. Earlier reviews correctly rejected incomplete evidence; no target write occurred on those failures.
- Same union fixture live controls: direct single 10,354 tokens / 4,402 ms; generated single 10,033 / 3,804; parallel workers 19,804 / 11,288; workers + verifier 39,896 / 10,417. All achieved full coverage; one sample per topology, not a statistical speed claim. Common final gates reject 12 deterministic seeded omission/addition/reordering outputs. No generic MAS superiority claim.
- Actual local hosts: Codex plugin 0.2.0 installs and invokes `buildmas_status`; Claude Code discovers the plugin Skill, connects MCP and calls the same tool; OpenCode V2 calls it through `mcp.servers` with explicit permission configuration. Isolated host config only; global host config remains untouched. Local Claude validation passes; public directory publication is intentionally not attempted (no license selected).
- Installed wheel `buildmas-wheel-final-cxgh6pxs` runs CLI registration from installed `site-packages`, not the editable repo. Private bootstrap also works using `uv` without modifying target dependencies.

### Final Acceptance

- One-agent refactor `buildmas-refactor-current-ypc8hfbv`, approved `run_2cf71b793c0436dc02ea45f0`, passes: changes only spec, topology-specific tests and docs; workflow.py/MCP/dependencies/request remain unchanged. Prior JSON/budget failure candidates were retained/recovered, not called successful.
- Final schemas regenerated from owners; exported result schema now describes VerificationReport, not its input plan. Package includes CLI/MCP service, templates, narrow CLI registry and all five schemas.
- Final SDK lifecycle probe `buildmas-sdk-lifecycle-recheck-bl1htz76`: continued/resumed/forked marker preserved; compact acknowledged; usage present; steer/interrupt acknowledged with terminal interrupted. Ephemeral fork uses the published `include_turns=False` contract. An earlier unsupported combination was rejected, not called successful.
- Final actual runtime permissions `buildmas-runtime-safety-final-bo9nj8ri`: read-only rejects target writing and sibling reading; scoped writer creates only the proof and preserves existing data. Both are real SDK executions.
- Current account API can return `workspace routing discovery timed out` while SDK initialization/model catalog and actual turns work. Preflight now preserves this as `account_unverified`, not ready; do not claim final account check passed.
- Final `pytest -q tests examples --disable-warnings`: 80 tests plus 6 original-example subtests pass in both the source environment and independent installed-wheel environment after the network boundary changes. `git diff --check` and secret-like scans pass. No graphify graph exists, so no graph update is necessary.
- Final wheel installed into an independent environment; CLI version/registration/status and actual stdio MCP result agree. `final-installed-package.json` records module path under installed site-packages, all six policy-enabled MCP tools and packaged schemas/template. Bootstrap updates only the private builder environment.
- Three actual host clients read the same saved one-agent fixture through buildmas_read and receive identical content/reference/pagination. Codex/Claude/OpenCode equality records are in `docs/acceptance-evidence/*-same-fixture.json`. OpenCode needed explicit read-tool permission and discovery; no service-side alternate behavior was added.
- Earlier architecture cases failed initial trials and were used for fixes: validation, not holdout. The first unseen small build selected the right single-agent architecture but failed its self-selected 4000-token target budget. That failure is retained in `unseen-initial-holdout.json`, not relabelled. After explicit caller-budget guidance, two different frozen construction cases both select one agent and pass approved real SDK application: 2/2 in `final-construction-holdout.json`. A tiny constrained sample is not a robust success-rate estimate.
- Final frozen Skill/tool template real check passes including explicit SkillInput, asserted output and actual validated MCP-to-CLI receipt. `final-skill-tool.json` records configuration and receipts. Tool policy and filesystem-denial tests also pass.
- macOS is live-tested. Linux/Windows end-to-end remain unvalidated for this release; no unsandboxed runtime fallback. Remote HTTPS model endpoints now use a request-scoped loopback CONNECT relay bound to exact configured authorities and public numeric DNS pins; arbitrary direct network and undeclared/private destinations stay denied. Deterministic sandbox relay tests pass, including pipelined bytes, bounded connections and teardown. The local routed resolver returns private addresses for official endpoints and is rejected; the no-credential public transport probe returned URLError, not proof of remote connectivity or model execution.
- No commit, push, deployment, public release, license choice, remote HTTP service or resident worker was executed or is part of this acceptance. Account-routing timeout remains truthfully `account_unverified`; successful actual model turns do not turn that account check into a pass.

### Historical Network And Package Revalidation

- [x] Confirmed single-agent-first is already implemented in instructions, architecture reference and contract tests; no topology redesign.
- [x] Real SDK regression `buildmas-network-live-regression-w_7hc2nm`: unchanged frozen template, compile, narrow CLI tool and actual SkillInput/model run all pass; output is LABEL:HELLO. This uses the configured local provider, not an independent remote-model trial.
- [x] Relay tests record real host/IP pins separately from sandbox loopback ports; only live checks receive explicitly configured model credential variables, never offline checks or exported credential values.
- [x] Rebuilt wheel includes network.py; all runtime/template/reference/schema bytes match the independent installed package. Private builder bootstrap and Codex launcher both report 0.2.0. Installed CLI/MCP results are exactly equal; six policy-enabled tools and five schemas are present.
- [x] Independent installed-wheel real SDK regression `buildmas-installed-sdk-regression-_o5sc579` also passes unchanged Skill/tool behavior. Fresh installed doctor still returns account_unverified/exit 4; its result is retained in final-doctor.json, not masked by successful model tasks.
- [x] Final full suite, schema synchronization, whitespace/secret scans and evidence manifest refreshed. Wheel SHA-256: 719da3ed1e9d17c6930fecfcefe0ed8a849bf3495a48260a6750668ca7b20424. model-network.json separates deterministic relay evidence, actual local-provider model evidence and unverified remote-model connectivity.

These earlier local trials are complete within their recorded scope. Current release evidence is separate; repository visibility and pushed HEAD must be verified at publication time.
