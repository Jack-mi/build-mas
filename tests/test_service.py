import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from codexwright.service import BuildService
from codexwright.store import digest, identifier
from codexwright.workspace import snapshot


class FakeRuntime:
    response = None
    calls = []

    def __init__(self, home, **kwargs):
        self.turns = 0
        self.tokens = 0
        self.home = home

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def thread(self, cwd, instructions, **kwargs):
        self.calls.append({"cwd": cwd, **kwargs})
        return SimpleNamespace(id=kwargs.get("thread_id") or "thread_fake")

    async def run(self, thread, text, **kwargs):
        self.turns += 1
        self.calls.append(kwargs)
        return SimpleNamespace(final_response=json.dumps(self.response) if kwargs.get("schema") else "Ready")


def setup_workspace(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    service = BuildService(tmp_path / "state", runtime_factory=FakeRuntime)
    workspace = service.register(root)
    return service, root, workspace


def test_read_only_intake_and_idempotent_continuation(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    FakeRuntime.response = {"operation": "review", "summary": "Nothing needs editing", "profile_json": '{}', "spec_json": None, "questions": [], "assumptions": []}
    FakeRuntime.calls = []
    envelope = {"workspace_id": workspace["id"], "operation": "review", "goal": "Review this workspace", "idempotency_key": "review-1"}
    first = asyncio.run(service.invoke(envelope))
    second = asyncio.run(service.invoke(envelope))
    assert first == second
    assert not list(root.iterdir())
    follow = asyncio.run(service.invoke({"workspace_id": workspace["id"], "session_id": first["session_id"], "operation": "analyze", "goal": "Explain next"}))
    assert follow["session_id"] == first["session_id"]
    assert any(item.get("thread_id") == "thread_fake" for item in FakeRuntime.calls)
    with pytest.raises(Exception, match="reused for different"):
        asyncio.run(service.invoke({**envelope, "goal": "different"}))


def prepared(service, root, workspace, spec):
    session = service.new_session(workspace["id"])
    spec = service.save_spec(session, spec)
    baseline = snapshot(root)
    proposal_id = identifier("prop")
    proposal = {"id": proposal_id, "session_id": session["id"], "workspace_id": workspace["id"], "spec_revision": spec.revision, "spec_hash": digest(spec.model_dump(mode="json")), "workspace_snapshot": baseline, "changes": [{"path": "workflow.py", "action": "write", "content": "print('fixture')\n"}], "write_roots": ["."], "verification": {"status": "passed"}, "status": "prepared"}
    service.store.write("proposals", proposal_id, proposal)
    return proposal, session


def test_exact_approval_apply_and_replay(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    (root / "user.txt").write_text("keep existing changes")
    proposal, session = prepared(service, root, workspace, spec)
    approved = service.approve(proposal["id"])
    request = {**approved, "idempotency_key": "apply-one"}
    result = asyncio.run(service.apply(request))
    assert result["status"] == "completed" and result["verification"] == "passed"
    assert (root / "workflow.py").exists()
    assert (root / "user.txt").read_text() == "keep existing changes"
    assert asyncio.run(service.apply(request)) == result
    with pytest.raises(Exception, match="consumed"):
        asyncio.run(service.apply({**request, "idempotency_key": "different"}))


def test_forged_or_stale_approval_cannot_write(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    request = {"proposal_id": proposal["id"], "workspace_id": workspace["id"], "expected_spec_revision": 1, "expected_workspace_snapshot": proposal["workspace_snapshot"]["sha256"], "idempotency_key": "x", "approval_reference": "approval_fake"}
    with pytest.raises(Exception):
        asyncio.run(service.apply(request))
    assert not list(root.iterdir())
    approved = service.approve(proposal["id"])
    (root / "new-user-change.txt").write_text("external modification")
    result = asyncio.run(service.apply({**approved, "idempotency_key": "y"}))
    assert result["status"] == "failed" and result["error"]["code"] == "workspace_conflict"
    assert not (root / "workflow.py").exists()


def test_plan_spec_requires_actual_runtime_route(tmp_path, spec_dict):
    service, root, workspace = setup_workspace(tmp_path)
    (root / "existing.py").write_text("from openai_codex import Codex\n")
    FakeRuntime.response = {"operation": "plan", "summary": "planned", "profile_json": '{}', "spec_json": json.dumps(spec_dict), "questions": [], "assumptions": []}
    result = asyncio.run(service.invoke({"workspace_id": workspace["id"], "operation": "plan", "goal": "Plan"}))
    assert result["status"] == "completed" and result["spec_revision"] == 1
    assert list(root.iterdir()) == [root / "existing.py"]
    FakeRuntime.response = {**FakeRuntime.response, "spec_json": json.dumps({**spec_dict, "runtime": {"source": "other", "action": "migrate", "target": "codex_sdk"}})}
    result = asyncio.run(service.invoke({"workspace_id": workspace["id"], "operation": "plan", "goal": "Plan another"}))
    assert result["status"] == "failed" and result["error"]["code"] in {"invalid_runtime_route", "invalid_input"}
