"""Thin stdio MCP harness over the shared service. No model-supplied approvals."""

import json

from mcp.server.mcpserver import Context, MCPServer
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel

from .errors import BuildMasError
from .store import digest


class ApprovalForm(BaseModel):
    approve: bool


def reply(value):
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(value, ensure_ascii=False))], structured_content=value, is_error=value.get("status") in {"failed", "blocked", "outcome_unknown"})


def server_for(service, *, allow_apply=False):
    server = MCPServer("build-mas", version="0.2.0", instructions="Use buildmas_invoke with the user's goal and selected materials at any task stage. It prepares analysis/spec/proposals, never changes the target. Read exact proposal diff via buildmas_read. buildmas_apply requires a real user approval or a locally pre-issued approval reference. Never invent approval or expose internal agents as services. Query run status and preserve incomplete verification.")

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    async def buildmas_preflight(workspace_id: str | None = None) -> CallToolResult:
        try:
            return reply(await service.doctor(workspace_id))
        except BuildMasError as exc:
            return reply({"status": "blocked", "error": exc.as_dict()})

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    async def buildmas_invoke(envelope: dict) -> CallToolResult:
        try:
            return reply(await service.invoke(envelope))
        except BuildMasError as exc:
            return reply({"status": "failed", "error": exc.as_dict()})

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    async def buildmas_verify(workspace_id: str, session_id: str) -> CallToolResult:
        try:
            return reply(await service.verify(workspace_id, session_id))
        except BuildMasError as exc:
            return reply({"status": "failed", "error": exc.as_dict()})

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def buildmas_status(session_id: str | None = None, run_id: str | None = None) -> CallToolResult:
        try:
            return reply(service.status(session_id=session_id, run_id=run_id))
        except BuildMasError as exc:
            return reply({"status": "failed", "error": exc.as_dict()})

    @server.tool(annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def buildmas_read(category: str, reference: str, offset: int = 0, limit: int = 12000) -> CallToolResult:
        try:
            return reply(service.read(category, reference, offset=offset, limit=limit))
        except BuildMasError as exc:
            return reply({"status": "failed", "error": exc.as_dict()})

    if allow_apply:
        @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
        async def buildmas_apply(request: dict, ctx: Context) -> CallToolResult:
            try:
                if not request.get("approval_reference"):
                    proposal = service.store.read("proposals", request.get("proposal_id", ""))
                    expected_hash = digest(proposal)
                    try:
                        page = service.read("proposals", proposal["id"], limit=50000)
                        if page["next_offset"] is not None:
                            return reply({"status": "approval_required", "error": {"code": "proposal_review_too_large", "message": "This proposal exceeds the confirmation display limit. Read every page of the diff, then issue one-use approval from the local CLI."}})
                        diff = page["content"]
                        answer = await ctx.elicit("Approve this exact scoped proposal? This also permits its declared live SDK check with isolated credentials, before applying files.\n" + diff, ApprovalForm)
                    except Exception as exc:
                        return reply({"status": "approval_required", "error": {"code": "approval_channel_unavailable", "message": "This MCP client has no supported human approval channel. Review and approve from local CLI; pass its approval reference."}})
                    action = getattr(answer.action, "value", answer.action)
                    if action != "accept" or not answer.data or not answer.data.approve:
                        raise BuildMasError("permission_denied", "User did not approve this proposal")
                    approved = service.approve(proposal["id"], actor="mcp_elicitation", expected_proposal_hash=expected_hash)
                    request = {**request, **approved}
                return reply(await service.apply(request))
            except BuildMasError as exc:
                return reply({"status": "failed", "error": exc.as_dict()})

    @server.resource("buildmas://sessions/{session_id}", mime_type="application/json")
    def session_resource(session_id: str) -> str:
        return json.dumps(service.status(session_id=session_id), ensure_ascii=False)

    @server.resource("buildmas://runs/{run_id}", mime_type="application/json")
    def run_resource(run_id: str) -> str:
        return json.dumps(service.status(run_id=run_id), ensure_ascii=False)

    return server


def serve(service, *, allow_apply=False):
    server_for(service, allow_apply=allow_apply).run(transport="stdio")
