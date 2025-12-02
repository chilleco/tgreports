# Repository Guidelines

## Project Structure & Module Organization
- Python package lives in `tgreports/` with the public entrypoint in `tgreports/__init__.py` and core logic in `tgreports/main.py`.
- Tests are in `tests/`; keep fixtures and helpers alongside test modules.
- Packaging metadata is in `pyproject.toml`; legacy `setup.py` remains for compatibility. Docs live in `docs/`.
- Build artifacts land in `build/` and `dist/` when created; keep them out of commits.

## Build, Test, and Development Commands
- Create a venv (defaulting to Python 3.10): `PYTHON_BIN=python3.10 make setup` (runtime) or `PYTHON_BIN=python3.10 make setup-tests` (runtime + dev/test extras).
- Run full test + lint suite: `make test` (invokes pylint and pytest).
- Release artifacts: `make release` (builds via `python -m build` then uploads with twine).
- Manual installs: `pip install -e .` for runtime, `pip install -e ".[dev]"` for dev/test tooling.

## Coding Style & Naming Conventions
- Python 3.8+ codebase; prefer f-strings and type-friendly patterns.
- Follow Pylint defaults with `tests/.pylintrc`; keep functions small and avoid broad excepts unless already used.
- Modules and files: lowercase with underscores (`report_utils.py`); tests mirror module names (`test_main.py`).
- Use docstrings on public functions/classes; keep inline comments minimal and purposeful.

## Testing Guidelines
- Frameworks: `pytest` with `pytest-asyncio` for async flows.
- Naming: test files `test_*.py`; functions `test_<behavior>`.
- Run all tests: `make test-unit-all` or `pytest -q tests`.
- Avoid external network/TG calls in tests; stub `Telegram.send` if needed.

## Commit & Pull Request Guidelines
- Commits: use concise, imperative messages (e.g., “Add Telegram request helper”).
- PRs: include what changed, why, and how to verify (commands run); link issues/tickets when relevant. Screenshots/log snippets welcome when behavior is user-facing.

## Security & Configuration Tips
- Keep secrets (TG tokens/chat IDs) out of commits; use environment variables when running locally.
- Generated logs (`app.log`, `app.err`, `test_app.log`, `test_app.err`) should stay untracked.*** End Patch+```
