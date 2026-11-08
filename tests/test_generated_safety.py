import asyncio
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from build_mas.contracts import ArchitectureSpec
from build_mas.target import scaffold
from build_mas.verify import structure_check
from test_generated_workflow import FakeCodex, load


def generated(tmp_path, spec, monkeypatch):
    root = tmp_path / "generated"; root.mkdir()
    scaffold(root, spec)
    module = load(root)
    monkeypatch.setattr(module, "AsyncCodex", FakeCodex)
    FakeCodex.starts, FakeCodex.inputs, FakeCodex.fail = [], [], False
    return root, module


def test_asserted_packet_retry_is_bounded(tmp_path, spec_dict, monkeypatch):
    data = copy.deepcopy(spec_dict)
    data["work_packets"][0].update(retries=2, assertions=[{"field": "value", "operator": "equals", "value": "NOT OK"}])
    _, module = generated(tmp_path, ArchitectureSpec.model_validate(data), monkeypatch)
    result = asyncio.run(module.run({"value": "hello"}))
    assert result["status"] == "failed" and result["turns"] == 3


def test_writes_need_explicit_authority_and_narrow_paths(tmp_path, spec_dict, monkeypatch):
    data = copy.deepcopy(spec_dict)
    data["agents"][0]["sandbox"] = "workspace_write"
    _, module = generated(tmp_path, ArchitectureSpec.model_validate(data), monkeypatch)
    module.SPEC["controls"]["write_roots"] = ["output"]
    with pytest.raises(PermissionError):
        asyncio.run(module.run({"value": "hello"}))
    result = asyncio.run(module.run({"value": "hello"}, approve_writes=True))
    assert result["status"] == "passed"
    permissions = FakeCodex.starts[-1]["config"]["permissions"]["workflow"]["filesystem"]
    assert permissions[str(module.ROOT)] == "read"
    assert permissions[str(module.ROOT / "output")] == "write"


def test_forged_passed_checkpoint_is_not_accepted(tmp_path, spec, monkeypatch):
    _, module = generated(tmp_path, spec, monkeypatch)
    path = tmp_path / "checkpoint.json"
    result = asyncio.run(module.run({"value": "hello"}, state_path=path))
    result["output"] = {"value": "FORGED"}
    path.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="differs from packet"):
        asyncio.run(module.run({"value": "hello"}, state_path=path))


def test_conditional_branch_and_missing_dependency(tmp_path, spec_dict, monkeypatch):
    data = copy.deepcopy(spec_dict)
    data["work_packets"].append({**data["work_packets"][0], "id": "conditional", "depends_on": ["normalize"], "required": False, "when": {"packet": "normalize", "field": "value", "equals": "NO"}})
    _, module = generated(tmp_path, ArchitectureSpec.model_validate(data), monkeypatch)
    result = asyncio.run(module.run({"value": "hello"}))
    assert result["status"] == "passed" and result["packets"]["conditional"]["status"] == "skipped"


def test_skills_are_explicit_and_the_harness_is_frozen(tmp_path, spec_dict, monkeypatch):
    from openai_codex import SkillInput
    data = copy.deepcopy(spec_dict)
    data["skills"] = [{"name": "value-format", "trigger": "Format a repeated text result", "procedure": "Return value OK.", "eval_cases": ["text yields OK"], "lifecycle": "generated"}]
    data["agents"][0]["skills"] = ["value-format"]
    data["work_packets"][0]["assertions"] = [{"field": "value", "operator": "equals", "value": "OK"}]
    data["verification"]["checks"].append({"id": "live", "kind": "codex_smoke", "target": "workflow.py", "arguments": ["run"]})
    data["runtime"] = {"source": "none", "target": "codex_sdk", "action": "new"}
    spec = ArchitectureSpec.model_validate(data)
    root, module = generated(tmp_path, spec, monkeypatch)
    assert structure_check(spec, root)[0]["lifecycle"] == "discovered"
    result = asyncio.run(module.run({"value": "hello"}))
    assert any(isinstance(item, SkillInput) for values in FakeCodex.inputs if isinstance(values, list) for item in values)
    assert result["packets"]["normalize"]["skills"][0]["lifecycle"] == "verified"
    (root / "workflow.py").write_text((root / "workflow.py").read_text() + "\nrun = None\n")
    with pytest.raises(Exception, match="host-owned"):
        structure_check(spec, root)


def test_packet_input_is_scoped_to_declared_fields(tmp_path, spec, monkeypatch):
    _, module = generated(tmp_path, spec, monkeypatch)
    assert module.packet_input({"left": {"ids": ["A"]}, "right": {"ids": ["B"]}}, {"input_refs": ["input.left"]}) == {"left": {"ids": ["A"]}}
    packet = {"output_schema": spec.outputs_schema, "assertions": [{"field": "value", "operator": "input_equals", "value": "input.value", "transform": "upper"}]}
    module.accept(packet, {"value": "HELLO"}, {"value": "hello"})
    with pytest.raises(ValueError):
        module.accept(packet, {"value": "hello"}, {"value": "hello"})


def test_read_only_agents_have_no_write_grants(tmp_path, spec, monkeypatch):
    _, module = generated(tmp_path, spec, monkeypatch)
    result = asyncio.run(module.run({"value": "hello"}))
    assert result["status"] == "passed"
    policy = FakeCodex.starts[-1]["config"]["permissions"]["workflow"]["filesystem"]
    assert "write" not in policy.values()
    assert FakeCodex.starts[-1]["config"]["project_doc_max_bytes"] == 0


def test_cancelled_turn_is_unknown_and_not_resumed(tmp_path, spec, monkeypatch):
    _, module = generated(tmp_path, spec, monkeypatch)
    class CancelledThread:
        id = "cancelled-thread"
        async def turn(self, *args, **kwargs):
            class Handle:
                async def run(self):
                    raise asyncio.CancelledError()
                async def interrupt(self):
                    pass
            return Handle()
    async def start(**kwargs):
        return CancelledThread()
    monkeypatch.setattr(FakeCodex, "thread_start", lambda self, **kwargs: start(**kwargs))
    path = tmp_path / "checkpoint.json"
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(module.run({"value": "hello"}, state_path=path))
    assert json.loads(path.read_text())["packets"]["normalize"]["status"] == "outcome_unknown"
    with pytest.raises(RuntimeError, match="unknown outcome"):
        asyncio.run(module.run({"value": "hello"}, state_path=path))
