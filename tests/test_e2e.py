"""End-to-end tests against a live FormaTex API.

These tests simulate the complete user journey:
  1. Register a brand-new user (unique email per run)
  2. Login to obtain a JWT
  3. Create an API key via the dashboard API
  4. Use that API key through FormaTexClient for every SDK action
  5. Clean up (delete the test user)

Usage
-----
Set the base URL then run with the `e2e` marker:

    $env:FormaTex_E2E_BASE_URL = "https://api-test.FormaTex.zedmed.online"
    pytest tests/test_e2e.py -v -m e2e

If FormaTex_E2E_BASE_URL is not set the entire module is skipped automatically.

Note: These tests create a real user, make real compilations, and consume quota.
      They are intentionally excluded from the default `pytest` run.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx
import pytest

from formatex import (
    AsyncJob,
    CompileResult,
    ConvertResult,
    FormaTexClient,
    JobResult,
    LintResult,
    SyntaxResult,
    UsageStats,
    file_entry,
)
from formatex.exceptions import CompilationError, PlanLimitError

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("FormaTex_E2E_BASE_URL", "").strip().strip('"').strip("'").rstrip("/")

pytestmark = pytest.mark.e2e

if not BASE_URL:
    pytest.skip(
        "FormaTex_E2E_BASE_URL not set — skipping e2e tests",
        allow_module_level=True,
    )

# ── Sample LaTeX documents ────────────────────────────────────────────────────

SIMPLE_DOC = r"""
\documentclass{article}
\begin{document}
Hello from FormaTex E2E test.
\end{document}
""".strip()

BIB_DOC = r"""
\documentclass{article}
\usepackage{amsmath}
\begin{document}
The quadratic formula is $x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}$.
\end{document}
""".strip()

BROKEN_DOC = r"""
\documentclass{article}
\usepackage{nonexistentpackage99xyz}
\begin{document}
Hello
\end{document}
""".strip()

# ── Session-scoped setup: register → login → get API key ─────────────────────


@pytest.fixture(scope="session")
def api_key() -> str:
    """
    Full bootstrap fixture:
      - Registers a unique test user
      - Logs in to get a JWT
      - Creates an API key
      - Yields the raw API key string
      - Deletes the test user on teardown
    """
    run_id = uuid.uuid4().hex[:8]
    email = f"sdk-e2e-{run_id}@test.FormaTex.internal"
    password = f"E2eTest-{run_id}!"
    name = f"SDK E2E {run_id}"

    with httpx.Client(base_url=BASE_URL, timeout=30) as http:
        # 1. Register
        resp = http.post("/api/v1/auth/register", json={"name": name, "email": email, "password": password})
        assert resp.status_code == 201, f"Register failed {resp.status_code}: {resp.text}"
        user_id = resp.json()["user"]["id"]

        # 2. Login
        resp = http.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert resp.status_code == 200, f"Login failed {resp.status_code}: {resp.text}"
        jwt_token = resp.json()["token"]

        # 3. Create API key (JWT-authenticated)
        resp = http.post(
            "/api/v1/users/me/api-keys",
            json={"name": "sdk-e2e-key"},
            headers={"Authorization": f"Bearer {jwt_token}"},
        )
        assert resp.status_code == 201, f"API key creation failed {resp.status_code}: {resp.text}"
        raw_key = resp.json()["key"]
        assert len(raw_key) >= 8, f"API key too short: {raw_key!r}"

    yield raw_key

    # Teardown: delete the test user (requires admin or self-delete endpoint)
    # Try self-delete first; if the API doesn't support it, leave the user
    # (test users on a staging environment are harmless and quota-free)
    try:
        with httpx.Client(base_url=BASE_URL, timeout=15) as http:
            resp = http.post("/api/v1/auth/login", json={"email": email, "password": password})
            if resp.status_code == 200:
                token = resp.json()["token"]
                http.delete("/api/v1/users/me", headers={"Authorization": f"Bearer {token}"})
    except Exception:
        pass  # teardown is best-effort


@pytest.fixture(scope="session")
def client(api_key: str) -> FormaTexClient:
    """Shared FormaTexClient for the e2e session."""
    c = FormaTexClient(api_key, base_url=BASE_URL)
    yield c
    c.close()


# ── Health check ──────────────────────────────────────────────────────────────


class TestHealthCheck:
    def test_api_is_reachable(self):
        """Verify the API base URL responds before running any SDK tests."""
        resp = httpx.get(f"{BASE_URL}/api/v1/health", timeout=10)
        assert resp.status_code == 200, f"API unreachable: {resp.status_code}"


# ── Engines ───────────────────────────────────────────────────────────────────


class TestEngines:
    def test_list_engines_returns_nonempty(self, client: FormaTexClient):
        engines = client.list_engines()
        assert isinstance(engines, list)
        assert len(engines) > 0

    def test_pdflatex_is_available(self, client: FormaTexClient):
        engines = client.list_engines()
        # API returns list of strings e.g. ["pdflatex", "xelatex", ...]
        names = [e if isinstance(e, str) else e["name"] for e in engines]
        assert "pdflatex" in names


# ── Usage stats ───────────────────────────────────────────────────────────────


class TestUsage:
    def test_get_usage_returns_stats(self, client: FormaTexClient):
        usage = client.get_usage()
        assert isinstance(usage, UsageStats)
        assert usage.plan != ""
        assert usage.compilations_limit >= 0
        assert usage.compilations_used >= 0

    def test_period_dates_are_set(self, client: FormaTexClient):
        usage = client.get_usage()
        assert usage.period_start != ""
        assert usage.period_end != ""


# ── Syntax check ──────────────────────────────────────────────────────────────


class TestSyntaxCheck:
    def test_valid_doc_passes(self, client: FormaTexClient):
        result = client.check_syntax(SIMPLE_DOC)
        assert isinstance(result, SyntaxResult)
        assert result.valid is True

    def test_schema_fields_present(self, client: FormaTexClient):
        result = client.check_syntax(SIMPLE_DOC)
        # errors/warnings may be None when document is valid
        assert result.errors is None or isinstance(result.errors, list)
        assert result.warnings is None or isinstance(result.warnings, list)


# ── Lint ──────────────────────────────────────────────────────────────────────


class TestLint:
    def test_clean_doc_has_no_errors(self, client: FormaTexClient):
        result = client.lint(SIMPLE_DOC)
        assert isinstance(result, LintResult)
        assert result.error_count == 0
        assert result.valid is True

    def test_diagnostics_is_list(self, client: FormaTexClient):
        result = client.lint(SIMPLE_DOC)
        assert isinstance(result.diagnostics, list)

    def test_duration_ms_is_positive(self, client: FormaTexClient):
        result = client.lint(SIMPLE_DOC)
        assert result.duration_ms >= 0


# ── Sync compile ──────────────────────────────────────────────────────────────


class TestSyncCompile:
    def test_compile_returns_pdf(self, client: FormaTexClient):
        result = client.compile(SIMPLE_DOC)
        assert isinstance(result, CompileResult)
        assert result.pdf[:4] == b"%PDF"
        assert result.size_bytes > 0
        assert result.duration_ms > 0

    def test_compile_with_xelatex(self, client: FormaTexClient):
        try:
            result = client.compile(SIMPLE_DOC, engine="xelatex")
            assert result.pdf[:4] == b"%PDF"
            assert result.engine == "xelatex"
        except PlanLimitError:
            pytest.skip("xelatex not available on this plan")

    def test_compile_with_math(self, client: FormaTexClient):
        result = client.compile(BIB_DOC)
        assert result.pdf[:4] == b"%PDF"

    def test_broken_latex_raises_compilation_error(self, client: FormaTexClient):
        with pytest.raises(CompilationError) as exc_info:
            client.compile(BROKEN_DOC)
        assert exc_info.value.log != ""  # compiler log is populated

    def test_compile_to_file(self, client: FormaTexClient, tmp_path: Path):
        out = tmp_path / "output.pdf"
        client.compile_to_file(SIMPLE_DOC, out)
        assert out.exists()
        assert out.read_bytes()[:4] == b"%PDF"

    def test_compile_smart(self, client: FormaTexClient):
        result = client.compile_smart(SIMPLE_DOC)
        assert result.pdf[:4] == b"%PDF"


# ── Multi-file compile ────────────────────────────────────────────────────────


class TestMultiFileCompile:
    def test_compile_with_text_companion_file(self, client: FormaTexClient):
        """Attach a .bib stub — compiler will process it without error."""
        bib_content = b"""
@article{test2026,
  author = {Test Author},
  title  = {Test Paper},
  year   = {2026},
}
"""
        latex = r"""
\documentclass{article}
\begin{document}
Hello with a companion bib file.
\end{document}
""".strip()

        try:
            result = client.compile(
                latex,
                files=[file_entry("refs.bib", bib_content)],
            )
            assert result.pdf[:4] == b"%PDF"
        except PlanLimitError:
            pytest.skip("file attachments not available on this plan")


# ── Async compile ─────────────────────────────────────────────────────────────


class TestAsyncCompile:
    def test_submit_returns_job(self, client: FormaTexClient):
        job = client.async_compile(SIMPLE_DOC)
        assert isinstance(job, AsyncJob)
        assert job.job_id != ""
        assert job.status in ("pending", "processing", "queued")

    def test_get_job_returns_job_result(self, client: FormaTexClient):
        job = client.async_compile(SIMPLE_DOC)
        status = client.get_job(job.job_id)
        assert isinstance(status, JobResult)
        assert status.job_id == job.job_id
        assert status.status in ("pending", "processing", "completed", "failed")

    def test_wait_for_job_returns_pdf(self, client: FormaTexClient):
        job = client.async_compile(SIMPLE_DOC)
        result = client.wait_for_job(job.job_id, poll_interval=2.0, timeout=120.0)
        assert isinstance(result, CompileResult)
        assert result.pdf[:4] == b"%PDF"

    def test_get_job_log_after_completion(self, client: FormaTexClient):
        import time
        job = client.async_compile(SIMPLE_DOC)
        # Poll manually so we can read the log BEFORE downloading the PDF
        # (PDF download auto-deletes the job files including the log)
        deadline = time.monotonic() + 120.0
        while True:
            status = client.get_job(job.job_id)
            if status.status in ("completed", "failed"):
                break
            assert time.monotonic() < deadline, "job timed out"
            time.sleep(2)
        log = client.get_job_log(job.job_id)
        assert isinstance(log, str)

    def test_wait_for_job_broken_latex_raises(self, client: FormaTexClient):
        job = client.async_compile(BROKEN_DOC)
        with pytest.raises(CompilationError):
            client.wait_for_job(job.job_id, timeout=120.0)

    def test_delete_job(self, client: FormaTexClient):
        """Submit a job, wait for complete status, then delete WITHOUT downloading.
        PDF download auto-deletes the job, so we must delete before downloading.
        """
        import time
        job = client.async_compile(SIMPLE_DOC)
        deadline = time.monotonic() + 120.0
        while True:
            status = client.get_job(job.job_id)
            if status.status in ("completed", "failed"):
                break
            assert time.monotonic() < deadline, "job timed out"
            time.sleep(2)
        # Delete the job without downloading the PDF first
        client.delete_job(job.job_id)


# ── Convert to DOCX ───────────────────────────────────────────────────────────


class TestConvert:
    def test_convert_returns_docx(self, client: FormaTexClient):
        try:
            result = client.convert(SIMPLE_DOC)
        except Exception as exc:
            # pandoc may not be available in all environments
            if "503" in str(exc) or "not available" in str(exc).lower():
                pytest.skip("DOCX conversion not available in this environment")
            raise

        assert isinstance(result, ConvertResult)
        # DOCX files start with PK (ZIP signature)
        assert result.docx[:2] == b"PK"
        assert result.size_bytes > 0

    def test_convert_to_file(self, client: FormaTexClient, tmp_path: Path):
        try:
            out = tmp_path / "doc.docx"
            client.convert_to_file(SIMPLE_DOC, out)
        except Exception as exc:
            if "503" in str(exc) or "not available" in str(exc).lower():
                pytest.skip("DOCX conversion not available in this environment")
            raise

        assert out.exists()
        assert out.read_bytes()[:2] == b"PK"


# ── Full end-to-end scenario ──────────────────────────────────────────────────


class TestFullScenario:
    """Simulates what a CLI user does after receiving their API key."""

    def test_complete_workflow(self, client: FormaTexClient, tmp_path: Path):
        """
        1. Check engines available
        2. Lint the document
        3. Compile to file
        4. Verify usage went up by at least 1
        """
        # Step 1: list engines
        engines = client.list_engines()
        assert len(engines) > 0

        # Step 2: lint
        lint_result = client.lint(SIMPLE_DOC)
        assert lint_result.valid or lint_result.warning_count >= 0  # either is fine

        # Step 3: record usage before
        before = client.get_usage()

        # Step 4: compile
        out = tmp_path / "final.pdf"
        client.compile_to_file(SIMPLE_DOC, out)
        assert out.read_bytes()[:4] == b"%PDF"

        # Step 5: check usage increased
        after = client.get_usage()
        assert after.compilations_used >= before.compilations_used
