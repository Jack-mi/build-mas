# build-mas 0.3.0 MCP-only migration acceptance

Date: 2026-11-09. Scope: remove the builder CLI, preserve Skill + MCP, add no hooks, and document commercialization without implementing it. No commit, push, deployment or payment setup is included.

## Current implementation

- `src/build_mas/cli.py` and the `build-mas` / `buildmas` console scripts are removed. The installed package and clean wheel contain neither the module nor entry-point metadata; old console executables are absent from the updated private environment.
- `python -m build_mas.mcp_server` starts stdio directly. `BUILD_MAS_HOME`, optional `BUILD_MAS_MODEL` and `BUILD_MAS_ALLOW_APPLY=1` select state, model and application-tool exposure. Exposure is not approval.
- Root, Codex, Claude Code and OpenCode adapters use the direct MCP module. Codex/Claude launchers take no old operation arguments. OpenCode V2 uses its documented `environment` field.
- Nine tools are available by default: register, import, login, recover, preflight, invoke, verify, status and read. Apply is the tenth tool when explicitly enabled.
- Skill guidance uses MCP for the complete builder lifecycle. No Hook is added. Generated workflow templates, their library/CLI/task-level MCP and Codex SDK runtime dependencies are unchanged.
- Application presents every diff page, then requires final human form elicitation; decline, unavailable elicitation and changes during review prevent target writes. Login uses user-only URL elicitation, cancels declined/unavailable/timed-out attempts and never asks the model for credentials.

## Verified evidence

| Requirement | Observed evidence | Scope |
| --- | --- | --- |
| Regression | `133 passed, 6 subtests passed` from `python -m pytest -q tests examples`; `git diff --check` passes | Repository unit/integration suite; fake model fixtures remain fixtures |
| Installed distribution | Clean 0.3.0 wheel installed into an independent temporary venv; package lives in site-packages, has no builder CLI or console entry points | Real package installation, not editable-source-only evidence |
| Local upgrade | Bootstrap updates only the private builder environment; version 0.3.0 and all 23 packaged source/schema/reference/template files match the repository | Existing private state directories retained; no target dependency install |
| Plugin | `codex plugin add build-mas@build-mas-local --json` returns installed 0.3.0; cached manifest, MCP config, launcher and Skill match source bytes | Local install/enablement; not public-directory submission |
| Actual Codex host | A new ephemeral Codex chat discovers the installed 0.3.0 Skill and calls `buildmas_preflight` and `buildmas_register` successfully; process exit 0, target fixture unchanged | Existing user configuration with the new local plugin; no builder CLI operation |
| MCP launch | Independent installed module and installed Codex plugin launcher both initialize as 0.3.0 and list ten enabled tools from an unrelated cwd | Actual stdio handshake and tool calls, no builder CLI |
| Registration/import | Actual installed stdio calls return workspace and asset IDs; selected fixture target stays unchanged | Selected temporary project and attachment |
| SDK readiness | Installed MCP preflight returns ready, account_present true, SDK/runtime 0.167.0 | Current configured local provider; not all providers |
| Real invoke | Installed MCP explains a one-file fixture using two real SDK turns, 36,156 reported tokens; status completed, verification not_run, changed_files empty | Read-only inference acceptance, not new generated-workflow production acceptance |
| Repeat/read/status | Repeating the same request returns the identical result; status is completed and bounded read returns the recorded run | Actual installed MCP, one logical request |
| Approval/apply/verify | Installed stdio without elicitation leaves target unchanged; decline rejects; accepted exact fixture proposal writes its declared file; verify passes | Real transport/approval/filesystem; deterministic fixture, no invented human production authorization |
| Recovery | Installed MCP reconciles an admitted interrupted apply as completed recovery, original run failed, target unchanged | Properly recorded proposal/admission; no blind write replay |
| Large approvals | Tests show both pages, final-only approval, decline at final page, and changed-proposal hash rejection | Fake human callbacks exercising adapter boundaries |
| Authentication | Tests cover required user-only confirmation, accept/decline/unavailable, timeout/failed login, handle cancellation and client closure | Fake SDK/auth callbacks; no new identity login completed |

The first wheel inspection found a stale generated `build/` directory carrying the deleted module. That cache was relocated, the wheel rebuilt and the private package reinstalled. Absence of CLI files was then checked in both the clean wheel and the installed package; source deletion alone was not treated as enough.

An isolated temporary-CODEX_HOME full Codex chat probe timed out after 180 seconds and is not counted as success. A subsequent new chat using the actual existing user configuration and installed local plugin completed preflight and registration successfully. This proves that local host path, not the cause of the isolated-config timeout. Existing open chats can retain older tool metadata until reconnect or a new chat.

## Remaining limits

- No paid/remote/multi-tenant implementation, payment transaction, commercial account authorization or cloud sandbox acceptance is claimed. `commercialization-plan.md` is a proposal only.
- Actual new browser/device login requires the user's identity and a client supporting URL elicitation. Without that channel, it fails closed. Form elicitation is independently required for apply.
- This migration does not rerun every historical 0.2.0 production-like generation trial or validate Windows/Linux host commissioning. Historical evidence stays historical.
- Existing open Codex chats are not forcibly restarted. Installed 0.3.0 is used by new MCP launches; refresh/reconnect is needed to discover additional tool names in an already-open chat.

## Sources

- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk): pinned runtime and public Python app-server boundary.
- [OpenCode V2 local MCP](https://opencode.ai/v2/docs/mcp-servers): command/interpreter and `environment` configuration.
- [RICH confirmation](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/confirm.zh-CN.md): explicit consent for high-cost or irreversible effects; design reference, not authority to auto-approve.
