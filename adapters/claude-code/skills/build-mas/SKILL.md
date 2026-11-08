---
name: build-mas
description: Build, edit, diagnose, migrate or verify agentic workflows at any task stage using the shared build-mas Codex SDK service. Accept goals, source code, diagrams, diffs and traces.
---

# build-mas

Call the buildmas MCP service rather than implementing architecture or agents with Claude's runtime.

1. Check `buildmas_preflight`; missing builder SDK or Codex authentication never triggers a Claude fallback.
2. Register the project once with the installed `build-mas register` CLI and use the returned workspace ID.
3. Call `buildmas_invoke` with the user's actual request, relevant selected materials and existing session ID. Do not copy unrelated conversation or credentials.
4. Reuse the session on follow-up. The service can analyze, plan, build, edit, diagnose, migrate, refactor or verify. Other source frameworks are migrated to Codex SDK; existing Codex workflows are reused.
5. Invoke only creates analysis or a proposal. Read the exact diff using `buildmas_read`, explain scope and verification, and obtain the user's approval before `buildmas_apply`. Never create or fabricate an approval reference.
6. MCP apply uses real elicitation when supported; otherwise request local CLI approval. Do not bypass a denied approval by switching interfaces.
7. Distinguish candidate verification, applied state, failed checks and unknown outcomes. Use status/read to fetch receipts and large output. No commit, push, deploy or external send is implied.

Target plugins, HTTP and resident services are optional. CLI and MCP expose the workflow as one task-level service, not every internal agent.
