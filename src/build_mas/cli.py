"""Terminal harness. Interactive approvals are local, scoped, and one-use."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from . import __version__
from .errors import BuildMasError
from .service import BuildService
from .store import digest


def exit_code(value):
    if value.get("error", {}).get("code") in {"invalid_input", "workspace_not_registered", "invalid_reference", "invalid_proposal", "stale_revision", "invalid_runtime_route"}:
        return 2
    status = value.get("status")
    if status == "outcome_unknown":
        return 5
    if status == "approval_required":
        return 3
    if status in {"blocked", "authentication_required", "account_unverified"}:
        return 4
    if status in {"failed", "partial"}:
        return 1
    return 0


def parser():
    root = argparse.ArgumentParser(prog="build-mas", description="Build, migrate, edit and verify agentic workflows with Codex SDK")
    root.add_argument("--version", action="version", version=__version__)
    root.add_argument("--home", type=Path)
    root.add_argument("--model")
    root.add_argument("--json", action="store_true")
    root.add_argument("--progress", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)
    register = commands.add_parser("register", help="Register a local project without changing it")
    register.add_argument("path", type=Path)
    attachment = commands.add_parser("import", help="Explicitly import a selected attachment into a private workspace asset registry")
    attachment.add_argument("path", type=Path)
    attachment.add_argument("--workspace", required=True)
    attachment.add_argument("--json", action="store_true", dest="command_json")
    for name in ("invoke", "plan", "build", "edit", "diagnose", "migrate", "refactor", "analyze", "review", "explain"):
        command = commands.add_parser(name)
        command.add_argument("goal", nargs="?", default="")
        command.add_argument("--workspace")
        command.add_argument("--cwd", type=Path)
        command.add_argument("--session")
        command.add_argument("--input", type=Path)
        command.add_argument("--file", action="append", default=[])
        command.add_argument("--image", action="append", default=[])
        command.add_argument("--url", action="append", default=[])
        command.add_argument("--asset", action="append", default=[])
        command.add_argument("--idempotency-key")
        command.add_argument("--proposal")
        command.add_argument("--yes", action="store_true", help="Approve exact proposal in this local CLI invocation; not a server policy")
        command.add_argument("--json", action="store_true", dest="command_json")
    for name in ("approve", "apply"):
        command = commands.add_parser(name)
        command.add_argument("--proposal", required=True)
        command.add_argument("--yes", action="store_true")
        command.add_argument("--input", type=Path)
        command.add_argument("--idempotency-key")
        command.add_argument("--json", action="store_true", dest="command_json")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--workspace")
    doctor.add_argument("--json", action="store_true", dest="command_json")
    login = commands.add_parser("login", help="Sign in to the private builder runtime without entering secrets into a prompt")
    login.add_argument("--device", action="store_true")
    verify = commands.add_parser("verify")
    verify.add_argument("--workspace", required=True)
    verify.add_argument("--session", required=True)
    verify.add_argument("--json", action="store_true", dest="command_json")
    status = commands.add_parser("status")
    status.add_argument("--session")
    status.add_argument("--run")
    status.add_argument("--json", action="store_true", dest="command_json")
    recover = commands.add_parser("recover", help="Verify and recover a completed failed run's staged candidate")
    recover.add_argument("--run", required=True)
    recover.add_argument("--json", action="store_true", dest="command_json")
    read = commands.add_parser("read")
    read.add_argument("category", choices=["proposals", "specs", "runs", "sessions"])
    read.add_argument("reference")
    read.add_argument("--offset", type=int, default=0)
    read.add_argument("--limit", type=int, default=12000)
    read.add_argument("--json", action="store_true", dest="command_json")
    serve = commands.add_parser("serve")
    serve.add_argument("--transport", choices=["stdio"], default="stdio")
    serve.add_argument("--allow-apply", action="store_true", help="Expose apply with mandatory MCP elicitation or pre-issued local approval")
    return root


def local_approval(service, proposal_id, yes):
    proposal = service.store.read("proposals", proposal_id)
    expected_hash = digest(proposal)
    if not yes:
        if not sys.stdin.isatty():
            raise BuildMasError("approval_required", "Review with read proposals, then approve explicitly using --yes")
        offset = 0
        while offset is not None:
            page = service.read("proposals", proposal_id, offset=offset, limit=50000)
            print(page["content"], file=sys.stderr)
            offset = page["next_offset"]
        answer = input(f"Apply {len(proposal['changes'])} files for {proposal_id}? Type approve: ")
        if answer.strip() != "approve":
            raise BuildMasError("permission_denied", "Proposal was not approved")
    return service.approve(proposal_id, expected_proposal_hash=expected_hash)


async def dispatch(args, service):
    if args.command == "register":
        return service.register(args.path)
    if args.command == "import":
        return service.import_asset(args.workspace, args.path)
    if args.command == "doctor":
        return await service.doctor(args.workspace)
    if args.command == "login":
        from .contracts import Budget

        async with service.runtime("login", Budget(timeout_seconds=300)) as runtime:
            return await runtime.login(device=args.device, announce=lambda value: print(json.dumps(value), file=sys.stderr, flush=True))
    if args.command == "status":
        return service.status(session_id=args.session, run_id=args.run)
    if args.command == "read":
        return service.read(args.category, args.reference, offset=args.offset, limit=args.limit)
    if args.command == "recover":
        return await service.recover(args.run)
    if args.command == "verify":
        return await service.verify(args.workspace, args.session)
    if args.command in {"approve", "apply"}:
        if args.input:
            value = json.loads(args.input.read_text())
        else:
            value = local_approval(service, args.proposal, args.yes)
            value["idempotency_key"] = args.idempotency_key or args.proposal
        return value if args.command == "approve" else await service.apply(value)
    if getattr(args, "proposal", None):
        if args.command != "build":
            raise BuildMasError("invalid_input", "Proposal shortcut is supported by build/apply")
        approved = local_approval(service, args.proposal, args.yes)
        approved["idempotency_key"] = args.idempotency_key or args.proposal
        return await service.apply(approved)
    if args.input:
        value = json.loads(args.input.read_text() if str(args.input) != "-" else sys.stdin.read())
    else:
        workspace = args.workspace
        if args.cwd:
            workspace = service.register(args.cwd)["id"]
        if not workspace:
            raise BuildMasError("workspace_not_registered", "Use --workspace or --cwd")
        materials = [{"kind": "file", "path": path, "source": "user"} for path in args.file]
        materials += [{"kind": "image", "path": path, "source": "user"} for path in args.image]
        materials += [{"kind": "url", "uri": url, "source": "external"} for url in args.url]
        materials += [{"kind": "file", "asset_id": name, "source": "user"} for name in args.asset]
        value = {"workspace_id": workspace, "goal": args.goal, "session_id": args.session, "operation": "auto" if args.command == "invoke" else args.command, "inputs": materials, "idempotency_key": args.idempotency_key}
    result = await service.invoke(value)
    if args.command == "build" and args.yes and result.get("proposal_id"):
        approved = local_approval(service, result["proposal_id"], True)
        approved["idempotency_key"] = result["proposal_id"]
        return await service.apply(approved)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    progress = (lambda kind, **fields: print(json.dumps({"event": kind, **fields}), file=sys.stderr, flush=True)) if args.progress else None
    service = BuildService(args.home, model=args.model, event=progress)
    if args.command == "serve":
        from .mcp_server import serve

        serve(service, allow_apply=args.allow_apply)
        return 0
    try:
        result = asyncio.run(dispatch(args, service))
    except BuildMasError as exc:
        result = {"status": "approval_required" if exc.code == "approval_required" else "failed", "error": exc.as_dict()}
    except KeyboardInterrupt:
        result = {"status": "outcome_unknown", "error": {"code": "interrupted", "message": "Interruption requested; inspect the run before retrying"}}
    except (ValueError, OSError) as exc:
        result = {"status": "failed", "error": {"code": "invalid_input", "message": str(exc)}}
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json or getattr(args, "command_json", False) else 2))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
