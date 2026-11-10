import asyncio
import json
import os
import signal
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import ElicitResult, InputRequiredResult

from codexwright.mcp_server import server_for, reply
from codexwright.service import BuildService
from codexwright.mcp_contracts import SUMMARY_BYTES, PublicResult, summary
from codexwright.mcp_interaction import LoginInteraction
from codexwright.templates.execution import bounded_output
from codexwright.mcp_progress import progress
from codexwright.runtime import CodexRuntime
from test_service import prepared, setup_workspace


def test_public_apply_replay_does_not_ask_or_write_twice(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    proposal["diff"] = service.proposal_diff(proposal["workspace_snapshot"], proposal["changes"])
    service.store.write("proposals", proposal["id"], proposal)
    prompts = []

    async def accept(ctx, message, schema):
        prompts.append(message)
        return SimpleNamespace(action="accept", data=SimpleNamespace(approve=True))

    monkeypatch.setattr("codexwright.mcp_server.Context.elicit", accept)

    async def probe():
        server = server_for(service, allow_apply=True)
        request = {"request": {"proposal_id": proposal["id"], "idempotency_key": "one-apply"}}
        first = await server.call_tool("codexwright_apply", request)
        second = await server.call_tool("codexwright_apply", request)
        assert first.structured_content["status"] == "completed"
        assert second.structured_content == first.structured_content
        assert len(prompts) == 1
        assert (root / "workflow.py").is_file()

    asyncio.run(probe())


def test_summary_limit_keeps_failure_and_readable_references():
    result = summary({"status": "approval_required", "run_id": "run_fixture", "session_id": "ses_fixture", "workspace_id": "ws_fixture", "proposal_id": "prop_fixture", "summary": "字" * 100000, "questions": ["blocked " + "x" * 2000] * 100, "unresolved": ["required " + "x" * 1000] * 100, "checks": [{"status": "failed", "output": "x" * 100000}], "baseline": {"files": "x" * 1000000}, "spec": {"value": "x" * 1000000}})
    assert len(json.dumps(result, ensure_ascii=False).encode()) <= SUMMARY_BYTES
    assert len(reply(result).model_dump_json(by_alias=True).encode()) <= SUMMARY_BYTES
    assert result["status"] == "approval_required" and result["checks_summary"] == {"failed": 1}
    assert result["omitted"] and result["questions"] and result["unresolved"]
    assert {"category": "runs", "reference": "run_fixture"} in result["references"]
    assert "baseline" not in result and "spec" not in result
    PublicResult.model_validate(result)


def test_events_paging_and_status_hide_private_input(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    session = service.new_session(workspace["id"])
    run_id = service.run_start("review", session, envelope={"content": "private context"}, baseline={"files": ["many"]})
    service.emit(run_id, "architecture_started")
    view = summary(service.status(run_id=run_id))
    assert view["last_stage"] == "architecture_started"
    assert "envelope" not in view and "baseline" not in view
    pages = []
    offset = 0
    while offset is not None:
        page = service.read("events", run_id, offset=offset, limit=17)
        pages.append(page["content"])
        offset = page["next_offset"]
    rows = [json.loads(row) for row in "".join(pages).splitlines()]
    assert rows[-1]["event"] == "architecture_started"


def test_event_reads_reject_symlinked_state_directory(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    session = service.new_session(workspace["id"])
    run_id = service.run_start("review", session)
    events = service.store.home / "events"
    events.rename(tmp_path / "retained-events")
    outside = tmp_path / "unselected-events"
    outside.mkdir()
    (outside / f"{run_id}.jsonl").write_text("private\n")
    events.symlink_to(outside, target_is_directory=True)
    with pytest.raises(Exception, match="symlink"):
        service.read("events", run_id)
    with pytest.raises(Exception, match="symlink"):
        service.store.event(run_id, "attempt")
    assert (outside / f"{run_id}.jsonl").read_text() == "private\n"


def test_verification_cancellation_stops_process_group(tmp_path):
    cancel = threading.Event()
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    timer = threading.Timer(0.1, cancel.set)
    timer.start()
    started = time.monotonic()
    _, error = bounded_output(process, timeout=60, cancel=cancel)
    timer.join()
    assert error == "cancelled" and time.monotonic() - started < 3
    assert process.poll() is not None
    with pytest.raises(ProcessLookupError):
        os.killpg(process.pid, 0)


def test_apply_refuses_bad_public_fields_before_confirmation(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    async def forbidden(*args):
        pytest.fail("Invalid input must not start a confirmation")
    monkeypatch.setattr("codexwright.mcp_server.Context.elicit", forbidden)
    async def probe():
        server = server_for(service, allow_apply=True)
        for request in ({"proposal_id": proposal["id"]}, {"proposal_id": proposal["id"], "idempotency_key": "x", "approval_reference": "approval_forged"}):
            result = await server.call_tool("codexwright_apply", {"request": request})
            assert result.is_error and result.structured_content["error"]["code"] == "invalid_input"
        assert not list(root.iterdir())
    asyncio.run(probe())


def test_decline_is_retained_and_new_key_is_new_request(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    prompts = []
    async def decline(*args):
        prompts.append(1)
        return SimpleNamespace(action="decline", data=None)
    monkeypatch.setattr("codexwright.mcp_server.Context.elicit", decline)
    async def probe():
        server = server_for(service, allow_apply=True)
        request = {"request": {"proposal_id": proposal["id"], "idempotency_key": "declined"}}
        first = await server.call_tool("codexwright_apply", request)
        repeated = await server.call_tool("codexwright_apply", request)
        assert repeated.structured_content == first.structured_content and len(prompts) == 1
        await server.call_tool("codexwright_apply", {"request": {"proposal_id": proposal["id"], "idempotency_key": "ask-again"}})
        assert len(prompts) == 2 and not list(root.iterdir())
    asyncio.run(probe())


def test_modern_multiple_pages_and_sealed_state(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    proposal["diff"] = "EXACT BEGIN\n" + "x" * 70000 + "\nEXACT END\n"
    service.store.write("proposals", proposal["id"], proposal)
    async def probe():
        async def answer(*args):
            return ElicitResult(action="decline")
        async with Client(server_for(service, allow_apply=True), elicitation_callback=answer) as client:
            arguments = {"request": {"proposal_id": proposal["id"], "idempotency_key": "sealed"}}
            first = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True)
            assert isinstance(first, InputRequiredResult) and "EXACT BEGIN" in first.input_requests["confirm"].params.message
            assert "offset" not in first.request_state
            second = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True, request_state=first.request_state, input_responses={"confirm": ElicitResult(action="accept", content={"approve": True})})
            assert isinstance(second, InputRequiredResult) and "EXACT END" in second.input_requests["confirm"].params.message
            assert not list(root.iterdir())
            final = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True, request_state=second.request_state, input_responses={"confirm": ElicitResult(action="decline")})
            assert final.structured_content["status"] == "failed" and not list(root.iterdir())
    asyncio.run(probe())


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_stdio_contracts_errors_and_cache_hints(tmp_path, mode):
    async def probe():
        environment = {**os.environ, "CODEXWRIGHT_HOME": str(tmp_path / "state")}
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "codexwright.mcp_server"], env=environment)
        async with Client(parameters, mode=mode) as client:
            tools = await client.list_tools()
            assert tools.ttl_ms == (300000 if mode == "auto" else 0) and tools.cache_scope == "private"
            schemas = {tool.name: tool.output_schema for tool in tools.tools}
            invalid = await client.call_tool("codexwright_invoke", {"envelope": {"workspace_id": "ws_fixture", "goal": "review"}})
            assert invalid.is_error and invalid.structured_content["error"]["code"] == "invalid_input"
            Draft202012Validator(schemas["codexwright_invoke"]).validate(invalid.structured_content)
            result = await client.call_tool("codexwright_read", {"category": "bad", "reference": "run_x"})
            assert result.structured_content["error"]["code"] == "invalid_input"
    asyncio.run(probe())


def test_request_progress_isolated_and_delivery_failure_is_harmless(tmp_path):
    service = BuildService(tmp_path / "state")
    received = {"a": [], "b": []}
    async def run(name, broken=False):
        root = tmp_path / name
        root.mkdir()
        workspace = service.register(root)
        session = service.new_session(workspace["id"])
        class Context:
            async def report_progress(self, value, *, message):
                if broken:
                    raise OSError("disconnected")
                received[name].append((value, message))
        async with progress(service, Context()):
            run_id = service.run_start("review", session)
            await asyncio.sleep(0.01)
            service.emit(run_id, "architecture_started")
            await asyncio.sleep(0.01)
        return run_id
    async def probe():
        a, b = await asyncio.gather(run("a"), run("b", broken=True))
        assert received["a"] and not received["b"]
        assert all(a in message and b not in message for _, message in received["a"])
        numbers = [i for i, _ in received["a"]]
        assert numbers == sorted(set(numbers))
    asyncio.run(probe())


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_modern_login_user_channel_and_cleanup(tmp_path, monkeypatch, action):
    events = []
    class Handle:
        auth_url = "https://auth.example.invalid/login"
        async def wait(self):
            events.append("wait")
            return SimpleNamespace(success=True)
        async def cancel(self):
            events.append("cancel")
    class Codex:
        def __init__(self, config):
            pass
        async def __aenter__(self):
            events.append("open")
            return self
        async def __aexit__(self, *args):
            events.append("close")
        async def login_chatgpt(self):
            events.append("start")
            return Handle()
    monkeypatch.setattr("codexwright.runtime.AsyncCodex", Codex)
    async def answer(ctx, params):
        events.append("user")
        assert params.mode == "url" and params.url == Handle.auth_url
        return ElicitResult(action=action)
    async def probe():
        service = BuildService(tmp_path / "state")
        async with Client(server_for(service), elicitation_callback=answer) as client:
            result = await client.call_tool("codexwright_login", {})
            assert result.structured_content["status"] == ("ready" if action == "accept" else "blocked")
            assert Handle.auth_url not in json.dumps(result.structured_content)
        assert events.count("start") == events.count("user") == events.count("close") == 1
        assert ("wait" in events) == (action == "accept")
        assert ("cancel" in events) == (action == "decline")
    asyncio.run(probe())


@pytest.mark.parametrize("kind", ["timeout", "close"])
def test_pending_modern_login_is_cancelled_and_unlocks(tmp_path, monkeypatch, kind):
    events = []
    class Runtime:
        async def start_login(self, *, device):
            return {"instruction": {"auth_url": "https://auth.example.invalid/login"}}
        async def cancel_login(self, attempt):
            events.append("cancel")
    service = BuildService(tmp_path / "state", runtime_factory=lambda *args, **kwargs: Runtime())
    class Context:
        protocol_version = "2026-07-28"
        request_state = None
        input_responses = None
        request_context = SimpleNamespace(session=SimpleNamespace(client_capabilities=None), meta=None)
    async def probe():
        interaction = LoginInteraction(service)
        if kind == "timeout":
            async def sleep(_seconds):
                return
            monkeypatch.setattr("codexwright.mcp_interaction.asyncio.sleep", sleep)
        result = await interaction.login(Context())
        assert isinstance(result, InputRequiredResult)
        if kind == "timeout":
            await interaction.pending["expiry_task"]
        else:
            await interaction.close()
        assert interaction.pending is None and events == ["cancel"]
        with service.store.lock("builder_login"):
            pass
    asyncio.run(probe())


def test_apply_concurrent_retry_reports_original_run(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    ready = asyncio.Event()
    proceed = asyncio.Event()
    calls = []
    async def verify(*args, **kwargs):
        calls.append(1)
        ready.set()
        await proceed.wait()
        return {"status": "passed", "checks": []}
    service.checked_verify = verify
    async def approve(*args):
        return SimpleNamespace(action="accept", data=SimpleNamespace(approve=True))
    monkeypatch.setattr("codexwright.mcp_server.Context.elicit", approve)
    async def probe():
        server = server_for(service, allow_apply=True)
        arguments = {"request": {"proposal_id": proposal["id"], "idempotency_key": "concurrent"}}
        first = asyncio.create_task(server.call_tool("codexwright_apply", arguments))
        await ready.wait()
        repeat = await server.call_tool("codexwright_apply", arguments)
        assert repeat.structured_content["status"] == "running"
        assert not list(root.iterdir())
        proceed.set()
        result = await first
        assert result.structured_content["status"] == "completed"
        assert result.structured_content["run_id"] == repeat.structured_content["run_id"]
        assert len(calls) == 2
    asyncio.run(probe())


@pytest.mark.parametrize("case", ["expired", "modified", "different_proposal", "restart"])
def test_apply_review_binding_fails_closed(tmp_path, spec, case):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    request = {"proposal_id": proposal["id"], "idempotency_key": "bound"}
    record = service.public_apply(request, review_owner="server_original")
    if case == "expired":
        record["expires_at"] = 0
        service.store.write("apply_requests", record["id"], record)
        with pytest.raises(Exception, match="expired"):
            service.review_page(record)
    elif case == "modified":
        proposal["changes"][0]["content"] = "changed"
        service.store.write("proposals", proposal["id"], proposal)
        with pytest.raises(Exception, match="changed"):
            service.review_page(record)
    elif case == "different_proposal":
        other, _ = prepared(service, root, workspace, spec)
        with pytest.raises(Exception, match="different proposal"):
            service.public_apply({**request, "proposal_id": other["id"]}, review_owner="server_original")
    else:
        with pytest.raises(Exception, match="restarted"):
            service.public_apply(request, review_owner="server_new")
    assert not list(root.iterdir())


def test_legacy_apply_record_reused_only_with_verified_association(tmp_path, spec):
    from codexwright.contracts import ApplyRequest
    from codexwright.store import digest
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    approved = service.approve(proposal["id"])
    run_id = service.run_start("apply", session, proposal_id=proposal["id"])
    key = "legacy"
    internal = {**approved, "idempotency_key": key}
    service.admit("apply_" + workspace["id"], key, digest(ApplyRequest.model_validate(internal).model_dump(mode="json")), run_id)
    record = service.public_apply({"proposal_id": proposal["id"], "idempotency_key": key})
    assert record["run_id"] == run_id
    assert service.public_apply_result(record)["status"] == "outcome_unknown"
    corrupted = service.store.read("runs", run_id)
    corrupted["proposal_id"] = "prop_other"
    service.store.write("runs", run_id, corrupted)
    with pytest.raises(Exception, match="safely associated"):
        service.public_apply({"proposal_id": proposal["id"], "idempotency_key": key})
    assert not list(root.iterdir())


def test_modern_confirmation_token_cannot_be_forged_or_skipped(tmp_path, spec):
    from mcp.shared.exceptions import MCPError
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    proposal["diff"] = "x" * 70000
    service.store.write("proposals", proposal["id"], proposal)
    async def approve(*args):
        return ElicitResult(action="accept", content={"approve": True})
    async def probe():
        arguments = {"request": {"proposal_id": proposal["id"], "idempotency_key": "no-skip"}}
        async with Client(server_for(service, allow_apply=True), elicitation_callback=approve) as client:
            first = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True)
            with pytest.raises(MCPError):
                await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True, request_state=first.request_state + "forged", input_responses={"confirm": ElicitResult(action="accept", content={"approve": True})})
            second = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True, request_state=first.request_state, input_responses={"confirm": ElicitResult(action="accept", content={"approve": True})})
            assert isinstance(second, InputRequiredResult)
            stale = await client.session.call_tool("codexwright_apply", arguments, allow_input_required=True, request_state=first.request_state, input_responses={"confirm": ElicitResult(action="accept", content={"approve": True})})
            assert stale.structured_content["error"]["code"] == "invalid_review_state"
            assert not list(root.iterdir())
    asyncio.run(probe())


def test_modern_client_round_limit_never_shortens_review(tmp_path, spec):
    from mcp.client import InputRequiredRoundsExceededError
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    proposal["diff"] = "x" * 70000
    service.store.write("proposals", proposal["id"], proposal)
    async def approve(*args):
        return ElicitResult(action="accept", content={"approve": True})
    async def probe():
        async with Client(server_for(service, allow_apply=True), elicitation_callback=approve, input_required_max_rounds=1) as client:
            with pytest.raises(InputRequiredRoundsExceededError):
                await client.call_tool("codexwright_apply", {"request": {"proposal_id": proposal["id"], "idempotency_key": "round-limit"}})
            assert not list(root.iterdir())
    asyncio.run(probe())


def test_actual_stdio_modern_approval_and_replay(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    proposal["diff"] = service.proposal_diff(proposal["workspace_snapshot"], proposal["changes"])
    service.store.write("proposals", proposal["id"], proposal)
    prompts = []
    async def approve(ctx, params):
        prompts.append(params.message)
        return ElicitResult(action="accept", content={"approve": True})
    async def probe():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "codexwright.mcp_server"], env={**os.environ, "CODEXWRIGHT_HOME": str(service.store.home), "CODEXWRIGHT_ALLOW_APPLY": "1"})
        async with Client(parameters, elicitation_callback=approve) as client:
            request = {"request": {"proposal_id": proposal["id"], "idempotency_key": "stdio-approved"}}
            first = await client.call_tool("codexwright_apply", request)
            repeated = await client.call_tool("codexwright_apply", request)
            assert first.structured_content["status"] == "completed" and first.structured_content == repeated.structured_content
            assert len(prompts) == 1 and (root / "workflow.py").is_file()
    asyncio.run(probe())


def test_sdk_cancel_preserves_unknown_until_reconciled(tmp_path):
    events = []
    started = asyncio.Event()
    class Handle:
        id = "turn_owned"
        async def interrupt(self):
            events.append("interrupt")
    class Thread:
        id = "thread_owned"
        async def turn(self, *args, **kwargs):
            return Handle()
    async def probe():
        runtime = CodexRuntime(tmp_path, event=lambda kind, **fields: events.append(kind))
        async def collect(handle):
            started.set()
            await asyncio.Event().wait()
        runtime.collect = collect
        task = asyncio.create_task(runtime.run(Thread(), "request"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert "interrupt" in events and "turn_interruption_requested" in events
        assert "turn_completed" not in events
    asyncio.run(probe())


def test_verification_cancel_waits_for_owned_worker(tmp_path):
    service = BuildService(tmp_path / "state")
    started = threading.Event()
    stopped = threading.Event()
    def verify(*args, **kwargs):
        from codexwright.service import _verification_cancel
        cancel = _verification_cancel.get()
        started.set()
        assert cancel.wait(5)
        stopped.set()
        return {"status": "blocked", "checks": []}
    service.mechanical_verify = verify
    async def probe():
        task = asyncio.create_task(service.checked_verify(None, tmp_path, tmp_path))
        await asyncio.to_thread(started.wait, 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert stopped.is_set()
    asyncio.run(probe())


def test_repeated_cancel_does_not_release_running_verification(tmp_path):
    service = BuildService(tmp_path / "state")
    started, finish = threading.Event(), threading.Event()
    def verify(*args, **kwargs):
        started.set()
        finish.wait(3)
        return {"status": "blocked", "checks": []}
    service.mechanical_verify = verify
    async def probe():
        task = asyncio.create_task(service.checked_verify(None, tmp_path, tmp_path))
        await asyncio.to_thread(started.wait, 3)
        task.cancel()
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.sleep(0.01)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(probe())


def test_tools_publish_descriptions_and_schemas(tmp_path):
    async def probe():
        server = server_for(BuildService(tmp_path / "state"), allow_apply=True)
        tools = await server.list_tools()
        for tool in tools:
            assert tool.description and tool.output_schema
            assert tool.output_schema["type"] == "object"
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator.check_schema(tool.output_schema)
        invoke = next(tool for tool in tools if tool.name == "codexwright_invoke")
        schema = invoke.input_schema
        assert "idempotency_key" in json.dumps(schema)
        bad = await server.call_tool("codexwright_invoke", {"envelope": {"workspace_id": "ws_fixture", "goal": "Explain"}})
        assert bad.is_error and bad.structured_content["error"]["code"] == "invalid_input"

    asyncio.run(probe())


@pytest.mark.parametrize("action", ["accept", "decline"])
def test_modern_protocol_approval(tmp_path, spec, action):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, _ = prepared(service, root, workspace, spec)
    messages = []

    async def approve(ctx, params):
        messages.append(params.message)
        return ElicitResult(action=action, content={"approve": True} if action == "accept" else None)

    async def probe():
        async with Client(server_for(service, allow_apply=True), elicitation_callback=approve) as client:
            result = await client.call_tool("codexwright_apply", {"request": {"proposal_id": proposal["id"], "idempotency_key": "modern"}})
            assert result.structured_content["status"] == ("completed" if action == "accept" else "failed")
            assert len(messages) == 1
            assert (root / "workflow.py").exists() == (action == "accept")

    asyncio.run(probe())
