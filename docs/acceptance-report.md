# build-mas 0.2.0 Acceptance

This is historical evidence for 0.2.0. The builder CLI is retired in 0.3.0; see [0.4.0 MCP acceptance](mcp-0.4-acceptance.md) for current contracts and checks, and [MCP-only migration acceptance](mcp-only-acceptance.md) for the earlier migration. Generated workflow CLI interfaces are not retired.

Historical trials: 2026-11-08. Release revalidation: 2026-11-09. Scope: the Codex Python SDK-only CLI/MCP builder and standalone workflows, with single-agent-first architecture. Publication is separate from runtime acceptance and is recorded in the release ledger.

## Current Release Evidence

The whole-project review supersedes the earlier green fixtures for security
claims. See [release fixes](release-fixes.md) for the regression checklist.

- Real current SDK runs pass explicit SkillInput + CLI calls, builtin + project stdio MCP calls, and no-tools/global-MCP isolation. These are scoped local-provider trials, not production reliability measurements.
- Independent installed builder CLI and stdio MCP apply both verify a dependency available only in the owning target venv. Approved staging and applied target use that interpreter; CLI/MCP status results agree.
- An independently installed generated `mas` CLI completes a real Skill/tool run with the package made read-only. Package bytes stay unchanged, state is external/private, and task-level MCP reads/revalidates the same structured checkpoint.
- Candidate structure failure prevents execution. Package-owned live-check code is copied from verified templates into private staging; project tool code remains in its own OS sandbox. No partial inherited-policy sandbox exemption remains.
- Source and independent installed-wheel final suites each pass 108 tests + 6 example subtests. Python-module and Python-file import checks are both sandboxed and supported.
- Historical evidence is redacted and rehashed without changing its observed statuses. `release-live.json`, `release-installed.json`, and `release-construction.json` distinguish current trials from prior examples. Fresh-construction failures are retained; current recovery/apply success reuses the candidate without regenerating code and is not an untouched holdout.

## Requirement Mapping

| Requirement | Implementation / actual evidence |
| --- | --- |
| Any project stage / selected materials | Shared IntakeEnvelope and operation router; real DOCX extraction + architecture PNG + SkillInput construction, trace diagnosis and scoped edit. |
| One Agent when enough | Mandatory baseline reason; single_agent_sufficient enforces one declared Agent. Fresh/triage/holdout cases are single-agent; one real unnecessary three-agent fixture refactored to one without replacing its host runtime. |
| Codex SDK-only builder/target | Public SDK import whitelist, installed pinned SDK/runtime 0.167.0. Host/client model never substitutes for builder. Old runtime retirement check and standalone target dependency manifest. |
| Target has no SDK / uses other framework | Builder-owned runtime and private bootstrap; real CrewAI-source fixture rebuilt with golden inputs/errors and old runtime removed. Old runtime wasn't executable: contract/golden agreement, not proven original-runtime parity. |
| Existing Codex workflow reuse | Local adapter edit and regression repair preserve workflow.py, existing data and unrelated files. Versioned session/spec continued across calls. |
| CLI + MCP core interfaces | Single shared BuildService; actual installed CLI and stdio MCP equality, status/read fallback independent of Resources. |
| Multiple flexible host mechanisms | Actual Codex local plugin, Claude session plugin and OpenCode V2 MCP/instructions. All read the same saved spec with identical result. Target plugins/HTTP/resident services are optional. |
| Runtime control outside model | Strict schemas/references/DAG, separate host-owned scheduler, per-role permissions, typed assertions, bounded concurrency/retries/tokens/time, workflow checkpoint identity. |
| Exact authorization / no implicit writes | invoke stages only. apply binds fixed proposal/hash/revision/snapshot and one-use approval, reconstructs candidate, verifies live/independently, then writes and reruns. Actual MCP accepted/declined/unavailable-channel tests; large proposal review is paginated or redirected to local approval. |
| Real Skills/tools | Generated/discovered/loaded/behavior-verified evidence separated. Public SkillInput plus task assertions; MCP JSON-to-CLI registry with local schemas, fixed entrypoint, timeout/output limits and OS sandbox. Actual command/tool receipt captured. |
| No false success | Missing/malformed/failed/interrupted outputs, forbidden paths/secrets, mutated source, missing checks, empty evidence/verdicts and partial dependencies never pass. Independent MAS review repeatedly rejects missing coverage and eventually passes exact evidence. |
| Crash/replay safety | Admission receipt before effects, workspace ownership lock, terminal status, original-turn reconciliation, snapshot checks, fixed review diff, backup record. Unknown results are not blindly retried; partial target changes are not automatically overwritten. |
| Real SDK boundaries | read-only target/sibling denials; scoped writer preserves existing files; multi-turn/resume/fork, compact acknowledgement, usage, steer/interrupt with actual terminal interrupted. |
| Architecture evaluation | Four live same-task variants plus fault-injected deterministic final gates. Single Agent is cheaper/faster on this tiny case; no generic MAS benefit asserted. |
| Packaged install / docs | Final wheel imports from separate site-packages; CLI/MCP launch, five synchronized schemas, compact adapters and bootstrap. README is current service usage rather than skill-only positioning. |

## Historical Measurements

One fixed union fixture per topology; model gpt-6.1-sol, low effort. All observe IDs A/B/C/D without omissions.

| Topology | Tokens | Workflow ms | Turns |
| --- | ---: | ---: | ---: |
| Direct Codex Thread | 10,354 | 4,402 | 1 |
| Generated single Agent | 10,033 | 3,804 | 1 |
| Two parallel workers | 19,804 | 11,288 | 2 |
| Workers + verifier | 39,896 | 10,417 | 4 |

No statistical latency/quality conclusion follows from one sample. MAS is warranted here only when separate contexts and independent verification are explicitly required. The same deterministic final gate rejects seeded omission/addition/reordering in every topology; MAS-specific tests additionally block bad upstream packets and forged verifier results.

The earlier architecture examples are validation after debugging. An initial unseen construction failed a model-selected token limit despite correct architecture; it remains a failure in the ledger. Two different final frozen, explicitly budgeted constructions pass end-to-end (2/2), both single Agent. This is a small local diagnostic sample, not a production reliability benchmark.

## Historical Evidence And Current Limits

The earlier network-boundary acceptance recorded 80 automated tests plus 6 example subtests and wheel SHA-256 `719da3ed1e9d17c6930fecfcefe0ed8a849bf3495a48260a6750668ca7b20424`. Those bytes/counts are historical, not the reviewed release. The manifest's `release_revalidation` records the current suite and wheel separately. Authentication, provider configuration, and raw SDK reasoning are not exported.

Verified platform is macOS. Linux offline bubblewrap code has not been commissioned end-to-end; Windows verification fails closed. Independent live checks allow configured loopback providers or a request-scoped CONNECT relay to exact configured remote HTTPS authorities and public numeric addresses. Deterministic sandbox tests verify allowed forwarding, denied undeclared/direct network, bounded connections and connection teardown; only live checks receive the configured model credential environment. The final local-provider SDK regression passes unchanged Skill/tool behavior. Remote-model end-to-end is not verified: the routed resolver returns private addresses for official endpoints and is rejected, while a no-credential public transport probe returned URLError rather than a successful connection. No alternate DNS or open-network fallback is used by the runtime. This internal relay is not a public HTTP product service.

An independent installed-wheel real SDK run also passes unchanged Skill/tool behavior; its receipt is separate from the source-environment regression. The fresh private-installed account API still has a workspace-routing timeout; doctor truthfully returns account_unverified/exit 4 even while real SDK tasks succeed, recorded in final-doctor.json. OAuth login requires actual user account interaction and was not completed automatically.

No license was chosen; local Claude plugin validation passes but public host-directory publication is not part of this release. Repository commit/push/public visibility are authorized and tracked separately in the release ledger. No production deployment, external-send tool, remote hosting product, or resident worker is claimed. State retention and credentials/runtime routing remain operator responsibilities.
