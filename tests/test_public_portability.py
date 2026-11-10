import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_is_english_and_uses_sdk_product_name():
    text = (ROOT / "README.md").read_text()
    assert not re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text)
    assert "Codex Python SDK" not in text and "Python Codex SDK" not in text
    assert "Codex SDK" in text and "docs/product-positioning.md" in text
    assert text.startswith("# codexwright\n")
    assert (ROOT / "docs/product-positioning.md").is_file()


def test_evidence_redaction_preserves_status_and_embedded_receipts():
    spec = importlib.util.spec_from_file_location("redact_evidence", ROOT / "scripts/redact_evidence.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    home = "/" + "Users/example"
    value = {"status": "failed", "source": home + "/project", "output": json.dumps({"status": "passed", "PATH": home + "/bin", "receipt": {"turn_id": "observed-turn"}})}
    result = module.redact(value)
    assert result["status"] == "failed" and result["source"] == "<user-home>/project"
    embedded = json.loads(result["output"])
    assert embedded == {"status": "passed", "PATH": "<runtime PATH omitted>", "receipt": {"turn_id": "observed-turn"}}
    assert module.redact({home: "deny"}) == {"<user-home>": "deny"}


def test_public_files_do_not_bind_the_developer_machine():
    prefixes = [str(Path.home()), "/" + "opt/homebrew", "/" + "private/var/folders", "/" + "var/folders"]
    paths = [ROOT / "README.md", ROOT / "pyproject.toml", ROOT / "plugin.json", ROOT / "mcp.json"]
    for folder in ("src", "adapters", "docs", ".agents"):
        paths.extend(path for path in (ROOT / folder).rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    for path in paths:
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".whl"}:
            continue
        text = path.read_text()
        assert not any(prefix in text for prefix in prefixes), str(path)
