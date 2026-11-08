import json

import pytest

from build_mas.service import BuildService
from build_mas.store import Store, digest
from build_mas.workspace import discover, snapshot, transaction_apply, validate_changes, relative_file


def test_source_runtime_detection(tmp_path):
    assert discover(tmp_path, snapshot(tmp_path))["source_runtime"] == "none"
    code = tmp_path / "workflow.py"
    code.write_text("from crewai import Agent\n")
    assert discover(tmp_path, snapshot(tmp_path))["source_runtime"] == "other"
    code.write_text("from openai_codex import Codex\n")
    assert discover(tmp_path, snapshot(tmp_path))["source_runtime"] == "codex_sdk"
    code.write_text("print('custom')\n")
    assert discover(tmp_path, snapshot(tmp_path))["source_runtime"] == "unknown"
    code.write_text("from openai_codex import Codex\nfrom anthropic import Anthropic\n")
    assert discover(tmp_path, snapshot(tmp_path))["source_runtime"] == "codex_sdk"


def test_secret_and_symlink_not_read(tmp_path):
    (tmp_path / ".env").write_text("PRIVATE=fixture")
    (tmp_path / "normal.txt").write_text("okay")
    (tmp_path / "hidden_token.txt").write_text("sk-proj-" + "z" * 40)
    (tmp_path / "escape.txt").symlink_to(tmp_path / ".env")
    captured = snapshot(tmp_path)
    assert set(captured["files"]) == {"normal.txt"}
    with pytest.raises(Exception):
        relative_file(tmp_path, "escape.txt")
    with pytest.raises(Exception):
        relative_file(tmp_path, "../not-here")


def test_transaction_preserves_dirty_and_rejects_conflict(tmp_path):
    root = tmp_path / "repo"; root.mkdir()
    (root / "user.txt").write_text("existing user change")
    baseline = snapshot(root)
    changes = [{"path": "result.txt", "action": "write", "content": "new"}]
    validate_changes(root, changes, ["."])
    after = transaction_apply(root, changes, baseline, tmp_path / "backups")
    assert (root / "user.txt").read_text() == "existing user change"
    assert (root / "result.txt").read_text() == "new"
    assert after["sha256"] != baseline["sha256"]
    with pytest.raises(Exception, match="changed since"):
        transaction_apply(root, changes, baseline, tmp_path / "backup2")


def test_write_roots_and_secret_rejected(tmp_path):
    changes = [{"path": "other.py", "action": "write", "content": "print('safe')\n"}]
    with pytest.raises(Exception, match="outside approved"):
        validate_changes(tmp_path, changes, ["allowed"])
    changes[0]["path"] = ".codex/config.toml"
    with pytest.raises(Exception, match="Protected"):
        validate_changes(tmp_path, changes, ["."])
    changes[0] = {"path": "token.txt", "action": "write", "content": "sk-proj-" + "x" * 45}
    with pytest.raises(Exception, match="Secret-like"):
        validate_changes(tmp_path, changes, ["."])


def test_store_lock_and_scope(tmp_path):
    store = Store(tmp_path / "state")
    with store.lock("ws_test"):
        with pytest.raises(Exception, match="owns this workspace"):
            with Store(tmp_path / "state").lock("ws_test"):
                pass
    with pytest.raises(Exception):
        store.read("runs", "../../escape")
    root = tmp_path / "repo"; root.mkdir()
    service = BuildService(tmp_path / "state")
    workspace = service.register(root)
    assert service.workspace(workspace["id"])["root"] == str(root)
    assert not list(root.iterdir())
