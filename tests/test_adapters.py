import json
from pathlib import Path

from codexwright.mcp_server import server_for
from codexwright import __version__
from codexwright.service import BuildService

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_manifests_reference_same_mcp():
    codex = json.loads((ROOT / "mcp.json").read_text())
    claude = json.loads((ROOT / "adapters/claude-code/.mcp.json").read_text())
    assert codex["mcpServers"]["codexwright"]["type"] == "stdio"
    command = claude["mcpServers"]["codexwright"]
    assert command["command"] == "python3" and len(command["args"]) == 1
    assert command["env"] == codex["mcpServers"]["codexwright"]["env"] == {"CODEXWRIGHT_ALLOW_APPLY": "1"}
    assert codex["mcpServers"]["codexwright"]["command"] == "./scripts/launch.py"
    assert command["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}")
    assert (ROOT / "scripts/launch.py").read_text() == (ROOT / "adapters/claude-code/scripts/launch.py").read_text()
    opencode = json.loads((ROOT / "adapters/opencode/opencode.jsonc").read_text())
    assert opencode["mcp"]["servers"]["codexwright"]["command"] == ["python", "-m", "codexwright.mcp_server"]
    assert opencode["mcp"]["servers"]["codexwright"]["environment"] == {"CODEXWRIGHT_ALLOW_APPLY": "1"}
    assert opencode["permissions"] == [{"action": "codexwright_codexwright_apply", "resource": "*", "effect": "ask"}]
    assert opencode["instructions"] == ["codexwright-host.md"]
    assert json.loads((ROOT / "plugin.json").read_text())["version"] == __version__
    assert json.loads((ROOT / "plugin.json").read_text())["name"] == "codexwright"
    assert json.loads((ROOT / "adapters/claude-code/.claude-plugin/plugin.json").read_text())["version"] == __version__
    marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())
    assert marketplace["name"] == "codexwright-local"
    assert marketplace["plugins"][0]["name"] == "codexwright"
    for name in ("plugin.json", "mcp.json", "scripts/launch.py", "skills/codexwright/SKILL.md"):
        assert (ROOT / name).read_text() == (ROOT / "adapters/codex" / name).read_text()
    assert json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())["plugins"][0]["source"]["path"] == "./adapters/codex"


def test_adapters_have_no_other_runtime():
    bodies = [(ROOT / "skills/codexwright/SKILL.md").read_text(), (ROOT / "adapters/claude-code/skills/codexwright/SKILL.md").read_text(), (ROOT / "adapters/opencode/codexwright-host.md").read_text()]
    for body in bodies:
        assert "invoke" in body and "apply" in body
        assert "approval" in body.lower()
        assert "Codex" in body
        assert "fallback" in body


def test_builder_has_no_cli_or_hooks():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    metadata = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert metadata["project"]["name"] == "codexwright"
    assert not metadata["project"].get("scripts")
    assert not (ROOT / "src/codexwright/cli.py").exists()
    assert not (ROOT / "adapters/codex/hooks").exists()
    for path in (ROOT / "src/codexwright").glob("*.py"):
        assert "codexwright.cli" not in path.read_text()
