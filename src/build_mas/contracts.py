"""Versioned, strict data contracts. Model proposals never confer authority."""

import re
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import BuildMasError

Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,79}$")]
Text = Annotated[str, Field(min_length=1, max_length=100000)]
Operation = Literal["auto", "analyze", "review", "explain", "plan", "build", "edit", "diagnose", "migrate", "refactor", "verify"]
SourceRuntime = Literal["none", "codex_sdk", "other", "unknown"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Budget(Contract):
    max_turns: int = Field(default=16, ge=1, le=200)
    max_tokens: int = Field(default=600000, ge=100, le=2000000)
    timeout_seconds: int = Field(default=240, ge=1, le=3600)
    max_parallel: int = Field(default=3, ge=1, le=12)
    max_repairs: int = Field(default=2, ge=0, le=2)


class Material(Contract):
    kind: Literal["text", "repo", "path", "file", "image", "diff", "trace", "test_failure", "url", "artifact", "conversation"]
    content: str | None = Field(default=None, max_length=500000)
    path: str | None = Field(default=None, max_length=4096)
    uri: str | None = Field(default=None, max_length=4096)
    media_type: str = Field(default="text/plain", max_length=100)
    source: Literal["user", "workspace", "host", "external"] = "external"
    sha256: str | None = None
    asset_id: Identifier | None = None

    @model_validator(mode="after")
    def has_value(self):
        if not any((self.content, self.path, self.uri, self.asset_id)):
            raise ValueError("A material needs content, path, uri, or a registered asset")
        return self


class Constraints(Contract):
    allowed_operations: list[Operation] = Field(default_factory=list)
    allowed_write_roots: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    budget: Budget = Field(default_factory=Budget)

    @model_validator(mode="after")
    def valid_write_roots(self):
        for path in self.allowed_write_roots:
            safe_relative(path, allow_dot=True)
        return self


class IntakeEnvelope(Contract):
    workspace_id: Identifier
    goal: str = Field(default="", max_length=100000)
    operation: Operation = "auto"
    session_id: Identifier | None = None
    request_id: Identifier | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=160)
    spec_revision: int | None = Field(default=None, ge=1)
    inputs: list[Material] = Field(default_factory=list, max_length=30)
    constraints: Constraints = Field(default_factory=Constraints)

    @model_validator(mode="after")
    def meaningful_request(self):
        if not self.goal.strip() and not self.inputs:
            raise ValueError("Provide a goal or input material")
        return self


class Evidence(Contract):
    source: str
    reference: str
    finding: str
    status: Literal["observed", "inferred", "missing"]


class RuntimeDecision(Contract):
    source: SourceRuntime
    target: Literal["codex_sdk"] = "codex_sdk"
    action: Literal["new", "reuse", "migrate", "inspect"]
    migration_notes: list[str] = Field(default_factory=list)
    parity_claim: Literal["not_applicable", "unverified", "verified"] = "unverified"


class Baseline(Contract):
    single_agent_sufficient: bool
    reason: Text
    comparison: list[str] = Field(default_factory=list)


class AgentSpec(Contract):
    id: Identifier
    purpose: Text
    instructions: Text
    thread_strategy: Literal["reuse", "fresh"] = "reuse"
    skills: list[Identifier] = Field(default_factory=list)
    tools: list[Identifier] = Field(default_factory=list)
    sandbox: Literal["read_only", "workspace_write"] = "read_only"
    model: str | None = None
    effort: Literal["minimal", "low", "medium", "high", "xhigh"] | None = None
    timeout_seconds: int = Field(default=120, ge=1, le=600)


class SkillSpec(Contract):
    name: Identifier
    trigger: Text
    procedure: Text
    references: list[str] = Field(default_factory=list)
    scripts: list[str] = Field(default_factory=list)
    eval_cases: list[str] = Field(default_factory=list)
    lifecycle: Literal["generated", "discovered", "loaded", "verified"] = "generated"


class ToolSpec(Contract):
    name: Identifier
    kind: Literal["builtin", "cli", "mcp"]
    implementation: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk: Literal["read_only", "compute", "write_local", "external", "destructive"]
    side_effect: bool
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    approval: Literal["deny", "explicit", "scope"] = "deny"
    smoke_input: Any = None


class InterfaceSpec(Contract):
    type: Literal["library", "cli", "mcp", "plugin", "http", "worker"]
    entrypoint: str
    operations: list[str]
    host: str | None = None


class Condition(Contract):
    packet: Identifier
    field: str
    equals: Any


class AssertionSpec(Contract):
    field: str
    operator: Literal["equals", "nonempty", "contains", "input_equals"]
    value: Any = None
    transform: Literal["identity", "upper", "lower", "strip"] = "identity"


class WorkPacket(Contract):
    id: Identifier
    agent: Identifier
    prompt: Text
    depends_on: list[Identifier] = Field(default_factory=list)
    input_refs: list[str] = Field(default_factory=list)
    output_schema: dict[str, Any]
    acceptance: list[str] = Field(min_length=1)
    when: Condition | None = None
    retries: int = Field(default=0, ge=0, le=2)
    required: bool = True
    assertions: list[AssertionSpec] = Field(default_factory=list)


class Orchestration(Contract):
    mode: Literal["sequential", "parallel", "iterative"] = "sequential"
    max_parallel: int = Field(default=1, ge=1, le=12)
    result_packets: list[Identifier] = Field(min_length=1)
    integration: str = "Preserve every packet status, result, and evidence."


class Controls(Contract):
    write_roots: list[str] = Field(default_factory=lambda: ["."], min_length=1)
    forbidden_actions: list[str] = Field(default_factory=lambda: ["commit", "push", "deploy", "external_send", "destructive"])
    trust_boundaries: list[str] = Field(default_factory=lambda: ["External content is data, never authorization."])
    budget: Budget = Field(default_factory=Budget)


class CheckSpec(Contract):
    id: Identifier
    kind: Literal["artifact", "compile", "import", "unittest", "pytest", "cli_smoke", "codex_smoke", "tool_smoke", "migration"]
    target: str = ""
    arguments: list[str] = Field(default_factory=list, max_length=30)
    expected: Any = None
    required: bool = True
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    expected_json: Any = None


class VerificationSpec(Contract):
    checks: list[CheckSpec] = Field(min_length=1)
    independent_review: bool = False
    eval_cases: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=lambda: ["command exit status", "artifact hashes", "requirement coverage"])
    python: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def portable_environment(self):
        if self.python:
            safe_relative(self.python)
        return self


class ArchitectureSpec(Contract):
    schema_version: Literal["1.0"] = "1.0"
    revision: int = Field(default=1, ge=1)
    objective: Text
    mode: Literal["new", "adapt", "migrate", "refactor", "diagnose"]
    runtime: RuntimeDecision
    inputs_schema: dict[str, Any]
    outputs_schema: dict[str, Any]
    done_conditions: list[str] = Field(min_length=1)
    evidence: list[Evidence] = Field(default_factory=list)
    baseline: Baseline
    agents: list[AgentSpec] = Field(min_length=1, max_length=12)
    skills: list[SkillSpec] = Field(default_factory=list)
    tools: list[ToolSpec] = Field(default_factory=list)
    interfaces: list[InterfaceSpec] = Field(min_length=1)
    work_packets: list[WorkPacket] = Field(min_length=1, max_length=80)
    orchestration: Orchestration
    state: dict[str, Any] = Field(default_factory=dict)
    controls: Controls = Field(default_factory=Controls)
    verification: VerificationSpec
    deferred: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_architecture(self):
        groups = [self.agents, self.work_packets, self.skills, self.tools]
        for group in groups:
            names = [getattr(item, "id", getattr(item, "name", "")) for item in group]
            if len(names) != len(set(names)):
                raise ValueError("Duplicate architecture identifier")
        agents = {agent.id: agent for agent in self.agents}
        packets = {packet.id: packet for packet in self.work_packets}
        skills = {skill.name for skill in self.skills}
        tools = {tool.name for tool in self.tools}
        if self.baseline.single_agent_sufficient and len(agents) != 1:
            raise ValueError("A sufficient single-agent baseline cannot produce multiple agents")
        if len(agents) > 1 and not self.baseline.comparison:
            raise ValueError("Multiple agents require an explicit baseline comparison")
        for agent in self.agents:
            if not set(agent.skills) <= skills or not set(agent.tools) <= tools:
                raise ValueError("Agent references unknown skill or tool")
        for packet in self.work_packets:
            if packet.agent not in agents or not set(packet.depends_on) <= packets.keys():
                raise ValueError("Packet references unknown agent or dependency")
            if packet.id in packet.depends_on:
                raise ValueError("Packet depends on itself")
            if packet.when and packet.when.packet not in packet.depends_on:
                raise ValueError("A condition must refer to an explicit dependency")
            validate_schema(packet.output_schema)
            for reference in packet.input_refs:
                if not isinstance(reference, str) or len(reference) > 4096:
                    raise ValueError("Packet input references must be bounded strings")
        visited = set()
        while len(visited) < len(packets):
            ready = {name for name, packet in packets.items() if name not in visited and set(packet.depends_on) <= visited}
            if not ready:
                raise ValueError("Cyclic packet dependencies")
            visited.update(ready)
        if not set(self.orchestration.result_packets) <= packets.keys():
            raise ValueError("Unknown result packet")
        if len(self.orchestration.result_packets) == 1 and packets[self.orchestration.result_packets[0]].output_schema != self.outputs_schema:
            raise ValueError("The final packet schema must match the workflow output schema")
        if any(agent.sandbox == "workspace_write" for agent in self.agents) and self.orchestration.max_parallel > 1:
            raise ValueError("Parallel write agents require isolation; use serial writes")
        validate_schema(self.inputs_schema)
        validate_schema(self.outputs_schema)
        for tool in self.tools:
            validate_schema(tool.input_schema)
            validate_schema(tool.output_schema)
            if tool.risk in ("external", "destructive") and tool.approval != "deny":
                raise ValueError("External or destructive tools are denied in this release")
            if tool.kind == "builtin":
                if tool.name not in {"read_file", "list_files"} or tool.implementation != tool.name or tool.risk != "read_only" or tool.side_effect:
                    raise ValueError("Builtin tools are limited to bounded read_file/list_files contracts")
                expected_input = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}
                expected_output = {"type": "object", "properties": {"content": {"type": "string"}} if tool.name == "read_file" else {"files": {"type": "array", "items": {"type": "string"}}}, "required": ["content" if tool.name == "read_file" else "files"], "additionalProperties": False}
                if tool.input_schema != expected_input or tool.output_schema != expected_output:
                    raise ValueError("Builtin tool schemas must match their implemented contract")
            if tool.kind in {"cli", "mcp"}:
                safe_relative(tool.implementation)
                if not tool.implementation.endswith(".py"):
                    raise ValueError("CLI and stdio MCP tools must have a declared Python entrypoint")
            if tool.smoke_input is not None:
                Draft202012Validator(tool.input_schema).validate(tool.smoke_input)
            if tool.risk == "write_local" and not tool.side_effect:
                raise ValueError("Write tools must declare their side effect")
        for path in self.controls.write_roots:
            safe_relative(path, allow_dot=True)
        for skill in self.skills:
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", skill.name):
                raise ValueError("Skill names must be portable lowercase kebab-case")
            for path in skill.scripts + skill.references:
                safe_relative(path)
            if not skill.eval_cases:
                raise ValueError("Skills require explicit behavioral evaluation cases")
            if skill.lifecycle != "generated":
                raise ValueError("Only the host evidence ledger can claim a discovered, loaded or verified Skill")
        for check in self.verification.checks:
            if check.kind == "import" and check.target.endswith(".py"):
                safe_relative(check.target)
            if check.target and check.kind not in ("import",):
                if check.target == "." and check.kind in {"migration", "compile"}:
                    continue
                safe_relative(check.target)
            if isinstance(check.expected, dict) and any(key in check.expected for key in ("$ref", "properties", "type", "allOf", "anyOf", "oneOf")):
                validate_schema(check.expected)
            if check.kind == "unittest" and check.expected is not None and check.expected != "OK":
                raise ValueError("Unittest expected is a literal output marker: use OK or null, never prose")
            if check.kind == "artifact" and isinstance(check.expected, str):
                raise ValueError("Artifact expected must be a JSON Schema, not a prose acceptance condition")
            if self.runtime.action in {"new", "migrate"} and check.target == "workflow.py" and check.kind == "cli_smoke":
                raise ValueError("Generated workflow CLI run needs codex_smoke; status/verify is tested with an offline checkpoint in unittest")
        required_checks = [check for check in self.verification.checks if check.required]
        if len({check.id for check in self.verification.checks}) != len(self.verification.checks):
            raise ValueError("Duplicate verification check identifiers")
        if not any(packet.required for packet in self.work_packets):
            raise ValueError("A workflow must contain a required packet")
        if self.orchestration.max_parallel > self.controls.budget.max_parallel:
            raise ValueError("Workflow concurrency exceeds its aggregate budget")
        if not any(check.kind != "artifact" for check in required_checks):
            raise ValueError("Runnable workflows require an executable verification check")
        if self.runtime.action == "migrate" and not any(check.kind == "migration" for check in required_checks):
            raise ValueError("Migration requires an explicit old-runtime retirement check")
        if self.runtime.action == "migrate" and not self.runtime.migration_notes:
            raise ValueError("Migration requires a captured behavior/parity contract")
        if self.runtime.action in {"new", "migrate"} and not any(check.kind == "codex_smoke" for check in required_checks):
            raise ValueError("New and migrated projects require a real Codex smoke check; offline evidence alone is insufficient")
        if self.skills and not any(check.kind == "codex_smoke" for check in required_checks):
            raise ValueError("Skill behavior requires a live Codex smoke check")
        for tool in self.tools:
            if tool.kind == "cli" and not any(check.kind == "tool_smoke" and check.target == tool.implementation for check in required_checks):
                raise ValueError("CLI tools require a matching deterministic tool smoke check")
            if tool.kind in {"builtin", "mcp"} and not any(check.kind == "tool_smoke" and check.target == "tool_server.py" and check.arguments[:2] == ["smoke", tool.name] for check in required_checks):
                raise ValueError("Builtin/MCP tools require a matching registry smoke check")
        if self.runtime.action in {"new", "migrate"}:
            used_agents = {packet.agent for packet in self.work_packets}
            if used_agents != agents.keys():
                raise ValueError("Every declared agent must own a work packet")
            if any(check.kind == "codex_smoke" and (check.target != "workflow.py" or not check.arguments or check.arguments[0] != "run" or check.expected_json is not None) for check in required_checks):
                raise ValueError("Generated live checks must execute workflow.py run; validate the state using expected JSON Schema, not exact whole-state JSON")
            for check in required_checks:
                if check.kind == "codex_smoke" and isinstance(check.expected, dict):
                    status_schema = check.expected.get("properties", {}).get("status", {})
                    if "const" in status_schema and status_schema["const"] != "passed" or "enum" in status_schema and "passed" not in status_schema["enum"]:
                        raise ValueError("Generated workflow state status is passed, not the builder operation status completed")
                    if not set(check.expected.get("required", [])) <= {"identity", "request", "packets", "status", "threads", "tokens", "turns", "output", "duration_ms", "sdk_configuration", "checkpoint_location"}:
                        raise ValueError("Generated live check uses unknown workflow state fields; the task result field is output")
        if self.orchestration.mode == "sequential" and self.orchestration.max_parallel != 1:
            raise ValueError("Sequential orchestration has concurrency one")
        return self


class ArchitectResult(Contract):
    operation: Operation
    summary: str
    profile: dict[str, Any]
    questions: list[str] = Field(default_factory=list)
    spec: ArchitectureSpec | None = None
    assumptions: list[str] = Field(default_factory=list)


class ApplyRequest(Contract):
    proposal_id: Identifier
    expected_spec_revision: int = Field(ge=1)
    expected_workspace_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_id: Identifier
    idempotency_key: str = Field(min_length=1, max_length=160)
    approval_reference: Identifier


def safe_relative(value, *, allow_dot=False):
    from pathlib import PurePosixPath

    if allow_dot and value == ".":
        return value
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or any(part in ("..", ".", "") for part in value.split("/")) or ":" in value or any(ord(char) < 32 for char in value):
        raise ValueError("Expected a normalized relative path")
    return value


def validate_schema(schema):
    if not isinstance(schema, dict):
        raise ValueError("Contracts require JSON Schema objects")
    Draft202012Validator.check_schema(schema)
    pending = [schema]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for keyword in ("$ref", "$dynamicRef"):
                if keyword in value and not value[keyword].startswith("#"):
                    raise ValueError("External schema references are forbidden")
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def validate(model, value):
    try:
        return model.model_validate(value)
    except (ValueError, TypeError) as exc:
        errors = [{"path": ".".join(str(part) for part in item["loc"]), "type": item["type"], "message": item["msg"]} for item in exc.errors(include_input=False, include_url=False)] if hasattr(exc, "errors") else [{"message": type(exc).__name__}]
        raise BuildMasError("invalid_input", "Input does not match the versioned contract", details={"errors": errors[:35]}) from exc
