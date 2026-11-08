"""A thin MCP surface over the generated workflow, not over individual agents."""

import json
import re
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.types import CallToolResult, TextContent
if __package__:
    from .workflow import SPEC, run, verify_state
    from .execution import state_directory
else:
    from workflow import SPEC, run, verify_state
    from execution import state_directory


def serve(state_dir):
    state_dir = Path(state_dir)
    server = MCPServer("generated-codex-workflow", instructions="Run the workflow as a single task-level service. Internal agents are not independent public services.")

    def reply(value):
        return CallToolResult(content=[TextContent(type="text", text=json.dumps(value))], structured_content=value, is_error=value.get("status") in {"failed", "blocked", "outcome_unknown", "partial"})

    def state_path(run_id):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
            raise ValueError("Invalid run ID")
        return state_dir / f"{run_id}.json"

    @server.tool()
    async def mas_run(request: dict, run_id: str = "latest") -> CallToolResult:
        return reply(await run(request, state_path=state_path(run_id)))

    @server.tool()
    def mas_status(run_id: str = "latest") -> CallToolResult:
        return reply(json.loads(state_path(run_id).read_text()))

    @server.tool()
    def mas_read(run_id: str = "latest") -> CallToolResult:
        state = json.loads(state_path(run_id).read_text())
        return reply({"status": state["status"], "output": state.get("output"), "packets": state["packets"]})

    @server.tool()
    def mas_verify(run_id: str = "latest") -> CallToolResult:
        from jsonschema import Draft202012Validator

        state = json.loads(state_path(run_id).read_text())
        if state.get("status") != "passed":
            return reply({"status": "failed", "reason": "Workflow has not passed"})
        verify_state(state, state.get("request"))
        return reply({"status": "passed", "run_id": run_id, "spec_revision": SPEC["revision"]})

    server.run(transport="stdio")


if __name__ == "__main__":
    serve(state_directory(Path(__file__).resolve().parent))
