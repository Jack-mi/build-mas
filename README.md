# build-mas

A small, skill-only Codex plugin for learning, building, and adapting agentic workflows with the Python Codex SDK. It accepts a rough goal, task description, diagram, document, URL, codebase, existing workflow, or failing trace. For existing systems it inspects the actual flow and makes a scoped change instead of rebuilding by default. It provides design guidance and a read-only two-role example; it does not install the SDK, register tools, grant permissions, or create agents automatically. The separate `agents-best-practices` skill is an optional architecture input, not bundled code. Multi-agent code review is a possible future teaching case, not an implemented feature.

This plugin currently **implements only the Codex Python SDK path**. A separate workflow collection documents reproduced external examples; listing an example there does not mean this plugin implements it. Claude Code and OpenCode support are future work, not current adapters.

## Layout

- `plugin.json`: portable plugin identity.
- `skills/build-mas/SKILL.md`: activation, architectural decision flow, SDK mapping.
- `examples/minimal_mas.py`: one worker and one independent verifier on separate threads. The host passes worker output as an `ExternalMessage`, checks the turn status, and rejects `failed`, `blocked`, malformed, or evidence-free verdicts.
- `examples/test_minimal_mas.py`: offline check for the read-only and untrusted-data boundaries.

## Try the example

```sh
python3 -m unittest discover -s examples -p 'test_*.py'
python3 -m pip install openai-codex
python3 examples/minimal_mas.py "Review the documentation gaps" --cwd /path/to/repository
```

Run the final command with a real repository path and an authenticated Codex session. The SDK installs its matching CLI runtime. The two example threads are ephemeral, so they are not saved to the Codex sidebar or available to resume after the process ends. The example is intentionally serial: first prove that a separate verifier improves outcomes, then consider parallel independent workers and an explicit integration step. A `passed` verdict requires evidence, but the host does not independently prove each evidence statement true.

## Try the plugin locally

The repository includes a local [marketplace](https://developers.openai.com/codex/plugins/build#build-your-own-curated-plugin-list). Register and install it with:

```sh
codex plugin marketplace add "$PWD"
codex plugin add build-mas@build-mas-local
```

Example requests: "I have a rough task flow; design the smallest Codex SDK workflow"; "Here is a diagram—explain and implement it"; "Inspect this existing workflow and add a verifier without changing its public behavior"; "Read this failed run and diagnose the first broken boundary." The plugin does not ship a dedicated code-review agent.

The example and skill were checked against the [official Python SDK docs](https://github.com/openai/codex/tree/main/sdk/python) and [plugin packaging guide](https://developers.openai.com/codex/plugins/build) on 2026-10-08. Recheck APIs when building a new project.
