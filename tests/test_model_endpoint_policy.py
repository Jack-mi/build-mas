import json
import socket

import pytest

from build_mas.errors import BuildMasError
from build_mas.runtime import verification_auth, verification_environment


def test_remote_model_network_is_pinned_to_public_numeric_endpoints(tmp_path, monkeypatch):
    source = tmp_path / "codex"; source.mkdir()
    (source / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nname="Chosen"\nbase_url="https://model.example/v1"\n')
    monkeypatch.setenv("CODEX_HOME", str(source))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))])
    _, pins = verification_auth(tmp_path / "state")
    assert pins == [{"host": "model.example", "port": 443, "addresses": ["93.184.216.34"]}]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 443))])
    with pytest.raises(Exception, match="private address"):
        verification_auth(tmp_path / "state")


def test_loopback_endpoint_is_explicit_and_public_http_is_refused(tmp_path, monkeypatch):
    source = tmp_path / "codex"; source.mkdir()
    (source / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nname="Chosen"\nbase_url="http://127.0.0.1:4321/v1"\n')
    monkeypatch.setenv("CODEX_HOME", str(source))
    _, pins = verification_auth(tmp_path / "state")
    assert pins == [4321]
    (source / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nname="Chosen"\nbase_url="http://model.example/v1"\n')
    with pytest.raises(Exception, match="require HTTPS"):
        verification_auth(tmp_path / "state")


def test_verification_passes_only_declared_model_credentials(tmp_path, monkeypatch):
    (tmp_path / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nenv_key="MODEL_KEY"\nenv_http_headers={"X-Project"="MODEL_PROJECT"}\n')
    monkeypatch.setenv("MODEL_KEY", "credential-fixture")
    monkeypatch.setenv("MODEL_PROJECT", "project-fixture")
    monkeypatch.setenv("UNRELATED_SECRET", "never-inherit")
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    assert verification_environment(tmp_path) == {"MODEL_KEY": "credential-fixture", "MODEL_PROJECT": "project-fixture"}
    (tmp_path / "config.toml").write_text('model_provider="chosen"\n[model_providers.chosen]\nenv_key="PYTHONPATH"\n')
    with pytest.raises(BuildMasError, match="cannot override"):
        verification_environment(tmp_path)
