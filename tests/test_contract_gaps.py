import copy

import pytest

from build_mas.contracts import ArchitectureSpec


def test_prose_is_not_executable_verification(spec_dict):
    data = copy.deepcopy(spec_dict)
    data["verification"]["checks"].append({"id": "test", "kind": "unittest", "target": "tests/test_workflow.py", "expected": "all tests pass"})
    with pytest.raises(ValueError, match="literal output marker"):
        ArchitectureSpec.model_validate(data)


def test_final_packet_must_match_public_contract(spec_dict):
    spec_dict["outputs_schema"] = {"type": "array"}
    with pytest.raises(ValueError, match="final packet schema"):
        ArchitectureSpec.model_validate(spec_dict)


def test_skill_cannot_self_promote(spec_dict):
    spec_dict["skills"] = [{"name": "facts", "trigger": "Extract facts", "procedure": "Use facts", "eval_cases": ["extract"], "lifecycle": "verified"}]
    with pytest.raises(ValueError, match="host evidence ledger"):
        ArchitectureSpec.model_validate(spec_dict)


def test_generated_check_cannot_confuse_operation_and_workflow_status(spec_dict):
    spec_dict["runtime"] = {"source": "none", "target": "codex_sdk", "action": "new"}
    spec_dict["verification"]["checks"].append({"id": "live", "kind": "codex_smoke", "target": "workflow.py", "arguments": ["run"], "expected": {"type": "object", "properties": {"status": {"const": "completed"}}}})
    with pytest.raises(ValueError, match="status is passed"):
        ArchitectureSpec.model_validate(spec_dict)
