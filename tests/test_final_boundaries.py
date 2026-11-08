import asyncio
import json
from types import SimpleNamespace

import pytest

from build_mas.cli import exit_code, local_approval
from build_mas.runtime import CodexRuntime
from test_service import prepared, setup_workspace


def test_interactive_review_displays_every_page(tmp_path, spec, monkeypatch, capsys):
    service, root, workspace = setup_workspace(tmp_path)
    proposal, session = prepared(service, root, workspace, spec)
    proposal["changes"][0]["content"] = "# " + "x" * 70000 + "\n"
    proposal["diff"] = "EXACT BEGIN\n" + "x" * 70000 + "\nEXACT END\n"
    service.store.write("proposals", proposal["id"], proposal)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "approve")
    approval = local_approval(service, proposal["id"], False)
    printed = capsys.readouterr().err
    assert "EXACT BEGIN" in printed and "EXACT END" in printed
    assert approval["proposal_id"] == proposal["id"]


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
    assert result["models"] == ["fixture-model"] and exit_code(result) == 4
