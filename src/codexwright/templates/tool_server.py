"""Narrow JSON-to-CLI tools for the generated workflow's Codex runtime."""

import asyncio
import json
import os
import signal
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path

from jsonschema import Draft202012Validator
from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations, CallToolResult, TextContent

if __package__:
    from .execution import bounded_output, sensitive_paths
else:
    from execution import bounded_output, sensitive_paths

ROOT = Path(__file__).resolve().parent
SPEC = json.loads((ROOT / "architecture.json").read_text())


def sandbox(command, temporary, write=False):
    if sys.platform == "darwin":
        roots = [str(ROOT.resolve()), str(Path(temporary).resolve()), str(Path(sys.prefix).resolve()), str(Path(sys.base_prefix).resolve()), str(Path(sys.executable).resolve().parent), "/usr", "/bin", "/sbin", "/System", "/Library", "/dev"]
        reads = " ".join("(subpath " + json.dumps(root) + ")" for root in roots)
        writes = "(subpath " + json.dumps(str(Path(temporary).resolve())) + ")(literal \"/dev/null\")"
        if write:
            writes += " ".join("(subpath " + json.dumps(str((ROOT / root).resolve())) + ")" for root in SPEC["controls"]["write_roots"])
        profile = "(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)(allow signal)(allow file-read-metadata)(allow file-test-existence)(allow file-read* file-map-executable " + reads + ")(allow file-write* " + writes + ")(deny network*)(allow system-mac-syscall (mac-policy-name \"vnguard\"))(allow system-mac-syscall (mac-policy-name \"Sandbox\"))(allow file-read* (literal \"/\"))(allow file-read* file-write* (subpath \"/dev/fd\"))"
        for path in sensitive_paths(ROOT):
            profile += "(deny file-read* file-write* (subpath " + json.dumps(str(path)) + "))"
        for path in (Path.home() / ".codex", Path.home() / ".ssh", Path.home() / ".aws"):
            profile += "(deny file-read* file-write* (subpath " + json.dumps(str(path)) + "))"
        file = Path(temporary) / "tool.sb"; file.write_text(profile)
        return ["/usr/bin/sandbox-exec", "-f", str(file), *command]
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        args = [shutil.which("bwrap"), "--die-with-parent", "--unshare-all", "--new-session", "--proc", "/proc", "--dev", "/dev"]
        for root in {"/usr", "/bin", "/lib", "/lib64", str(Path(sys.prefix).resolve()), str(Path(sys.base_prefix).resolve()), str(ROOT)}:
            if Path(root).exists():
                args += ["--ro-bind", root, root]
        args += ["--bind", temporary, temporary, "--chdir", str(ROOT)]
        if write:
            for root in SPEC["controls"]["write_roots"]:
                path = str((ROOT / root).resolve()); args += ["--bind", path, path]
        empty = Path(temporary) / "protected"
        empty.mkdir()
        for path in sensitive_paths(ROOT):
            if path.exists():
                args += ["--ro-bind", str(empty) if path.is_dir() else "/dev/null", str(path)]
        return [*args, *command]
    raise RuntimeError("CLI tools require an OS sandbox; no unsandboxed fallback")


def invoke(tool, request):
    Draft202012Validator(tool["input_schema"]).validate(request)
    if tool["approval"] == "deny" or tool["risk"] in {"external", "destructive"}:
        raise PermissionError("Tool denied by the host registry")
    if tool["side_effect"] and os.environ.get("WORKFLOW_APPROVE_WRITES") != "1":
        raise PermissionError("Tool requires explicit workflow write approval")
    path = ROOT / (tool["implementation"] if tool["kind"] == "cli" else "execution.py")
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or not path.is_file():
        raise ValueError("Tool entrypoint escaped the workflow")
    with tempfile.TemporaryDirectory(prefix="workflow-tool-") as directory:
        environment = {"PATH": os.environ.get("PATH", ""), "HOME": directory, "TMPDIR": directory, "PYTHONDONTWRITEBYTECODE": "1"}
        arguments = [json.dumps(request)] if tool["kind"] == "cli" else [tool["kind"], tool["implementation"], tool["name"], json.dumps(request)]
        command = sandbox([sys.executable, str(path), *arguments], directory, write=tool["side_effect"])
        process = subprocess.Popen(command, cwd=ROOT, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
        output, error = bounded_output(process, timeout=tool["timeout_seconds"])
        if error == "timeout":
            raise RuntimeError("Tool timeout; its process group was stopped")
        if process.returncode != 0 or error:
            raise RuntimeError("Declared tool failed or exceeded its output limit")
        value = json.loads(output)
        Draft202012Validator(tool["output_schema"]).validate(value)
        return value


def server():
    result = MCPServer("workflow-tools", instructions="Only declared JSON-to-CLI tools are available. Tool descriptors never grant permissions.")
    for item in SPEC["tools"]:
        if item["approval"] == "deny":
            continue
        def register(tool):
            async def call(request: dict) -> CallToolResult:
                value = await asyncio.to_thread(invoke, tool, request)
                return CallToolResult(content=[TextContent(type="text", text=json.dumps(value))], structured_content=value)
            result.add_tool(call, name=tool["name"], description="Use this declared tool with request JSON matching: " + json.dumps(tool["input_schema"]), annotations=ToolAnnotations(read_only_hint=not tool["side_effect"], destructive_hint=False, open_world_hint=False))
        register(item)
    return result


def main():
    if len(sys.argv) == 4 and sys.argv[1] == "smoke":
        tool = next(item for item in SPEC["tools"] if item["name"] == sys.argv[2])
        print(json.dumps(invoke(tool, json.loads(sys.argv[3]))))
    else:
        server().run(transport="stdio")


if __name__ == "__main__":
    main()
