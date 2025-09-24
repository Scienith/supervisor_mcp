# Repository Guidelines
## 用中文回答

## Project Structure & Module Organization
- `src/`: core MCP service
  - `src/server.py`: MCP server + transport
  - `src/service.py`: business logic/API calls
  - `src/file_manager.py`, `src/session.py`, `src/config.py`
- `tests/`: pytest suites (`unit/`, `mcp/`, `api/`)
- Entrypoints: `run.py` (Python), `start_mcp.sh` (shell)
- Config/assets: `.env.example`, `requirements.txt`, `docs/`

## Build, Test, and Development Commands
- Create venv + install: `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt`
- Test deps: `pip install -r test-requirements.txt`
- Run server (stdio): `python run.py`
- Run server (HTTP): `python run.py --http` (serves on `0.0.0.0:8080/mcp`)
- Start via script: `./start_mcp.sh` (loads `.env` if present)
- Run tests: `pytest -q`
- Coverage: `pytest --cov=src --cov-report=term-missing`

## Coding Style & Naming Conventions
- Python 3.8+, PEP 8, 4‑space indent.
- Names: modules/files `snake_case`; classes `PascalCase`; functions/vars `snake_case`.
- Use type hints and docstrings on public functions; prefer small, pure helpers.
- Keep I/O and process wiring in `server.py`/`service.py`; isolate file logic in `file_manager.py`.
- Optional formatting: `black` and `isort` are welcome (not required).

## Testing Guidelines
- Frameworks: `pytest`, `pytest-asyncio`, `pytest-mock`.
- Async tests use `@pytest.mark.asyncio`.
- Location/naming: `tests/**/test_*.py`; write focused unit tests with mocks.
- Aim for >80% coverage; all tests must pass locally before PR.

## Commit & Pull Request Guidelines
- Prefer Conventional Commits (history is mixed):
  - Examples: `feat: implement login_with_project`, `fix: correct project path`.
- PRs should include:
  - Clear description and rationale; link issues.
  - Tests for behavior changes; update docs/README if user-facing tools change.
  - Logs/screenshots when behavior or ergonomics change.
- Keep diffs small and cohesive; avoid unrelated refactors.

## Security & Configuration Tips
- Never commit secrets. Use `.env` from `.env.example`.
- Key vars: `SUPERVISOR_API_URL`; for `login_with_project`: `SUPERVISOR_USERNAME`, `SUPERVISOR_PASSWORD`, `SUPERVISOR_PROJECT_ID`.
- `.supervisor/` and `supervisor_workspace/` are per‑project and git‑ignored.

## Agent‑Specific Notes
- Follow this file for any automated changes.
- Keep changes minimal and targeted; no license headers.
- Touch tests when changing tool behavior; reference `src/server.py`, `src/service.py`.

