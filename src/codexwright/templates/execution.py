"""Bounded subprocess I/O and portable runtime helpers shared by host/tools."""

import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

PROTECTED_DIRS = {".git", ".codex", ".claude", ".opencode", ".ssh", ".aws", ".azure", ".gcloud"}
SECRET_NAMES = {"auth.json", "credentials", "credentials.json", "id_rsa", "id_ed25519", ".netrc", ".npmrc", ".pypirc"}


def secret_path(path):
    value = Path(path)
    return any(part in PROTECTED_DIRS for part in value.parts) or value.name in SECRET_NAMES or value.name == ".env" or value.name.startswith(".env.") or value.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}


def sensitive_paths(root):
    root = Path(root).resolve()
    paths = {root / name for name in PROTECTED_DIRS | SECRET_NAMES | {".env"}}
    for directory, folders, files in os.walk(root, followlinks=False):
        for name in folders + files:
            path = Path(directory) / name
            if secret_path(path.relative_to(root)):
                paths.add(path)
        folders[:] = [name for name in folders if name not in {".venv", "venv", "node_modules", "__pycache__"} and not secret_path(name) and not (Path(directory) / name).is_symlink()]
    return sorted(paths)


def bounded_output(process, *, timeout, max_bytes=1000000, cancel=None):
    chunks = []
    size = 0
    deadline = time.monotonic() + timeout
    error = None
    with selectors.DefaultSelector() as selector:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            if cancel is not None and cancel.is_set():
                error = "cancelled"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                error = "timeout"
                break
            for key, _ in selector.select(min(remaining, 0.1) if cancel is not None else remaining):
                data = os.read(key.fd, 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                size += len(data)
                if size > max_bytes:
                    error = "output_limit"
                    break
                chunks.append(data)
            if error:
                break
    while cancel is not None and process.poll() is None and error is None:
        if cancel.is_set():
            error = "cancelled"
        elif time.monotonic() >= deadline:
            error = "timeout"
        else:
            time.sleep(0.05)
    if error:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=max(0.1, deadline - time.monotonic()) if not error else 5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=5)
        error = error or "timeout"
    finally:
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
    return b"".join(chunks), error


def executable_files(command):
    import shutil

    path = Path(shutil.which(command) or command).resolve(strict=True)
    files = {path}
    if os.uname().sysname == "Darwin":
        pending = [path]
        runpaths = []

        def inspect(arguments):
            process = subprocess.Popen(["/usr/bin/otool", *arguments], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)
            output, error = bounded_output(process, timeout=10, max_bytes=500000)
            if error:
                raise RuntimeError("Executable dependency inspection exceeded its bound")
            return output.decode(errors="replace").splitlines()

        def expand(value, loader):
            if value.startswith("@loader_path/"):
                return loader.parent / value.removeprefix("@loader_path/")
            if value.startswith("@executable_path/"):
                return path.parent / value.removeprefix("@executable_path/")
            return Path(value) if value.startswith("/") else None

        while pending:
            binary = pending.pop()
            lines = inspect(["-l", str(binary)])
            for index, line in enumerate(lines):
                if line.strip() == "cmd LC_RPATH":
                    value = lines[index + 2].strip().removeprefix("path ").split(" (offset", 1)[0]
                    directory = expand(value, binary)
                    if directory and directory not in runpaths:
                        runpaths.append(directory)
            for line in inspect(["-L", str(binary)])[1:]:
                value = line.strip().split(" (", 1)[0]
                dependency = next((directory / value.removeprefix("@rpath/") for directory in runpaths if (directory / value.removeprefix("@rpath/")).is_file()), None) if value.startswith("@rpath/") else expand(value, binary)
                if dependency and dependency.is_file():
                    dependency = dependency.resolve()
                    if dependency not in files:
                        files.add(dependency)
                        pending.append(dependency)
            if len(files) > 100:
                raise RuntimeError("Executable dependency discovery exceeded its bound")
    return files


def safe_tool_path(root, value):
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or secret_path(path):
        raise ValueError("Tool path is outside its non-sensitive workspace scope")
    current = Path(root)
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("Tool paths must not traverse symlinks")
    if not current.resolve().is_relative_to(Path(root).resolve()):
        raise ValueError("Tool path escaped the workspace")
    return current


def state_directory(root):
    import hashlib

    if os.environ.get("CODEXWRIGHT_TEST_HOME"):
        return Path(os.environ["CODEXWRIGHT_TEST_HOME"]).expanduser().resolve()
    if os.environ.get("BUILD_MAS_TEST_HOME"):
        return Path(os.environ["BUILD_MAS_TEST_HOME"]).expanduser().resolve()
    if os.environ.get("WORKFLOW_STATE_DIR"):
        return Path(os.environ["WORKFLOW_STATE_DIR"]).expanduser().resolve()
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")).expanduser()
    return base / "codex-workflows" / hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:24]


def toml_value(value):
    import json

    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key) + "=" + toml_value(item) for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ",".join(toml_value(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (str, int, float)):
        return json.dumps(value)
    raise ValueError("Unsupported runtime configuration value")


def isolated_sdk_home(home, root):
    import shutil
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    directory = Path(home) / "sdk"
    if directory.is_symlink():
        raise ValueError("SDK directory must not be a symlink")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    source_config = source / "config.toml"
    config = tomllib.loads(source_config.read_text()) if source_config.is_file() else {}
    selected = {key: config[key] for key in ("model", "model_provider", "model_reasoning_effort", "openai_base_url", "chatgpt_base_url") if key in config}
    provider = config.get("model_provider")
    if provider in config.get("model_providers", {}):
        selected["model_providers"] = {provider: config["model_providers"][provider]}
    selected["projects"] = {str(Path(root).resolve()): {"trust_level": "untrusted"}}
    selected["project_root_markers"] = []
    text = "\n".join(key + "=" + toml_value(value) for key, value in selected.items()) + "\n"
    destination = directory / "config.toml"
    if destination.is_symlink():
        raise ValueError("SDK config must not be a symlink")
    destination.write_text(text)
    destination.chmod(0o600)
    original = source / "auth.json"
    target = directory / "auth.json"
    if target.is_symlink():
        raise ValueError("SDK authentication must not be a symlink")
    if original.is_file() and original.resolve() != target.resolve():
        shutil.copyfile(original, target)
        target.chmod(0o600)
    return directory


def main():
    import asyncio
    import json
    import sys

    kind, implementation, name, raw = sys.argv[1:]
    request = json.loads(raw)
    root = Path(__file__).resolve().parent
    if kind == "builtin":
        path = safe_tool_path(root, request["path"])
        if implementation == "read_file":
            if not path.is_file() or path.stat().st_size > 100000:
                raise ValueError("Read-file tool requires a bounded regular file")
            result = {"content": path.read_text(encoding="utf-8")}
        elif implementation == "list_files":
            names = []
            for item in path.iterdir():
                if not item.is_symlink() and not item.name.startswith("."):
                    names.append(item.name)
                if len(names) > 1000:
                    raise ValueError("Directory listing exceeded its bound")
            result = {"files": sorted(names)}
        else:
            raise ValueError("Unsupported builtin tool")
    elif kind == "mcp":
        from mcp import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        server = safe_tool_path(root, implementation)

        async def call():
            parameters = StdioServerParameters(command=sys.executable, args=[str(server)], env=dict(os.environ))
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    reply = await client.call_tool(name, request)
                    if reply.is_error:
                        raise RuntimeError("Declared MCP tool failed")
                    return reply.structured_content if reply.structured_content is not None else json.loads(next(item.text for item in reply.content if item.type == "text"))

        result = asyncio.run(call())
    else:
        raise ValueError("Unsupported execution kind")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
