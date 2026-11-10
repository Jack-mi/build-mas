# 0.4.1: feedback-driven retrieval and observability

## Scope and contracts

This iteration addresses the latest selected project analysis feedback without
changing that project, introducing another Agent/runtime, weakening approvals,
or publishing a release. API/record version stays `0.4`; package/plugin version
is `0.4.1`, with the existing pinned Codex SDK/runtime `0.167.0`.

1. **Materials:** complete selected text is frozen under `_buildmas_inputs`
   with a JSON index, source/content hashes, provenance, character counts and
   private file permissions. Long text contributes only a 256-character preview
   to the model-facing context; small text up to 1,024 characters stays inline.
   The request no longer embeds a second copy of input bodies. The architecture
   and construction contexts use the same indexed evidence. The complete index
   path is established outside the external message, so a shortened message
   does not remove the retrieval route. Full-input secret checks, attachment
   ownership/hash checks and workspace/path protections remain enforced.
2. **Result retrieval:** `buildmas_read(category="results", reference=run_id)`
   pages the full operation result, retaining conclusions, assumptions, checks,
   errors, usage and verification without original input/baseline inventories.
   Existing `runs`, `events` and frozen proposal reads are unchanged. Follow
   character offsets to a null `next_offset`; the summary cap remains 16 KiB.
3. **Scope validation:** registration captures a bounded snapshot before saving
   a workspace. Counts/limits are returned; oversized scopes report partial
   observed counts and their first over-limit path. Workspace preflight checks
   the current scope before starting SDK readiness checks. Invocation still
   captures and compares its own current snapshot; registration is not a lease.
4. **Usage:** stream usage is accounted as it arrives, including failed or
   interrupted turns. Totals distinguish SDK turns, observed inference calls,
   tool calls, input/cached/cache-write/uncached/output/reasoning tokens and turns
   without usage. Duplicate updates and historical usage on resumed threads do
   not charge a new operation. Observed counts are not invoices or guaranteed
   complete provider billing; cancellation does not prove zero charge.
5. **Progress:** the existing request-local notification channel sends material
   and usage stages as well as operation stages. `progress` and
   `request_progress_token` indicate only the current request token. Service
   support is separately represented by `progress_notifications`,
   `status_polling` and `event_replay`. Pass a client's progress callback on
   invoke; status/events remain usable without notifications. Delivery failure
   never makes analysis fail or grants approval. No background completion or
   rollback is implied.

`material_coverage.review_status="not_measured"` is intentional. A complete
file being accessible does not prove that the model consumed or understood all
of it. Model-disclosed limitations remain visible. Exact retrieval tests do not
establish general architecture quality, production reliability or token savings.

## Verification ledger

The [receipt](acceptance-evidence/mcp-0.4.1-feedback.json) records source and
independent installed-wheel suites: **178 passed plus six example subtests**
each. Two cases are deliberately deselected: the unrelated PNG portability
baseline failure below and the separately executed live SDK case. All 30 package
files match the installed wheel. Its SHA-256 is
`865e949fde96b179e98afbbd12a4213af7b7ebfecfddad5f285b7db384134e63`.

The selected original 18 materials (15 imported files) were re-projected without
another model analysis: every frozen text and hash matched. The model-facing
envelope shrank from **257,403 to 42,594 bytes (83.45%)**; character counts fell
from 192,473 to 38,608. This is exact projection evidence, not measured token,
latency, billed-cost or semantic-quality improvement.

A real installed-SDK stdio fixture read the hidden tail of a **220,043-character**
attachment, returned the expected evidence, and left the target unchanged. It
completed in 27.16 seconds with two SDK turns, four observed inference calls,
76,143 total tokens (40,407 cached input), and **14 progress notifications**.
The result correctly retained `verification="not_run"` and unmeasured material
review. Separate actual-stdio regression covers full result pagination after
summary truncation and subscriber isolation; failed notification delivery does
not fail the operation.

The local private environment and Codex plugin are refreshed to `0.4.1` using
their supported package/plugin installers. A fresh ephemeral Codex host called
preflight exactly once and returned all new request/service capability fields.
It still supplied no request progress token; actual desktop invoke progress UI
is not claimed. Existing connected MCP processes keep their already-loaded
module/schema until reconnect or a new chat; they were not forcibly stopped.
Historical results were readable through the new result view without changing
their original records. No commit, push, release, deployment, target-project
changes or business workflow execution occurred.

The historical 0.4.0 receipts are not relabelled as 0.4.1 acceptance.

The pre-change complete source suite returned 163 passed and six example
subtests, with one unrelated failure: the portability check treats every file
under docs as UTF-8 text, while a concurrent documentation task added a PNG.
This iteration preserves that task's image and document edits; it does not
weaken unrelated tests or silently claim an all-green baseline.

## Sources and boundaries

- Architecture guidance: agents-best-practices `1.18.0`, canonical commit
  `da245f8cbfc4c358e8c3cde61dbb703bd40292bc`, rechecked 2026-11-09.
- Official Codex Python SDK `ExternalMessage` and token-usage contracts:
  [API reference](https://github.com/openai/codex/blob/main/sdk/python/docs/api-reference.md)
  and [usage protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server-protocol/src/protocol/v2/thread.rs).
  Public SDK exports and the pinned installed runtime remain authoritative.
- Relevant RICH guidance: [Error, lines 23-26](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/error.zh-CN.md#L23),
  early explicit errors, actionable recovery and retained diagnostics. This is
  interaction guidance, not a requirement to adopt Ant Design X components.
- Product-methods: the locally read *Simple and Usable* transfer strategy moves
  retrieval/state complexity to the system without concealing limitations or
  taking approval away from the user.
