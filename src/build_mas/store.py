"""Private, atomic run records and inter-process workspace ownership."""

import hashlib
import json
import os
import secrets
import time
from contextlib import contextmanager
from pathlib import Path

from .errors import BuildMasError


def identifier(prefix):
    return f"{prefix}_{secrets.token_hex(12)}"


def digest(value):
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Store:
    def __init__(self, home=None):
        requested = Path(home or os.environ.get("BUILD_MAS_HOME", Path.home() / ".local/share/build-mas")).expanduser()
        if requested.is_symlink():
            raise BuildMasError("unsafe_state_path", "State directory must not be a symlink")
        self.home = requested.resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.home.is_symlink():
            raise BuildMasError("unsafe_state_path", "State directory must not be a symlink")
        os.chmod(self.home, 0o700)
        self._locks = {}

    def path(self, category, name):
        import re

        if not re.fullmatch(r"[a-z_]+", category) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,159}", name):
            raise BuildMasError("invalid_reference", "Invalid state reference")
        path = self.home / category / f"{name}.json"
        if path.is_symlink() or path.parent.is_symlink():
            raise BuildMasError("unsafe_state_path", "State files must not be symlinks")
        return path

    def read(self, category, name):
        path = self.path(category, name)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise BuildMasError("not_found", f"Unknown {category} reference: {name}") from exc
        except (ValueError, OSError) as exc:
            raise BuildMasError("state_corrupt", f"Cannot read {category} record") from exc

    def write(self, category, name, value):
        from .workspace import has_secret

        if has_secret(json.dumps(value, ensure_ascii=False)):
            raise BuildMasError("secret_detected", "Secret-like state was rejected before persistence")
        atomic_json(self.path(category, name), value)
        return value

    def event(self, run_id, kind, **fields):
        directory = self.home / "events"
        directory.mkdir(exist_ok=True, mode=0o700)
        self.path("runs", run_id)
        path = directory / f"{run_id}.jsonl"
        if path.is_symlink():
            raise BuildMasError("unsafe_state_path", "Event log must not be a symlink")
        payload = {"at": time.time(), "event": kind, **fields}
        descriptor = os.open(path, os.O_APPEND | os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def mark_owner(self, scope, run_id):
        stream = self._locks.get(scope)
        if stream is not None:
            stream.seek(0)
            stream.truncate()
            json.dump({"run_id": run_id}, stream)
            stream.flush()
            os.fsync(stream.fileno())

    def owner(self, scope):
        import fcntl

        path = self.path("locks", scope)
        if not path.exists():
            return None
        with path.open("r+") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                try:
                    return json.load(stream).get("run_id")
                except ValueError:
                    return None
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        return None

    @contextmanager
    def lock(self, scope):
        import fcntl

        path = self.path("locks", scope)
        path.parent.mkdir(exist_ok=True, mode=0o700)
        with path.open("a+") as stream:
            os.chmod(path, 0o600)
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BuildMasError("workspace_locked", "Another operation owns this workspace or session") from exc
            self._locks[scope] = stream
            try:
                yield
            finally:
                self._locks.pop(scope, None)
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
