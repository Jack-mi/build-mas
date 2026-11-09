#!/usr/bin/env python3
"""Start the privately installed builder without depending on a shell's PATH."""

import os
import subprocess
import sys
from pathlib import Path


def main():
    environment = Path(os.environ.get("BUILD_MAS_ENV", Path.home() / ".local/share/build-mas/venv")).expanduser()
    python = Path(os.environ["BUILD_MAS_PYTHON"]) if os.environ.get("BUILD_MAS_PYTHON") else environment / "bin/python"
    if not python.is_file():
        print("build-mas is not installed. Run the repository's scripts/bootstrap.py first, or set BUILD_MAS_PYTHON to its private Python executable. The target project's environment is not used.", file=sys.stderr)
        return 4
    if len(sys.argv) != 1:
        print("Start the build-mas MCP launcher without CLI arguments.", file=sys.stderr)
        return 2
    return subprocess.call([str(python), "-m", "build_mas.mcp_server"])


if __name__ == "__main__":
    raise SystemExit(main())
