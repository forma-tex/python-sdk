"""FormaTex exception hierarchy."""


class FormaTexError(Exception):
    """Base exception for all FormaTex errors."""

    def __init__(self, message: str, status_code: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class AuthenticationError(FormaTexError):
    """Invalid or missing API key (401)."""


class CompilationError(FormaTexError):
    """LaTeX compilation failed (422). Contains `log` attribute with compiler output."""

    def __init__(self, message: str, log: str = "", **kwargs):
        super().__init__(message, **kwargs)
        self.log = log


class RateLimitError(FormaTexError):
    """Too many requests (429). Contains `retry_after` in seconds."""

    def __init__(self, message: str, retry_after: float = 0, **kwargs):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class PlanLimitError(FormaTexError):
    """Plan limit exceeded (403/429). Upgrade required."""
