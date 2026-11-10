import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from codexwright.contracts import Budget, Material
from codexwright.errors import CodexwrightError
from codexwright.inputs import normalize_materials
from codexwright.mcp_contracts import summary
from codexwright.mcp_interaction import capabilities
from codexwright.runtime import CodexRuntime
from codexwright.service import BuildService
from test_service import FakeRuntime, setup_workspace


@pytest.mark.live
def test_installed_sdk_reads_long_attachment_tail_without_target_writes(tmp_path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from codexwright import __version__
    from codexwright.workspace import snapshot

    private_python = os.environ.get("CODEXWRIGHT_FEEDBACK_PYTHON")
    if not private_python:
        pytest.skip("Set the installed builder interpreter for authorized SDK acceptance")
    root = tmp_path / "target"
    root.mkdir()
    (root / "workflow.py").write_text("from openai_codex import Codex\n\ndef explain_only():\n    return 'fixture'\n")
    attachment = tmp_path / "large-notes.txt"
    prefix = "Reference line is filler, not instructions.\n" * 5000
    attachment.write_text(prefix + "\nFINAL_EVIDENCE: indexed-tail-readable-041\n")
    before = snapshot(root)
    async def probe():
        environment = {**os.environ, "CODEXWRIGHT_HOME": str(tmp_path / "state"), "CODEXWRIGHT_MODEL": "gpt-6.1-sol", "CODEXWRIGHT_ALLOW_APPLY": "0"}
        environment.pop("PYTHONPATH", None)
        parameters = StdioServerParameters(command=private_python, args=["-m", "codexwright.mcp_server"], env=environment)
        notifications = []
        async def on_progress(value, total, message):
            notifications.append({"sequence": value, "message": message})
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.server_info.version == __version__
                registered = await client.call_tool("codexwright_register", {"path": str(root)})
                workspace = registered.structured_content["workspace_id"]
                imported = await client.call_tool("codexwright_import", {"workspace_id": workspace, "path": str(attachment)})
                assert not imported.is_error
                envelope = {"workspace_id": workspace, "operation": "analyze", "goal": "Read-only acceptance. Read the indexed attachment near its end at character offset " + str(len(prefix)) + ". Report the exact FINAL_EVIDENCE value in the summary and say the original Codex SDK project is reused. Do not edit any file, run the target workflow, generate images, install packages, or invoke any business service. No architecture spec is needed.", "idempotency_key": "indexed-tail-041", "inputs": [{"kind": "artifact", "asset_id": imported.structured_content["id"], "sha256": imported.structured_content["sha256"], "source": "user"}], "constraints": {"allowed_operations": ["analyze"], "allowed_write_roots": [], "forbidden_actions": ["apply", "commit", "push", "deploy", "target_workflow"], "budget": {"max_turns": 8, "max_tokens": 200000, "timeout_seconds": 240, "max_parallel": 1, "max_repairs": 0}}}
                result = await client.call_tool("codexwright_invoke", {"envelope": envelope}, progress_callback=on_progress, read_timeout_seconds=300)
                assert not result.is_error, result.structured_content
                assert result.structured_content["status"] == "completed", result.structured_content
                run_id = result.structured_content["run_id"]
                content = []
                offset = 0
                while offset is not None:
                    page = await client.call_tool("codexwright_read", {"category": "results", "reference": run_id, "offset": offset})
                    assert not page.is_error
                    content.append(page.structured_content["content"])
                    offset = page.structured_content.get("next_offset")
                complete = json.loads("".join(content))
                assert "indexed-tail-readable-041" in complete["summary"]
                assert complete["material_coverage"]["indexed_only"] == 1
                assert complete["material_coverage"]["available_chars"] == len(attachment.read_text())
                assert complete["usage"]["inference_calls"] >= 2 and complete["usage"]["tokens"] > 0
                assert notifications and any("Materials indexed" in entry["message"] for entry in notifications)
                assert any("Model usage updated" in entry["message"] for entry in notifications)
                assert all(run_id in entry["message"] for entry in notifications)
                assert snapshot(root)["sha256"] == before["sha256"]
                from codexwright.store import atomic_json
                receipt = {"package_version": __version__, "api_version": complete.get("api_version", "0.4"), "fixture": "long-attachment-tail", "sdk_runtime": "0.167.0", "target_unchanged": True, "summary": complete["summary"], "status": complete["status"], "verification": complete["verification"], "usage": complete["usage"], "material_coverage": complete["material_coverage"], "progress_notifications": len(notifications), "run_id": run_id}
                receipt_path = os.environ.get("CODEXWRIGHT_FEEDBACK_RECEIPT")
                if receipt_path:
                    atomic_json(receipt_path, receipt)
                print(json.dumps(receipt, ensure_ascii=False))
    asyncio.run(probe())


def test_long_materials_are_complete_private_and_indexed(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    text = "start\n" + "evidence\n" * 15000 + "TAIL_EVIDENCE"
    attachment = tmp_path / "notes.txt"
    attachment.write_text(text)
    asset = service.import_asset(workspace["id"], attachment)
    stage = tmp_path / "stage"
    materials, images = normalize_materials([Material(kind="artifact", asset_id=asset["id"], sha256=asset["sha256"], source="user")], root, stage, store=service.store, workspace_id=workspace["id"])
    projected = materials[0]
    assert not images and not list(root.iterdir())
    assert "content" not in projected and projected["inline_complete"] is False
    assert projected["availability"] == "complete" and projected["review_status"] == "not_measured"
    frozen = stage / projected["path"]
    assert frozen.read_text() == text and frozen.stat().st_mode & 0o777 == 0o600
    assert projected["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert projected["source_sha256"] == asset["sha256"]
    assert projected["content_chars"] == len(text) and projected["inline_chars"] == 256


def test_material_tail_secrets_and_symlink_destinations_are_rejected(tmp_path):
    root = tmp_path / "target"
    root.mkdir()
    (root / "notes.txt").write_text("x" * 100001 + "sk-proj-" + "x" * 30)
    with pytest.raises(CodexwrightError, match="Secret-like"):
        normalize_materials([Material(kind="file", path="notes.txt")], root, tmp_path / "stage")
    outside = tmp_path / "outside"
    outside.mkdir()
    stage = tmp_path / "linked-stage"
    stage.mkdir()
    (stage / "_codexwright_inputs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(CodexwrightError, match="symlinks"):
        normalize_materials([Material(kind="text", content="notes")], root, stage)
    assert not list(outside.iterdir())


def test_word_extraction_preserves_evidence_after_old_truncation_boundary(tmp_path):
    import zipfile
    root = tmp_path / "target"
    root.mkdir()
    text = "word evidence " * 10000 + "FINAL_WORD_EVIDENCE"
    xml = '<w:document xmlns:w="urn:word"><w:body><w:t>' + text + '</w:t></w:body></w:document>'
    with zipfile.ZipFile(root / "notes.docx", "w") as archive:
        archive.writestr("word/document.xml", xml)
    stage = tmp_path / "stage"
    values, images = normalize_materials([Material(kind="file", path="notes.docx")], root, stage)
    assert not images and values[0]["content_chars"] == len(text)
    assert (stage / values[0]["path"]).read_text() == text


def test_builder_cannot_write_frozen_input_mount(tmp_path, monkeypatch):
    root = tmp_path / "stage"
    root.mkdir()
    (root / "_codexwright_inputs").mkdir()
    monkeypatch.setattr("codexwright.runtime.runtime_home", lambda home: (tmp_path / "sdk", {}))
    config = CodexRuntime(tmp_path / "state").config(root, write=True)
    settings = "\n".join(config.config_overrides)
    assert json.dumps(str(root.resolve())) + '="write"' in settings
    assert json.dumps(str(root / "_codexwright_inputs")) + '="read"' in settings


def test_service_context_has_frozen_index_without_raw_input_duplication(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    FakeRuntime.calls = []
    FakeRuntime.response = {"operation": "analyze", "summary": "Evidence available; review is unmeasured", "profile_json": "{}", "spec_json": None, "questions": [], "assumptions": []}
    content = "UNIQUE_INPUT" + "evidence " * 20000 + "TAIL"
    result = asyncio.run(service.invoke({"workspace_id": workspace["id"], "operation": "analyze", "goal": "Read the selected material", "inputs": [{"kind": "text", "content": content, "source": "user"}]}))
    external = next(call["external"] for call in FakeRuntime.calls if "external" in call)
    assert "inputs" not in external["request"]
    assert len(json.dumps(external)) < 25000
    stage = service.store.home / "staging" / result["run_id"]
    index = json.loads((stage / "_codexwright_inputs/index.json").read_text())
    assert (stage / index[0]["path"]).read_text() == content
    assert result["material_coverage"]["indexed_only"] == 1
    assert result["material_coverage"]["review_status"] == "not_measured"
    assert summary(service.status(run_id=result["run_id"]))["material_coverage"] == result["material_coverage"]
    assert not list(root.iterdir())


def test_results_view_pages_exact_result_without_private_record(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    session = service.new_session(workspace["id"])
    run_id = service.run_start("review", session, envelope={"content": "PRIVATE_INPUT"}, baseline={"files": "PRIVATE_BASELINE" * 5000})
    result = {"status": "completed", "operation": "review", "run_id": run_id, "workspace_id": workspace["id"], "session_id": session["id"], "summary": "完整结论" * 6000, "verification": "not_run", "assumptions": ["not validated"], "checks": [], "changed_files": []}
    service.run_finish(run_id, result)
    offset = 0
    parts = []
    while offset is not None:
        page = service.read("results", run_id, offset=offset, limit=401)
        parts.append(page["content"])
        offset = page["next_offset"]
    assert json.loads("".join(parts)) == result
    assert "PRIVATE_INPUT" not in "".join(parts) and "PRIVATE_BASELINE" not in "".join(parts)
    assert {"category": "results", "reference": run_id} in summary(service.status(run_id=run_id))["references"]
    assert "PRIVATE_BASELINE" in service.read("runs", run_id, limit=50000)["content"]
    with pytest.raises(CodexwrightError, match="Offset exceeds"):
        service.read("results", run_id, offset=1000000)


def test_registration_rejects_oversize_before_state_and_model(tmp_path):
    root = tmp_path / "target"
    root.mkdir()
    with (root / "large.txt").open("wb") as stream:
        stream.truncate(30000001)
    service = BuildService(tmp_path / "state", runtime_factory=lambda *args, **kwargs: pytest.fail("Do not start a model for an oversized workspace"))
    with pytest.raises(CodexwrightError) as raised:
        service.register(root)
    assert raised.value.code == "workspace_too_large"
    assert raised.value.details["limits"]["bytes"] == 30000000
    assert raised.value.details["observed"]["bytes"] == 30000001
    assert raised.value.details["scan_complete"] is False
    assert not (service.store.home / "workspaces").exists()
    assert not (service.store.home / "sessions").exists()


def test_preflight_validates_changed_workspace_before_starting_runtime(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    assert workspace["workspace"]["files"] == 0 and workspace["workspace"]["bytes"] == 0
    with (root / "large.txt").open("wb") as stream:
        stream.truncate(30000001)
    service.runtime_factory = lambda *args, **kwargs: pytest.fail("No runtime preflight for oversized input")
    with pytest.raises(CodexwrightError, match="snapshot limit"):
        asyncio.run(service.doctor(workspace["id"]))


def test_stream_usage_counts_inference_calls_not_turns_or_duplicate_updates(tmp_path):
    events = []
    runtime = CodexRuntime(tmp_path, budget=Budget(max_tokens=10000), event=lambda event, **fields: events.append((event, fields)))
    class Handle:
        id = "turn-1"
        async def stream(self):
            for total in (100, 100, 300):
                usage = {"total": {"totalTokens": total, "inputTokens": total - 10, "cachedInputTokens": max(0, total - 110), "outputTokens": 10}, "last": {"totalTokens": total}}
                yield SimpleNamespace(method="thread/tokenUsage/updated", payload=SimpleNamespace(thread_id="thread-1", token_usage=usage))
            yield SimpleNamespace(method="item/completed", payload=SimpleNamespace(item=SimpleNamespace(type="agentMessage", phase="final_answer", text="okay")))
            yield SimpleNamespace(method="turn/completed", payload=SimpleNamespace(turn=SimpleNamespace(status="completed", error=None)))
    class Thread:
        id = "thread-1"
        async def turn(self, *args, **kwargs):
            return Handle()
    asyncio.run(runtime.run(Thread(), "read"))
    assert runtime.tokens == 300 and runtime.usage["turns"] == 1
    assert runtime.usage["inference_calls"] == 2
    assert runtime.usage["input_tokens"] == 290 and runtime.usage["cached_input_tokens"] == 190
    assert runtime.usage["uncached_input_tokens"] == 100
    assert len([event for event, fields in events if event == "usage_updated"]) == 2


def test_failed_stream_keeps_observed_usage(tmp_path):
    runtime = CodexRuntime(tmp_path)
    class Handle:
        id = "failed-turn"
        async def stream(self):
            yield SimpleNamespace(method="thread/tokenUsage/updated", payload=SimpleNamespace(thread_id="thread-1", token_usage={"total": {"total_tokens": 120}, "last": {"total_tokens": 120}}))
            yield SimpleNamespace(method="turn/completed", payload=SimpleNamespace(turn=SimpleNamespace(status="failed", error={"message": "failure"})))
    class Thread:
        id = "thread-1"
        async def turn(self, *args, **kwargs):
            return Handle()
    with pytest.raises(CodexwrightError, match="did not complete"):
        asyncio.run(runtime.run(Thread(), "read"))
    assert runtime.usage["tokens"] == 120 and runtime.usage["inference_calls"] == 1


def test_failed_turn_without_usage_is_explicitly_unmeasured(tmp_path):
    events = []
    runtime = CodexRuntime(tmp_path, event=lambda kind, **fields: events.append((kind, fields)))
    async def collect(handle):
        return SimpleNamespace(status="failed", error={"message": "failure"}, final_response=None, usage=None)
    runtime.collect = collect
    class Thread:
        id = "thread-1"
        async def turn(self, *args, **kwargs):
            return SimpleNamespace(id="failed-turn")
    with pytest.raises(CodexwrightError, match="did not complete"):
        asyncio.run(runtime.run(Thread(), "read"))
    assert runtime.usage["unmeasured_turns"] == 1 and runtime.usage["tokens"] == 0
    assert any(kind == "usage_incomplete" for kind, fields in events)


def test_incomplete_stream_without_usage_preserves_unknown_cost(tmp_path):
    runtime = CodexRuntime(tmp_path)
    async def collect(handle):
        raise CodexwrightError("outcome_unknown", "Stream ended without terminal evidence")
    runtime.collect = collect
    class Thread:
        id = "thread-1"
        async def turn(self, *args, **kwargs):
            return SimpleNamespace(id="incomplete-turn")
    with pytest.raises(CodexwrightError, match="terminal evidence"):
        asyncio.run(runtime.run(Thread(), "read"))
    assert runtime.usage["unmeasured_turns"] == 1
    assert not runtime.handles and not runtime.handle_threads


def test_resumed_stream_counts_all_new_inferences_but_not_history(tmp_path):
    runtime = CodexRuntime(tmp_path, budget=Budget(max_tokens=1000))
    runtime.thread_tokens["thread-1"] = None
    class Handle:
        id = "new-turn"
        async def stream(self):
            for turn_id, total, last in (("old-turn", 500000, 500000), ("new-turn", 500100, 100), ("new-turn", 500350, 250)):
                yield SimpleNamespace(method="thread/tokenUsage/updated", payload=SimpleNamespace(thread_id="thread-1", turn_id=turn_id, token_usage={"total": {"total_tokens": total}, "last": {"total_tokens": last}}))
            yield SimpleNamespace(method="item/completed", payload=SimpleNamespace(item=SimpleNamespace(type="agentMessage", phase="final_answer", text="okay")))
            yield SimpleNamespace(method="turn/completed", payload=SimpleNamespace(turn=SimpleNamespace(status="completed", error=None)))
    class Thread:
        id = "thread-1"
        async def turn(self, *args, **kwargs):
            return Handle()
    asyncio.run(runtime.run(Thread(), "continue"))
    assert runtime.tokens == 350 and runtime.usage["inference_calls"] == 2


def test_request_progress_is_separate_from_service_delivery_support():
    context = SimpleNamespace(protocol_version="2025-06-18", request_context=SimpleNamespace(meta=None, session=SimpleNamespace(client_capabilities=SimpleNamespace(elicitation=None))))
    value = capabilities(context, True)
    assert value["progress"] is value["request_progress_token"] is False
    assert value["progress_notifications"] and value["status_polling"] and value["event_replay"]
    context.request_context.meta = SimpleNamespace(progress_token="owned-token")
    assert capabilities(context, True)["request_progress_token"] is True


def test_real_stdio_progress_subscription_and_result_paging(tmp_path):
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from codexwright import __version__

    root = tmp_path / "target"
    root.mkdir()
    runner = tmp_path / "server.py"
    runner.write_text("""import asyncio,json
from types import SimpleNamespace
from codexwright.mcp_server import server_for
from codexwright.service import BuildService
class Runtime:
    def __init__(self, home, *, event, **kwargs):
        self.event=event
        self.turns=0
        self.tokens=0
        self.usage={"turns":0,"tokens":0,"inference_calls":0}
    async def __aenter__(self): return self
    async def __aexit__(self,*args): pass
    async def thread(self,*args,**kwargs): return SimpleNamespace(id="fixture-thread")
    async def run(self,thread,text,**kwargs):
        self.turns+=1
        self.tokens+=100
        self.usage={"turns":self.turns,"tokens":self.tokens,"inference_calls":self.turns}
        self.event("usage_updated",usage=self.usage)
        await asyncio.sleep(0.02)
        result={"operation":"analyze","summary":"完整结论"*5000,"profile_json":"{}","spec_json":None,"questions":[],"assumptions":[]}
        return SimpleNamespace(final_response=json.dumps(result) if kwargs.get("schema") else "READY")
server_for(BuildService(runtime_factory=Runtime)).run(transport="stdio")
""")
    async def probe():
        parameters = StdioServerParameters(command=sys.executable, args=[str(runner)], env={**os.environ, "CODEXWRIGHT_HOME": str(tmp_path / "state")})
        notifications = []
        async def on_progress(value, total, message):
            notifications.append((value, message))
        async with stdio_client(parameters) as (read, write):
            async with ClientSession(read, write) as client:
                initialized = await client.initialize()
                assert initialized.server_info.version == __version__
                registered = await client.call_tool("codexwright_register", {"path": str(root)})
                result = await client.call_tool("codexwright_invoke", {"envelope": {"workspace_id": registered.structured_content["workspace_id"], "operation": "analyze", "goal": "Analyze", "idempotency_key": "stdio-progress"}}, progress_callback=on_progress)
                assert not result.is_error and result.structured_content["omitted"]["summary"]
                run_id = result.structured_content["run_id"]
                assert notifications and all(run_id in message for value, message in notifications)
                assert any("Materials indexed" in message for value, message in notifications)
                assert any("Model usage updated" in message for value, message in notifications)
                values = [value for value, message in notifications]
                assert values == sorted(set(values))
                offset = 0
                content = []
                while offset is not None:
                    page = await client.call_tool("codexwright_read", {"category": "results", "reference": run_id, "offset": offset, "limit": 4000})
                    assert not page.is_error
                    content.append(page.structured_content["content"])
                    offset = page.structured_content.get("next_offset")
                full = json.loads("".join(content))
                assert full["summary"] == "完整结论" * 5000
                assert full["usage"] == {"turns": 2, "tokens": 200, "inference_calls": 2}
                assert not list(root.iterdir())
    asyncio.run(probe())
