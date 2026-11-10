# Codexwright 0.5.0 Rename And Migration

`build-mas` is now `codexwright`. Version 0.5.0 renames the public package,
plugin, Skills and MCP contract together rather than leaving the old name in
day-to-day installation and tool calls.

## Identifier Mapping

| 0.4.x and earlier | 0.5.0 |
| --- | --- |
| `build-mas` distribution/plugin/Skill | `codexwright` |
| `build_mas` Python package | `codexwright` |
| `buildmas` MCP server key | `codexwright` |
| `buildmas_*` MCP tools | `codexwright_*` |
| `buildmas://` resources | `codexwright://` |
| `BUILD_MAS_*` environment variables | `CODEXWRIGHT_*` |
| `~/.local/share/build-mas` default state | `~/.local/share/codexwright` |
| `_buildmas_inputs` staged materials | `_codexwright_inputs` |

The generated workflow's generic `mas` CLI and `mas_*` task-level MCP tools are
unchanged. They belong to the generated product, not to the builder's brand.

## Upgrade

1. Run `python3 scripts/bootstrap.py` from the renamed repository. This installs
   a private environment under `~/.local/share/codexwright/venv` by default.
2. Replace the old local plugin with `codexwright` from `codexwright-local`, or
   update the host's MCP configuration to launch `python -m codexwright.mcp_server`.
3. Replace `buildmas_*` tool calls and `BUILD_MAS_*` variables in automation.
   For OpenCode, update the apply permission action to
   `codexwright_codexwright_apply`.
4. Reconnect or restart the host so it refreshes MCP tool metadata. Existing
   chats may contain old tool names and should not be treated as upgraded proof.

The GitHub repository is now `https://github.com/Jack-mi/codexwright`. Installation
links clone it into a local `codexwright` directory. Existing checkouts should
switch their remote with:

```sh
git remote set-url origin git@github.com:Jack-mi/codexwright.git
```

## State Compatibility

An explicit `CODEXWRIGHT_HOME` takes precedence. The former `BUILD_MAS_HOME` is
still accepted as a fallback. Without either variable, an existing
`~/.local/share/build-mas` directory is used while the new default has no state
records. A bootstrap-created `venv` alone does not count as state. Once the new
location contains state, it takes precedence; an explicit home can select either.

This fallback keeps existing workspaces, sessions, runs and proposals reachable
without moving live state. It does not rewrite historical records. Verification
also supplies the former `BUILD_MAS_TEST_HOME` alongside `CODEXWRIGHT_TEST_HOME`
so previously generated workflow templates retain their test-state behavior.

## Historical Evidence

The 0.2–0.4 acceptance documents, evidence JSON and old wheels are frozen. They
prove only the old-named releases and are not presented as 0.5.0 commissioning.
Current rename verification is recorded separately after source and clean-wheel
tests complete.

The local verification record is
[`acceptance-evidence/codexwright-0.5-rename.json`](acceptance-evidence/codexwright-0.5-rename.json).
