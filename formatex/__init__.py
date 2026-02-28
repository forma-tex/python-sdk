"""FormaTex Python SDK — compile LaTeX to PDF."""

from FormaTex.client import (
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
from FormaTex.exceptions import (
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
