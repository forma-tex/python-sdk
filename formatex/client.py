"""FormatEx Python client."""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from formatex._http import HTTPClient
from formatex.exceptions import FormatExError

DEFAULT_BASE_URL = "https://api.formatex.com"

# ── Data classes ──────────────────────────────────────────────────────────────


@dataclass
class CompileResult:
    """Result of a synchronous compilation request."""

    pdf: bytes
    engine: str
    duration_ms: int
    size_bytes: int
    job_id: str
    log: str = ""
    analysis: dict | None = None  # present only for smart compile


@dataclass
class AsyncJob:
    """Reference to an async compilation job (returned immediately on submit)."""

    job_id: str
    status: str  # pending | processing | completed | failed


@dataclass
class JobResult:
    """Full status of a polled async job."""

    job_id: str
    status: str       # pending | processing | completed | failed
    log: str = ""
    duration_ms: int = 0
    error: str = ""
    success: bool = False


@dataclass
class LintDiagnostic:
    """A single lint issue reported by ChkTeX."""

    line: int
    column: int
    severity: str     # error | warning | info
    message: str
    source: str = "chktex"
    code: str = ""


@dataclass
class LintResult:
    """Result of a lint operation."""

    diagnostics: list[LintDiagnostic]
    duration_ms: int
    error_count: int = field(init=False)
    warning_count: int = field(init=False)

    def __post_init__(self) -> None:
        self.error_count = sum(1 for d in self.diagnostics if d.severity == "error")
        self.warning_count = sum(1 for d in self.diagnostics if d.severity == "warning")

    @property
    def valid(self) -> bool:
        return self.error_count == 0


@dataclass
class SyntaxResult:
    """Result of a fast syntax check (no quota cost)."""

    valid: bool
    errors: list[dict]
    warnings: list[dict]


@dataclass
class ConvertResult:
    """Result of a LaTeX → DOCX conversion."""

    docx: bytes
    size_bytes: int


@dataclass
class UsageStats:
    """Monthly usage statistics."""

    plan: str
    compilations_used: int
    compilations_limit: int
    period_start: str
    period_end: str
    raw: dict


# ── Helper ────────────────────────────────────────────────────────────────────


def file_entry(name: str, content: bytes | str | Path) -> dict:
    """Build a companion-file entry for multi-file compilation.

    Args:
        name: Filename as it appears in the LaTeX source (e.g. ``"fig.png"``).
        content: Raw bytes, a file path, or an already-encoded base64 string.

    Returns:
        ``{"name": name, "content": "<base64>"}`` dict for the ``files`` list.

    Example::

        result = client.compile(
            latex,
            files=[
                file_entry("logo.png", Path("assets/logo.png")),
                file_entry("refs.bib", open("refs.bib", "rb").read()),
            ],
        )
    """
    if isinstance(content, Path):
        content = content.read_bytes()
    if isinstance(content, bytes):
        content = base64.b64encode(content).decode()
    return {"name": name, "content": content}


# ── Client ────────────────────────────────────────────────────────────────────


class FormatExClient:
    """High-level client for the FormatEx LaTeX-to-PDF API.

    Initialise with an API key obtained from the dashboard::

        from formatex import FormatExClient

        client = FormatExClient("fx_your_api_key")

    Use as a context manager to ensure the underlying HTTP connection is closed::

        with FormatExClient("fx_your_api_key") as client:
            result = client.compile(r"\\documentclass{article}...")
            Path("out.pdf").write_bytes(result.pdf)
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
        """Close the underlying HTTP connection pool."""
        self._http.close()

    def __enter__(self) -> "FormatExClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ── Sync Compilation ──────────────────────────────────────────────────────

    def compile(
        self,
        latex: str,
        *,
        engine: str = "pdflatex",
        timeout: int | None = None,
        runs: int | None = None,
        files: list[dict] | None = None,
    ) -> CompileResult:
        """Compile LaTeX source to PDF synchronously.

        Blocks until the PDF is ready (or raises on error).
        For large documents use :meth:`async_compile` + :meth:`wait_for_job`.

        Args:
            latex: LaTeX source code.
            engine: ``pdflatex`` (default), ``xelatex``, ``lualatex``, or ``latexmk``.
            timeout: Max compile time in seconds (plan-limited).
            runs: Number of compiler passes (1–5).
            files: Companion files (images, .bib, etc.) — use :func:`file_entry`
                   to build entries.

        Returns:
            :class:`CompileResult` with ``.pdf`` bytes and metadata.

        Raises:
            :class:`~formatex.CompilationError`: LaTeX errors in source.
            :class:`~formatex.PlanLimitError`: Monthly quota or plan restriction.
            :class:`~formatex.AuthenticationError`: Invalid API key.
        """
        body: dict[str, Any] = {"latex": latex, "engine": engine}
        if timeout is not None:
            body["timeout"] = timeout
        if runs is not None:
            body["runs"] = runs
        if files:
            body["files"] = files

        data = self._http.post_json("/api/v1/compile", body)
        return CompileResult(
            pdf=base64.b64decode(data["pdf"]),
            engine=data.get("engine", engine),
            duration_ms=data.get("duration", 0),
            size_bytes=data.get("sizeBytes", 0),
            job_id=data.get("jobId", ""),
            log=data.get("log", ""),
        )

    def compile_smart(
        self,
        latex: str,
        *,
        timeout: int | None = None,
        files: list[dict] | None = None,
    ) -> CompileResult:
        """Smart compile — auto-detects the required engine from the preamble.

        Inspects ``\\usepackage`` declarations to pick the best engine
        automatically (e.g. ``fontspec`` → xelatex, ``luacode`` → lualatex).

        Args:
            latex: LaTeX source code.
            timeout: Max compile time in seconds.
            files: Companion files — use :func:`file_entry`.

        Returns:
            :class:`CompileResult` with ``.analysis`` dict describing detected engine.
        """
        body: dict[str, Any] = {"latex": latex, "engine": "auto"}
        if timeout is not None:
            body["timeout"] = timeout
        if files:
            body["files"] = files

        data = self._http.post_json("/api/v1/compile/smart", body)
        return CompileResult(
            pdf=base64.b64decode(data["pdf"]),
            engine=data.get("engine", "auto"),
            duration_ms=data.get("duration", 0),
            size_bytes=data.get("sizeBytes", 0),
            job_id=data.get("jobId", ""),
            log=data.get("log", ""),
            analysis=data.get("analysis"),
        )

    def compile_to_file(
        self,
        latex: str,
        output_path: str | Path,
        *,
        engine: str = "pdflatex",
        smart: bool = False,
        **kwargs: Any,
    ) -> CompileResult:
        """Compile and write the PDF directly to a file.

        Args:
            latex: LaTeX source code.
            output_path: Destination path for the PDF (created/overwritten).
            engine: Engine to use (ignored when ``smart=True``).
            smart: Use :meth:`compile_smart` instead of :meth:`compile`.
            **kwargs: Forwarded to the underlying compile call.

        Returns:
            :class:`CompileResult` (same as compile).
        """
        result = self.compile_smart(latex, **kwargs) if smart else self.compile(latex, engine=engine, **kwargs)
        Path(output_path).write_bytes(result.pdf)
        return result

    # ── Async Compilation ─────────────────────────────────────────────────────

    def async_compile(
        self,
        latex: str,
        *,
        engine: str = "pdflatex",
        timeout: int | None = None,
        runs: int | None = None,
        files: list[dict] | None = None,
    ) -> AsyncJob:
        """Submit a compilation job to the background queue.

        Returns immediately with a job ID. Poll :meth:`get_job` to check
        progress, or use :meth:`wait_for_job` to block until done.

        Pro/max/entreprise plans get priority queue access.

        Args:
            latex: LaTeX source code.
            engine: Compilation engine.
            timeout: Max compile time in seconds.
            runs: Number of compiler passes.
            files: Companion files — use :func:`file_entry`.

        Returns:
            :class:`AsyncJob` with ``job_id`` and initial ``status="pending"``.
        """
        body: dict[str, Any] = {"latex": latex, "engine": engine}
        if timeout is not None:
            body["timeout"] = timeout
        if runs is not None:
            body["runs"] = runs
        if files:
            body["files"] = files

        data = self._http.post_json("/api/v1/compile/async", body)
        return AsyncJob(job_id=data["jobId"], status=data.get("status", "pending"))

    def get_job(self, job_id: str) -> JobResult:
        """Poll the status of an async compilation job.

        Args:
            job_id: ID returned by :meth:`async_compile`.

        Returns:
            :class:`JobResult` with current ``status``.
            When ``status == "completed"``, call :meth:`get_job_pdf` to
            download the PDF (it is deleted from the server after download).

        Raises:
            :class:`~formatex.FormatExError`: Job not found (expired or never existed).
        """
        data = self._http.get_json(f"/api/v1/jobs/{job_id}")
        result = data.get("result") or {}
        return JobResult(
            job_id=data.get("id", job_id),
            status=data.get("status", "unknown"),
            log=result.get("log", ""),
            duration_ms=result.get("duration", 0),
            error=result.get("error", ""),
            success=result.get("success", False),
        )

    def get_job_pdf(self, job_id: str) -> bytes:
        """Download the PDF for a completed async job.

        The PDF is **deleted from the server immediately after this call**
        (one-time download). Save the bytes before calling again.

        Args:
            job_id: ID of a job with ``status == "completed"``.

        Returns:
            Raw PDF bytes.
        """
        return self._http.get_bytes(f"/api/v1/jobs/{job_id}/pdf")

    def get_job_log(self, job_id: str) -> str:
        """Fetch the compiler log for an async job (available after completion).

        Args:
            job_id: Job ID.

        Returns:
            Compiler log as plain text.
        """
        data = self._http.get_json(f"/api/v1/jobs/{job_id}/log")
        return data.get("log", "")

    def delete_job(self, job_id: str) -> None:
        """Delete a job and its associated files from the server.

        Useful to free storage early; jobs are auto-deleted after download
        or after a TTL window regardless.

        Args:
            job_id: Job ID to delete.
        """
        self._http.delete_json(f"/api/v1/jobs/{job_id}")

    def wait_for_job(
        self,
        job_id: str,
        *,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> CompileResult:
        """Block until an async job completes and return the result.

        Polls :meth:`get_job` every ``poll_interval`` seconds. Downloads the PDF
        automatically when the job reaches ``completed``.

        Args:
            job_id: ID returned by :meth:`async_compile`.
            poll_interval: Seconds between status checks (default 2).
            timeout: Maximum total wait time in seconds (default 300).

        Returns:
            :class:`CompileResult` with the compiled PDF bytes.

        Raises:
            :class:`~formatex.CompilationError`: If the job failed.
            :class:`~formatex.FormatExError`: If the timeout is exceeded.
        """
        from formatex.exceptions import CompilationError

        deadline = time.monotonic() + timeout

        while True:
            job = self.get_job(job_id)

            if job.status == "completed":
                pdf = self.get_job_pdf(job_id)
                return CompileResult(
                    pdf=pdf,
                    engine="",
                    duration_ms=job.duration_ms,
                    size_bytes=len(pdf),
                    job_id=job_id,
                    log=job.log,
                )

            if job.status == "failed":
                raise CompilationError(
                    job.error or "compilation failed",
                    log=job.log,
                    status_code=422,
                    body={"log": job.log, "error": job.error},
                )

            if time.monotonic() >= deadline:
                raise FormatExError(
                    f"job {job_id} did not complete within {timeout}s (status: {job.status})",
                    status_code=None,
                )

            time.sleep(poll_interval)

    # ── Syntax Check ─────────────────────────────────────────────────────────

    def check_syntax(self, latex: str) -> SyntaxResult:
        """Validate LaTeX syntax without compiling (free, no quota cost).

        Uses a fast parser pass — does not invoke TeX.

        Args:
            latex: LaTeX source code.

        Returns:
            :class:`SyntaxResult` with ``valid`` flag and ``errors``/``warnings`` lists.
        """
        data = self._http.post_json("/api/v1/compile/check", {"latex": latex})
        return SyntaxResult(
            valid=data.get("valid", False),
            errors=data.get("errors", []),
            warnings=data.get("warnings", []),
        )

    # ── Lint ─────────────────────────────────────────────────────────────────

    def lint(self, latex: str) -> LintResult:
        """Run ChkTeX static analysis on LaTeX source.

        Returns structured diagnostics with line numbers, severity levels,
        and ChkTeX error codes. Useful for editor integrations and CI pipelines.

        Does **not** count against your monthly compilation quota.

        Args:
            latex: LaTeX source code.

        Returns:
            :class:`LintResult` with per-diagnostic details and aggregate counts.

        Example::

            result = client.lint(latex)
            for d in result.diagnostics:
                print(f"  Line {d.line}: [{d.severity}] {d.message}")
            if not result.valid:
                print(f"{result.error_count} error(s) found")
        """
        data = self._http.post_json("/api/v1/lint", {"latex": latex})
        diagnostics = [
            LintDiagnostic(
                line=d.get("line", 0),
                column=d.get("column", 0),
                severity=d.get("severity", "warning"),
                message=d.get("message", ""),
                source=d.get("source", "chktex"),
                code=d.get("code", ""),
            )
            for d in (data.get("diagnostics") or [])
        ]
        return LintResult(
            diagnostics=diagnostics,
            duration_ms=data.get("duration", 0),
        )

    # ── Convert ──────────────────────────────────────────────────────────────

    def convert(
        self,
        latex: str,
        *,
        files: list[dict] | None = None,
    ) -> ConvertResult:
        """Convert LaTeX source to a Word document (DOCX) via pandoc.

        Math is converted to native OOXML equations (Word's equation editor).
        Section structure, tables, and images are preserved.

        Counts against your monthly compilation quota (engine logged as ``pandoc``).

        Args:
            latex: LaTeX source code.
            files: Companion files (images, .bib) — use :func:`file_entry`.

        Returns:
            :class:`ConvertResult` with raw ``.docx`` bytes.

        Example::

            result = client.convert(latex)
            Path("document.docx").write_bytes(result.docx)
        """
        body: dict[str, Any] = {"latex": latex}
        if files:
            body["files"] = files
        docx = self._http.post_bytes("/api/v1/convert", body)
        return ConvertResult(docx=docx, size_bytes=len(docx))

    def convert_to_file(
        self,
        latex: str,
        output_path: str | Path,
        *,
        files: list[dict] | None = None,
    ) -> ConvertResult:
        """Convert LaTeX to DOCX and write directly to a file.

        Args:
            latex: LaTeX source code.
            output_path: Destination path for the ``.docx`` file.
            files: Companion files — use :func:`file_entry`.

        Returns:
            :class:`ConvertResult`.
        """
        result = self.convert(latex, files=files)
        Path(output_path).write_bytes(result.docx)
        return result

    # ── Usage ────────────────────────────────────────────────────────────────

    def get_usage(self) -> UsageStats:
        """Get current month's compilation usage for this API key.

        Returns:
            :class:`UsageStats` with plan info and compilation counts.
        """
        data = self._http.get_json("/api/v1/usage")
        comp = data.get("compilations", {})
        period = data.get("period", {})
        return UsageStats(
            plan=data.get("plan", ""),
            compilations_used=comp.get("used", data.get("compilationsUsed", 0)),
            compilations_limit=comp.get("limit", data.get("compilationsLimit", 0)),
            period_start=period.get("start", data.get("periodStart", "")),
            period_end=period.get("end", data.get("periodEnd", "")),
            raw=data,
        )

    # ── Engines ──────────────────────────────────────────────────────────────

    def list_engines(self) -> list[dict]:
        """List available compilation engines and their status.

        Returns:
            List of engine info dicts (name, available, version, etc.).
        """
        data = self._http.get_json("/api/v1/engines")
        return data.get("engines", [])

