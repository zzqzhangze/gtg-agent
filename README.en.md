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

### Prerequisites

- Python >= 3.13
- Any OpenAI-compatible LLM service (Ollama, OpenAI API, vLLM, Azure OpenAI, DeepSeek, etc.)
- [OpenSandbox](https://open-sandbox.ai) sandbox service

### Installation

```bash
# Create .venv and install dependencies
uv sync
```

### Configuration

Copy `config.env` and edit it with your LLM endpoint:

```env
# ── LLM ──────────────────────────────────────────────────────────────
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxxxx
MODEL_NAME=gpt-4o

# ── Sandbox ──────────────────────────────────────────────────────────
SANDBOX_API_URL=http://127.0.0.1:8080
# SANDBOX_API_KEY=my-secret-api-key-007
# SANDBOX_USE_SERVER_PROXY=false
```

### Start the Sandbox

### Start the Sandbox

```bash
# Generate config (first run only)
uvx opensandbox-server init-config ~/.sandbox.toml --example docker

# Start the server (background)
uvx opensandbox-server &
```

> Windows users need Docker Desktop with WSL2 backend.
> The first start pulls the sandbox runtime images (~2-3 min).

Verify the service is ready:

```bash
curl http://127.0.0.1:8080/v1/health
```

Edit `~/.sandbox.toml` to customize. See the [official config docs](https://open-sandbox.ai/getting-started/configuration) for details.

### Run

**CLI mode (REPL):**

```bash
python main.py
# Single execution with files
python main.py "summarize this file" report.txt data.csv
```

REPL commands:

| Command | Description |
|---------|-------------|
| `/file <path>` | Add a file to the conversation |
| `/files` | List added files |
| `/clear` | Clear file list |
| `/history` | View conversation history |
| `/history all` | View all persisted sessions |
| `/history clear` | Clear current session history |
| `/history clear --all` | Clear all session history |
| `/help` | Show help |
| `/exit` or Ctrl+C | Exit |

**API server:**

```bash
uv run uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Web chat UI |
| POST | `/chat` | Send message + upload files |
| GET | `/health` | Health check |
| GET | `/files/{session_id}/{filename}` | Download processed files |
| DELETE | `/sessions/{session_id}/history` | Delete session history |
| GET | `/mcp/` | MCP management UI |

## Project Structure

```
gtg_agent/
├── api.py              # FastAPI entry point
├── main.py             # CLI entry point
├── static/             # Web UI frontend
├── pyproject.toml      # Project metadata & dependencies
├── config.env          # Environment config
├── AGENTS.md           # AI behavior instructions
├── CONTRIBUTING.md     # Development reference
├── src/                # Core source code
│   ├── config.py       # Centralized config
│   ├── llm.py          # LLM compatibility layer
│   ├── sandbox/        # Sandbox abstraction
│   ├── agent/          # LangGraph orchestration
│   └── mcp/            # MCP protocol integration
├── tests/              # Test suite
├── .omo/               # Runtime data & docs
```

## License

[MIT](LICENSE)
