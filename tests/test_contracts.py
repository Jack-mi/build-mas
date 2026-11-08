import copy

import pytest

from build_mas.contracts import ArchitectureSpec, IntakeEnvelope, validate_schema
from build_mas.router import resolve_operation


def test_strict_intake_and_material():
    with pytest.raises(ValueError):
        IntakeEnvelope(workspace_id="ws_test", goal="hello", confirmed=True)
    with pytest.raises(ValueError):
        IntakeEnvelope(workspace_id="ws_test")
    with pytest.raises(ValueError):
        IntakeEnvelope(workspace_id="../../escape", goal="hello")
    value = IntakeEnvelope(workspace_id="ws_test", inputs=[{"kind": "trace", "content": "failure", "source": "external"}])
    assert value.inputs[0].source == "external"


@pytest.mark.parametrize("mutation", ["cycle", "unknown_agent", "unknown_result", "multi_single", "external_schema", "write_parallel", "path_escape"])
def test_invalid_spec_is_rejected(spec_dict, mutation):
    value = copy.deepcopy(spec_dict)
    if mutation == "cycle":
        value["work_packets"][0]["depends_on"] = ["normalize"]
    elif mutation == "unknown_agent":
        value["work_packets"][0]["agent"] = "missing"
    elif mutation == "unknown_result":
        value["orchestration"]["result_packets"] = ["missing"]
    elif mutation == "multi_single":
        agent = copy.deepcopy(value["agents"][0]); agent["id"] = "second"
        value["agents"].append(agent)
    elif mutation == "external_schema":
        value["inputs_schema"] = {"$ref": "https://example.com/schema.json"}
    elif mutation == "write_parallel":
        value["agents"][0]["sandbox"] = "workspace_write"
        value["orchestration"]["max_parallel"] = 2
    elif mutation == "path_escape":
        value["controls"]["write_roots"] = ["../other"]
    with pytest.raises(ValueError):
        ArchitectureSpec.model_validate(value)


def test_source_runtime_route():
    assert resolve_operation("edit", "edit", "other", []) == "migrate"
    assert resolve_operation("migrate", "migrate", "codex_sdk", []) == "edit"
    assert resolve_operation("review", "build", "other", []) == "review"
    with pytest.raises(Exception, match="not yet evidenced"):
        resolve_operation("auto", "build", "unknown", [])
    with pytest.raises(Exception, match="outside caller"):
        resolve_operation("auto", "edit", "codex_sdk", ["analyze"])
