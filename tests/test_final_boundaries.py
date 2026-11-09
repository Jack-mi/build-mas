import asyncio
import json
from types import SimpleNamespace

import pytest

from build_mas.mcp_server import server_for
from build_mas.runtime import CodexRuntime
from test_service import prepared, setup_workspace


def test_mcp_review_displays_every_page(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    proposal["changes"][0]["content"] = "# " + "x" * 70000 + "\n"
    proposal["diff"] = "EXACT BEGIN\n" + "x" * 70000 + "\nEXACT END\n"
    service.store.write("proposals", proposal["id"], proposal)
    messages = []
    async def elicit(context, message, schema):
        messages.append(message)
        assert not list(root.iterdir())
        return SimpleNamespace(action="accept", data=SimpleNamespace(approve=True))
    monkeypatch.setattr("build_mas.mcp_server.Context.elicit", elicit)
    server = server_for(service, allow_apply=True)
    result = asyncio.run(server.call_tool("buildmas_apply", {"request": {"proposal_id": proposal["id"], "idempotency_key": "paged-approval"}}))
    assert result.structured_content["status"] == "completed"
    assert len(messages) == 2 and "EXACT BEGIN" in messages[0] and "EXACT END" in messages[-1]
    assert "no files are applied yet" in messages[0] and "live SDK check" in messages[-1]


@pytest.mark.parametrize("decision", ["decline", "changed"])
def test_paged_approval_rejects_decline_and_changed_proposal(tmp_path, spec, monkeypatch, decision):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    proposal["diff"] = "x" * 70000
    service.store.write("proposals", proposal["id"], proposal)
    pages = []
    async def elicit(context, message, schema):
        pages.append(message)
        if len(pages) == 2:
            if decision == "decline":
                return SimpleNamespace(action="decline", data=None)
            proposal["changes"][0]["content"] = "print('changed after review')"
            service.store.write("proposals", proposal["id"], proposal)
        return SimpleNamespace(action="accept", data=SimpleNamespace(approve=True))
    monkeypatch.setattr("build_mas.mcp_server.Context.elicit", elicit)
    result = asyncio.run(server_for(service, allow_apply=True).call_tool("buildmas_apply", {"request": {"proposal_id": proposal["id"], "idempotency_key": "changed-pages"}}))
    assert result.is_error and len(pages) == 2
    assert result.structured_content["error"]["code"] == ("permission_denied" if decision == "decline" else "stale_proposal")
    assert not list(root.iterdir())


def test_post_apply_exception_reports_written_files(tmp_path, spec, monkeypatch):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    approved = service.approve(proposal["id"])
    count = 0
    def checks(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("regression runner failed")
        return {"status": "passed", "checks": [], "semantic_review": None}
    monkeypatch.setattr(service, "mechanical_verify", checks)
    result = asyncio.run(service.apply({**approved, "idempotency_key": "post-apply-error"}))
    assert result["status"] == "failed"
    assert result["changed_files"] == ["workflow.py"] and result["backup_ref"]
    assert (root / "workflow.py").is_file()


def test_account_timeout_is_not_runtime_or_auth_success(tmp_path, monkeypatch):
    class Client:
        def __init__(self, config):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def models(self):
            return SimpleNamespace(data=[SimpleNamespace(model="fixture-model")])
        async def account(self):
            raise RuntimeError("routing unavailable")
    monkeypatch.setattr("build_mas.runtime.AsyncCodex", Client)
    result = asyncio.run(CodexRuntime(tmp_path).preflight(tmp_path))
    assert result["status"] == "account_unverified" and result["account_present"] is None
    assert result["models"] == ["fixture-model"]
