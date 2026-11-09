"""Thin stdio MCP adapter over the shared Codex SDK workflow service."""

import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from mcp.server.caching import CacheHint
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, InputRequiredResult, TextContent, ToolAnnotations
from pydantic import BaseModel, Field, ValidationError

from . import __version__
from .contracts import Identifier, validate
from .errors import BuildMasError
from .mcp_contracts import InvokeEnvelope, PageResult, PublicApplyRequest, PublicResult, ReadCategory, dump, summary
from .mcp_interaction import LoginInteraction, apply, capabilities
from .mcp_progress import progress
from .store import identifier


class ApprovalForm(BaseModel):
    approve: bool


def reply(value, *, page=False):
    data = dump(PageResult, {"status": "failed" if value.get("error") else "completed", **value}) if page else summary(value)
    if page and not value.get("error"):
        data["next_offset"] = value["next_offset"]
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))], structured_content=data, is_error=data["status"] in {"failed", "blocked", "outcome_unknown", "partial", "authentication_required", "account_unverified"})


def failure(error, *, page=False):
    if isinstance(error, BuildMasError):
        data = error.as_dict()
    else:
        fields = []
        current = error
        while current is not None:
            if isinstance(current, ValidationError):
                fields = [{"path": ".".join(map(str, item["loc"])), "type": item["type"]} for item in current.errors(include_input=False, include_url=False)][:35]
                break
            current = current.__cause__
        invalid = bool(fields) or isinstance(error, ValidationError)
        data = {"code": "invalid_input" if invalid else "operation_failed", "message": "Input does not match the public MCP contract" if invalid else "Tool could not complete; inspect recorded evidence", "details": {"fields": fields}}
    return reply({"status": "failed", "error": data}, page=page)


class BuildMasServer(MCPServer):
    async def call_tool(self, name, arguments, context=None):
        try:
            if name in {"buildmas_invoke", "buildmas_apply"}:
                field, contract = ("envelope", InvokeEnvelope) if name == "buildmas_invoke" else ("request", PublicApplyRequest)
                if not isinstance(arguments, dict) or set(arguments) != {field}:
                    raise BuildMasError("invalid_input", "Use exactly the documented tool argument wrapper")
                validate(contract, arguments[field])
            return await super().call_tool(name, arguments, context)
        except BuildMasError as exc:
            return failure(exc, page=name == "buildmas_read")
        except (ToolError, ValidationError) as exc:
            return failure(exc, page=name == "buildmas_read")


def server_for(service, *, allow_apply=False):
    login = LoginInteraction(service)
    review_owner = identifier("server")

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            await login.close()

    server = BuildMasServer("build-mas", version=__version__, lifespan=lifespan,
        instructions="Register the selected project and invoke with workspace_id, goal/materials and a stable idempotency_key. Reuse session_id for follow-up. Invoke never writes the target. Read all proposal diff pages before apply. Apply requires real human confirmation, never model approval. Reuse the exact key after a lost response; unknown results require status/recovery, not replay. Summary results provide references for full details. No builder CLI, hooks or host-model fallback.",
        cache_hints={"tools/list": CacheHint(300000, "private"), "resources/read": CacheHint(0, "private")})

    async def validation_errors(ctx, call_next):
        try:
            return await call_next(ctx)
        except ValidationError as exc:
            if ctx.method != "tools/call":
                raise
            return failure(exc, page=(ctx.params or {}).get("name") == "buildmas_read")
    server.middleware.append(validation_errors)

    read_only = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)
    local = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)

    @server.tool(annotations=local)
    def buildmas_register(path: Annotated[str, Field(min_length=1, max_length=4096)]) -> Annotated[CallToolResult, PublicResult]:
        """Register a user-selected absolute project directory; never edit target files. Retain workspace_id."""
        try:
            if not Path(path).is_absolute():
                raise BuildMasError("invalid_workspace", "Select an absolute project directory")
            workspace = service.register(path)
            return reply({**workspace, "workspace_id": workspace["id"]})
        except (OSError, ValueError):
            return failure(BuildMasError("invalid_workspace", "Selected project directory is unavailable"))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=local)
    def buildmas_import(workspace_id: Identifier, path: Annotated[str, Field(min_length=1, max_length=4096)]) -> Annotated[CallToolResult, PublicResult]:
        """Import a selected non-sensitive attachment into private state; use its id as asset_id, target unchanged."""
        try:
            if not Path(path).is_absolute():
                raise BuildMasError("unsafe_asset", "Select an absolute attachment path")
            return reply(service.import_asset(workspace_id, path))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True))
    async def buildmas_login(ctx: Context, device: bool = False) -> Annotated[CallToolResult, PublicResult] | InputRequiredResult:
        """Authenticate private Codex runtime via user-only URL confirmation. Never send credentials in tool arguments."""
        try:
            result = await login.login(ctx, device=device)
            return result if isinstance(result, InputRequiredResult) else reply(result)
        except BuildMasError as exc:
            return reply({"status": "blocked", "error": exc.as_dict()})

    @server.tool(annotations=local)
    async def buildmas_recover(run_id: Identifier, ctx: Context) -> Annotated[CallToolResult, PublicResult]:
        """Reconcile an interrupted original run and recover its candidate; never blindly replay writes or claim unknown success."""
        try:
            async with progress(service, ctx):
                return reply(await service.recover(run_id))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=local)
    async def buildmas_preflight(ctx: Context, workspace_id: Identifier | None = None) -> Annotated[CallToolResult, PublicResult]:
        """Check runtime/account readiness and client login, approval and progress channels. Capability is not authorization."""
        client = capabilities(ctx, allow_apply)
        try:
            result = await service.doctor(workspace_id)
            return reply({**result, "capabilities": client})
        except BuildMasError as exc:
            return reply({"status": "blocked", "error": exc.as_dict(), "capabilities": client})

    @server.tool(annotations=local)
    async def buildmas_invoke(envelope: InvokeEnvelope, ctx: Context) -> Annotated[CallToolResult, PublicResult]:
        """Analyze, plan or prepare scoped Codex SDK workflow changes. Stable idempotency_key required; reuse session_id. Never writes target."""
        try:
            async with progress(service, ctx):
                return reply(await service.invoke(envelope.model_dump(mode="json")))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=local)
    async def buildmas_verify(workspace_id: Identifier, session_id: Identifier, ctx: Context) -> Annotated[CallToolResult, PublicResult]:
        """Execute saved checks for this workspace/session. Inspect verification separately from operation status; details via read."""
        try:
            async with progress(service, ctx):
                return reply(await service.verify(workspace_id, session_id))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=read_only)
    def buildmas_status(session_id: Identifier | None = None, run_id: Identifier | None = None) -> Annotated[CallToolResult, PublicResult]:
        """Read compact session/run state with last stage and evidence references. Unknown outcome needs recovery, not a new invoke."""
        try:
            return reply(service.status(session_id=session_id, run_id=run_id))
        except BuildMasError as exc:
            return failure(exc)

    @server.tool(annotations=read_only)
    def buildmas_read(category: ReadCategory, reference: Identifier, offset: Annotated[int, Field(ge=0)] = 0, limit: Annotated[int, Field(ge=1, le=50000)] = 12000) -> Annotated[CallToolResult, PageResult]:
        """Read complete specs, frozen proposal diffs, records or events in bounded character pages. Continue at next_offset until null."""
        try:
            return reply(service.read(category, reference, offset=offset, limit=limit), page=True)
        except BuildMasError as exc:
            return failure(exc, page=True)

    if allow_apply:
        @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
        async def buildmas_apply(request: PublicApplyRequest, ctx: Context) -> Annotated[CallToolResult, PublicResult] | InputRequiredResult:
            """Apply an exact proposal only after every diff page and final human approval. Same key returns original result; no approval fields accepted."""
            try:
                async with progress(service, ctx):
                    result = await apply(service, request, ctx, ApprovalForm, review_owner=review_owner)
                    return result if isinstance(result, InputRequiredResult) else reply(result)
            except BuildMasError as exc:
                return failure(exc)

    @server.resource("buildmas://sessions/{session_id}", mime_type="application/json")
    def session_resource(session_id: str) -> str:
        return json.dumps(summary(service.status(session_id=session_id)), ensure_ascii=False)

    @server.resource("buildmas://runs/{run_id}", mime_type="application/json")
    def run_resource(run_id: str) -> str:
        return json.dumps(summary(service.status(run_id=run_id)), ensure_ascii=False)

    return server


def serve(service, *, allow_apply=False):
    server_for(service, allow_apply=allow_apply).run(transport="stdio")


def main():
    """Start stdio MCP; no builder CLI operations are installed."""
    if len(sys.argv) != 1:
        print("Start python -m build_mas.mcp_server without arguments; no builder CLI operations.", file=sys.stderr)
        return 2
    from .service import BuildService
    serve(BuildService(model=os.environ.get("BUILD_MAS_MODEL")), allow_apply=os.environ.get("BUILD_MAS_ALLOW_APPLY") == "1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
