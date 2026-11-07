"""Offline contract check: worker output crosses the boundary as untrusted data."""

import sys
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from minimal_mas import VERDICT_SCHEMA, checked_response, run_workflow


class FakeThread:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.inputs = []

    def run(self, value, **kwargs):
        self.inputs.append((value, kwargs))
        return types.SimpleNamespace(status="completed", error=None, final_response=next(self.responses))


class FakeCodex:
    def __init__(self, verdict='{"verdict":"passed","summary":"verified","evidence":["fixture"]}'):
        self.threads = [FakeThread(["untrusted findings"]), FakeThread(["ready", verdict])]
        self.sandboxes = []
        self.workspaces = []
        self.ephemeral = []

    def thread_start(self, *, sandbox, cwd, ephemeral):
        self.sandboxes.append(sandbox)
        self.workspaces.append(cwd)
        self.ephemeral.append(ephemeral)
        return self.threads[len(self.sandboxes) - 1]


class WorkflowTests(unittest.TestCase):
    def test_worker_result_stays_untrusted(self):
        class Sandbox:
            read_only = object()

        class ExternalMessage:
            def __init__(self, *, tool_name, namespace, content):
                self.tool_name, self.namespace, self.content = tool_name, namespace, content

        previous = sys.modules.get("openai_codex")
        sys.modules["openai_codex"] = types.SimpleNamespace(
            Sandbox=Sandbox, ExternalMessage=ExternalMessage
        )
        try:
            codex = FakeCodex()
            self.assertEqual(run_workflow(codex, "Inspect docs", "/repo")["verdict"], "passed")
            self.assertEqual(codex.sandboxes, [Sandbox.read_only, Sandbox.read_only])
            self.assertEqual(codex.workspaces, ["/repo", "/repo"])
            self.assertEqual(codex.ephemeral, [True, True])
            handoff, kwargs = codex.threads[1].inputs[1]
            self.assertIsInstance(handoff, ExternalMessage)
            self.assertEqual(handoff.content, "untrusted findings")
            self.assertEqual(kwargs["output_schema"], VERDICT_SCHEMA)
            with self.assertRaises(RuntimeError):
                checked_response(types.SimpleNamespace(status="failed", error="failed", final_response=None))
            for verdict in ('{"verdict":"failed","summary":"bad","evidence":[]}',
                            '{"verdict":"blocked","summary":"unknown","evidence":[]}',
                            '{"verdict":"passed","summary":"unproven","evidence":[]}',
                            '{"verdict":"passed","summary":"unproven","evidence":["  "]}',
                            'not json',
                            '{"verdict":"passed","summary":42,"evidence":[]}'):
                with self.subTest(verdict=verdict), self.assertRaises(RuntimeError):
                    run_workflow(FakeCodex(verdict), "Inspect docs", "/repo")
            with self.assertRaises(RuntimeError):
                checked_response(types.SimpleNamespace(status="interrupted", error=None, final_response="done"))
        finally:
            if previous is None:
                del sys.modules["openai_codex"]
            else:
                sys.modules["openai_codex"] = previous


if __name__ == "__main__":
    unittest.main()
