import importlib.util
import json
from pathlib import Path

from jsonschema import Draft202012Validator
import asyncio

from build_mas.mcp_contracts import InvokeEnvelope, PageResult, PublicApplyRequest, PublicResult
from build_mas.mcp_server import server_for
from build_mas.service import BuildService


def test_exported_schemas_match_owning_code():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("export_schemas", root / "scripts/export_schemas.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    for name, schema in module.schemas().items():
        Draft202012Validator.check_schema(schema)
        assert json.loads((root / "src/build_mas/schemas" / f"{name}.schema.json").read_text()) == schema


def test_discovered_tools_use_owning_mcp_schemas(tmp_path):
    async def check():
        tools = await server_for(BuildService(tmp_path / "state"), allow_apply=True).list_tools()
        for tool in tools:
            expected = PageResult if tool.name == "buildmas_read" else PublicResult
            assert tool.output_schema == expected.model_json_schema()
        invoke = next(tool for tool in tools if tool.name == "buildmas_invoke")
        apply = next(tool for tool in tools if tool.name == "buildmas_apply")
        assert "idempotency_key" in invoke.input_schema["$defs"]["InvokeEnvelope"]["required"]
        assert apply.input_schema["$defs"]["PublicApplyRequest"] == PublicApplyRequest.model_json_schema()
    asyncio.run(check())
