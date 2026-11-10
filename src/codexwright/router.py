"""Intent is model-proposed; mutation policy is deterministic and host-owned."""

from .errors import CodexwrightError

READ_OPERATIONS = {"analyze", "review", "explain", "diagnose"}
CHANGE_OPERATIONS = {"build", "edit", "migrate", "refactor"}


def resolve_operation(requested, proposed, source_runtime, allowed):
    effective = proposed if requested == "auto" else requested
    if effective == "auto":
        raise CodexwrightError("invalid_route", "Architect must choose a concrete operation")
    if requested in READ_OPERATIONS and effective not in READ_OPERATIONS:
        raise CodexwrightError("permission_denied", "Read-only requests cannot become construction")
    if source_runtime == "unknown" and effective in CHANGE_OPERATIONS:
        raise CodexwrightError("source_runtime_unknown", "Source runtime is not yet evidenced; inspect before migration")
    if source_runtime == "other" and effective in CHANGE_OPERATIONS:
        effective = "migrate"
    if source_runtime == "codex_sdk" and effective == "migrate":
        effective = "edit"
    if allowed and effective not in allowed:
        raise CodexwrightError("permission_denied", "Operation is outside caller's allowed operations")
    return effective
