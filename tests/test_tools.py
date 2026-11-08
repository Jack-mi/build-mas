import asyncio
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

from build_mas.contracts import ArchitectureSpec
from build_mas.target import scaffold


def tool_project(root, spec_dict):
    value = copy.deepcopy(spec_dict)
    value["tools"] = [{"name": "echo_value", "kind": "cli", "implementation": "tools/echo.py", "input_schema": value["inputs_schema"], "output_schema": value["outputs_schema"], "risk": "compute", "side_effect": False, "approval": "scope", "smoke_input": {"value": "hello"}}]
    value["agents"][0]["tools"] = ["echo_value"]
    value["verification"]["checks"].append({"id": "tool", "kind": "tool_smoke", "target": "tools/echo.py", "arguments": ['{"value":"hello"}']})
    spec = ArchitectureSpec.model_validate(value)
    scaffold(root, spec)
    (root / "tools").mkdir()
    (root / "tools/echo.py").write_text('import json,sys\nprint(json.dumps(json.loads(sys.argv[1])))\n')
    path = importlib.util.spec_from_file_location("fixture_tool_server", root / "tool_server.py")
    module = importlib.util.module_from_spec(path)
    sys.modules.pop("execution", None)
    sys.path.insert(0, str(root))
    try:
        path.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_cli_registry_schema_permission_and_sandbox(tmp_path, spec_dict):
    root = tmp_path / "target"; root.mkdir()
    module = tool_project(root, spec_dict)
    tool = module.SPEC["tools"][0]
    assert module.invoke(tool, {"value": "hello"}) == {"value": "hello"}
    with pytest.raises(Exception):
        module.invoke(tool, {"wrong": "input"})
    with pytest.raises(PermissionError):
        module.invoke({**tool, "approval": "deny"}, {"value": "hello"})
    with pytest.raises(PermissionError):
        module.invoke({**tool, "side_effect": True}, {"value": "hello"})
    sibling = tmp_path / "private.txt"; sibling.write_text("private")
    (root / "tools/echo.py").write_text('from pathlib import Path\nPath(' + repr(str(sibling)) + ').read_text()\n')
    with pytest.raises(RuntimeError, match="failed"):
        module.invoke(tool, {"value": "hello"})
    assert sibling.read_text() == "private"


def test_actual_registered_tool_annotations(tmp_path, spec_dict):
    root = tmp_path / "target"; root.mkdir(); module = tool_project(root, spec_dict)
    async def probe():
        server = module.server()
        tool = (await server.list_tools())[0]
        assert tool.name == "echo_value" and tool.annotations.read_only_hint
        result = await server.call_tool("echo_value", {"request": {"value": "hello"}})
        assert result.structured_content == {"value": "hello"}
    asyncio.run(probe())
