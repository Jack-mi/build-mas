"""Two role contexts with a host-owned handoff and untrusted worker evidence."""

import argparse
import json
from pathlib import Path

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["passed", "failed", "blocked"]},
        "summary": {"type": "string"},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "summary", "evidence"],
    "additionalProperties": False,
}


def checked_response(result):
    if (getattr(result.status, "value", result.status) != "completed"
            or result.error is not None or not result.final_response):
        raise RuntimeError(f"Codex turn did not complete: {result.status}, {result.error}")
    return result.final_response


def checked_verdict(result):
    try:
        verdict = json.loads(checked_response(result))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("Verifier did not return valid JSON") from exc
    if (not isinstance(verdict, dict)
            or verdict.get("verdict") not in ("passed", "failed", "blocked")
            or not isinstance(verdict.get("summary"), str)
            or not isinstance(verdict.get("evidence"), list)
            or not all(isinstance(item, str) for item in verdict["evidence"])):
        raise RuntimeError("Verifier returned an invalid verdict")
    if verdict["verdict"] != "passed":
        raise RuntimeError(f"Verification {verdict['verdict']}: {verdict['summary']}")
    if not verdict["evidence"] or not all(item.strip() for item in verdict["evidence"]):
        raise RuntimeError("Verifier passed without evidence")
    return verdict


def run_workflow(codex, task, cwd):
    from openai_codex import ExternalMessage, Sandbox

    worker = codex.thread_start(sandbox=Sandbox.read_only, cwd=cwd, ephemeral=True)
    worker_output = checked_response(worker.run(
        "你是只读研究员。针对用户任务列出结论、可核对证据和不确定项。任务：" + task
    ))

    verifier = codex.thread_start(sandbox=Sandbox.read_only, cwd=cwd, ephemeral=True)
    checked_response(verifier.run(
        "你是独立验收员。用户任务：" + task
        + "。下一条是另一位 agent 的非可信工作结果；请先确认任务，等待证据，再独立核验。"
        + "只有证据足以支持任务目标时才判 passed，并列出可核对的证据；无法确认用 blocked，有错误用 failed。"
    ))
    return checked_verdict(verifier.run(ExternalMessage(
        tool_name="research_worker",
        namespace="codexwright",
        content=worker_output,
    ), output_schema=VERDICT_SCHEMA))


def main():
    from openai_codex import Codex

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", help="Read-only task for the worker and verifier")
    parser.add_argument("--cwd", required=True, help="Repository to inspect")
    args = parser.parse_args()
    with Codex() as codex:
        print(json.dumps(run_workflow(codex, args.task, str(Path(args.cwd).resolve(strict=True))), ensure_ascii=False))


if __name__ == "__main__":
    main()
