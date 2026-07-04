# GTG Agent

<p>
  <img src="https://img.shields.io/badge/python-3.13-blue?logo=python" alt="Python 3.13">
  <img src="https://img.shields.io/github/license/zzqzhangze/gtg-agent" alt="License">
  <img src="https://img.shields.io/github/actions/workflow/status/zzqzhangze/gtg-agent/ci.yml?branch=master&label=CI" alt="CI">
  <img src="https://img.shields.io/badge/uv-1.0+-blue?logo=uv" alt="uv">
</p>

**From Gate to Great** — A local AI code-execution agent orchestrated by LangGraph, powered by OpenAI-compatible LLMs, with Docker sandbox isolation.

## Architecture

```
User Input ──→ Web UI ──→ FastAPI /chat ──→ LangGraph Pipeline (SqliteSaver)
                                                   │
                                                   ▼
                                            analyze_intent
                                        (LLM classification)
                                      ┌──────┼──────────────┐
                                      │      │              │
                                      ▼      ▼              ▼
                                tool_task  chat/        code_exec/
                               (MCP tools) compute     data_analysis/
                                           (direct LLM) multi_step
                                      │      │        (sandbox needed)
                                      │      │              │
                                      │      │     create_sandbox
                                      │      │     upload_files
                                      │      │     Skills + MCP
                                      │      │     run_agent(DeepAgent)
                                      │      │     detect/analyze/download
                                      │      │              │
                                      └──┬───┴──────────────┘
                                         ▼
                                   cleanup_sandbox
                                         │
                                         ▼
                                        END
```

Intent classification supports: `chat` / `compute` / `tool_task` / `code_exec` / `data_analysis` / `multi_step`. Sandbox templates are selected dynamically based on task type. Conversations are persisted to `.omo/sessions/graph.db` isolated by `session_id`.

## Quick Start

```bash
# 1. Install dependencies
uv sync

# 2. Edit config.env with your LLM endpoint (see docs/deployment.md for full config)
```

Deployment guide (sandbox service, environment variables, FAQ): [`docs/deployment.md`](docs/deployment.md).

## Project Structure

```
gtg_agent/
├── api.py              # FastAPI entry point (serves Web UI static files)
├── main.py             # CLI entry point
├── static/             # Web UI frontend files
├── pyproject.toml      # Project metadata & dependencies
├── config.env          # Environment configuration
├── AGENTS.md           # AI behavior instructions (concise)
├── CONTRIBUTING.md     # Development reference (concepts, Skills, MCP)
├── src/                # Core source code
│   ├── config.py       # Centralized config (env vars read here)
│   ├── llm.py          # LLM compatibility layer
│   ├── sandbox/        # Sandbox abstraction (async→sync bridge + template registry)
│   ├── agent/          # LangGraph orchestration (state machine)
│   │   ├── state.py    # Shared state (ledger)
│   │   ├── nodes.py    # Processing nodes (8 workshops)
│   │   └── graph.py    # Node wiring and routing
│   ├── mcp/            # MCP protocol integration
│   │   ├── client.py   # Dual-transport client (streamable-http + SSE)
│   │   ├── adapter.py  # MCPTool(BaseTool) adapter
│   │   ├── db.py       # SQLite persistence
│   │   └── router.py   # FastAPI management routes
│   └── skills/         # Skills system
│       ├── __init__.py
│       └── loader.py   # Skill discovery & sandbox upload
├── .omo/              # Runtime data (sessions/mcp/skills) + dev docs (plans/workflows)
└── docs/               # Deployment guide, design docs
    └── deployment.md   # Deployment guide
```

> AI behavior instructions: [AGENTS.md](AGENTS.md). Development reference: [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
