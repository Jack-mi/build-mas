# build-mas 0.4.0: MCP contract and acceptance

Date: 2026-11-09. This iteration retains one local MCP server, shared BuildService
and thin Skills. No builder CLI, hooks, background scheduler, remote SaaS,
payment service, public package publication or automatic Git publication is added.

## Upgrade contract

- Tool names and the `envelope` / `request` wrappers are unchanged. MCP invoke
  requires `idempotency_key`; apply accepts only `proposal_id` and
  `idempotency_key`. Internal approval fields are rejected before any prompt.
- Default responses are bounded summaries, not old private store records.
  `checks_summary`, `references` and `omitted` explain what happened and where
  full details live. `read` retains character-based pagination and adds `events`.
- Public apply admission precedes confirmation. Frozen proposal hash, revision,
  snapshot and sequential page position bind the review. Approval handles are
  server-owned and do not change the logical request identity.
- Same request/key returns the original result or original run state without
  another approval/check/write. Same key for another proposal conflicts. A
  retained decline requires a new key; legacy records are reused only with
  verified workspace/proposal/run association.
- Old protocol confirmation uses callbacks; modern `2026-07-28` confirmation
  uses SDK-sealed multi-round request state. Missing capability, skipped pages,
  modified/expired state and client round limits do not grant authority. An
  unfinished review cannot continue across a server restart.
- Login is a bounded private attempt: user-only URL interaction, no credential
  tool arguments, at most one outstanding attempt per runtime, 300-second expiry,
  cancellation and connection-close cleanup. Automated callbacks are not proof
  of a human completing identity login.
- Progress is request-scoped, monotonic and best effort. Last stage/sequence and
  known usage remain in the run record. Missing notifications do not change
  business outcomes. SDK interruption and verification process-group termination
  preserve uncertainty where no terminal evidence exists.

Re-run bootstrap in the selected private environment, reinstall the selected
local plugin and reconnect/new-chat to refresh schemas. No state directories,
history, candidates or backups are deleted. Existing target workflow interfaces
and Codex SDK/runtime 0.167.0 remain unchanged.

## Evidence scope

The current automated evidence includes schema discovery, strict public inputs,
bounded summary/paging, public apply replay/concurrency/decline, legacy association,
modern sealed confirmation and multiple pages, old/new real stdio transports,
notification isolation/failure, login lifecycle callbacks, SDK interruption and
actual verification subprocess termination. Whole-project tests cover the existing
single-agent, reuse/migration, generated-workflow and security gates.

`tests/test_mcp_iteration.py` exercises application and login with deterministic
fixture proposals and automatic test callbacks. They establish server/transport
behavior, not human production authorization, new live identity login or a model
success rate. Historical 0.2.0/0.3.0 model trials remain historical.

Source and independent installed-wheel suites each passed 164 tests plus six
example subtests at the recorded checkpoint. The clean wheel contains 30 package
files and nine schemas, no builder CLI or console entry points; package payload
hashes match source. Final commands and real SDK results are recorded in
`mcp-0.4-*` evidence.

A real installed-MCP read-only trial reached the configured SDK/runtime and
completed its first turn, but the current default CatPaw IDE backend rejected
the second turn's structured-output parameter. Its operation is **failed**,
verification **not_run**. Five stage notifications, exact repeat-result identity,
event retrieval and target preservation passed. This is a provider limitation,
not a successful workflow construction or a reason to bypass the schema. No
global model/provider setting was changed.

A separate installed-MCP trial explicitly selected catalog model `gpt-6.1-sol`
through process-local `BUILD_MAS_MODEL`: two real SDK turns completed, reporting
53,498 tokens and 20.29 seconds. Eight monotonic progress notifications, 27
readable events, exact repeat-result identity and target preservation passed.
Verification remains **not_run** because this was read-only explanation, not
construction/application acceptance. The failed default-provider trial is retained.

Three additional real installed-MCP SDK cases completed: new-workflow planning
selected one Agent and required a Codex smoke check; existing-SDK analysis
preserved its runtime; other-framework migration planning selected one Agent,
required migration retirement and Codex smoke checks, and kept parity unverified.
All fixture targets stayed unchanged. These are architecture/analysis acceptance,
not newly generated-code application, production parity or user-authorized writes.

A new actual Codex ephemeral host session loaded the installed 0.4.0 Skill/plugin,
called preflight and registration, returned API 0.4, reported form/URL
capabilities, and exited 0 with its target unchanged. Unrelated pre-existing MCP
authentication warnings are not build-mas failures. No human apply or identity
login was attempted.

A real single-agent construction trial prepared a ten-file proposal: six offline
checks passed and one live SDK check remained approval-gated (`pending_live`).
The user-owned file and target directory were preserved. A separate existing-SDK
edit trial selected runtime reuse but failed because its generated unittest
pattern discovered zero tests; two bounded repairs did not fix the pattern.
The service correctly rejected the candidate and left the target unchanged.
These trials are retained in `mcp-0.4-construction.json`, not labelled complete
application or a general generation success rate.

A follow-up fresh edit fixture specified the exact unittest file path and still
failed safely: its builder produced no actual changes (`empty_proposal`), so no
proposal/application was accepted. The original runtime and target files remained
unchanged. `mcp-0.4-edit-explicit.json` preserves this unresolved live editing
reliability limit; deterministic edit/regression coverage is not substituted for
real successful candidate generation.

## Host support matrix

| Host | Adapter | 0.4.0 tool/record path | Progress | Human form approval | New identity login |
| --- | --- | --- | --- | --- | --- |
| Codex | Local Skill + stdio plugin | Installed 0.4.0 plugin, launcher and actual Codex host preflight/register | Declared capability / pending UI acceptance | Pending real human UI acceptance | Pending user identity acceptance |
| Claude Code | Session Skill + same stdio service | Adapter contract regression; pending current host commissioning | Pending current host UI acceptance | Pending real human UI acceptance | Pending user identity acceptance |
| OpenCode V2 | MCP configuration + host instructions | Configuration regression; pending current host commissioning | Pending current host UI acceptance | Pending real human UI acceptance | Pending user identity acceptance |
| MCP Python client | Real stdio, legacy and modern | Automated schema/read/approval/replay tests | Request callback regression | Deterministic test callback only | Deterministic SDK/auth callback only |

Basic tool access enables inspection and proposals. Do not advertise complete
apply/login support until that host's real user-only interaction is accepted.
Capability metadata never proves the response came from a human.

## Sources and remaining limits

- [MCP Python SDK 2.3.0 migration](https://github.com/modelcontextprotocol/python-sdk/blob/v2.3.0/docs/migration.md): protocol-era confirmation, progress and official Tasks extension not yet implemented in this dependency.
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk): public runtime/login/turn boundary; this iteration does not upgrade the pinned runtime.
- [RICH generation feedback](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/confirm-generation-process.zh-CN.md): phase feedback and clear error/termination reporting; not authority to expose private reasoning or auto-approve.
- Architecture Skill checked against canonical commit `da245f8cbfc4c358e8c3cde61dbb703bd40292bc` (version 1.18.0) using the isolated coherent snapshot; installed/customized Skill packages were not overwritten.

No Windows/Linux commissioning, remote-provider universality, paid metering,
durable background completion or public release is claimed. Private-state and
OS-sandbox assumptions remain those of the existing local builder.
