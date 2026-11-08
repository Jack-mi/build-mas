import json
from pathlib import Path

from build_mas.mcp_server import server_for
from build_mas.service import BuildService

ROOT = Path(__file__).resolve().parents[1]


def test_adapter_manifests_reference_same_cli():
    codex = json.loads((ROOT / "mcp.json").read_text())
    claude = json.loads((ROOT / "adapters/claude-code/.mcp.json").read_text())
    assert codex["mcpServers"]["buildmas"]["type"] == "stdio"
    command = claude["mcpServers"]["buildmas"]
    assert command["command"] == "python3" and command["args"][1] == "serve"
    assert codex["mcpServers"]["buildmas"]["command"] == "./scripts/launch.py"
    assert command["args"][0].startswith("${CLAUDE_PLUGIN_ROOT}")
    assert (ROOT / "scripts/launch.py").read_text() == (ROOT / "adapters/claude-code/scripts/launch.py").read_text()
    opencode = json.loads((ROOT / "adapters/opencode/opencode.jsonc").read_text())
    assert opencode["mcp"]["servers"]["buildmas"]["command"] == ["build-mas", *command["args"][1:]]
    assert json.loads((ROOT / "plugin.json").read_text())["version"] == "0.2.0"
    assert json.loads((ROOT / "adapters/claude-code/.claude-plugin/plugin.json").read_text())["version"] == "0.2.0"
    for name in ("plugin.json", "mcp.json", "scripts/launch.py", "skills/build-mas/SKILL.md"):
        assert (ROOT / name).read_text() == (ROOT / "adapters/codex" / name).read_text()
    assert json.loads((ROOT / ".agents/plugins/marketplace.json").read_text())["plugins"][0]["source"]["path"] == "./adapters/codex"


def test_adapters_have_no_other_runtime():
    bodies = [(ROOT / "skills/build-mas/SKILL.md").read_text(), (ROOT / "adapters/claude-code/skills/build-mas/SKILL.md").read_text(), (ROOT / "adapters/opencode/build-mas-host.md").read_text()]
    for body in bodies:
        assert "invoke" in body and "apply" in body
        assert "approval" in body.lower()
        assert "Codex" in body
        assert "fallback" in body
