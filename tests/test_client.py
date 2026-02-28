"""Unit tests for the FormatEx Python SDK.

All tests mock the HTTP transport layer — no real API calls are made.
Run with:  pytest
Coverage:  pytest --cov=formatex --cov-report=term-missing
"""

from __future__ import annotations

import base64
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from formatex import (
    AsyncJob,
    AuthenticationError,
    CompilationError,
    CompileResult,
    ConvertResult,
    FormatExClient,
    FormatExError,
    JobResult,
    LintDiagnostic,
    LintResult,
    PlanLimitError,
    RateLimitError,
    SyntaxResult,
    UsageStats,
    file_entry,
)
from formatex.exceptions import FormatExError as _FormatExError


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    """FormatExClient with a fully-mocked HTTP layer."""
    c = FormatExClient("fx_test_key_abc")
    c._http = MagicMock()
    return c


FAKE_PDF = b"%PDF-1.4 fake-content"
FAKE_PDF_B64 = base64.b64encode(FAKE_PDF).decode()


# ── file_entry helper ─────────────────────────────────────────────────────────


class TestFileEntry:
    def test_from_bytes_encodes_base64(self):
        raw = b"\x89PNG\r\n"
        entry = file_entry("img.png", raw)
        assert entry["name"] == "img.png"
        assert entry["content"] == base64.b64encode(raw).decode()

    def test_from_path_reads_and_encodes(self, tmp_path):
        p = tmp_path / "logo.png"
        p.write_bytes(b"pngdata")
        entry = file_entry("logo.png", p)
        assert entry["content"] == base64.b64encode(b"pngdata").decode()

    def test_from_str_passthrough(self):
        already_encoded = base64.b64encode(b"data").decode()
        entry = file_entry("data.bin", already_encoded)
        assert entry["content"] == already_encoded

    def test_name_preserved_exactly(self):
        entry = file_entry("refs/main.bib", b"")
        assert entry["name"] == "refs/main.bib"


# ── LintResult dataclass ───────────────────────────────────────────────────────


class TestLintResult:
    def _make(self, diagnostics):
        return LintResult(diagnostics=diagnostics, duration_ms=10)

    def test_counts_errors_and_warnings(self):
        diags = [
            LintDiagnostic(line=1, column=1, severity="error", message="e1"),
            LintDiagnostic(line=2, column=1, severity="error", message="e2"),
            LintDiagnostic(line=3, column=1, severity="warning", message="w1"),
        ]
        result = self._make(diags)
        assert result.error_count == 2
        assert result.warning_count == 1

    def test_valid_is_true_when_no_errors(self):
        diags = [LintDiagnostic(line=1, column=1, severity="warning", message="w")]
        assert self._make(diags).valid is True

    def test_valid_is_false_when_errors_present(self):
        diags = [LintDiagnostic(line=1, column=1, severity="error", message="e")]
        assert self._make(diags).valid is False

    def test_empty_diagnostics(self):
        result = self._make([])
        assert result.error_count == 0
        assert result.warning_count == 0
        assert result.valid is True


# ── compile ───────────────────────────────────────────────────────────────────


class TestCompile:
    def test_returns_compile_result(self, client):
        client._http.post_json.return_value = {
            "pdf": FAKE_PDF_B64,
            "engine": "pdflatex",
            "duration": 312,
            "sizeBytes": len(FAKE_PDF),
            "jobId": "job-1",
            "log": "This is pdflatex...",
        }
        result = client.compile(r"\documentclass{article}\begin{document}Hi\end{document}")

        assert isinstance(result, CompileResult)
        assert result.pdf == FAKE_PDF
        assert result.engine == "pdflatex"
        assert result.duration_ms == 312
        assert result.size_bytes == len(FAKE_PDF)
        assert result.job_id == "job-1"
        assert "pdflatex" in result.log

    def test_sends_engine_and_optional_params(self, client):
        client._http.post_json.return_value = {
            "pdf": FAKE_PDF_B64, "engine": "xelatex",
            "duration": 100, "sizeBytes": 100, "jobId": "", "log": "",
        }
        files = [file_entry("img.png", b"data")]
        client.compile(r"\doc", engine="xelatex", timeout=30, runs=2, files=files)

        _, body = client._http.post_json.call_args[0]
        assert body["engine"] == "xelatex"
        assert body["timeout"] == 30
        assert body["runs"] == 2
        assert body["files"] == files

    def test_missing_optional_fields_default(self, client):
        client._http.post_json.return_value = {"pdf": FAKE_PDF_B64}
        result = client.compile(r"\doc")
        assert result.log == ""
        assert result.job_id == ""
        assert result.duration_ms == 0
        assert result.analysis is None

    def test_omits_optional_body_keys_when_none(self, client):
        client._http.post_json.return_value = {"pdf": FAKE_PDF_B64}
        client.compile(r"\doc")
        _, body = client._http.post_json.call_args[0]
        assert "timeout" not in body
        assert "runs" not in body
        assert "files" not in body


# ── compile_smart ─────────────────────────────────────────────────────────────


class TestCompileSmart:
    def test_returns_analysis(self, client):
        client._http.post_json.return_value = {
            "pdf": FAKE_PDF_B64,
            "engine": "xelatex",
            "duration": 500,
            "sizeBytes": 200,
            "jobId": "j2",
            "log": "",
            "analysis": {"detected": "xelatex", "reason": "fontspec"},
        }
        result = client.compile_smart(r"\doc")
        assert result.engine == "xelatex"
        assert result.analysis == {"detected": "xelatex", "reason": "fontspec"}

    def test_sends_engine_auto(self, client):
        client._http.post_json.return_value = {"pdf": FAKE_PDF_B64}
        client.compile_smart(r"\doc")
        _, body = client._http.post_json.call_args[0]
        assert body["engine"] == "auto"


# ── compile_to_file ───────────────────────────────────────────────────────────


class TestCompileToFile:
    def test_writes_pdf_to_path(self, client, tmp_path):
        client._http.post_json.return_value = {
            "pdf": FAKE_PDF_B64, "engine": "pdflatex",
            "duration": 100, "sizeBytes": len(FAKE_PDF), "jobId": "", "log": "",
        }
        out = tmp_path / "output.pdf"
        client.compile_to_file(r"\doc", out)
        assert out.read_bytes() == FAKE_PDF

    def test_uses_compile_smart_when_smart_true(self, client, tmp_path):
        client._http.post_json.return_value = {"pdf": FAKE_PDF_B64}
        out = tmp_path / "out.pdf"
        client.compile_to_file(r"\doc", out, smart=True)
        path, _ = client._http.post_json.call_args[0]
        assert "smart" in path


# ── async_compile ─────────────────────────────────────────────────────────────


class TestAsyncCompile:
    def test_returns_async_job(self, client):
        client._http.post_json.return_value = {"jobId": "async-1", "status": "pending"}
        job = client.async_compile(r"\doc", engine="lualatex")
        assert isinstance(job, AsyncJob)
        assert job.job_id == "async-1"
        assert job.status == "pending"

    def test_sends_correct_body(self, client):
        client._http.post_json.return_value = {"jobId": "x", "status": "pending"}
        client.async_compile(r"\doc", engine="xelatex", timeout=60, runs=3)
        _, body = client._http.post_json.call_args[0]
        assert body["engine"] == "xelatex"
        assert body["timeout"] == 60
        assert body["runs"] == 3


# ── get_job ───────────────────────────────────────────────────────────────────


class TestGetJob:
    def test_pending_status(self, client):
        client._http.get_json.return_value = {
            "id": "j1", "status": "processing", "result": None
        }
        job = client.get_job("j1")
        assert isinstance(job, JobResult)
        assert job.status == "processing"
        assert job.success is False
        assert job.log == ""

    def test_completed_status_maps_result(self, client):
        client._http.get_json.return_value = {
            "id": "j1",
            "status": "completed",
            "result": {"success": True, "log": "Done.", "duration": 450, "error": ""},
        }
        job = client.get_job("j1")
        assert job.status == "completed"
        assert job.success is True
        assert job.log == "Done."
        assert job.duration_ms == 450

    def test_calls_correct_endpoint(self, client):
        client._http.get_json.return_value = {"id": "j1", "status": "pending"}
        client.get_job("j1")
        path = client._http.get_json.call_args[0][0]
        assert path == "/api/v1/jobs/j1"


# ── get_job_pdf ───────────────────────────────────────────────────────────────


class TestGetJobPdf:
    def test_returns_bytes(self, client):
        client._http.get_bytes.return_value = FAKE_PDF
        pdf = client.get_job_pdf("j1")
        assert pdf == FAKE_PDF
        client._http.get_bytes.assert_called_once_with("/api/v1/jobs/j1/pdf")


# ── get_job_log ───────────────────────────────────────────────────────────────


class TestGetJobLog:
    def test_returns_log_string(self, client):
        client._http.get_json.return_value = {"log": "Compilation output..."}
        log = client.get_job_log("j1")
        assert log == "Compilation output..."

    def test_missing_log_defaults_to_empty(self, client):
        client._http.get_json.return_value = {}
        assert client.get_job_log("j1") == ""


# ── delete_job ────────────────────────────────────────────────────────────────


class TestDeleteJob:
    def test_calls_delete_endpoint(self, client):
        client._http.delete_json.return_value = {}
        client.delete_job("j1")
        client._http.delete_json.assert_called_once_with("/api/v1/jobs/j1")

    def test_returns_none(self, client):
        client._http.delete_json.return_value = {}
        assert client.delete_job("j1") is None


# ── wait_for_job ──────────────────────────────────────────────────────────────


class TestWaitForJob:
    def test_polls_then_returns_on_completion(self, client):
        client._http.get_json.side_effect = [
            {"id": "j1", "status": "processing", "result": None},
            {"id": "j1", "status": "completed", "result": {"log": "OK", "duration": 800}},
        ]
        client._http.get_bytes.return_value = FAKE_PDF

        with patch("formatex.client.time.sleep") as mock_sleep:
            with patch("formatex.client.time.monotonic", return_value=0.0):
                result = client.wait_for_job("j1", timeout=60.0, poll_interval=2.0)

        assert result.pdf == FAKE_PDF
        assert result.duration_ms == 800
        assert result.log == "OK"
        mock_sleep.assert_called_once_with(2.0)

    def test_raises_compilation_error_on_failure(self, client):
        client._http.get_json.return_value = {
            "id": "j1",
            "status": "failed",
            "result": {"error": "Undefined control sequence", "log": "! error log"},
        }

        with patch("formatex.client.time.sleep"):
            with patch("formatex.client.time.monotonic", return_value=0.0):
                with pytest.raises(CompilationError) as exc_info:
                    client.wait_for_job("j1")

        assert "Undefined control sequence" in str(exc_info.value)
        assert "error log" in exc_info.value.log

    def test_raises_formatex_error_on_timeout(self, client):
        client._http.get_json.return_value = {
            "id": "j1", "status": "processing", "result": None
        }
        # monotonic: first call sets deadline=10.0, second call returns 999 (expired)
        with patch("formatex.client.time.monotonic", side_effect=[0.0, 999.0]):
            with patch("formatex.client.time.sleep"):
                with pytest.raises(FormatExError, match="did not complete within 10"):
                    client.wait_for_job("j1", timeout=10.0)


# ── check_syntax ──────────────────────────────────────────────────────────────


class TestCheckSyntax:
    def test_valid_document(self, client):
        client._http.post_json.return_value = {"valid": True, "errors": [], "warnings": []}
        result = client.check_syntax(r"\documentclass{article}\begin{document}\end{document}")
        assert isinstance(result, SyntaxResult)
        assert result.valid is True
        assert result.errors == []

    def test_invalid_document(self, client):
        client._http.post_json.return_value = {
            "valid": False,
            "errors": [{"message": "Missing \\end{document}"}],
            "warnings": [],
        }
        result = client.check_syntax(r"\documentclass{article}\begin{document}")
        assert result.valid is False
        assert len(result.errors) == 1

    def test_calls_correct_endpoint(self, client):
        client._http.post_json.return_value = {"valid": True, "errors": [], "warnings": []}
        client.check_syntax(r"\doc")
        path, _ = client._http.post_json.call_args[0]
        assert path == "/api/v1/compile/check"


# ── lint ─────────────────────────────────────────────────────────────────────


class TestLint:
    def test_returns_lint_result_with_diagnostics(self, client):
        client._http.post_json.return_value = {
            "diagnostics": [
                {"line": 5, "column": 3, "severity": "warning", "message": "Command terminated", "source": "chktex", "code": "1"},
                {"line": 12, "column": 1, "severity": "error", "message": "Wrong length", "source": "chktex", "code": "8"},
            ],
            "duration": 45,
        }
        result = client.lint(r"\doc")

        assert isinstance(result, LintResult)
        assert len(result.diagnostics) == 2
        assert result.error_count == 1
        assert result.warning_count == 1
        assert result.valid is False
        assert result.duration_ms == 45

        diag = result.diagnostics[0]
        assert isinstance(diag, LintDiagnostic)
        assert diag.line == 5
        assert diag.column == 3
        assert diag.severity == "warning"
        assert diag.code == "1"

    def test_empty_diagnostics_is_valid(self, client):
        client._http.post_json.return_value = {"diagnostics": [], "duration": 10}
        result = client.lint(r"\doc")
        assert result.valid is True
        assert result.diagnostics == []

    def test_null_diagnostics_handled(self, client):
        client._http.post_json.return_value = {"diagnostics": None, "duration": 5}
        result = client.lint(r"\doc")
        assert result.diagnostics == []

    def test_calls_correct_endpoint(self, client):
        client._http.post_json.return_value = {"diagnostics": [], "duration": 5}
        client.lint(r"\doc")
        path, _ = client._http.post_json.call_args[0]
        assert path == "/api/v1/lint"


# ── convert ───────────────────────────────────────────────────────────────────


FAKE_DOCX = b"PK\x03\x04fake-docx-content"


class TestConvert:
    def test_returns_convert_result(self, client):
        client._http.post_bytes.return_value = FAKE_DOCX
        result = client.convert(r"\doc")
        assert isinstance(result, ConvertResult)
        assert result.docx == FAKE_DOCX
        assert result.size_bytes == len(FAKE_DOCX)

    def test_sends_files_when_provided(self, client):
        client._http.post_bytes.return_value = FAKE_DOCX
        files = [file_entry("img.png", b"png")]
        client.convert(r"\doc", files=files)
        _, body = client._http.post_bytes.call_args[0]
        assert body["files"] == files

    def test_omits_files_key_when_none(self, client):
        client._http.post_bytes.return_value = FAKE_DOCX
        client.convert(r"\doc")
        _, body = client._http.post_bytes.call_args[0]
        assert "files" not in body

    def test_calls_correct_endpoint(self, client):
        client._http.post_bytes.return_value = FAKE_DOCX
        client.convert(r"\doc")
        path, _ = client._http.post_bytes.call_args[0]
        assert path == "/api/v1/convert"


class TestConvertToFile:
    def test_writes_docx_to_path(self, client, tmp_path):
        client._http.post_bytes.return_value = FAKE_DOCX
        out = tmp_path / "doc.docx"
        result = client.convert_to_file(r"\doc", out)
        assert out.read_bytes() == FAKE_DOCX
        assert result.docx == FAKE_DOCX


# ── get_usage ─────────────────────────────────────────────────────────────────


class TestGetUsage:
    def test_nested_api_format(self, client):
        client._http.get_json.return_value = {
            "plan": "developer",
            "compilations": {"used": 45, "limit": 500, "overage": 0},
            "period": {"start": "2026-02-01T00:00:00Z", "end": "2026-02-28T23:59:59Z"},
        }
        usage = client.get_usage()
        assert isinstance(usage, UsageStats)
        assert usage.plan == "developer"
        assert usage.compilations_used == 45
        assert usage.compilations_limit == 500
        assert usage.period_start == "2026-02-01T00:00:00Z"
        assert usage.period_end == "2026-02-28T23:59:59Z"

    def test_legacy_flat_format(self, client):
        client._http.get_json.return_value = {
            "plan": "free",
            "compilationsUsed": 10,
            "compilationsLimit": 50,
            "periodStart": "2026-02-01",
            "periodEnd": "2026-02-28",
        }
        usage = client.get_usage()
        assert usage.compilations_used == 10
        assert usage.compilations_limit == 50
        assert usage.period_start == "2026-02-01"

    def test_raw_field_preserved(self, client):
        raw = {"plan": "pro", "compilations": {"used": 1, "limit": 2000}, "period": {}}
        client._http.get_json.return_value = raw
        usage = client.get_usage()
        assert usage.raw == raw


# ── list_engines ──────────────────────────────────────────────────────────────


class TestListEngines:
    def test_returns_engines_list(self, client):
        client._http.get_json.return_value = {
            "engines": [
                {"name": "pdflatex", "available": True},
                {"name": "xelatex", "available": True},
                {"name": "lualatex", "available": False},
            ]
        }
        engines = client.list_engines()
        assert len(engines) == 3
        assert engines[0]["name"] == "pdflatex"

    def test_empty_list_when_missing_key(self, client):
        client._http.get_json.return_value = {}
        assert client.list_engines() == []


# ── context manager ───────────────────────────────────────────────────────────


class TestContextManager:
    def test_close_called_on_exit(self):
        with FormatExClient("fx_key") as c:
            c._http = MagicMock()
        c._http.close.assert_called_once()


# ── exception hierarchy ───────────────────────────────────────────────────────


class TestExceptions:
    def test_all_exceptions_inherit_formatex_error(self):
        assert issubclass(AuthenticationError, FormatExError)
        assert issubclass(CompilationError, FormatExError)
        assert issubclass(RateLimitError, FormatExError)
        assert issubclass(PlanLimitError, FormatExError)

    def test_compilation_error_has_log(self):
        err = CompilationError("failed", log="! Undefined control sequence")
        assert err.log == "! Undefined control sequence"

    def test_rate_limit_error_has_retry_after(self):
        err = RateLimitError("too many requests", retry_after=30.5)
        assert err.retry_after == 30.5

    def test_formatex_error_status_code(self):
        err = FormatExError("oops", status_code=500)
        assert err.status_code == 500
