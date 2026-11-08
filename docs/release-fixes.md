# Public Release Fix Ledger

The 2026-11-08 review found gaps after the earlier local acceptance. Earlier
green fixtures are historical evidence, not proof that these gaps are fixed.
Current review fixes and acceptance below are dated 2026-11-09.

- [x] 1. Isolate generated SDK config and reject undeclared actual tool calls. Real no-tools probe excludes the injected global MCP; actual declared calls have schema-valid receipts.
- [x] 2. Remove environment-controlled and inherited-policy sandbox bypass. Project tools always receive an independent sandbox; isolated SDK auth, outside paths, .env variants and nested credentials are denied. Frozen live verification uses package-owned code, not an imported target harness; structural failure blocks all candidate checks.
- [x] 3. Bind existing-project checks to the owning target environment, including approved apply staging. Target-only dependency passes through real installed CLI/MCP apply; unrelated workspaces cannot supply their venv. No automatic package installation is implied.
- [x] 4. Keep generated CLI/MCP state outside installed packages. Real installed read-only target runs, unchanged package bytes, private external checkpoint, and shared structured CLI/MCP results verified.
- [x] 5. Validate executable tool bindings. Only bounded read_file/list_files builtins, Python CLI modules, and project-local Python stdio MCP implementations are enabled; deterministic and real SDK tool receipts pass.
- [x] 6. Preserve and block unresolved builder/reviewer findings. Explicit incomplete builder result cannot produce a proposal; reviewer gaps fail the application gate.
- [x] 7. Discover exact executable/runtime dependencies without a Homebrew-prefix grant. Custom executable prefix and actual sandboxed PDF extraction pass; dyld runpaths are resolved from executable metadata.
- [x] 8. Kill over-limit subprocesses while reading, including stderr/PDF, timeout, and child-process cleanup. No unbounded communicate allocation remains in project execution paths.
- [x] 9. Redact historical machine paths and full PATH values, preserving original failures/IDs/scope; refresh hashes. Public portability and embedded-receipt redaction regressions pass. Original raw records are retained privately outside the repository.
- [x] 10. Rewrite the homepage around the CLI/MCP product, distinguish builder from generated workflow, document host adapters and actual supported limits. Pushed remote README bytes match the local product introduction.
- [x] 11. Commit/push all authorized project changes, set repository public, and verify actual remote HEAD, README/source, and unauthenticated access. Implementation commit `72a5cdaea79713e2d282903c691557c11b28861a` is on main; unauthenticated repository API returns 200/public and six README/package/CLI/MCP/template files match exactly.

## Current Acceptance

- `acceptance-evidence/release-live.json`: real SDK Skill + CLI, builtin + project MCP, and no-tools MCP isolation; each test is scoped to the current local-provider environment.
- `acceptance-evidence/release-installed.json`: independently installed builder/target, actual CLI/MCP apply with target-only dependency, package read-only/state portability, and real target Skill/tool receipt.
- `acceptance-evidence/release-construction.json`: current installed builder recovers a fresh retained candidate after import-file support was fixed, without regenerating its code; approved application and all required checks pass, one Agent and existing user data preserved. This is recovery validation, not an untouched holdout success.
- `release-construction-initial.json`, `release-construction-status-gap.json`, and `release-construction-import-gap.json` preserve failed earlier trials. Installed-interpreter/host-check guidance, the passed-versus-completed contract guard, and sandboxed Python-file import support address their earliest boundaries without relabelling outcomes.
- Final source and independently installed wheel suites: **108 passed + 6 example subtests passed** in each environment. Five exported schemas, package/source bytes, public portability, and secret/whitespace checks agree.
- `acceptance-evidence/manifest.json` keeps historical 80-test/wheel records separate from current release suite and package hashes.
- `acceptance-evidence/release-publication.json` records the observed public implementation commit and remote file hashes. A follow-up documentation-only commit records these completed publication checks without amending implementation history.

## Source And Product Boundaries

Architecture guidance remains agents-best-practices 1.18.0 at
`da245f8cbfc4c358e8c3cde61dbb703bd40292bc`, reverified upstream for this task.
Official SDK docs were fetched again on 2026-11-09; public SDK/runtime APIs
remain pinned to `0.167.0`. No private SDK API is used for policy enforcement.
RICH [explicit confirmation](https://github.com/ant-design/x/blob/8b76d6a22067945c5d224c02ee1448dfb30144ff/packages/x/docs/spec/confirm.zh-CN.md#L17)
guidance applies to visible approvals/states, with no hidden reasoning exposed.

CLI/MCP are core service forms for build-mas itself and its generated workflows.
Target plugins, HTTP services, and resident workers are optional, not mandatory
scaffolds. Single-Agent-first is already enforced and was not redesigned.

macOS is commissioned. Linux/Windows, production reliability, remote-model
connectivity, and unavailable original-framework execution parity remain outside
validated scope. No license, PyPI release, deployment, or host-directory
publication has been selected or claimed.
