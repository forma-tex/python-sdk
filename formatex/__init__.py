"""FormatEx Python SDK — compile LaTeX to PDF."""

from formatex.client import (
    FormatExClient,
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
    FormatExError,
    AuthenticationError,
    CompilationError,
    RateLimitError,
    PlanLimitError,
)

__all__ = [
    # Client
    "FormatExClient",
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
    "FormatExError",
    "AuthenticationError",
    "CompilationError",
    "RateLimitError",
    "PlanLimitError",
]
