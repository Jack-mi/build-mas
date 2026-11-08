import asyncio
import copy
import importlib.util
import json
from types import SimpleNamespace

import pytest

from build_mas.target import scaffold


def load(root):
    module_spec = importlib.util.spec_from_file_location("generated_workflow_fixture", root / "workflow.py")
    module = importlib.util.module_from_spec(module_spec)
    import sys
    sys.modules.pop("execution", None)
    sys.path.insert(0, str(root))
    try:
        module_spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class FakeCodex:
    active = 0
    peak = 0
    starts = []
    fail = False
    inputs = []

    def __init__(self, config=None):
        self.config = config

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def thread_start(self, **kwargs):
        self.starts.append(kwargs)
        return FakeThread(f"thread_{len(self.starts)}")

    async def thread_resume(self, thread_id, **kwargs):
        return FakeThread(thread_id)


class FakeThread:
    def __init__(self, name):
        self.id = name

    async def turn(self, value, **kwargs):
        FakeCodex.inputs.append(value)
        schema = kwargs.get("output_schema")

        class Handle:
            id = "turn_fixture"
            async def run(self):
                FakeCodex.active += 1
                FakeCodex.peak = max(FakeCodex.peak, FakeCodex.active)
                await asyncio.sleep(.01)
                FakeCodex.active -= 1
                if FakeCodex.fail and schema:
                    return SimpleNamespace(status="failed", error="fixture failure", final_response=None, usage=None)
                return SimpleNamespace(id=self.id, status="completed", error=None, final_response=json.dumps({"value": "OK"}) if schema else "READY", usage=None, items=[])

            async def interrupt(self):
                pass

        return Handle()


def test_standalone_run_schema_and_checkpoint(tmp_path, spec, monkeypatch):
    root = tmp_path / "generated"; root.mkdir()
    scaffold(root, spec)
    module = load(root)
    monkeypatch.setattr(module, "AsyncCodex", FakeCodex)
    FakeCodex.starts, FakeCodex.inputs, FakeCodex.fail = [], [], False
    checkpoint = tmp_path / "runs/latest.json"
    result = asyncio.run(module.run({"value": "hello"}, state_path=checkpoint))
    assert result["status"] == "passed" and result["output"] == {"value": "OK"}
    assert len(FakeCodex.starts) == 1
    assert asyncio.run(module.run({"value": "hello"}, state_path=checkpoint)) == result
    with pytest.raises(ValueError, match="different inputs"):
        asyncio.run(module.run({"value": "changed"}, state_path=checkpoint))
    with pytest.raises(Exception):
        asyncio.run(module.run({"missing": "hello"}))
    assert "build_mas" not in (root / "workflow.py").read_text()


def test_parallel_dag_handoff_and_failure(tmp_path, spec_dict, monkeypatch):
    from build_mas.contracts import ArchitectureSpec
    from openai_codex import ExternalMessage

    data = copy.deepcopy(spec_dict)
    data["baseline"] = {"single_agent_sufficient": False, "reason": "Independent branches plus verifier", "comparison": ["Independent branch coverage benefits from parallel runs"]}
    second = {**data["agents"][0], "id": "other"}
    third = {**data["agents"][0], "id": "verifier"}
    data["agents"] += [second, third]
    data["work_packets"] += [{**data["work_packets"][0], "id": "branch", "agent": "other"}, {**data["work_packets"][0], "id": "join", "agent": "verifier", "depends_on": ["normalize", "branch"]}]
    data["orchestration"].update(mode="parallel", max_parallel=2, result_packets=["join"])
    data["controls"]["budget"]["max_parallel"] = 2
    root = tmp_path / "generated"; root.mkdir(); scaffold(root, ArchitectureSpec.model_validate(data))
    module = load(root); monkeypatch.setattr(module, "AsyncCodex", FakeCodex)
    FakeCodex.starts, FakeCodex.inputs, FakeCodex.fail, FakeCodex.peak = [], [], False, 0
    result = asyncio.run(module.run({"value": "hello"}))
    assert result["status"] == "passed" and FakeCodex.peak == 2
    assert any(isinstance(value, ExternalMessage) for value in FakeCodex.inputs)
    FakeCodex.fail = True
    result = asyncio.run(module.run({"value": "hello"}))
    assert result["status"] == "failed" and result["packets"]["join"]["status"] == "blocked"
    FakeCodex.fail = False


def test_checkpoint_unknown_is_not_replayed(tmp_path, spec, monkeypatch):
    root = tmp_path / "generated"; root.mkdir(); scaffold(root, spec)
    module = load(root); monkeypatch.setattr(module, "AsyncCodex", FakeCodex)
    checkpoint = tmp_path / "checkpoint.json"
    import hashlib
    identity = hashlib.sha256(json.dumps({"spec": module.SPEC, "input": {"value": "hello"}}, sort_keys=True).encode()).hexdigest()
    checkpoint.write_text(json.dumps({"identity": identity, "status": "running", "packets": {"normalize": {"status": "outcome_unknown"}}}))
    with pytest.raises(RuntimeError, match="unknown outcome"):
        asyncio.run(module.run({"value": "hello"}, state_path=checkpoint))
