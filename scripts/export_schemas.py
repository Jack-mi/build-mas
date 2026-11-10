"""Export the packaged request/spec schemas and actual service result shapes."""

import json
from pathlib import Path

from codexwright.contracts import ApplyRequest, ArchitectureSpec, IntakeEnvelope
from codexwright.mcp_contracts import InvokeEnvelope, PageResult, PublicApplyRequest, PublicResult


def schemas():
    result = {name: model.model_json_schema() for name, model in {"apply-request": ApplyRequest, "architecture-spec": ArchitectureSpec, "intake-envelope": IntakeEnvelope}.items()}
    result.update({name: model.model_json_schema() for name, model in {"mcp-invoke-envelope": InvokeEnvelope, "mcp-apply-request": PublicApplyRequest, "mcp-result": PublicResult, "mcp-page-result": PageResult}.items()})
    status = {"enum": ["completed", "running", "partial", "failed", "blocked", "approval_required", "outcome_unknown"]}
    verification = {"enum": ["not_run", "pending_live", "passed", "partial", "failed", "blocked"]}
    result["operation-result"] = {"title": "OperationResult", "type": "object", "required": ["status", "operation", "run_id", "session_id", "workspace_id", "verification", "changed_files", "checks"], "properties": {"status": status, "operation": {"type": "string"}, "run_id": {"type": "string"}, "session_id": {"type": "string"}, "workspace_id": {"type": "string"}, "spec_revision": {"type": ["integer", "null"]}, "verification": verification, "changed_files": {"type": "array", "items": {"type": "string"}}, "checks": {"type": "array", "items": {"type": "object"}}}}
    result["verification-report"] = {"title": "VerificationReport", "type": "object", "required": ["status", "checks", "spec_revision", "snapshot", "semantic_review", "skills"], "properties": {"status": {"enum": ["pending_live", "passed", "partial", "failed", "blocked"]}, "spec_revision": {"type": "integer", "minimum": 1}, "snapshot": {"type": "string", "pattern": "^[a-f0-9]{64}$"}, "checks": {"type": "array", "items": {"type": "object", "required": ["id", "kind", "required", "status"]}}, "semantic_review": {"type": ["object", "null"]}, "skills": {"type": "array", "items": {"type": "object"}}}}
    return {name: {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema} for name, schema in result.items()}


def main():
    directory = Path(__file__).resolve().parents[1] / "src/codexwright/schemas"
    for name, schema in schemas().items():
        (directory / f"{name}.schema.json").write_text(json.dumps(schema, indent=2) + "\n")


if __name__ == "__main__":
    main()
