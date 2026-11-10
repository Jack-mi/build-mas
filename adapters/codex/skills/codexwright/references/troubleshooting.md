# Safe recovery

| Signal | Meaning | Safe action |
| --- | --- | --- |
| `invalid_input` | Missing key, unsupported field or malformed value | Fix the named field; validation does not authorize execution |
| `workspace_too_large` | Registration or refreshed preflight exceeds snapshot limits | Inspect `error.details` limits/partial counts/path; register a narrower selected directory and explicitly import relevant outside documents |
| `idempotency_conflict` | Same key, different logical request | Keep the original key for original input; use a new key for new intent |
| `running` | Original run still owns the workspace | Read status/events; do not recover or start overlapping work |
| `outcome_unknown` | Completion is not established | Inspect original run and backups; recover without replaying effects |
| `permission_denied` | User rejected confirmation | Stop; another attempt needs new user intent and a new key |
| `approval_expired`, `review_restarted` | Review expired or server restarted | New key, complete review from page one, new human approval |
| `stale_proposal`, `stale_revision`, `workspace_conflict` | Reviewed data no longer matches | Prepare a new scoped proposal; never force apply |
| `approval_channel_unavailable` | Client cannot present human form approval | Analysis/proposals remain available; use a verified supporting client |
| `login_channel_unavailable`, `login_expired` | No user-only URL channel or expired login | Use a supporting client; never paste keys, passwords or device codes into chat |

MCP protocol confirmation state is not an approval grant. Do not alter it. Clients that stop after too many confirmation rounds leave the target unchanged; increase the client's supported round limit or reduce the proposed change, never skip diff pages.

`preflight.capabilities` reports declared protocol features, not evidence that a human personally approved anything. An existing account can remain usable even if the current client lacks login UI. Only runtime-specific installed SDK execution proves a model call worked; catalog availability is not account or task success.

`progress:false` means this request lacks a progress token. It does not mean the service has no progress implementation. Supply the MCP client's progress callback on invoke, or inspect original status/events; never restart a run just to obtain feedback. Read `category="results"` for full conclusions when the summary is shortened. Material availability and token telemetry do not prove full model review, successful verification, billed cost or a performance improvement.
