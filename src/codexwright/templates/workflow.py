"""Standalone, generated Codex workflow. This file has no builder dependency."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import shlex
import sys
import time
import tempfile
from contextlib import contextmanager
from pathlib import Path

from jsonschema import Draft202012Validator
from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ExternalMessage, SkillInput, TextInput

if __package__:
    from .execution import isolated_sdk_home, state_directory, sensitive_paths
else:
    from execution import isolated_sdk_home, state_directory, sensitive_paths

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "architecture.json").read_text())
TOOL_SERVER = ROOT / "tool_server.py"


def completed(result, schema):
    if getattr(result.status, "value", result.status) != "completed" or result.error or not result.final_response:
        raise RuntimeError("Codex turn did not complete with a final result")
    value = json.loads(result.final_response)
    Draft202012Validator(schema).validate(value)
    return value


def output_schema(schema):
    value = json.loads(json.dumps(schema))
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            for name in ("default", "uniqueItems", "patternProperties", "minProperties", "maxProperties", "propertyNames", "contains", "minContains", "maxContains", "unevaluatedProperties", "if", "then", "else", "dependentRequired", "dependentSchemas"):
                item.pop(name, None)
            if item.get("type") == "object" and "properties" in item:
                item["required"] = list(item["properties"])
                item["additionalProperties"] = False
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


def field(value, path):
    for part in path.split(".") if path else []:
        if isinstance(value, dict) and part in value:
            value = value[part]
        elif isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        else:
            raise ValueError("Missing acceptance field: " + path)
    return value


def packet_input(request, packet):
    selected = {}
    references = [item[6:] for item in packet.get("input_refs", []) if item.startswith("input.")]
    if not references:
        return {} if packet.get("depends_on") else request
    for reference in references:
        parts = reference.split(".")
        destination = selected
        for part in parts[:-1]:
            destination = destination.setdefault(part, {})
        destination[parts[-1]] = field(request, reference)
    return selected


def accept(packet, output, request):
    Draft202012Validator(packet["output_schema"]).validate(output)
    for assertion in packet.get("assertions", []):
        actual = field(output, assertion["field"])
        operator = assertion["operator"]
        expected = assertion.get("value")
        if operator == "input_equals":
            expected = field(request, expected.removeprefix("input."))
            transform = assertion.get("transform", "identity")
            if transform != "identity":
                if not isinstance(expected, str) or transform not in {"upper", "lower", "strip"}:
                    raise ValueError("Invalid acceptance input transformation")
                expected = getattr(expected, transform)()
        okay = actual == expected if operator in {"equals", "input_equals"} else bool(actual) if operator == "nonempty" else expected in actual if operator == "contains" else False
        if not okay:
            raise ValueError("Packet acceptance failed: " + assertion["field"])


def verify_state(state, request):
    identity = hashlib.sha256(json.dumps({"spec": SPEC, "input": request}, sort_keys=True).encode()).hexdigest()
    if state.get("identity") != identity or state.get("status") != "passed":
        raise ValueError("State is not a passed run of this exact spec and input")
    packets = {packet["id"]: packet for packet in SPEC["work_packets"]}
    if set(state.get("packets", {})) != set(packets):
        raise ValueError("Passed checkpoint is missing packet evidence")
    for name, packet in packets.items():
        record = state["packets"][name]
        if record.get("status") == "passed":
            if not record.get("thread_id") or not record.get("turn_id"):
                raise ValueError("Passed packet lacks actual SDK turn evidence")
            accept(packet, record.get("output"), request)
        elif record.get("status") == "skipped" and packet.get("when"):
            condition = packet["when"]
            source = state["packets"][condition["packet"]]
            if source["status"] != "passed" or field(source["output"], condition["field"]) == condition["equals"]:
                raise ValueError("Checkpoint forged a conditional skip")
        else:
            raise ValueError("Passed checkpoint contains incomplete packet evidence")
    names = SPEC["orchestration"]["result_packets"]
    if any(state["packets"][name]["status"] != "passed" for name in names):
        raise ValueError("A required result packet cannot be skipped")
    outputs = {name: state["packets"][name]["output"] for name in names}
    expected = outputs[names[0]] if len(names) == 1 else outputs
    if state.get("output") != expected:
        raise ValueError("Checkpoint output differs from packet evidence")
    Draft202012Validator(SPEC["outputs_schema"]).validate(state["output"])
    return state


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(6))
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


@contextmanager
def checkpoint_lock(path):
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_suffix(".lock")
    if path.is_symlink() or lock_path.is_symlink():
        raise ValueError("Checkpoint paths must not be symlinks")
    with lock_path.open("a+") as stream:
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("Another process owns this workflow run") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


async def run(request, *, state_path=None, approve_writes=False):
    request = json.loads(json.dumps(request))
    if any(agent["sandbox"] == "workspace_write" for agent in SPEC["agents"]) and not approve_writes:
        raise PermissionError("Workflow includes local write agents; explicit approve_writes is required")
    if state_path:
        with checkpoint_lock(Path(state_path)):
            return await execute_workflow(request, state_path=Path(state_path), approve_writes=approve_writes)
    return await execute_workflow(request, approve_writes=approve_writes)


async def execute_workflow(request, *, state_path=None, approve_writes=False):
    Draft202012Validator(SPEC["inputs_schema"]).validate(request)
    budget = SPEC["controls"]["budget"]
    previous = json.loads(state_path.read_text()) if state_path and state_path.exists() else {}
    identity = hashlib.sha256(json.dumps({"spec": SPEC, "input": request}, sort_keys=True).encode()).hexdigest()
    if previous and previous.get("identity") != identity:
        raise ValueError("Checkpoint belongs to different inputs or spec; start a new run")
    state = previous or {"identity": identity, "request": request, "packets": {}, "status": "running", "threads": {}, "tokens": 0, "turns": 0}
    if state.get("status") == "passed":
        return verify_state(state, request)
    if any(item.get("status") in ("running", "outcome_unknown") for item in state["packets"].values()):
        raise RuntimeError("Interrupted work has an unknown outcome; reconcile before resuming")
    agents = {item["id"]: item for item in SPEC["agents"]}
    packets = {item["id"]: item for item in SPEC["work_packets"]}
    semaphore = asyncio.Semaphore(min(budget["max_parallel"], SPEC["orchestration"]["max_parallel"]))
    locks = {name: asyncio.Lock() for name in agents}
    started = time.monotonic()
    sdk = isolated_sdk_home(state_path.parent if state_path else state_directory(ROOT), ROOT)
    config = CodexConfig(cwd=str(sdk.parent), env={"CODEX_HOME": str(sdk)}, config_overrides=("approval_policy=\"never\"", "sandbox_mode=\"read-only\"", "sandbox_workspace_write.network_access=false", "features.hooks=false", "features.apps=false", "features.multi_agent=false", "web_search=\"disabled\"", "skills.bundled.enabled=false", "skills.include_instructions=false", "project_doc_max_bytes=0", "project_root_markers=[]", "mcp_servers={}"))
    async with AsyncCodex(config) as codex:
        threads = {}

        def save():
            if state_path:
                atomic(state_path, state)

        thread_tokens = {}

        async def turn(thread, value, schema=None, timeout=120):
            if state["turns"] >= budget["max_turns"] or state["tokens"] >= budget["max_tokens"]:
                raise RuntimeError("Workflow aggregate budget reached")
            state["turns"] += 1
            if time.monotonic() - started >= budget["timeout_seconds"]:
                raise RuntimeError("Workflow wall-time budget reached")
            if isinstance(value, str) and schema:
                value += "\nReturn only JSON matching this exact schema:\n" + json.dumps(schema)
            agent = next(item for item in SPEC["agents"] if threads.get(item["id"]) is thread)
            handle = await thread.turn(value, approval_mode=ApprovalMode.deny_all, output_schema=output_schema(schema) if schema else None, effort=agent.get("effort") or "low")
            try:
                result = await asyncio.wait_for(handle.run(), timeout=min(timeout, max(1, budget["timeout_seconds"] - (time.monotonic() - started))))
            except asyncio.TimeoutError:
                try:
                    await asyncio.wait_for(handle.interrupt(), timeout=10)
                except Exception:
                    pass
                raise RuntimeError("Turn timeout; interruption requested, outcome unknown")
            except asyncio.CancelledError:
                try:
                    await asyncio.wait_for(handle.interrupt(), timeout=10)
                except Exception:
                    pass
                raise
            if result.usage:
                total = result.usage.total.total_tokens
                baseline = thread_tokens.get(thread.id, 0)
                state["tokens"] += result.usage.last.total_tokens if baseline is None else max(0, total - baseline)
                thread_tokens[thread.id] = total
            if state["tokens"] > budget["max_tokens"]:
                raise RuntimeError("Workflow token budget exceeded")
            if schema:
                return completed(result, schema), result
            if getattr(result.status, "value", result.status) != "completed" or result.error or not result.final_response:
                raise RuntimeError("Context turn failed before handoff")
            return result

        async def execute(packet):
            agent = agents[packet["agent"]]
            async with semaphore, locks[agent["id"]]:
                condition = packet.get("when")
                if condition:
                    source = state["packets"][condition["packet"]].get("output", {})
                    actual = source
                    for part in condition["field"].split("."):
                        actual = actual.get(part) if isinstance(actual, dict) else None
                    if actual != condition["equals"]:
                        return {"status": "skipped", "reason": "condition_not_met"}
                state["packets"][packet["id"]] = {"status": "running"}
                save()
                try:
                    thread = threads.get(agent["id"])
                    if thread is None or agent["thread_strategy"] == "fresh":
                        kwargs = {"cwd": str(ROOT), "developer_instructions": agent["instructions"] + "\nAssigned task:\n" + packet["prompt"] + "\nThe turn input is a JSON object containing the actual task data. Process its fields only, not the surrounding task instructions or schema.", "approval_mode": ApprovalMode.deny_all}
                        temporary = Path(tempfile.mkdtemp(prefix="workflow-role-" + agent["id"] + "-")).resolve()
                        if len(agents) > 1 and not agent["tools"] and not agent["skills"] and agent["sandbox"] == "read_only":
                            kwargs["cwd"] = str(temporary)
                        filesystem = {":minimal": "read", str(Path.home()): "deny", str(ROOT): "read" if agent["tools"] or agent["skills"] or agent["sandbox"] == "workspace_write" else "deny", str(Path(sys.prefix).resolve()): "read", str(Path(sys.base_prefix).resolve()): "read", str(temporary): "read" if agent["sandbox"] == "read_only" else "write"}
                        if agent["sandbox"] == "workspace_write":
                            for scope in SPEC["controls"]["write_roots"]:
                                filesystem[str((ROOT / scope).resolve())] = "write"
                        for path in sensitive_paths(ROOT):
                            filesystem[str(path)] = "deny"
                        agent_config = {"project_doc_max_bytes": 0, "sandbox_mode": "workspace-write" if agent["sandbox"] == "workspace_write" else "read-only", "default_permissions": "workflow", "permissions": {"workflow": {"filesystem": filesystem, "network": {"enabled": False}}}, "features": {"shell_tool": False, "apply_patch_freeform": agent["sandbox"] == "workspace_write", "hooks": False, "apps": False, "multi_agent": False}, "web_search": "disabled", "shell_environment_policy": {"inherit": "none", "set": {"PATH": os.environ.get("PATH", ""), "HOME": str(temporary), "TMPDIR": str(temporary)}}, "mcp_servers": {}}
                        assigned_tools = [tool for tool in SPEC["tools"] if tool["name"] in agent["tools"] and tool["approval"] != "deny" and (not tool["side_effect"] or approve_writes)]
                        if assigned_tools:
                            agent_config["mcp_servers"] = {"workflow_tools": {"command": str(Path(sys.executable).absolute()), "args": [str(TOOL_SERVER)], "enabled_tools": [tool["name"] for tool in assigned_tools], "default_tools_approval_mode": "approve", "env": {"WORKFLOW_APPROVE_WRITES": "1" if approve_writes else "0"}}}
                        kwargs["config"] = agent_config
                        if agent.get("model"):
                            kwargs["model"] = agent["model"]
                        if agent.get("effort"):
                            kwargs["config"]["model_reasoning_effort"] = agent["effort"]
                        saved_id = state["threads"].get(agent["id"])
                        thread = await codex.thread_resume(saved_id, **kwargs) if saved_id and agent["thread_strategy"] == "reuse" else await codex.thread_start(**kwargs)
                        thread_tokens[thread.id] = None if saved_id and agent["thread_strategy"] == "reuse" else 0
                        threads[agent["id"]] = thread
                        state["threads"][agent["id"]] = thread.id
                        state.setdefault("sdk_configuration", {})[agent["id"]] = {"cwd": kwargs["cwd"], "model": kwargs.get("model"), "effort": agent.get("effort") or "low", "approval_mode": "deny_all", "config": agent_config}
                    prompt = json.dumps(packet_input(request, packet), ensure_ascii=False)
                    catalog = [tool for tool in SPEC["tools"] if tool["name"] in agent["tools"]]
                    permitted = [tool for tool in catalog if tool["approval"] != "deny" and (not tool["side_effect"] or approve_writes)]
                    if catalog:
                        prompt += "\nUse only these host-permitted tool contracts. Each CLI is available as an MCP workflow_tools tool accepting {request: <input JSON>}; call the MCP tool, never shell.\n" + json.dumps(permitted)
                    skills = [item for item in SPEC["skills"] if item["name"] in agent["skills"]]
                    if skills:
                        skill_inputs = [TextInput(prompt + "\nUse " + " ".join("$" + item["name"] for item in skills))]
                        skill_inputs.extend(SkillInput(item["name"], str(ROOT / "skills" / item["name"] / "SKILL.md")) for item in skills)
                    else:
                        skill_inputs = prompt
                    if packet["depends_on"]:
                        await turn(thread, skill_inputs + "\nWait for the dependency evidence and return only READY." if isinstance(skill_inputs, str) else skill_inputs)
                        evidence = {name: state["packets"][name] for name in packet["depends_on"]}
                        value = ExternalMessage(tool_name="work_packet_results", namespace="workflow", content=json.dumps(evidence, ensure_ascii=False))
                    else:
                        value = skill_inputs
                    last_error = None
                    for attempt in range(packet.get("retries", 0) + 1):
                        try:
                            output, receipt = await turn(thread, value, packet["output_schema"], agent["timeout_seconds"])
                            accept(packet, output, request)
                            tool_receipts = []
                            items = receipt.items
                            if permitted and hasattr(thread, "read"):
                                recorded = await thread.read(include_turns=True)
                                actual_turn = next((item for item in recorded.thread.turns if item.id == receipt.id), None)
                                if actual_turn:
                                    items = actual_turn.items
                            for raw in items:
                                item = raw.root if hasattr(raw, "root") else raw
                                if getattr(item, "type", None) == "mcpToolCall":
                                    if getattr(item, "server", None) != "workflow_tools":
                                        raise ValueError("Undeclared MCP server was called")
                                    tool = next((tool for tool in permitted if tool["name"] == item.tool), None)
                                    if tool is None or getattr(item.status, "value", item.status) != "completed" or item.error or item.result is None:
                                        raise ValueError("Declared tool call failed or escaped the registry")
                                    result_data = item.result.model_dump(mode="json", by_alias=False)
                                    observed = result_data.get("structured_content")
                                    if observed is None:
                                        observed = json.loads(next(content["text"] for content in result_data.get("content", []) if isinstance(content, dict) and content.get("type") == "text"))
                                    Draft202012Validator(tool["output_schema"]).validate(observed)
                                    tool_receipts.append({"name": tool["name"], "transport": "mcp_cli_registry" if tool["kind"] == "cli" else "mcp_registry", "exit_code": 0, "output": observed, "call_id": item.id})
                                if getattr(item, "type", None) == "commandExecution":
                                    raise ValueError("Native shell execution is not a declared narrow tool")
                            if any(tool["name"] not in {item["name"] for item in tool_receipts} for tool in permitted):
                                raise ValueError("Required declared tool has no actual runtime receipt")
                            return {"status": "passed", "output": output, "thread_id": thread.id, "turn_id": receipt.id, "attempts": attempt + 1, "skills": [{"name": item["name"], "lifecycle": "verified" if packet.get("assertions") else "loaded", "loading": "explicit_SkillInput", "eval_cases": item["eval_cases"]} for item in skills], "tools": tool_receipts}
                        except Exception as exc:
                            if not isinstance(exc, (ValueError,)) and "ValidationError" not in type(exc).__name__:
                                raise
                            last_error = exc
                            value = ExternalMessage(tool_name="validation_feedback", namespace="workflow", content=str(exc))
                    raise last_error
                except asyncio.CancelledError:
                    state["packets"][packet["id"]] = {"status": "outcome_unknown", "error": "Cancelled; reconcile turn before resume"}
                    save()
                    raise
                except Exception as exc:
                    return {"status": "outcome_unknown" if "unknown" in str(exc) else "failed", "error": str(exc) or type(exc).__name__}

        pending = {name for name in packets if state["packets"].get(name, {}).get("status") != "passed"}
        while pending:
            ready = [packets[name] for name in sorted(pending) if all(state["packets"].get(dep, {}).get("status") == "passed" for dep in packets[name]["depends_on"])]
            if not ready:
                for name in pending:
                    state["packets"][name] = {"status": "blocked", "error": "Required dependency failed"}
                break
            results = await asyncio.gather(*(execute(packet) for packet in ready))
            for packet, result in zip(ready, results):
                state["packets"][packet["id"]] = result
                pending.remove(packet["id"])
            save()
        result_packets = SPEC["orchestration"]["result_packets"]
        outputs = {name: state["packets"][name].get("output") for name in result_packets}
        state["output"] = outputs[result_packets[0]] if len(result_packets) == 1 else outputs
        required = [state["packets"][name] for name, packet in packets.items() if packet["required"]]
        state["status"] = "passed" if all(item["status"] in ("passed", "skipped") for item in required) and all(state["packets"][name]["status"] == "passed" for name in result_packets) else "failed"
        if state["status"] == "passed" and any(item["status"] not in {"passed", "skipped"} for item in state["packets"].values()):
            state["status"] = "partial"
        if state["status"] == "passed":
            verify_state(state, request)
        state["duration_ms"] = round((time.monotonic() - started) * 1000)
        state["checkpoint_location"] = str(state_path) if state_path else None
        save()
        return state


def main():
    parser = argparse.ArgumentParser(description="Run, inspect, and verify this Codex SDK workflow")
    parser.add_argument("operation", choices=["run", "status", "verify", "serve"])
    parser.add_argument("--input")
    parser.add_argument("--run-id", default="latest")
    parser.add_argument("--state-dir", type=Path, default=state_directory(ROOT))
    parser.add_argument("--approve-writes", action="store_true")
    args = parser.parse_args()
    if not args.run_id.replace("-", "").replace("_", "").isalnum():
        parser.error("Invalid run ID")
    state_path = args.state_dir / f"{args.run_id}.json"
    if args.operation == "serve":
        if __package__:
            from .mcp_server import serve
        else:
            from mcp_server import serve

        serve(args.state_dir)
        return 0
    if args.operation in {"status", "verify"}:
        state = json.loads(state_path.read_text())
        if args.operation == "verify" and state.get("status") == "passed":
            verify_state(state, state.get("request"))
    else:
        request = json.loads(Path(args.input).read_text() if args.input else sys.stdin.read())
        state = asyncio.run(run(request, state_path=state_path, approve_writes=args.approve_writes))
    print(json.dumps(state, ensure_ascii=False))
    return 0 if state.get("status") == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        raise SystemExit(1)
