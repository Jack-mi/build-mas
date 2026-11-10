"""Public MCP contracts and bounded views; private records remain in the store."""

import json
from collections import Counter
from typing import Annotated, Any, Literal

from pydantic import Field

from .contracts import Contract, Identifier, IntakeEnvelope

SUMMARY_BYTES = 16 * 1024
ReadCategory = Literal["specs", "proposals", "runs", "results", "sessions", "events"]
IdempotencyKey = Annotated[str, Field(min_length=1, max_length=160)]


class InvokeEnvelope(IntakeEnvelope):
    idempotency_key: IdempotencyKey


class PublicApplyRequest(Contract):
    proposal_id: Identifier
    idempotency_key: IdempotencyKey


class Reference(Contract):
    category: ReadCategory
    reference: str


class PublicResult(Contract):
    api_version: Literal["0.4"] = "0.4"
    status: Literal["completed", "running", "partial", "failed", "blocked", "approval_required", "outcome_unknown", "ready", "authentication_required", "account_unverified"]
    operation: str | None = None
    id: str | None = None
    workspace_id: str | None = None
    session_id: str | None = None
    run_id: str | None = None
    proposal_id: str | None = None
    spec_revision: int | None = None
    summary: str | None = None
    verification: str | None = None
    changed_files: list[str] = Field(default_factory=list)
    proposed_files: list[dict[str, str]] = Field(default_factory=list)
    checks_summary: dict[str, int] = Field(default_factory=dict)
    questions: list[str] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    omitted: dict[str, int] = Field(default_factory=dict)
    error: dict[str, Any] | None = None
    next_safe_action: str | None = None
    usage: dict[str, int] | None = None
    material_coverage: dict[str, Any] | None = None
    last_stage: str | None = None
    stage_sequence: int | None = None
    updated_at: float | None = None
    started_at: float | None = None
    finished_at: float | None = None
    run_count: int | None = None
    latest_run: dict[str, Any] | None = None
    recovery_required: bool | None = None
    recovered_from: str | None = None
    root: str | None = None
    registered_at: float | None = None
    file_name: str | None = None
    sha256: str | None = None
    media_type: str | None = None
    versions: dict[str, str] | None = None
    models: list[str] = Field(default_factory=list)
    selected_model: str | None = None
    account_present: bool | None = None
    sdk_managed_runtime: bool | None = None
    builder_private_auth: bool | None = None
    capabilities: dict[str, Any] | None = None
    workspace: dict[str, Any] | None = None


class PageResult(Contract):
    api_version: Literal["0.4"] = "0.4"
    status: Literal["completed", "failed"]
    content: str | None = None
    next_offset: int | None = None
    reference: str | None = None
    error: dict[str, Any] | None = None


def dump(model, value):
    return model.model_validate(value).model_dump(mode="json", exclude_none=True)


def summary_size(value):
    text = json.dumps(value, ensure_ascii=False)
    envelope = {"content": [{"type": "text", "text": text}], "structuredContent": value, "isError": False, "resultType": "complete"}
    return len(json.dumps(envelope, ensure_ascii=False).encode()) + 512


def summary(value):
    raw = value
    if value.get("id", "").startswith("run_"):
        value = {**value, **value.get("result", {}), "status": value["status"], "run_id": value["id"]}
    result = {key: item for key, item in value.items() if key in PublicResult.model_fields and item is not None}
    result.setdefault("status", "completed")
    result["checks_summary"] = dict(Counter(check.get("status", "unknown") for check in value.get("checks", [])))
    result["references"] = []
    for category, reference in (("results", value.get("run_id")), ("runs", value.get("run_id")), ("events", value.get("run_id")), ("sessions", value.get("session_id")), ("proposals", value.get("proposal_id"))):
        if reference:
            result["references"].append({"category": category, "reference": reference})
    if value.get("session_id") and value.get("spec_revision"):
        result["references"].append({"category": "specs", "reference": f"{value['session_id']}_r{value['spec_revision']}"})
    if "runs" in raw:
        result["run_count"] = len(raw["runs"])
        result["session_id"] = raw["id"]
        result["references"].append({"category": "sessions", "reference": raw["id"]})
        result["latest_run"] = summary(raw["latest_run"]) if raw.get("latest_run") else None
    result = dump(PublicResult, result)
    if "account_present" in value:
        result["account_present"] = value["account_present"]
    # Large detail stays addressable; never truncate the status or error code.
    while summary_size(result) > SUMMARY_BYTES:
        fields = [(len(json.dumps(item, ensure_ascii=False).encode()), key) for key, item in result.items() if key not in {"status", "api_version", "references", "omitted", "run_id", "session_id", "workspace_id", "proposal_id", "operation", "capabilities", "usage"} and isinstance(item, (str, list, dict)) and len(item)]
        _, key = max(fields)
        item = result[key]
        if isinstance(item, list):
            keep = len(item) // 2
            result["omitted"][key] = result["omitted"].get(key, 0) + len(item) - keep
            result[key] = item[:keep]
        elif isinstance(item, str):
            keep = len(item) // 2
            result["omitted"][key] = result["omitted"].get(key, 0) + len(item) - keep
            result[key] = item[:keep]
        elif key == "error":
            result["omitted"]["error.details"] = len(item.get("details", {}))
            result[key] = {"code": item.get("code", "operation_failed"), "message": str(item.get("message", "Operation failed"))[:1000]}
        elif key == "latest_run":
            result["omitted"][key] = len(item)
            result[key] = {k: v for k, v in item.items() if k in {"status", "verification", "run_id", "references"}}
            if item.get("error"):
                result[key]["error"] = {"code": item["error"].get("code", "operation_failed"), "message": str(item["error"].get("message", "Operation failed"))[:1000]}
        else:
            result["omitted"][key] = len(item)
            result[key] = {}
    return result
