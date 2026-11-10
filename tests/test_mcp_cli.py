import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from codexwright.mcp_server import server_for
from codexwright.service import BuildService
from codexwright import __version__
from test_service import FakeRuntime


def test_mcp_tool_surface_and_no_auto_approval(tmp_path):
    async def probe():
        service = BuildService(tmp_path / "state")
        default = server_for(service)
        names = {item.name for item in await default.list_tools()}
        assert names == {"codexwright_preflight", "codexwright_register", "codexwright_import", "codexwright_login", "codexwright_recover", "codexwright_invoke", "codexwright_verify", "codexwright_status", "codexwright_read"}
        writable = server_for(service, allow_apply=True)
        names = {item.name for item in await writable.list_tools()}
        assert "codexwright_apply" in names
        result = await default.call_tool("codexwright_status", {"session_id": "ses_nonexistent"})
        assert result.is_error
        assert result.structured_content["error"]["code"] == "not_found"
    asyncio.run(probe())


def test_actual_stdio_registration_import_and_core_equivalence(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    home = tmp_path / "state"
    service = BuildService(home)
    workspace = service.register(root)
    session = service.new_session(workspace["id"])
    from codexwright.mcp_contracts import summary
    expected = summary(service.status(session_id=session["id"]))
    attachment = tmp_path / "notes.txt"
    attachment.write_text("selected notes")

    async def probe():
        environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "CODEXWRIGHT_HOME": str(home), "CODEXWRIGHT_ALLOW_APPLY": "0"}
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "codexwright.mcp_server"], env=environment)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.server_info.version == __version__
                tools = await client.list_tools()
                assert "codexwright_status" in {item.name for item in tools.tools}
                result = await client.call_tool("codexwright_status", {"session_id": session["id"]})
                assert result.structured_content == expected
                assert not result.is_error
                registered = await client.call_tool("codexwright_register", {"path": str(root)})
                assert registered.structured_content["workspace_id"] == workspace["id"]
                imported = await client.call_tool("codexwright_import", {"workspace_id": workspace["id"], "path": str(attachment)})
                assert not imported.is_error
                assert imported.structured_content["workspace_id"] == workspace["id"]
                assert not list(root.iterdir())
                invalid = await client.call_tool("codexwright_register", {"path": str(tmp_path / "missing")})
                assert invalid.is_error and invalid.structured_content["error"]["code"] == "invalid_workspace"
    asyncio.run(probe())


def test_mcp_register_invoke_continue_and_idempotency(tmp_path):
    async def probe():
        root = tmp_path / "project"
        root.mkdir()
        service = BuildService(tmp_path / "state", runtime_factory=FakeRuntime)
        server = server_for(service)
        registered = await server.call_tool("codexwright_register", {"path": str(root)})
        workspace = registered.structured_content["workspace_id"]
        FakeRuntime.response = {"operation": "review", "summary": "No changes", "profile_json": "{}", "spec_json": None, "questions": [], "assumptions": []}
        envelope = {"workspace_id": workspace, "operation": "review", "goal": "Review", "idempotency_key": "same-request"}
        first = await server.call_tool("codexwright_invoke", {"envelope": envelope})
        repeated = await server.call_tool("codexwright_invoke", {"envelope": envelope})
        assert first.structured_content == repeated.structured_content
        assert first.structured_content["status"] == "completed"
        follow = await server.call_tool("codexwright_invoke", {"envelope": {"workspace_id": workspace, "session_id": first.structured_content["session_id"], "goal": "Explain", "operation": "explain", "idempotency_key": "follow-up"}})
        assert follow.structured_content["session_id"] == first.structured_content["session_id"]
        assert not list(root.iterdir())
    asyncio.run(probe())


def test_register_and_import_reject_unscoped_paths(tmp_path):
    async def probe():
        root = tmp_path / "project"
        root.mkdir()
        server = server_for(BuildService(tmp_path / "state"))
        for path in (".", str(Path.home()), str(tmp_path / "state")):
            result = await server.call_tool("codexwright_register", {"path": path})
            assert result.is_error
        workspace = (await server.call_tool("codexwright_register", {"path": str(root)})).structured_content["workspace_id"]
        result = await server.call_tool("codexwright_import", {"workspace_id": workspace, "path": "notes.txt"})
        assert result.is_error and result.structured_content["error"]["code"] == "unsafe_asset"
    asyncio.run(probe())


def test_mcp_recover_dispatch_and_unknown_run(tmp_path):
    async def probe():
        service = BuildService(tmp_path / "state")
        calls = []
        async def recover(run_id):
            calls.append(run_id)
            return {"status": "approval_required", "run_id": run_id}
        service.recover = recover
        result = await server_for(service).call_tool("codexwright_recover", {"run_id": "run_fixture"})
        assert result.structured_content["status"] == "approval_required"
        assert calls == ["run_fixture"]
        unknown = await server_for(BuildService(tmp_path / "other")).call_tool("codexwright_recover", {"run_id": "run_missing"})
        assert unknown.is_error and unknown.structured_content["error"]["code"] == "not_found"
    asyncio.run(probe())


@pytest.mark.parametrize("action", ["accept", "decline", "unavailable"])
@pytest.mark.parametrize("device", [False, True])
def test_mcp_login_uses_user_url_channel(tmp_path, monkeypatch, action, device):
    calls = []
    class Runtime(FakeRuntime):
        async def login(self, *, device, authorize):
            calls.append("login")
            await authorize({"verification_url": "https://auth.example.invalid/device", "user_code": "USER-ONLY"} if device else {"auth_url": "https://auth.example.invalid/login"})
            calls.append("completed")
            return {"status": "ready", "account_present": True}
    async def elicit_url(context, message, url, elicitation_id):
        assert "credentials" in message and url.startswith("https://auth.")
        assert ("USER-ONLY" in message) == device
        calls.append("user_url")
        if action == "unavailable":
            raise RuntimeError("No URL support")
        return SimpleNamespace(action=action)
    monkeypatch.setattr("codexwright.mcp_server.Context.elicit_url", elicit_url)
    result = asyncio.run(server_for(BuildService(tmp_path / "state", runtime_factory=Runtime)).call_tool("codexwright_login", {"device": device}))
    assert "USER-ONLY" not in json.dumps(result.structured_content)
    if action == "accept":
        assert not result.is_error and result.structured_content["status"] == "ready"
        assert calls == ["login", "user_url", "completed"]
    else:
        assert result.is_error and result.structured_content["status"] == "blocked"
        assert calls == ["login", "user_url"]
        assert result.structured_content["error"]["code"] == ("permission_denied" if action == "decline" else "login_channel_unavailable")


def test_generated_mcp_returns_structured_cli_checkpoint(tmp_path, spec, monkeypatch):
    from codexwright.target import scaffold
    from test_generated_workflow import FakeCodex, load
    root = tmp_path / "target"
    root.mkdir()
    scaffold(root, spec)
    flow = load(root)
    monkeypatch.setattr(flow, "AsyncCodex", FakeCodex)
    state_dir = tmp_path / "state"
    state = asyncio.run(flow.run({"value": "hello"}, state_path=state_dir / "latest.json"))
    async def probe():
        environment = {k: v for k, v in os.environ.items() if k != "CODEXWRIGHT_TEST_HOME"}
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


def test_actual_plugin_launcher_without_cli_arguments(tmp_path):
    async def probe():
        repository = Path(__file__).resolve().parents[1]
        environment = {**os.environ, "PYTHONPATH": str(repository / "src"), "CODEXWRIGHT_PYTHON": sys.executable, "CODEXWRIGHT_HOME": str(tmp_path / "state"), "CODEXWRIGHT_ALLOW_APPLY": "1"}
        parameters = StdioServerParameters(command=sys.executable, args=[str(repository / "adapters/codex/scripts/launch.py")], env=environment, cwd=str(tmp_path))
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.server_info.version == __version__
                tools = await client.list_tools()
                assert len(tools.tools) == 10
                assert "codexwright_register" in {entry.name for entry in tools.tools}
    asyncio.run(probe())


def test_mcp_entrypoint_rejects_legacy_cli_subcommands(tmp_path):
    environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "CODEXWRIGHT_HOME": str(tmp_path / "state")}
    result = subprocess.run([sys.executable, "-m", "codexwright.mcp_server", "doctor"], capture_output=True, text=True, env=environment, cwd=tmp_path)
    assert result.returncode == 2 and not result.stdout
    assert "without arguments" in result.stderr
    assert not (tmp_path / "state").exists()
