"""Host-owned artifact validation and OS-sandboxed command receipts."""

import ast
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import nullcontext
from pathlib import Path

from jsonschema import Draft202012Validator

from .contracts import CheckSpec
from .errors import CodexwrightError
from .network import model_network
from .runtime import verification_environment
from .templates.execution import bounded_output, executable_files, sensitive_paths
from .store import atomic_json
from .workspace import FRAMEWORKS, file_hash, has_secret, relative_file, snapshot


def verification_python(root, configured=None):
    root = Path(root).resolve()
    if configured:
        from .contracts import safe_relative
        safe_relative(configured)
    candidates = [configured] if configured else [".venv/bin/python", ".venv/Scripts/python.exe", "venv/bin/python"]
    for name in candidates:
        path = Path(root) / name
        if not path.is_file():
            continue
        environment = path.parent.parent.resolve()
        binary = path.resolve(strict=True)
        base = binary.parent.parent
        if not environment.is_relative_to(root) or not (environment / "pyvenv.cfg").is_file() or base in {Path("/"), Path.home(), root.parent, root}:
            raise CodexwrightError("target_environment_unavailable", "Verification requires a project-local Python virtual environment")
        probe = "import json,sys; print(json.dumps([sys.prefix,sys.base_prefix]))"
        with tempfile.TemporaryDirectory(prefix="codexwright-interpreter-probe-") as temporary:
            command = sandbox_command([str(path), "-I", "-c", probe], root, temporary, python_roots=[environment, base])
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True, env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1", "HOME": temporary, "TMPDIR": temporary})
            output, error = bounded_output(process, timeout=10, max_bytes=10000)
        if process.returncode != 0 or error:
            raise CodexwrightError("target_environment_unavailable", "Target Python environment did not initialize")
        roots = json.loads(output)
        if len(roots) != 2 or [Path(value).resolve() for value in roots] != [environment, base]:
            raise CodexwrightError("target_environment_unavailable", "Target interpreter returned invalid runtime roots")
        return str(path.absolute()), roots
    if configured:
        raise CodexwrightError("target_environment_unavailable", "Configured target interpreter is missing")
    return sys.executable, [sys.prefix, sys.base_prefix]


def structure_check(spec, root):
    root = Path(root)
    skills = []
    for skill in spec.skills:
        path = relative_file(root, f"skills/{skill.name}/SKILL.md")
        text = path.read_text()
        if not text.startswith("---\n") or f"name: {skill.name}\n" not in text or not re.search(r"(?m)^description: .+", text):
            raise CodexwrightError("invalid_skill", "Skill frontmatter does not match its declared name and trigger")
        for name in skill.references + skill.scripts:
            if not relative_file(root, name).is_file():
                raise CodexwrightError("missing_artifact", "Skill reference or script is missing")
        skills.append({"name": skill.name, "lifecycle": "discovered", "path": str(path), "sha256": file_hash(path), "eval_cases": skill.eval_cases})
    if spec.runtime.action in {"new", "migrate"}:
        architecture = json.loads(relative_file(root, "architecture.json").read_text())
        if architecture != spec.model_dump(mode="json"):
            raise CodexwrightError("architecture_drift", "Generated runtime spec differs from the host-approved architecture")
        source = relative_file(root, "workflow.py").read_text()
        template = (Path(__file__).parent / "templates/workflow.py").read_text()
        actual = ast.parse(source)
        expected = ast.parse(template)
        if ast.dump(actual, include_attributes=False) != ast.dump(expected, include_attributes=False):
            raise CodexwrightError("harness_drift", "Generated code changed the host-owned scheduler, permissions or acceptance gates")
        actual_execution = ast.parse(relative_file(root, "execution.py").read_text())
        expected_execution = ast.parse((Path(__file__).parent / "templates/execution.py").read_text())
        if ast.dump(actual_execution, include_attributes=False) != ast.dump(expected_execution, include_attributes=False):
            raise CodexwrightError("harness_drift", "Generated execution helper changed the host-owned sandbox or output bounds")
        if any(interface.type == "mcp" for interface in spec.interfaces):
            actual_mcp = ast.parse(relative_file(root, "mcp_server.py").read_text())
            expected_mcp = ast.parse((Path(__file__).parent / "templates/mcp_server.py").read_text())
            if ast.dump(actual_mcp, include_attributes=False) != ast.dump(expected_mcp, include_attributes=False):
                raise CodexwrightError("harness_drift", "Generated MCP changed the host-owned invocation or verification boundary")
        if spec.tools:
            actual_tool = ast.parse(relative_file(root, "tool_server.py").read_text())
            expected_tool = ast.parse((Path(__file__).parent / "templates/tool_server.py").read_text())
            if ast.dump(actual_tool, include_attributes=False) != ast.dump(expected_tool, include_attributes=False):
                raise CodexwrightError("harness_drift", "Generated CLI registry changed its host-owned trust boundary")
    return skills


def command_for(check, root, *, python=None):
    kind = check.kind
    target = check.target
    args = check.arguments
    executable = str(python or sys.executable)
    if any("\x00" in value or "\n" in value for value in args):
        raise CodexwrightError("invalid_check", "Invalid check argument")
    if kind == "unittest":
        relative_file(root, target or "tests/test_workflow.py")
        folder = target and (Path(root) / target).is_dir()
        return [executable, "-m", "unittest", "discover", "-s", target if folder else str(Path(target).parent if target else "tests"), "-p", "test_*.py" if folder else Path(target).name if target else "test_*.py"]
    if kind == "pytest":
        relative_file(root, target)
        return [executable, "-m", "pytest", "-q", target]
    if kind == "compile":
        if target == ".":
            return [executable, "-c", "import ast,pathlib; [ast.parse(p.read_text()) for p in pathlib.Path('.').rglob('*.py') if '.venv' not in p.parts]"]
        relative_file(root, target)
        return [executable, "-c", "import ast,pathlib; ast.parse(pathlib.Path(" + repr(target) + ").read_text())"]
    if kind == "import":
        if target.endswith(".py"):
            relative_file(root, target)
            return [executable, "-c", "import runpy; runpy.run_path(" + repr(target) + ")"]
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_.]*", target):
            raise CodexwrightError("invalid_check", "Invalid import module")
        return [executable, "-c", "import importlib; importlib.import_module(" + repr(target) + ")"]
    if kind in {"cli_smoke", "codex_smoke", "tool_smoke"}:
        relative_file(root, target)
        if not target.endswith(".py"):
            raise CodexwrightError("invalid_check", "Smoke tests execute declared Python entrypoints only")
        for value in args:
            if value.startswith(("/", "../", "~")) or "/../" in value or value.startswith(("--home", "--cwd", "--root")):
                raise CodexwrightError("invalid_check", "Smoke arguments must stay within the project")
        return [executable, target, *args]
    raise CodexwrightError("invalid_check", "Unknown executable check")


def sandbox_command(argv, root, temporary, *, runtime_home=None, model_ports=None, python_roots=None):
    root = Path(root).resolve()
    temporary = Path(temporary).resolve()
    if sys.platform == "darwin":
        permitted = {str(root), str(temporary), str(Path(sys.prefix).resolve()), str(Path(sys.base_prefix).resolve()), str(Path(sys.executable).resolve().parent), "/usr", "/bin", "/sbin", "/System", "/Library", "/dev", *(str(Path(p).resolve()) for p in python_roots or [])}
        exact_reads = " ".join(f"(literal {json.dumps(str(path))})" for path in executable_files(argv[0]))
        denied = [str(Path.home() / ".codex"), str(Path.home() / ".ssh"), str(Path.home() / ".aws"), *(str(path) for path in sensitive_paths(root))]
        if runtime_home:
            permitted.add(str(Path(runtime_home).resolve()))
        read_rules = " ".join(f"(subpath {json.dumps(path)})" for path in sorted(permitted)) + " " + exact_reads
        write_rules = f"(subpath {json.dumps(str(temporary))}) (literal \"/dev/null\")"
        profile = "(version 1)(deny default)(allow process*)(allow sysctl-read)(allow mach-lookup)(allow signal)(allow file-read-metadata)(allow file-test-existence)(allow file-map-executable " + read_rules + ")(allow file-read* " + read_rules + ")(allow file-write* " + write_rules + ")(deny network*)(allow system-mac-syscall (mac-policy-name \"vnguard\"))(allow system-mac-syscall (mac-policy-name \"Sandbox\"))(allow file-read* (literal \"/\"))(allow file-read* file-write* (subpath \"/dev/fd\"))"
        if runtime_home:
            profile += "(allow file-write* (subpath " + json.dumps(str(Path(runtime_home).resolve())) + "))"
            profile += '(allow user-preference-read (preference-domain "com.openai.codex"))(allow ipc-posix-shm-read* (ipc-posix-name-prefix "apple.cfprefs."))'
            profile += "(deny file-write* (literal " + json.dumps(str(Path(runtime_home).resolve() / "auth.json")) + "))"
        for port in model_ports or []:
            if not isinstance(port, int) or not 1 <= port <= 65535:
                raise CodexwrightError("unsafe_model_endpoint", "The OS sandbox accepts only explicit local relay ports")
            profile += '(allow network-outbound (remote ip "localhost:' + str(port) + '"))'
        for path in denied:
            if not runtime_home or Path(path).resolve() != Path(runtime_home).resolve():
                profile += "(deny file-read* (subpath " + json.dumps(path) + "))"
        profile_path = temporary / "sandbox.sb"
        profile_path.write_text(profile)
        return ["/usr/bin/sandbox-exec", "-f", str(profile_path), *argv]
    if sys.platform.startswith("linux"):
        import shutil

        executable = shutil.which("bwrap")
        if not executable:
            raise CodexwrightError("sandbox_unavailable", "Install bubblewrap for independent checks; unsandboxed execution is never used")
        bindings = [executable, "--die-with-parent", "--unshare-all", "--new-session", "--proc", "/proc", "--dev", "/dev"]
        for name in {"/usr", "/bin", "/lib", "/lib64", str(Path(sys.prefix).resolve()), str(Path(sys.base_prefix).resolve()), str(root), *(str(Path(p).resolve()) for p in python_roots or [])}:
            if Path(name).exists():
                bindings.extend(["--ro-bind", name, name])
        bindings.extend(["--bind", str(temporary), str(temporary), "--chdir", str(root)])
        empty = temporary / "protected"
        empty.mkdir(exist_ok=True)
        for path in sensitive_paths(root):
            if path.exists():
                bindings.extend(["--ro-bind", str(empty) if path.is_dir() else "/dev/null", str(path)])
        return [*bindings, *argv]
    raise CodexwrightError("sandbox_unavailable", "OS-sandboxed deterministic checks are currently supported on macOS and Linux")


def trusted_entrypoint(spec, root, temporary, entrypoint):
    directory = Path(temporary) / "trusted_harness"
    directory.mkdir(mode=0o700)
    templates = Path(__file__).parent / "templates"
    for name in ("workflow.py", "execution.py", "tool_server.py", "mcp_server.py"):
        (directory / name).write_bytes((templates / name).read_bytes())
    (directory / "architecture.json").write_text(json.dumps(spec.model_dump(mode="json")))
    for name in ("workflow", "tool_server"):
        code = "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).resolve().parent))\nimport " + name + " as entry\nentry.ROOT = Path(" + repr(str(Path(root).resolve())) + ")\n"
        if name == "workflow":
            code += "entry.TOOL_SERVER = Path(__file__).with_name('run_tool_server.py')\n"
        code += "raise SystemExit(entry.main())\n"
        (directory / f"run_{name}.py").write_text(code)
    return directory / f"run_{entrypoint}.py"


def execute_check(check, root, output, *, runtime_home=None, model_ports=None, python=None, python_roots=None, spec=None, cancel=None):
    check = check if isinstance(check, CheckSpec) else CheckSpec.model_validate(check)
    endpoints = model_ports if check.kind == "codex_smoke" else []
    with model_network(endpoints) if check.kind == "codex_smoke" else nullcontext(([], {})) as (ports, proxy):
        return _execute_check(check, root, output, runtime_home=runtime_home, model_ports=ports, model_proxy=proxy, model_endpoints=endpoints, python=python, python_roots=python_roots, spec=spec, cancel=cancel)


def _execute_check(check, root, output, *, runtime_home=None, model_ports=None, model_proxy=None, model_endpoints=None, python=None, python_roots=None, spec=None, cancel=None):
    check = check if isinstance(check, CheckSpec) else CheckSpec.model_validate(check)
    root = Path(root).resolve()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    record = {"id": check.id, "kind": check.kind, "required": check.required, "status": "failed", "exit_code": None, "evidence_ref": str(output / f"{check.id}.json")}
    started = time.monotonic()
    before = snapshot(root)
    try:
        if cancel is not None and cancel.is_set():
            raise CodexwrightError("check_cancelled", "Verification was cancelled before execution")
        if check.kind == "artifact":
            path = relative_file(root, check.target)
            if not path.is_file():
                raise CodexwrightError("missing_artifact", f"Required file missing: {check.target}")
            record["sha256"] = file_hash(path)
            if isinstance(check.expected, dict):
                value = json.loads(path.read_text())
                Draft202012Validator(check.expected).validate(value)
            record["status"] = "passed"
        elif check.kind == "migration":
            old_imports = []
            for name in before["files"]:
                if not name.endswith(".py"):
                    continue
                tree = ast.parse(relative_file(root, name).read_text())
                for node in ast.walk(tree):
                    modules = [item.name for item in node.names] if isinstance(node, ast.Import) else [node.module] if isinstance(node, ast.ImportFrom) and node.module else []
                    if any(module.split(".")[0] in FRAMEWORKS for module in modules):
                        old_imports.append(name)
            if old_imports:
                raise CodexwrightError("migration_incomplete", "Old Agent runtime imports remain", details={"files": sorted(set(old_imports))})
            for name in ("requirements.txt", "pyproject.toml"):
                path = root / name
                if path.is_file():
                    content = path.read_text()
                    if re.search(r"(?im)^[\s\"']*(?:crewai|langgraph|autogen-agentchat|pyautogen|claude-agent-sdk|smolagents)(?:[=><~\[\s\"']|$)", content):
                        raise CodexwrightError("migration_incomplete", "Old Agent runtime dependency remains", details={"path": name})
            record["status"] = "passed"
        else:
            argv = command_for(check, root, python=python)
            temporary = Path(tempfile.mkdtemp(prefix="codexwright-check-", dir=output))
            environment = {"PATH": os.environ.get("PATH", ""), "HOME": str(temporary), "TMPDIR": str(temporary), "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": os.pathsep.join([str(root), str(root / "src")]), "PYTHONIOENCODING": "utf-8", "CODEXWRIGHT_TEST_HOME": str(temporary), "BUILD_MAS_TEST_HOME": str(temporary)}
            check_runtime_home = runtime_home if check.kind == "codex_smoke" else None
            check_model_ports = model_ports if check.kind == "codex_smoke" else None
            if check_runtime_home:
                environment["CODEX_HOME"] = str(runtime_home)
                environment.update(verification_environment(check_runtime_home))
            if check.kind == "codex_smoke":
                environment.update(model_proxy or {})
            record["execution_environment"] = {key: environment[key] for key in ("HOME", "TMPDIR", "CODEXWRIGHT_TEST_HOME", "PYTHONDONTWRITEBYTECODE")}
            record["model_endpoint_pins"] = model_endpoints or []
            record["sandbox_loopback_ports"] = check_model_ports or []
            fixed_template = spec is not None and spec.runtime.action in {"new", "migrate"} and (check.kind == "codex_smoke" or check.kind == "tool_smoke" and check.target == "tool_server.py")
            if fixed_template:
                structure_check(spec, root)
                entrypoint = "workflow" if check.kind == "codex_smoke" else "tool_server"
                runner = trusted_entrypoint(spec, root, temporary, entrypoint)
                # Only package-owned code runs outside the check sandbox; project tools get their own sandbox.
                wrapped = [sys.executable, "-I", "-B", str(runner), *argv[2:]]
                environment.pop("PYTHONPATH", None)
                record["execution"] = "verified_package_template_with_sandboxed_project_tools"
                record["execution_python"] = sys.executable
            else:
                wrapped = sandbox_command(argv, root, temporary, runtime_home=check_runtime_home, model_ports=check_model_ports, python_roots=python_roots)
            process = subprocess.Popen(wrapped, cwd=root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
            stdout, error = bounded_output(process, timeout=check.timeout_seconds, cancel=cancel)
            if error == "cancelled":
                record["status"] = "blocked"
                record["error"] = {"code": "check_cancelled", "message": "Verification process group was stopped after cancellation"}
            if error == "timeout":
                record["status"] = "blocked"
                record["error"] = {"code": "check_timeout", "message": "Check exceeded timeout and its process group was stopped"}
            if error == "output_limit":
                record["error"] = {"code": "output_limit", "message": "Check output exceeded evidence limit"}
                record["status"] = "failed"
            else:
                text = stdout.decode("utf-8", errors="replace")
                if has_secret(text):
                    text = "[REDACTED: secret-like command output]"
                    record["status"] = "failed"
                    record["error"] = {"code": "secret_detected", "message": "Secret-like output rejected"}
                record["output"] = text
            record["argv"] = argv
            record["exit_code"] = process.returncode
            if not record.get("error"):
                record["status"] = "passed" if process.returncode == 0 else "failed"
            if record["status"] == "passed" and check.expected is not None:
                if isinstance(check.expected, str):
                    if check.expected not in record.get("output", ""):
                        record["status"] = "failed"
                        record["error"] = {"code": "expected_output_missing", "message": "Expected output was not observed"}
                elif isinstance(check.expected, dict):
                    try:
                        observed = json.loads(record.get("output", ""))
                        if any(key in check.expected for key in ("$schema", "$ref", "type", "properties", "allOf", "anyOf", "oneOf")):
                            Draft202012Validator(check.expected).validate(observed)
                        elif observed != check.expected:
                            raise ValueError("Observed JSON differs from expected value")
                    except Exception as exc:
                        record["status"] = "failed"
                        record["error"] = {"code": "invalid_check_output", "message": type(exc).__name__}
            if record["status"] == "passed" and check.expected_json is not None:
                try:
                    if json.loads(record.get("output", "")) != check.expected_json:
                        raise ValueError("Observed JSON differs from expected_json")
                except ValueError:
                    record["status"] = "failed"
                    record["error"] = {"code": "expected_output_mismatch", "message": "Command did not produce the exact required JSON"}
    except CodexwrightError as exc:
        record["status"] = "blocked" if exc.code == "sandbox_unavailable" else "failed"
        record["error"] = exc.as_dict()
    except Exception as exc:
        record["error"] = {"code": "check_failed", "message": type(exc).__name__}
    if snapshot(root)["sha256"] != before["sha256"]:
        record["status"] = "failed"
        record["error"] = {"code": "verification_mutation", "message": "A check changed target source files"}
    record["duration_ms"] = round((time.monotonic() - started) * 1000)
    atomic_json(output / f"{check.id}.json", record)
    return record


def verify_project(spec, root, output, *, runtime_home=None, model_ports=None, defer_live=False, python=None, python_roots=None, cancel=None):
    records = []
    try:
        skills = structure_check(spec, root)
        records.append({"id": "host_structure", "kind": "structure", "required": True, "status": "passed", "exit_code": None, "evidence": {"template_sha256": file_hash(Path(__file__).parent / "templates/workflow.py"), "candidate_sha256": file_hash(Path(root) / "workflow.py") if (Path(root) / "workflow.py").is_file() else None, "comparison": "Whole-module AST equals the owning package template" if spec.runtime.action in {"new", "migrate"} else "Existing runtime is preserved; no scaffold replacement"}})
    except Exception as exc:
        skills = []
        records.append({"id": "host_structure", "kind": "structure", "required": True, "status": "failed", "exit_code": None, "error": exc.as_dict() if isinstance(exc, CodexwrightError) else {"code": "structure_failed", "message": type(exc).__name__}})
    for check in spec.verification.checks:
        if records[0]["status"] != "passed":
            records.append({"id": check.id, "kind": check.kind, "required": check.required, "status": "blocked", "exit_code": None, "reason": "Host structure validation failed; candidate code was not executed"})
        elif defer_live and check.kind == "codex_smoke":
            records.append({"id": check.id, "kind": check.kind, "required": check.required, "status": "pending_approval", "exit_code": None, "reason": "Exact generated code must be reviewed before it can receive Codex authentication"})
        else:
            records.append(execute_check(check, root, output, runtime_home=runtime_home, model_ports=model_ports, python=python, python_roots=python_roots, spec=spec, cancel=cancel))
    required = [record for record in records if record["required"]]
    if not required:
        status = "blocked"
    elif all(record["status"] in {"passed", "pending_approval"} for record in required) and any(record["status"] == "pending_approval" for record in records):
        status = "pending_live"
    elif all(record["status"] == "passed" for record in required):
        status = "passed" if all(record["status"] == "passed" for record in records) else "partial"
    elif any(record["status"] == "blocked" for record in required):
        status = "blocked"
    else:
        status = "failed"
    report = {"status": status, "checks": records, "spec_revision": spec.revision, "snapshot": snapshot(root)["sha256"], "semantic_review": None, "skills": skills}
    if not defer_live and skills and status == "passed":
        observed = {}
        for record in records:
            if record["kind"] != "codex_smoke" or record["status"] != "passed":
                continue
            try:
                state = json.loads(record.get("output", ""))
                for packet in state.get("packets", {}).values():
                    if packet.get("status") == "passed" and packet.get("turn_id"):
                        for item in packet.get("skills", []):
                            if item.get("lifecycle") == "verified":
                                observed[item["name"]] = {**item, "turn_id": packet["turn_id"], "thread_id": packet["thread_id"], "check_id": record["id"]}
            except (ValueError, KeyError):
                continue
        report["skills"] = [{**item, **observed.get(item["name"], {})} for item in skills]
        if any(item["lifecycle"] != "verified" for item in report["skills"]):
            report["status"] = "failed"
            report["skill_gap"] = "Live SkillInput and asserted behavioral evidence is missing"
    atomic_json(Path(output) / "verification.json", report)
    return report
