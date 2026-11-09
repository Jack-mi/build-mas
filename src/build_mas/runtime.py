"""The sole builder boundary to the public Codex Python SDK."""

import asyncio
import inspect
import json
import os
import shutil
import sys
import time
from importlib import metadata
from pathlib import Path
from types import SimpleNamespace

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, ExternalMessage, LocalImageInput, SkillInput, TextInput

from .contracts import Budget
from .errors import BuildMasError
from .templates.execution import sensitive_paths

SDK_VERSION = "0.167.0"


def sdk_capabilities():
    from openai_codex import AsyncThread

    return {
        "sdk_version": SDK_VERSION,
        "builder_python": sys.executable,
        "thread_start": str(inspect.signature(AsyncCodex.thread_start)),
        "thread_resume": str(inspect.signature(AsyncCodex.thread_resume)),
        "turn": str(inspect.signature(AsyncThread.turn)),
        "config": str(inspect.signature(CodexConfig)),
        "no_agent_tools_parameter": True,
        "documented_no_tools_config": ["features.shell_tool=false", "features.apply_patch_freeform=false", "features.multi_agent=false", "features.hooks=false", "features.apps=false", "web_search=\"disabled\"", "skills.include_instructions=false"],
        "skills": "TextInput with $skill-name plus SkillInput(name, absolute_SKILL_path); separate discovery and behavior verification",
        "external": "ExternalMessage as complete input; cannot be mixed into a user-input list",
        "budget": "Aggregate SDK token usage includes runtime/system prompt and input context. Inherit caller budget unless a smaller target budget is explicitly requested; short output does not mean a small token budget. Fixed local 0.167.0 trials consumed about 10000 input+output tokens for one no-tool turn, not a universal provider estimate.",
        "mcp": "mcp==2.3.0 uses MCPServer from mcp.server.mcpserver, snake_case ToolAnnotations and ClientSession",
        "tools": "Bounded read_file/list_files builtins, Python CLI modules and project-local Python stdio MCP servers use the host-owned registry, schemas, OS sandbox and actual receipts. General native shell tools are disabled. No public tools=[], register_tool or spawn_agent method.",
    }


def serializable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable(item) for item in value]
    return value


def runtime_home(home):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    home = Path(home)
    target = home / "sdk"
    target.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")).expanduser()
    config_path = source / "config.toml"
    config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    for filename in ("auth.json",):
        existing = source / filename
        destination = target / filename
        if existing.is_file() and existing.resolve() != destination.resolve():
            shutil.copyfile(existing, destination)
            os.chmod(destination, 0o600)
    selected = {key: config[key] for key in ("model", "model_provider", "model_reasoning_effort", "openai_base_url", "chatgpt_base_url") if key in config}
    provider = config.get("model_provider")
    if provider and provider in config.get("model_providers", {}):
        selected["model_providers"] = {provider: config["model_providers"][provider]}
    baseline = "\n".join(f"{key} = {toml_value(value)}" for key, value in selected.items()) + "\n"
    destination = target / "config.toml"
    if not destination.exists() or destination.read_text() != baseline:
        destination.write_text(baseline)
        os.chmod(destination, 0o600)
    return target, selected


def toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ",".join(toml_value(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key) + "=" + toml_value(item) for key, item in value.items()) + "}"
    raise BuildMasError("invalid_runtime_config", "Unsupported runtime configuration value")


def verification_auth(home, destination=None):
    import urllib.parse
    import socket
    import ipaddress

    sdk, selected = runtime_home(home)
    if destination:
        destination = Path(destination).resolve()
        destination.mkdir(parents=True, exist_ok=True, mode=0o700)
        for filename in ("auth.json", "config.toml"):
            source = sdk / filename
            if source.is_file():
                shutil.copyfile(source, destination / filename)
                os.chmod(destination / filename, 0o600)
        sdk = destination
    providers = selected.get("model_providers", {})
    urls = [provider.get("base_url", "") for provider in providers.values()]
    if not urls:
        urls = [selected.get("openai_base_url", "https://api.openai.com/v1"), selected.get("chatgpt_base_url", "https://chatgpt.com/backend-api/codex"), "https://auth.openai.com"]
    ports = []
    for url in urls:
        parsed = urllib.parse.urlsplit(url)
        if not parsed.hostname or parsed.username or parsed.password or parsed.scheme not in {"https", "http"}:
            raise BuildMasError("unsafe_model_endpoint", "Model endpoint must be an explicit HTTP(S) URL without user information")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
            ports.append(port)
            continue
        if parsed.scheme != "https":
            raise BuildMasError("unsafe_model_endpoint", "Non-loopback model endpoints require HTTPS")
        addresses = {item[4][0] for item in socket.getaddrinfo(parsed.hostname, port, type=socket.SOCK_STREAM)}
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise BuildMasError("unsafe_model_endpoint", "Remote model endpoint resolved to a private address")
        ports.append({"host": parsed.hostname, "port": port, "addresses": sorted(addresses)})
    return sdk, ports


def verification_environment(sdk_home):
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    config = tomllib.loads((Path(sdk_home) / "config.toml").read_text())
    provider = config.get("model_providers", {}).get(config.get("model_provider"), {})
    names = {"OPENAI_API_KEY", "CODEX_API_KEY"}
    names.update(provider.get("env_http_headers", {}).values())
    if provider.get("env_key"):
        names.add(provider["env_key"])
    for name in names:
        if not isinstance(name, str) or not name.isascii() or not name.isidentifier() or name in {"PATH", "HOME", "TMPDIR", "ALL_PROXY", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"} or name.startswith(("PYTHON", "DYLD_", "LD_", "BUILD_MAS_", "CODEX_HOME")):
            raise BuildMasError("unsafe_runtime_config", "Model credential variables cannot override the verification environment")
    return {name: os.environ[name] for name in names if name in os.environ}


class CodexRuntime:
    def __init__(self, home, *, budget=None, event=None, model=None):
        self.home = Path(home)
        self.budget = budget or Budget()
        self.event = event or (lambda *args, **kwargs: None)
        self.model = model
        self.turns = 0
        self.tokens = 0
        self.started = time.monotonic()
        self.handles = {}
        self.clients = []
        self.thread_tokens = {}

    def config(self, cwd, *, write=False):
        sdk_home, selected = runtime_home(self.home)
        root = str(Path(cwd).resolve())
        temporary = self.home / "runtime_tmp"
        temporary.mkdir(parents=True, exist_ok=True, mode=0o700)
        filesystem = {":minimal": "read", str(Path.home()): "deny", str(self.home): "deny", str(Path(sys.prefix).resolve()): "read", str(Path(sys.base_prefix).resolve()): "read", root: "write" if write else "read", str(temporary): "write"}
        for path in sensitive_paths(root):
            filesystem[str(path)] = "deny"
        profile = {"filesystem": filesystem, "network": {"enabled": False}}
        settings = {
            "approval_policy": "never",
            "default_permissions": "buildmas",
            "permissions": {"buildmas": profile},
            "features": {"apps": False, "hooks": False, "multi_agent": False},
            "web_search": "disabled",
            "skills": {"bundled": {"enabled": False}, "include_instructions": False},
            "project_doc_max_bytes": 0,
            "project_root_markers": [],
            "projects": {root: {"trust_level": "untrusted"}},
            "mcp_servers": {},
            "shell_environment_policy": {"inherit": "none", "set": {"PATH": os.environ.get("PATH", ""), "HOME": str(sdk_home), "TMPDIR": str(temporary)}},
        }
        overrides = tuple(f"{key}={toml_value(value)}" for key, value in settings.items())
        return CodexConfig(cwd=root, env={"CODEX_HOME": str(sdk_home)}, config_overrides=overrides, client_name="build_mas", client_title="build-mas")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        for client in self.clients:
            await client.close()

    async def preflight(self, cwd):
        versions = {}
        for name in ("openai-codex", "openai-codex-cli-bin"):
            try:
                versions[name] = metadata.version(name)
            except metadata.PackageNotFoundError as exc:
                raise BuildMasError("builder_sdk_missing", f"Install build-mas to provide {name}") from exc
        if any(version != SDK_VERSION for version in versions.values()):
            raise BuildMasError("builder_runtime_mismatch", "SDK and bundled runtime must match the pinned release", details=versions)
        client = AsyncCodex(self.config(cwd))
        try:
            async with client:
                models = await asyncio.wait_for(client.models(), timeout=30)
                try:
                    account = await asyncio.wait_for(client.account(), timeout=30)
                except Exception as exc:
                    return {"status": "account_unverified", "versions": versions, "account_present": None, "models": [item.model for item in models.data], "sdk_managed_runtime": True, "error": {"code": "account_check_failed", "message": "Runtime initialized and model catalog loaded, but account validation did not complete", "type": type(exc).__name__}, "next_safe_action": "Verify account/network routing or run a separately authorized minimal model task. Catalog availability is not authentication evidence."}
                return {"status": "ready" if account.account is not None else "authentication_required", "versions": versions, "account_present": account.account is not None, "models": [item.model for item in models.data], "selected_model": self.model, "sdk_managed_runtime": True}
        except BuildMasError:
            raise
        except Exception as exc:
            raise BuildMasError("builder_runtime_unavailable", "Codex runtime could not start; inspect buildmas_preflight", details={"type": type(exc).__name__}) from exc

    async def login(self, *, device=False, timeout=300, authorize=None):
        if authorize is None:
            raise BuildMasError("login_channel_unavailable", "Authentication requires a user-only URL confirmation channel")
        attempt = await self.start_login(device=device, timeout=timeout)
        try:
            await asyncio.wait_for(authorize(attempt["instruction"]), timeout=max(0, attempt["expires"] - time.monotonic()))
        except asyncio.TimeoutError as exc:
            await self.cancel_login(attempt)
            raise BuildMasError("authentication_required", "Login confirmation expired; retry without sharing credentials") from exc
        except BaseException:
            await self.cancel_login(attempt)
            raise
        return await self.finish_login(attempt)

    async def start_login(self, *, device=False, timeout=300):
        expires = time.monotonic() + timeout
        root = self.home / "login"
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        client = AsyncCodex(self.config(root))
        await asyncio.wait_for(client.__aenter__(), timeout=max(0, expires - time.monotonic()))
        try:
            call = client.login_chatgpt_device_code() if device else client.login_chatgpt()
            handle = await asyncio.wait_for(call, timeout=max(0, expires - time.monotonic()))
        except BaseException:
            await client.__aexit__(None, None, None)
            raise
        return {"client": client, "handle": handle, "expires": expires, "instruction": {"verification_url": handle.verification_url, "user_code": handle.user_code} if device else {"auth_url": handle.auth_url}}

    async def finish_login(self, attempt):
        try:
            receipt = await asyncio.wait_for(attempt["handle"].wait(), timeout=max(0, attempt["expires"] - time.monotonic()))
            if not receipt.success:
                raise BuildMasError("authentication_required", "Codex account login did not complete")
            return {"status": "ready", "account_present": True, "builder_private_auth": True}
        except asyncio.TimeoutError as exc:
            await attempt["handle"].cancel()
            raise BuildMasError("authentication_required", "Login expired; retry without sharing credentials") from exc
        except asyncio.CancelledError:
            await attempt["handle"].cancel()
            raise
        except Exception:
            await attempt["handle"].cancel()
            raise
        finally:
            await attempt["client"].__aexit__(None, None, None)

    async def cancel_login(self, attempt):
        try:
            await attempt["handle"].cancel()
        finally:
            await attempt["client"].__aexit__(None, None, None)

    async def thread(self, cwd, instructions, *, write=False, thread_id=None, ephemeral=False, model=None):
        if time.monotonic() - self.started >= self.budget.timeout_seconds:
            raise BuildMasError("budget_exceeded", "Operation wall-time budget reached")
        client = AsyncCodex(self.config(cwd, write=write))
        await client.__aenter__()
        self.clients.append(client)
        options = {"cwd": str(Path(cwd).resolve()), "approval_mode": ApprovalMode.deny_all, "developer_instructions": instructions, "config": {"model_reasoning_effort": "medium"}}
        if model or self.model:
            options["model"] = model or self.model
        if thread_id:
            thread = await client.thread_resume(thread_id, include_turns=False, **options)
        else:
            thread = await client.thread_start(ephemeral=ephemeral, **options)
        self.thread_tokens[thread.id] = None if thread_id else 0
        self.event("thread_started", thread_id=thread.id, write=write, resumed=bool(thread_id))
        return thread

    async def run(self, thread, user_text, *, schema=None, external=None, images=None, skills=None, effort=None, timeout=None):
        if self.turns >= self.budget.max_turns or self.tokens >= self.budget.max_tokens:
            raise BuildMasError("budget_exceeded", "Aggregate turn or token budget reached")
        self.turns += 1
        value = [TextInput(user_text + ("\nReturn only JSON matching this exact schema:\n" + json.dumps(schema) if schema and external is None else ""))]
        value.extend(LocalImageInput(str(path)) for path in images or [])
        value.extend(SkillInput(name, str(path)) for name, path in skills or [])
        options = {"approval_mode": ApprovalMode.deny_all}
        if schema:
            options["output_schema"] = strict_schema(schema)
        if effort:
            options["effort"] = effort
        else:
            options["effort"] = "medium"
        if external is not None:
            if images or skills:
                raise BuildMasError("invalid_input", "Establish image/skill input before an external-message turn")
            value = ExternalMessage(tool_name="workspace_evidence", namespace="buildmas", content=json.dumps(external, ensure_ascii=False))
        handle = await thread.turn(value, **options)
        self.handles[handle.id] = handle
        self.event("turn_started", thread_id=thread.id, turn_id=handle.id)
        remaining = self.budget.timeout_seconds - (time.monotonic() - self.started)
        allowed = max(1, min(timeout or self.budget.timeout_seconds, remaining))
        try:
            result = await asyncio.wait_for(self.collect(handle), timeout=allowed)
        except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
            try:
                await asyncio.wait_for(handle.interrupt(), timeout=10)
            except Exception:
                pass
            self.event("turn_interruption_requested", thread_id=thread.id, turn_id=handle.id)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise BuildMasError("outcome_unknown", "Turn timed out; interruption requested, result must be reconciled", details={"thread_id": thread.id, "turn_id": handle.id}) from exc
        finally:
            self.handles.pop(handle.id, None)
        if result.status != "completed" or result.error:
            error = result.error or {}
            raise BuildMasError("codex_turn_failed", "Codex did not complete the requested turn", details={"status": result.status, "turn_id": handle.id, "error_message": error.get("message", "")[:1800]})
        if not result.final_response or not result.final_response.strip():
            raise BuildMasError("empty_output", "Codex turn returned no final response")
        if result.usage:
            total = result.usage.get("total", {})
            cumulative = total.get("totalTokens", total.get("total_tokens", 0))
            baseline = self.thread_tokens.get(thread.id, 0)
            last = result.usage.get("last", {})
            self.tokens += last.get("totalTokens", last.get("total_tokens", 0)) if baseline is None else max(0, cumulative - baseline)
            self.thread_tokens[thread.id] = cumulative
        self.event("turn_completed", thread_id=thread.id, turn_id=handle.id, tokens=self.tokens, turns=self.turns, status=result.status)
        if self.tokens > self.budget.max_tokens:
            self.event("budget_exceeded", tokens=self.tokens, allowed=self.budget.max_tokens)
            raise BuildMasError("budget_exceeded", "Aggregate token budget exceeded after completed turn")
        return result

    async def check_command(self, cwd, argv, *, expected=None, timeout=120):
        import shlex

        thread = await self.thread(cwd, "Run exactly the host-provided validation command once. Do not modify source, create substitute output, install packages or call external tools. Report completion only after the command exits.", ephemeral=True)
        result = await self.run(thread, "Execute exactly this validation command:\n" + shlex.join(argv), timeout=timeout, effort="low")
        receipts = [item for item in result.items if isinstance(item, dict) and item.get("type") == "commandExecution"]
        matching = [item for item in receipts if item.get("command") and shlex.join(argv) in item["command"]]
        if not matching:
            raise BuildMasError("command_not_executed", "No runtime command receipt matches the requested validation")
        receipt = matching[-1]
        output = receipt.get("aggregatedOutput", receipt.get("aggregated_output", "")) or ""
        exit_code = receipt.get("exitCode", receipt.get("exit_code"))
        passed = exit_code == 0
        if expected is not None:
            try:
                passed = passed and json.loads(output) == expected
            except ValueError:
                passed = False
        return {"status": "passed" if passed else "failed", "exit_code": exit_code, "argv": argv, "output": output[:20000], "thread_id": thread.id, "turn_id": result.id, "evidence_source": "codex_command_receipt"}

    async def collect(self, handle):
        texts = []
        usage = None
        completed = None
        items = []
        async for event in handle.stream():
            payload = event.payload
            if event.method == "item/completed":
                item = payload.item.root if hasattr(payload.item, "root") else payload.item
                if getattr(item, "type", None) == "commandExecution":
                    items.append(serializable(item))
                phase = getattr(item, "phase", None)
                phase = getattr(phase, "value", phase)
                if getattr(item, "type", None) == "agentMessage" and phase in (None, "final_answer"):
                    texts.append(item.text)
            elif event.method == "thread/tokenUsage/updated":
                usage = serializable(payload.token_usage)
            elif event.method == "turn/completed":
                completed = payload.turn
                self.event("turn_terminal", turn_id=handle.id, status=getattr(completed.status, "value", completed.status))
            if event.method in ("item/started", "item/completed", "turn/completed"):
                self.event("runtime_event", method=event.method, turn_id=handle.id)
        if completed is None:
            raise BuildMasError("outcome_unknown", "Turn stream ended without terminal evidence")
        status = getattr(completed.status, "value", completed.status)
        return SimpleNamespace(id=handle.id, status=status, error=serializable(completed.error), final_response=texts[-1] if texts else None, items=items, usage=usage, duration_ms=getattr(completed, "duration_ms", None))

    async def reconcile(self, cwd, thread_id, turn_id):
        thread = await self.thread(cwd, "Read recorded turn status only. Do not execute work.", thread_id=thread_id)
        response = await asyncio.wait_for(thread.read(include_turns=True), timeout=30)
        turn = next((item for item in response.thread.turns if item.id == turn_id), None)
        if turn is None:
            raise BuildMasError("outcome_unknown", "Original turn has no terminal runtime record")
        status = getattr(turn.status, "value", turn.status)
        if status not in {"completed", "failed", "interrupted"}:
            raise BuildMasError("outcome_unknown", "Original Codex turn is still active; do not replay it")
        return {"thread_id": thread_id, "turn_id": turn_id, "status": status}


def strict_schema(schema):
    value = json.loads(json.dumps(schema))
    pending = [value]
    while pending:
        current = pending.pop()
        if isinstance(current, dict):
            current.pop("default", None)
            if current.get("type") == "object" and "properties" in current:
                current["required"] = list(current["properties"])
                current["additionalProperties"] = False
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return value
