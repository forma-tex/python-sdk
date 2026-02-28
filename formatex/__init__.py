"""FormaTex Python SDK — compile LaTeX to PDF."""

from formatex.client import (
    FormaTexClient,
    AsyncJob,
    CompileResult,
    ConvertResult,
    JobResult,
    LintDiagnostic,
    LintResult,
    SyntaxResult,
    UsageStats,
    file_entry,
)
from formatex.exceptions import (
    FormaTexError,
    AuthenticationError,
    CompilationError,
    RateLimitError,
    PlanLimitError,
)

__all__ = [
    # Client
    "FormaTexClient",
    "file_entry",
    # Result types
    "AsyncJob",
    "CompileResult",
    "ConvertResult",
    "JobResult",
    "LintDiagnostic",
    "LintResult",
    "SyntaxResult",
    "UsageStats",
    # Exceptions
    "FormaTexError",
    "AuthenticationError",
    "CompilationError",
    "RateLimitError",
    "PlanLimitError",
]
