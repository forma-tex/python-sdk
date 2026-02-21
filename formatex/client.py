"""FormatEx Python client."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from formatex._http import HTTPClient

DEFAULT_BASE_URL = "https://api.formatex.com"


@dataclass
class CompileResult:
    """Result of a compilation request."""

    pdf: bytes
    engine: str
    duration: float
    size_bytes: int
    job_id: str
    analysis: dict | None = None  # present only for smart compile


@dataclass
class SyntaxResult:
    """Result of a syntax check."""

    valid: bool
    errors: list[dict]
    warnings: list[dict]


@dataclass
class UsageStats:
    """Monthly usage statistics."""

    plan: str
    compilations_used: int
    compilations_limit: int
    period_start: str
    period_end: str
    raw: dict


class FormatExClient:
    """High-level client for the FormatEx LaTeX-to-PDF API.

    Usage::

        from formatex import FormatExClient

        client = FormatExClient("fx_your_api_key")
        result = client.compile("\\\\documentclass{article}\\n\\\\begin{document}Hello\\\\end{document}")
        with open("out.pdf", "wb") as f:
            f.write(result.pdf)
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 120.0,
    ):
        self._http = HTTPClient(api_key=api_key, base_url=base_url, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ── Compilation ──────────────────────────────────────────────────────────

    def compile(
        self,
        latex: str,
        *,
        engine: str = "pdflatex",
        timeout: int | None = None,
        runs: int | None = None,
    ) -> CompileResult:
        """Compile LaTeX source to PDF.

        Args:
            latex: LaTeX source code.
            engine: One of pdflatex, xelatex, lualatex, latexmk.
            timeout: Max compile time in seconds (plan-limited).
            runs: Number of compiler passes (1-5).

        Returns:
            CompileResult with pdf bytes and metadata.
        """
        body: dict[str, Any] = {"latex": latex, "engine": engine}
        if timeout is not None:
            body["timeout"] = timeout
        if runs is not None:
            body["runs"] = runs

        data = self._http.post_json("/api/v1/compile", body)
        return CompileResult(
            pdf=base64.b64decode(data["pdf"]),
            engine=data.get("engine", engine),
            duration=data.get("duration", 0),
            size_bytes=data.get("sizeBytes", 0),
            job_id=data.get("jobId", ""),
        )

    def compile_smart(
        self,
        latex: str,
        *,
        timeout: int | None = None,
    ) -> CompileResult:
        """Smart compile — auto-detects engine and applies fixes.

        Args:
            latex: LaTeX source code.
            timeout: Max compile time in seconds.

        Returns:
            CompileResult with pdf bytes, metadata, and analysis dict.
        """
        body: dict[str, Any] = {"latex": latex, "engine": "auto"}
        if timeout is not None:
            body["timeout"] = timeout

        data = self._http.post_json("/api/v1/compile/smart", body)
        return CompileResult(
            pdf=base64.b64decode(data["pdf"]),
            engine=data.get("engine", "auto"),
            duration=data.get("duration", 0),
            size_bytes=data.get("sizeBytes", 0),
            job_id=data.get("jobId", ""),
            analysis=data.get("analysis"),
        )

    def compile_to_file(
        self,
        latex: str,
        output_path: str | Path,
        *,
        engine: str = "pdflatex",
        smart: bool = False,
        **kwargs,
    ) -> CompileResult:
        """Compile and save the PDF directly to a file.

        Args:
            latex: LaTeX source code.
            output_path: Path to write the PDF.
            engine: Engine to use (ignored if smart=True).
            smart: Use smart compile instead of basic.
            **kwargs: Extra args forwarded to compile/compile_smart.

        Returns:
            CompileResult (pdf bytes are also written to output_path).
        """
        if smart:
            result = self.compile_smart(latex, **kwargs)
        else:
            result = self.compile(latex, engine=engine, **kwargs)

        Path(output_path).write_bytes(result.pdf)
        return result

    # ── Syntax Check ─────────────────────────────────────────────────────────

    def check_syntax(self, latex: str) -> SyntaxResult:
        """Validate LaTeX syntax without compiling (free, no quota cost).

        Args:
            latex: LaTeX source code.

        Returns:
            SyntaxResult with valid flag and error/warning lists.
        """
        data = self._http.post_json("/api/v1/compile/check", {"latex": latex})
        return SyntaxResult(
            valid=data.get("valid", False),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

    # ── Usage ────────────────────────────────────────────────────────────────

    def get_usage(self) -> UsageStats:
        """Get current month's compilation usage.

        Returns:
            UsageStats with plan info and compilation counts.
        """
        data = self._http.get_json("/api/v1/usage")
        return UsageStats(
            plan=data.get("plan", ""),
            compilations_used=data.get("compilationsUsed", 0),
            compilations_limit=data.get("compilationsLimit", 0),
            period_start=data.get("periodStart", ""),
            period_end=data.get("periodEnd", ""),
            raw=data,
        )

    # ── Engines ──────────────────────────────────────────────────────────────

    def list_engines(self) -> list[dict]:
        """List available compilation engines.

        Returns:
            List of engine info dicts.
        """
        data = self._http.get_json("/api/v1/engines")
        return data.get("engines", [])
