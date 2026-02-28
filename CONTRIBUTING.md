# Contributing to the FormaTex Python SDK

Thanks for your interest in contributing!

## Before You Start

- For **bug reports** and **feature requests**, open a GitHub Issue first.
- For **security vulnerabilities**, see [SECURITY.md](SECURITY.md) — do **not** open a public issue.

## Development Setup

```bash
git clone https://github.com/forma-tex/python-sdk.git
cd python-sdk
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run unit tests:

```bash
pytest tests/ -v
```

## Making Changes

1. Fork the repo and create a branch from `main`: `git checkout -b fix/my-fix`
2. Make your changes in `formatex/`
3. Ensure `pytest tests/` passes
4. Update `README.md` if you changed the public API
5. Open a pull request

## Pull Request Guidelines

- Keep PRs focused — one fix or feature per PR
- Write a clear PR description explaining **what** and **why**
- Do not bump the version in `pyproject.toml` — maintainers handle releases

## Code Style

- Python ≥ 3.9, type hints required on all public functions
- No additional runtime dependencies beyond `httpx`

## Releasing (maintainers only)

1. Update `version` in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Commit: `git commit -m "chore: release vX.Y.Z"`
4. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
5. GitHub Actions publishes to PyPI automatically

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
