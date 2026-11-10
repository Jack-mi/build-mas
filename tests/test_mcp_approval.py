import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import ElicitResult

from test_service import prepared, setup_workspace


def test_real_stdio_approval_accept_decline_and_unavailable(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    request = {"proposal_id": proposal["id"], "idempotency_key": "mcp-apply"}
    async def call(action=None):
        async def approve(context, params):
            assert "live SDK check" in params.message and proposal["id"] in params.message
            return ElicitResult(action=action, content={"approve": action == "accept"} if action == "accept" else None)
        environment = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src"), "CODEXWRIGHT_HOME": str(service.store.home), "CODEXWRIGHT_ALLOW_APPLY": "1"}
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "codexwright.mcp_server"], env=environment)
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write, elicitation_callback=approve if action else None) as client:
                await client.initialize()
                return await client.call_tool("codexwright_apply", {"request": {**request, "idempotency_key": "mcp-apply-" + str(action)}})
    result = asyncio.run(call())
    assert result.structured_content["status"] == "approval_required" and not list(root.iterdir())
    result = asyncio.run(call("decline"))
    assert result.is_error and result.structured_content["error"]["code"] == "permission_denied"
    assert not list(root.iterdir())
    result = asyncio.run(call("accept"))
    assert not result.is_error and result.structured_content["status"] == "completed", result
    assert (root / "workflow.py").is_file()
