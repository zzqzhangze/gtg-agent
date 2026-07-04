# Changelog

## [Unreleased]

### Added

- OpenSandbox sandbox image address now configurable via `SANDBOX_IMAGE` env var
- `docker-compose.yml` for one-click OpenSandbox deployment
- Test suite with 30+ unit tests (intent parsing, MCP DB CRUD)
- CI workflow (pytest + ruff via GitHub Actions)
- `.github/` issue templates (bug report, feature request) and PR template
- English README (`README.en.md`)
- `SECURITY.md` and `CODE_OF_CONDUCT.md`
- `CHANGELOG.md`
- README badges (Python version, License, CI, uv)

### Changed

- `AGENTS.md` streamlined from 144 lines to ~67 lines, reference content moved to `CONTRIBUTING.md`
- `pyproject.toml`: added Bug Tracker, Documentation, Changelog URLs; expanded keywords
- `src/mcp/db.py`: `datetime.utcnow()` replaced with `datetime.now(UTC)`

## [0.1.0] - 2026-06-11

### Added

- Initial release
- LangGraph orchestration pipeline with 7 nodes
- LLM-driven intent classification (`chat`, `compute`, `tool_task`, `code_exec`, `data_analysis`, `multi_step`)
- OpenSandbox + LangSmith sandbox backends
- MCP protocol integration with dual-mode transport (Streamable HTTP + SSE)
- Skills system with progressive disclosure
- Web UI with chat interface, MCP management panel
- REPL CLI mode
- File upload, download, and batch zip
- Session persistence via SqliteSaver
- Full Chinese documentation
