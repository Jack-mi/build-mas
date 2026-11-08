import asyncio
import json
import os
import subprocess
import sys

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from build_mas.mcp_server import server_for
from build_mas.service import BuildService


def test_mcp_tool_surface_and_no_auto_approval(tmp_path):
    async def probe():
        service = BuildService(tmp_path / "state")
        default = server_for(service)
        names = {item.name for item in await default.list_tools()}
        assert names == {"buildmas_preflight", "buildmas_invoke", "buildmas_verify", "buildmas_status", "buildmas_read"}
        writable = server_for(service, allow_apply=True)
        names = {item.name for item in await writable.list_tools()}
        assert "buildmas_apply" in names
        result = await default.call_tool("buildmas_status", {"session_id": "ses_nonexistent"})
        assert result.is_error
        assert result.structured_content["error"]["code"] == "not_found"
    asyncio.run(probe())


def test_actual_stdio_mcp_and_cli_equivalence(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    home = tmp_path / "state"
    service = BuildService(home)
    workspace = service.register(root)
    session = service.new_session(workspace["id"])
    cli = subprocess.run([sys.executable, "-m", "build_mas.cli", "--home", str(home), "status", "--session", session["id"], "--json"], capture_output=True, text=True)
    assert cli.returncode == 0, cli.stderr
    expected = json.loads(cli.stdout)

    async def probe():
        environment = {**os.environ, "PYTHONPATH": str(__import__('pathlib').Path(__file__).resolve().parents[1] / "src")}
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "build_mas.cli", "--home", str(home), "serve"], env=environment)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                tools = await client.list_tools()
                assert "buildmas_status" in {item.name for item in tools.tools}
                result = await client.call_tool("buildmas_status", {"session_id": session["id"]})
                assert result.structured_content == expected
                assert not result.is_error
    asyncio.run(probe())


def test_cli_error_exit_and_approval_not_accepted(tmp_path):
    result = subprocess.run([sys.executable, "-m", "build_mas.cli", "--home", str(tmp_path / "state"), "invoke", "review"], capture_output=True, text=True)
    assert result.returncode != 0
    assert json.loads(result.stdout)["error"]["code"] == "workspace_not_registered"


def test_generated_mcp_returns_structured_cli_checkpoint(tmp_path, spec, monkeypatch):
    from build_mas.target import scaffold
    from test_generated_workflow import FakeCodex, load
    root = tmp_path / "target"
    root.mkdir()
    scaffold(root, spec)
    flow = load(root)
    monkeypatch.setattr(flow, "AsyncCodex", FakeCodex)
    state_dir = tmp_path / "state"
    state = asyncio.run(flow.run({"value": "hello"}, state_path=state_dir / "latest.json"))
    async def probe():
        environment = {k: v for k, v in os.environ.items() if k != "BUILD_MAS_TEST_HOME"}
        environment["WORKFLOW_STATE_DIR"] = str(state_dir)
        parameters = StdioServerParameters(command=sys.executable, args=[str(root / "mcp_server.py")], env=environment)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                result = await client.call_tool("mas_run", {"request": {"value": "hello"}})
                assert result.structured_content == state and not result.is_error
                verified = await client.call_tool("mas_verify", {})
                assert verified.structured_content["status"] == "passed"
    asyncio.run(probe())
