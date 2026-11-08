"""Redact machine details in public evidence without changing observed outcomes."""

import argparse
import hashlib
import json
import re
from pathlib import Path


def redact(value):
    if isinstance(value, dict):
        return {redact(key): "<runtime PATH omitted>" if key == "PATH" else redact(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        embedded = json.loads(value)
        if isinstance(embedded, (dict, list)):
            return json.dumps(redact(embedded), ensure_ascii=False) + ("\n" if value.endswith("\n") else "")
    except ValueError:
        pass
    value = re.sub(r"/(?:private/)?var/folders/[^/\s]+/[^/\s]+/T(?=/|\b)", "<temp-root>", value)
    value = re.sub(r"/(?:Users|home)/[^/\s\"'<>\\]+", "<user-home>", value)
    return value.replace("/opt/homebrew", "<package-prefix>").replace("/Applications/ChatGPT.app", "<host-app>")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path(__file__).resolve().parents[1] / "docs/acceptance-evidence")
    args = parser.parse_args()
    for path in sorted(args.directory.glob("*.json")):
        if path.name != "manifest.json":
            path.write_text(json.dumps(redact(json.loads(path.read_text())), ensure_ascii=False, indent=2) + "\n")
    manifest_path = args.directory / "manifest.json"
    if manifest_path.is_file():
        manifest = redact(json.loads(manifest_path.read_text()))
        manifest["public_redaction"] = "Machine home/temp/package paths use placeholders; full PATH values omitted. Observed outcomes remain unchanged."
        manifest["evidence_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.directory.glob("*.json")) if path.name != "manifest.json"}
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
