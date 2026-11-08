"""Structured operation failures shared by every harness."""


class BuildMasError(Exception):
    def __init__(self, code, message, *, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def as_dict(self):
        from .workspace import has_secret

        def safe(value):
            if isinstance(value, str):
                return "[REDACTED: secret-like diagnostic]" if has_secret(value) else value
            if isinstance(value, dict):
                return {key: safe(item) for key, item in value.items()}
            if isinstance(value, list):
                return [safe(item) for item in value]
            return value

        return safe({"code": self.code, "message": self.message, "details": self.details})
