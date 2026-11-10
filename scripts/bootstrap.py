"""Install a private codexwright environment without changing the target project."""

import argparse
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path, default=Path.home() / ".local/share/codexwright/venv")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    environment = args.environment.expanduser().resolve()
    source = args.source.expanduser().resolve(strict=True)
    if not (source / "pyproject.toml").is_file():
        parser.error("Use the codexwright repository or a prepared distribution directory")
    uv = shutil.which("uv")
    if not environment.exists():
        if uv:
            subprocess.run([uv, "venv", "--python", sys.executable, str(environment)], check=True)
        else:
            venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    command = [uv, "pip", "install", "--python", str(python), str(source)] if uv else [str(python), "-m", "pip", "install", str(source)]
    subprocess.run(command, check=True)
    print(f"Builder installed: {environment}")
    print(f"MCP command: {python} -m codexwright.mcp_server")
    print("Set CODEXWRIGHT_ALLOW_APPLY=1 in the MCP server environment to expose human-approved application.")
    print("Use the printed absolute command in each host's MCP configuration. The target venv is untouched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
