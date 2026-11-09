import asyncio
from enum import Enum
from types import SimpleNamespace

import pytest

from build_mas.contracts import Budget
from build_mas.runtime import CodexRuntime, strict_schema


class Phase(Enum):
    final_answer = "final_answer"


class FakeHandle:
    id = "turn_fixture"

    async def stream(self):
        yield SimpleNamespace(method="item/completed", payload=SimpleNamespace(item=SimpleNamespace(type="agentMessage", phase=Phase.final_answer, text='{"value":"okay"}')))
        yield SimpleNamespace(method="turn/completed", payload=SimpleNamespace(turn=SimpleNamespace(status="completed", error=None, duration_ms=1)))


def test_enum_phase_and_terminal_evidence(tmp_path):
    result = asyncio.run(CodexRuntime(tmp_path).collect(FakeHandle()))
    assert result.final_response == '{"value":"okay"}'
    assert result.status == "completed"


def test_empty_or_incomplete_stream_never_success(tmp_path):
    class EmptyHandle:
        id = "empty"

        async def stream(self):
            if False:
                yield None

    with pytest.raises(Exception, match="without terminal"):
        asyncio.run(CodexRuntime(tmp_path).collect(EmptyHandle()))


def test_public_imports_only():
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "src/build_mas"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("openai_codex"):
                assert node.module in {"openai_codex", "openai_codex.types"}
                assert path.name == "runtime.py" or "templates" in path.parts
            if isinstance(node, ast.Attribute):
                assert node.attr not in {"_client", "register_tool", "spawn_agent", "create_agent"}


def test_strict_sdk_outer_schema():
    schema = strict_schema({"type": "object", "properties": {"value": {"type": "string", "default": "x"}}})
    assert schema["required"] == ["value"]
    assert schema["additionalProperties"] is False
    assert "default" not in schema["properties"]["value"]


def test_resumed_thread_charges_only_current_turn(tmp_path):
    runtime = CodexRuntime(tmp_path, budget=Budget(max_tokens=1000))
    runtime.thread_tokens["old-thread"] = None
    async def collect(handle):
        return SimpleNamespace(status="completed", error=None, final_response="okay", usage={"total": {"totalTokens": 500100}, "last": {"totalTokens": 100}})
    runtime.collect = collect
    class Thread:
        id = "old-thread"
        async def turn(self, *args, **kwargs):
            return SimpleNamespace(id="new-turn")
    asyncio.run(runtime.run(Thread(), "continue"))
    assert runtime.tokens == 100


@pytest.mark.parametrize("outcome", ["accept", "decline", "unavailable", "timeout", "failed"])
@pytest.mark.parametrize("device", [False, True])
def test_login_requires_user_confirmation_and_cancels_on_failure(tmp_path, monkeypatch, outcome, device):
    events = []
    class Login:
        auth_url = "https://auth.example.invalid/login"
        verification_url = "https://auth.example.invalid/device"
        user_code = "USER-ONLY"
        async def wait(self):
            events.append("wait")
            if outcome == "timeout":
                raise asyncio.TimeoutError
            return SimpleNamespace(success=outcome != "failed")
        async def cancel(self):
            events.append("cancel")
    class Client:
        def __init__(self, config):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            events.append("closed")
        async def login_chatgpt(self):
            events.append("start")
            return Login()
        async def login_chatgpt_device_code(self):
            events.append("start")
            return Login()
    monkeypatch.setattr("build_mas.runtime.AsyncCodex", Client)
    runtime = CodexRuntime(tmp_path)
    async def authorize(instruction):
        events.append("authorize")
        assert instruction == ({"verification_url": Login.verification_url, "user_code": Login.user_code} if device else {"auth_url": Login.auth_url})
        if outcome in {"decline", "unavailable"}:
            raise RuntimeError(outcome)
    if outcome == "accept":
        assert asyncio.run(runtime.login(device=device, authorize=authorize))["status"] == "ready"
        assert events == ["start", "authorize", "wait", "closed"]
    else:
        with pytest.raises(Exception):
            asyncio.run(runtime.login(device=device, authorize=authorize))
        assert "closed" in events
        if outcome != "failed":
            assert "cancel" in events
        if outcome in {"decline", "unavailable"}:
            assert "wait" not in events


def test_login_without_confirmation_never_starts_sdk(tmp_path, monkeypatch):
    def forbidden(config):
        pytest.fail("SDK login must not start without a user-only confirmation channel")
    monkeypatch.setattr("build_mas.runtime.AsyncCodex", forbidden)
    with pytest.raises(Exception, match="confirmation channel"):
        asyncio.run(CodexRuntime(tmp_path).login())
