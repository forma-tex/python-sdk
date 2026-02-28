# Changelog

All notable changes to this project will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.0.4] - 2026-02-28

### Removed
- `base_url` and `staging` constructor parameters removed from public API

---

## [1.0.3] - 2026-02-20

### Fixed
- Package renamed to lowercase `formatex` throughout for PEP 8 compliance

---

## [1.0.0] - 2026-02-18

### Added
- Initial release
- `FormaTexClient` with full API coverage: `compile`, `compile_smart`, `compile_to_file`, `async_compile`, `wait_for_job`, `get_job`, `get_job_pdf`, `get_job_log`, `delete_job`, `check_syntax`, `lint`, `convert`, `convert_to_file`, `get_usage`, `list_engines`
- `file_entry()` helper for attaching companion files
- Typed exceptions: `FormaTexError`, `AuthenticationError`, `CompilationError`, `RateLimitError`, `PlanLimitError`
- Sync and async context manager support
- Python ≥ 3.9, only dependency: `httpx`
