"""Bounded workspace snapshots, safe material reads, and reversible file application."""

import ast
import hashlib
import os
import re
import shutil
import subprocess
from pathlib import Path

from .contracts import safe_relative
from .errors import CodexwrightError
from .store import digest
from .templates.execution import PROTECTED_DIRS, SECRET_NAMES, secret_path

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache", "dist", "build", ".codexwright", ".build-mas", "_codexwright_inputs", "_buildmas_inputs"}
FRAMEWORKS = {"crewai", "langgraph", "langchain", "autogen", "autogen_agentchat", "claude_agent_sdk", "agents", "smolagents"}
SNAPSHOT_MAX_FILES = 2000
SNAPSHOT_MAX_BYTES = 30000000


def has_secret(text):
    return bool(re.search(r"(?i)(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{18,}|gh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:api[_-]?key|password|access[_-]?token|secret)\s*[:=]\s*[\"'][^\"'\s]{12,}[\"'])", text))


def relative_file(root, name, *, writable=False):
    try:
        safe_relative(name)
    except ValueError as exc:
        raise CodexwrightError("path_escape", str(exc)) from exc
    root = Path(root).resolve()
    path = root / name
    if secret_path(name) or any(part in SKIP_DIRS for part in Path(name).parts):
        raise CodexwrightError("protected_path", f"Protected workspace path: {name}")
    current = root
    for part in Path(name).parts:
        current = current / part
        if current.is_symlink():
            raise CodexwrightError("path_escape", f"Symlinks are not allowed: {name}")
    if not path.resolve().is_relative_to(root):
        raise CodexwrightError("path_escape", "Path leaves workspace")
    if writable and path.exists() and not path.is_file():
        raise CodexwrightError("invalid_target", "Write target is not a regular file")
    return path


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot(root, *, max_files=SNAPSHOT_MAX_FILES, max_bytes=SNAPSHOT_MAX_BYTES):
    root = Path(root).resolve(strict=True)
    files = {}
    skipped = []
    total = 0
    for directory, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(name for name in directories if name not in SKIP_DIRS and name not in PROTECTED_DIRS and not name.endswith(".egg-info") and not (Path(directory) / name).is_symlink())
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or secret_path(relative):
                skipped.append(relative)
                continue
            size = path.stat().st_size
            total += size
            if len(files) >= max_files or total > max_bytes:
                raise CodexwrightError("workspace_too_large", "Workspace snapshot limit exceeded; register a narrower directory", details={"limits": {"files": max_files, "bytes": max_bytes}, "observed": {"files": len(files) + 1, "bytes": total}, "limit_path": relative, "scan_complete": False})
            payload = path.read_bytes()
            if has_secret(payload.decode("utf-8", errors="ignore")):
                skipped.append(relative)
                continue
            files[relative] = {"sha256": hashlib.sha256(payload).hexdigest(), "size": size, "mode": path.stat().st_mode & 0o777}
    git = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    baseline = git.stdout.strip() if git.returncode == 0 else None
    value = {"root": str(root), "files": files, "git_revision": baseline, "excluded_sensitive_paths": skipped}
    value["sha256"] = digest(value)
    return value


def snapshot_summary(captured):
    return {"snapshot": captured["sha256"], "files": len(captured["files"]), "bytes": sum(item["size"] for item in captured["files"].values()), "excluded_sensitive_paths": len(captured["excluded_sensitive_paths"]), "limits": {"files": SNAPSHOT_MAX_FILES, "bytes": SNAPSHOT_MAX_BYTES}}


def discover(root, captured):
    imports = {}
    commands = []
    evidence = []
    custom = False
    for name, metadata in captured["files"].items():
        if metadata["size"] > 250000 or not name.endswith((".py", ".toml", ".json", ".md", ".txt", ".yaml", ".yml", ".js", ".ts")):
            continue
        try:
            content = relative_file(root, name).read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if has_secret(content):
            continue
        if name.endswith(".py"):
            try:
                tree = ast.parse(content)
            except SyntaxError:
                continue
            found = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    found.update(item.name.split(".")[0] for item in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    found.add(node.module.split(".")[0])
            relevant = sorted(found & (FRAMEWORKS | {"openai_codex", "openai", "anthropic"}))
            if relevant:
                imports[name] = relevant
            if found & FRAMEWORKS or found & {"openai", "anthropic"}:
                custom = True
            if 'if __name__' in content:
                commands.append({"kind": "python_entrypoint", "path": name})
        if name.startswith("tests/") or name.startswith("test_"):
            commands.append({"kind": "test", "path": name})
        if name in {"pyproject.toml", "requirements.txt", "package.json", "AGENTS.md"}:
            evidence.append({"path": name, "sha256": metadata["sha256"], "excerpt": content[:6000]})
    all_imports = {item for values in imports.values() for item in values}
    if "openai_codex" in all_imports and not (all_imports & FRAMEWORKS):
        source = "codex_sdk"
    elif custom or all_imports & FRAMEWORKS:
        source = "other"
    elif not captured["files"]:
        source = "none"
    elif any(name.endswith((".py", ".ts", ".js")) for name in captured["files"]):
        source = "unknown"
    else:
        source = "none"
    return {"source_runtime": source, "imports": imports, "commands": commands, "evidence": evidence, "files": list(captured["files"]), "excluded_paths": captured["excluded_sensitive_paths"]}


def copy_workspace(root, destination, captured):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name, metadata in captured["files"].items():
        source = relative_file(root, name)
        if file_hash(source) != metadata["sha256"]:
            raise CodexwrightError("workspace_conflict", "Workspace changed while staging")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


def validate_changes(root, changes, write_roots):
    if not changes or len(changes) > 120:
        raise CodexwrightError("invalid_proposal", "A proposal needs 1 to 120 file changes")
    names = set()
    total = 0
    for change in changes:
        if set(change) != {"path", "action", "content"}:
            raise CodexwrightError("invalid_proposal", "Unexpected file-change fields")
        name = change["path"]
        relative_file(root, name, writable=True)
        if name in names:
            raise CodexwrightError("invalid_proposal", "Duplicate changed path")
        names.add(name)
        if not any(scope == "." or name == scope or name.startswith(scope.rstrip("/") + "/") for scope in write_roots):
            raise CodexwrightError("permission_denied", f"Path is outside approved write roots: {name}")
        if change["action"] not in {"write", "delete"}:
            raise CodexwrightError("invalid_proposal", "Unsupported file action")
        content = change["content"]
        if not isinstance(content, str) or (change["action"] == "delete" and content):
            raise CodexwrightError("invalid_proposal", "Invalid file contents")
        if has_secret(content):
            raise CodexwrightError("secret_detected", f"Secret-like content in proposed file: {name}")
        total += len(content.encode())
        if total > 1500000:
            raise CodexwrightError("invalid_proposal", "Proposal content exceeds limit")
        if name.endswith(".py") and change["action"] == "write":
            try:
                ast.parse(content)
            except SyntaxError as exc:
                raise CodexwrightError("invalid_proposal", f"Invalid Python in {name}", details={"line": exc.lineno}) from exc


def write_changes(root, changes):
    for change in changes:
        target = relative_file(root, change["path"], writable=True)
        if change["action"] == "delete":
            target.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.codexwright-tmp")
            if temporary.exists() or temporary.is_symlink():
                raise CodexwrightError("workspace_conflict", "Temporary target already exists")
            temporary.write_text(change["content"], encoding="utf-8")
            if target.exists():
                os.chmod(temporary, target.stat().st_mode & 0o777)
            os.replace(temporary, target)


def transaction_apply(root, changes, baseline, backup):
    current = snapshot(root)
    if current["sha256"] != baseline["sha256"]:
        raise CodexwrightError("workspace_conflict", "Workspace changed since proposal was created")
    backup = Path(backup)
    backup.mkdir(parents=True, exist_ok=True, mode=0o700)
    original = {}
    for change in changes:
        name = change["path"]
        target = relative_file(root, name, writable=True)
        recorded = baseline["files"].get(name)
        if recorded and (not target.is_file() or file_hash(target) != recorded["sha256"]):
            raise CodexwrightError("workspace_conflict", "A file changed before application")
        if not recorded and target.exists():
            raise CodexwrightError("workspace_conflict", "An excluded or newly-created file cannot be overwritten")
        original[name] = target.read_bytes() if target.exists() else None
        if target.exists():
            saved = backup / name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
    from .store import atomic_json

    atomic_json(backup / "transaction.json", {"baseline": baseline["sha256"], "changes": [{"path": item["path"], "action": item["action"], "original_exists": original[item["path"]] is not None} for item in changes]})
    try:
        write_changes(root, changes)
    except BaseException:
        for name, content in original.items():
            target = relative_file(root, name, writable=True)
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        raise
    return snapshot(root)
