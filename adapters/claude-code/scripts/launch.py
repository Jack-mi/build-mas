#!/usr/bin/env python3
"""Start the privately installed builder without depending on a shell's PATH."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    environment = Path(os.environ.get("CODEXWRIGHT_ENV", Path.home() / ".local/share/codexwright/venv")).expanduser()
    python = Path(os.environ["CODEXWRIGHT_PYTHON"]) if os.environ.get("CODEXWRIGHT_PYTHON") else environment / "bin/python"
    if not python.is_file():
        print("codexwright is not installed. Run the repository's scripts/bootstrap.py first, or set CODEXWRIGHT_PYTHON to its private Python executable. The target project's environment is not used.", file=sys.stderr)
        return 4
    if len(sys.argv) != 1:
        print("Start the codexwright MCP launcher without CLI arguments.", file=sys.stderr)
        return 2
    return subprocess.call([str(python), "-m", "codexwright.mcp_server"])


if __name__ == "__main__":
    raise SystemExit(main())
