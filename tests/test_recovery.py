import asyncio
import json

import pytest

from codexwright.service import BuildService
from codexwright.store import digest, identifier
from codexwright.workspace import snapshot
from test_service import prepared, setup_workspace, FakeRuntime


def test_admission_survives_crash_without_replay(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    approved = service.approve(proposal["id"])
    request = {**approved, "idempotency_key": "crashed-apply"}
    from codexwright.contracts import ApplyRequest

    with service.store.lock(workspace["id"]):
        run_id = service.run_start("apply", session, proposal_id=proposal["id"])
        service.admit("apply_" + workspace["id"], request["idempotency_key"], digest(ApplyRequest.model_validate(request).model_dump(mode="json")), run_id)
        assert service.status(run_id=run_id)["status"] == "running"
    # The process is still alive, but its ownership lease was released.
    assert service.status(run_id=run_id)["status"] == "outcome_unknown"
    result = asyncio.run(service.apply(request))
    assert result["status"] == "outcome_unknown" and result["run_id"] == run_id
    assert not list(root.iterdir())
    recovered = asyncio.run(service.recover(run_id))
    assert recovered["status"] == "completed"
    assert service.status(run_id=run_id)["status"] == "failed"
    assert not list(root.iterdir())


def test_recover_error_is_terminal(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    session = service.new_session(workspace["id"])
    previous = service.run_start("build", session)
    service.run_finish(previous, {"status": "failed", "operation": "build", "session_id": session["id"], "workspace_id": workspace["id"]})
    result = asyncio.run(service.recover(previous))
    assert result["status"] == "failed"
    assert service.store.read("runs", result["run_id"])["status"] == "failed"


def test_verify_exception_is_terminal(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    _, session = prepared(service, root, workspace, spec)
    def broken(*args, **kwargs):
        raise OSError("fixture failure")
    monkeypatch.setattr(service, "mechanical_verify", broken)
    result = asyncio.run(service.verify(workspace["id"], session["id"]))
    assert result["status"] == "failed"
    assert service.status(run_id=result["run_id"])["status"] == "failed"


def test_approval_expiry_and_changed_review_are_rejected(tmp_path, spec):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    approved = service.approve(proposal["id"], expires_seconds=-1)
    with pytest.raises(Exception, match="expired"):
        asyncio.run(service.apply({**approved, "idempotency_key": "expired"}))
    before = digest(proposal)
    proposal["changes"][0]["content"] = "print('changed')\n"
    service.store.write("proposals", proposal["id"], proposal)
    with pytest.raises(Exception, match="changed while"):
        service.approve(proposal["id"], expected_proposal_hash=before)
    assert not list(root.iterdir())


def test_model_secret_is_never_persisted_or_returned(tmp_path):
    service, root, workspace = setup_workspace(tmp_path)
    secret = "sk-proj-" + "F" * 40
    FakeRuntime.response = {"operation": "review", "summary": secret, "profile_json": "{}", "spec_json": None, "questions": [], "assumptions": []}
    result = asyncio.run(service.invoke({"workspace_id": workspace["id"], "operation": "review", "goal": "review"}))
    assert result["status"] == "failed" and result["error"]["code"] == "secret_detected"
    assert secret not in json.dumps(result)
    assert all(secret not in path.read_text() for path in service.store.home.rglob("*.json"))
