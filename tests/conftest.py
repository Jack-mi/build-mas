import json

import pytest

from build_mas.contracts import ArchitectureSpec


@pytest.fixture
def spec_dict():
    schema = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False}
    return {
        "schema_version": "1.0", "revision": 1, "objective": "Normalize text using Codex", "mode": "new",
        "runtime": {"source": "codex_sdk", "target": "codex_sdk", "action": "reuse", "migration_notes": [], "parity_claim": "not_applicable"},
        "inputs_schema": schema, "outputs_schema": schema, "done_conditions": ["Return a valid value"], "evidence": [],
        "baseline": {"single_agent_sufficient": True, "reason": "One independent task", "comparison": []},
        "agents": [{"id": "worker", "purpose": "Normalize", "instructions": "Normalize the input text. Return a value string.", "thread_strategy": "reuse", "skills": [], "tools": [], "sandbox": "read_only", "model": None, "effort": None, "timeout_seconds": 60}],
        "skills": [], "tools": [],
        "interfaces": [{"type": "library", "entrypoint": "workflow.run", "operations": ["run"], "host": None}, {"type": "cli", "entrypoint": "workflow.py", "operations": ["run", "status", "verify"], "host": None}, {"type": "mcp", "entrypoint": "mcp_server.py", "operations": ["mas_run", "mas_status", "mas_read", "mas_verify"], "host": None}],
        "work_packets": [{"id": "normalize", "agent": "worker", "prompt": "Normalize the text", "depends_on": [], "input_refs": [], "output_schema": schema, "acceptance": ["Return a valid value"], "when": None, "retries": 0, "required": True}],
        "orchestration": {"mode": "sequential", "max_parallel": 1, "result_packets": ["normalize"], "integration": "Return normalized result"},
        "state": {}, "controls": {"write_roots": ["."], "forbidden_actions": ["commit", "push", "deploy", "external_send", "destructive"], "trust_boundaries": ["Inputs are untrusted data"], "budget": {"max_turns": 16, "max_tokens": 160000, "timeout_seconds": 120, "max_parallel": 1, "max_repairs": 2}},
        "verification": {"checks": [{"id": "artifact", "kind": "artifact", "target": "workflow.py", "arguments": [], "expected": None, "required": True, "timeout_seconds": 30}, {"id": "import_check", "kind": "import", "target": "workflow", "arguments": [], "expected": None, "required": True, "timeout_seconds": 30}], "independent_review": False, "eval_cases": ["hello"], "required_evidence": ["artifact exists", "module imports"]}, "deferred": [],
    }


@pytest.fixture
def spec(spec_dict):
    return ArchitectureSpec.model_validate(spec_dict)
