"""Prepare runnable SDK projects and derive actual file proposals from staged work."""

import json
from pathlib import Path

from .errors import CodexwrightError
from .workspace import relative_file


def scaffold(root, spec):
    root = Path(root)
    template_root = Path(__file__).parent / "templates"
    files = {
        "__init__.py": '"""Standalone Codex SDK workflow package."""\n',
        "architecture.json": json.dumps(spec.model_dump(mode="json"), ensure_ascii=False, indent=2),
        "workflow.py": (template_root / "workflow.py").read_text(),
        "execution.py": (template_root / "execution.py").read_text(),
        "pyproject.toml": '[build-system]\nrequires = ["setuptools>=75"]\nbuild-backend = "setuptools.build_meta"\n\n[project]\nname = "generated-codex-workflow"\nversion = "0.1.0"\nrequires-python = ">=3.10"\ndependencies = ["openai-codex==0.167.0", "jsonschema>=4.26,<5", "mcp==2.3.0", "tomli>=2,<3; python_version < \'3.11\'"]\n\n[tool.setuptools]\npackages = ["codex_workflow"]\n\n[tool.setuptools.package-dir]\ncodex_workflow = "."\n\n[tool.setuptools.package-data]\ncodex_workflow = ["architecture.json", "*.json", "skills/**/*.md", "skills/**/*.py", "tools/*.py"]\n\n[project.scripts]\nmas = "codex_workflow.workflow:main"\n',
        "README.md": '# Generated Codex SDK Workflow\n\nInstall this project in an isolated Python environment. Run `python workflow.py run --input request.json`, inspect with `status`, and validate with `verify`. `python workflow.py serve` exposes task-level MCP tools. Credentials are managed by Codex, never by this project.\n',
    }
    if any(interface.type == "mcp" for interface in spec.interfaces):
        files["mcp_server.py"] = (template_root / "mcp_server.py").read_text()
    if spec.tools:
        files["tool_server.py"] = (template_root / "tool_server.py").read_text()
    for skill in spec.skills:
        name = f"skills/{skill.name}/SKILL.md"
        files[name] = f"---\nname: {skill.name}\ndescription: {json.dumps(skill.trigger)}\n---\n\n{skill.procedure}\n"
    files = {name: content for name, content in files.items() if any(scope == "." or name == scope or name.startswith(scope.rstrip("/") + "/") for scope in spec.controls.write_roots)}
    for name, content in files.items():
        destination = relative_file(root, name, writable=True)
        if spec.runtime.action == "migrate" and destination.exists() and name in {"README.md", "pyproject.toml"}:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    return files


def staged_changes(root, before, after):
    changes = []
    for name in sorted(set(before["files"]) | set(after["files"])):
        old = before["files"].get(name)
        new = after["files"].get(name)
        if old == new:
            continue
        if new is None:
            changes.append({"path": name, "action": "delete", "content": ""})
        else:
            try:
                content = relative_file(root, name).read_text(encoding="utf-8")
            except UnicodeError as exc:
                raise CodexwrightError("unsupported_change", "Binary changes require a separate reviewed asset flow") from exc
            changes.append({"path": name, "action": "write", "content": content})
    return changes
