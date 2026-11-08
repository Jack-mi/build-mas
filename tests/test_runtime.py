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
