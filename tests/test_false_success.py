import json
from pathlib import Path

from build_mas.contracts import ArchitectureSpec, CheckSpec
from build_mas.verify import verify_project


def test_optional_failure_is_partial_not_complete(tmp_path, spec):
    root = tmp_path / "target"; root.mkdir()
    (root / "workflow.py").write_text("value = 'fixture'\n")
    (root / "bad.py").write_text("raise SystemExit(8)\n")
    optional = CheckSpec(id="optional_live", kind="cli_smoke", target="bad.py", required=False)
    spec.verification.checks.append(optional)
    report = verify_project(spec, root, tmp_path / "evidence")
    assert report["status"] == "partial"
    assert any(item["status"] == "failed" for item in report["checks"])


def test_artifact_only_plan_cannot_claim_runnable(spec_dict):
    import pytest

    spec_dict["verification"]["checks"] = [spec_dict["verification"]["checks"][0]]
    with pytest.raises(ValueError, match="executable verification"):
        ArchitectureSpec.model_validate(spec_dict)


def test_migration_without_parity_contract_fails(spec_dict):
    import pytest

    spec_dict["runtime"] = {"source": "other", "target": "codex_sdk", "action": "migrate", "migration_notes": [], "parity_claim": "unverified"}
    with pytest.raises(ValueError, match="retirement check"):
        ArchitectureSpec.model_validate(spec_dict)
