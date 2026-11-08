import json
import socket
import threading

import pytest

from build_mas.contracts import CheckSpec
from build_mas.verify import execute_check, command_for


def test_artifact_receipt(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    (root / "value.json").write_text('{"value":"okay"}')
    check = CheckSpec(id="file", kind="artifact", target="value.json", expected={"type": "object", "required": ["value"]})
    receipt = execute_check(check, root, tmp_path / "evidence")
    assert receipt["status"] == "passed" and receipt["sha256"]
    missing = execute_check(CheckSpec(id="missing", kind="artifact", target="missing.py"), root, tmp_path / "evidence")
    assert missing["status"] == "failed" and missing["error"]["code"] == "missing_artifact"


def test_executable_check_captures_failure(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    (root / "fail.py").write_text("raise SystemExit(7)\n")
    result = execute_check(CheckSpec(id="failed", kind="cli_smoke", target="fail.py"), root, tmp_path / "evidence")
    assert result["status"] == "failed"
    assert result["exit_code"] != 0


def test_import_check_accepts_module_or_python_file(tmp_path):
    root = tmp_path / "target"
    root.mkdir()
    (root / "workflow.py").write_text("value='imported'\n")
    for target in ("workflow", "workflow.py"):
        record = execute_check(CheckSpec(id="import", kind="import", target=target), root, tmp_path / "evidence")
        assert record["status"] == "passed", record
    with pytest.raises(Exception):
        command_for(CheckSpec(id="bad", kind="import", target="../outside.py"), root)


def test_sandbox_blocks_mutation_and_external_read(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    sibling = tmp_path / "private.txt"; sibling.write_text("fixture")
    (root / "probe.py").write_text("from pathlib import Path\nfor name in " + repr([str(sibling), str(root / "modified")]) + ":\n    try:\n        Path(name).write_text('attempt')\n    except PermissionError:\n        pass\n    else:\n        raise SystemExit(9)\nprint('DENIED')\n")
    result = execute_check(CheckSpec(id="sandbox", kind="cli_smoke", target="probe.py", expected="DENIED"), root, tmp_path / "evidence")
    assert result["status"] == "passed", result
    assert sibling.read_text() == "fixture" and not (root / "modified").exists()


def test_migration_finds_old_import(tmp_path):
    root = tmp_path / "target"; root.mkdir()
    (root / "old.py").write_text("from crewai import Agent\n")
    result = execute_check(CheckSpec(id="migration", kind="migration"), root, tmp_path / "evidence")
    assert result["status"] == "failed" and result["error"]["code"] == "migration_incomplete"


def test_sandbox_uses_only_declared_relay_and_records_real_pins(tmp_path, monkeypatch):
    root = tmp_path / "target"
    root.mkdir()
    (root / "probe.py").write_text("""import json, os, socket, urllib.parse
port = urllib.parse.urlsplit(os.environ["HTTPS_PROXY"]).port
with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
    client.sendall(b"CONNECT model.example:443 HTTP/1.1\\r\\n\\r\\nPING")
    stream = client.makefile("rb", buffering=0)
    assert b"200" in stream.readline()
    assert stream.readline() == b"\\r\\n"
    assert stream.read(4) == b"PONG"
with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
    client.sendall(b"CONNECT undeclared.example:443 HTTP/1.1\\r\\n\\r\\n")
    assert b"403" in client.recv(100)
try:
    socket.create_connection(("1.1.1.1", 443), timeout=1)
except OSError:
    pass
else:
    raise SystemExit("Direct undeclared network was permitted")
print(json.dumps({"relay": "passed", "undeclared": "denied", "direct": "denied"}))
""")
    upstream, remote = socket.socketpair()

    def respond():
        with remote:
            assert remote.recv(4) == b"PING"
            remote.sendall(b"PONG")

    thread = threading.Thread(target=respond)
    thread.start()
    pins = [{"host": "model.example", "port": 443, "addresses": ["93.184.216.34"]}]
    calls = []

    def connect(address, **kwargs):
        calls.append(address)
        return upstream

    monkeypatch.setattr("build_mas.network.socket.create_connection", connect)
    expected = {"relay": "passed", "undeclared": "denied", "direct": "denied"}
    receipt = execute_check(CheckSpec(id="relay", kind="codex_smoke", target="probe.py", expected_json=expected), root, tmp_path / "evidence", model_ports=pins)
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert receipt["status"] == "passed", receipt
    assert json.loads(receipt["output"]) == expected
    assert receipt["model_endpoint_pins"] == pins
    assert len(receipt["sandbox_loopback_ports"]) == 1
    assert calls == [("93.184.216.34", 443)]


@pytest.mark.parametrize("kind", ["cli_smoke", "codex_smoke"])
def test_only_live_check_receives_configured_model_credential(tmp_path, monkeypatch, kind):
    root = tmp_path / "target"
    root.mkdir()
    sdk = tmp_path / "sdk"
    sdk.mkdir()
    (sdk / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nenv_key="MODEL_KEY"\n')
    monkeypatch.setenv("MODEL_KEY", "fixture-not-exported")
    monkeypatch.setenv("UNRELATED_SECRET", "fixture-not-exported")
    (root / "probe.py").write_text('import json,os\nprint(json.dumps({"credential_present":bool(os.getenv("MODEL_KEY")),"unrelated_present":bool(os.getenv("UNRELATED_SECRET"))}))\n')
    expected = {"credential_present": kind == "codex_smoke", "unrelated_present": False}
    receipt = execute_check(CheckSpec(id="credential", kind=kind, target="probe.py", expected_json=expected), root, tmp_path / "evidence", runtime_home=sdk)
    assert receipt["status"] == "passed", receipt
    assert "fixture-not-exported" not in json.dumps(receipt)
