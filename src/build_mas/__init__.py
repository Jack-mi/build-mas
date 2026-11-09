"""Agentic workflow architecture and construction through the Codex Python SDK."""

__version__ = "0.4.0"


def service(*args, **kwargs):
    from .service import BuildService

    return BuildService(*args, **kwargs)
