# MCP Tool Integration Implementation Plan

> status: draft
> branch: feat/mcp-integration
> created: 2026-06-01
> updated: 2026-06-01

**Goal:** Add MCP protocol tool access to my_deep_agent, with Web-based management UI for MCP server configuration and tool enable/disable.

**Architecture:** MCP HTTP SSE client → LangChain `BaseTool` adapter → inject via `create_deep_agent(tools=[...])` in the existing `run_agent` node. Server configs and tool states stored in SQLite (`.sisyphus/mcp.db`). Web UI manages servers/tools via FastAPI endpoints under `/mcp/`.

**Tech Stack:** `httpx` (SSE client), LangChain `BaseTool`, FastAPI, SQLite3, vanilla HTML/CSS/JS.

**Design doc:** `docs/mcp-skills-upgrade-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/mcp/client.py` | **Create** | MCP HTTP SSE client: connect/disconnect, list_tools, call_tool |
| `src/mcp/adapter.py` | **Create** | `MCPTool(BaseTool)`: wraps MCP tool as LangChain-compatible tool |
| `src/mcp/db.py` | **Create** | SQLite CRUD: mcp_servers + mcp_tables, auto-create DB on first use |
| `src/mcp/router.py` | **Create** | FastAPI router: 8 MCP management endpoints under `/mcp/` |
| `src/agent/nodes.py` | **Modify** | `run_agent`: load MCP tools before `create_deep_agent()` |
| `api.py` | **Modify** | Register MCP router + serve `static/mcp.html` as MCP management page |
| `static/mcp.html` | **Create** | MCP management page: server list + CRUD dialog + tool toggle table |
| `static/mcp.js` | **Create** | MCP management page logic: fetch API, CRUD operations, test/sync/toggle |
| `.sisyphus/plans/INDEX.md` | **Modify** | Register this plan |
| `AGENTS.md` | **Modify** | Add MCP-related workflow and constraint notes |

---

### Task 1: SQLite persistence layer

**Files:**
- Create: `src/mcp/db.py`
- Modify: `.sisyphus/plans/INDEX.md`

- [ ] **Step 1: Create `src/mcp/__init__.py`**

```python
```

- [ ] **Step 2: Write `src/mcp/db.py` with table creation and CRUD**

Create `src/mcp/db.py`:

```python
import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parents[2] / ".sisyphus" / "mcp.db"


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    _ensure_tables(conn)
    return conn


def _ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS mcp_servers (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            timeout INTEGER DEFAULT 60,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS mcp_tools (
            id TEXT PRIMARY KEY,
            server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            input_schema TEXT,
            enabled INTEGER DEFAULT 1,
            UNIQUE(server_id, name)
        );
    """)


# ── Servers ──

def list_servers() -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM mcp_servers ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def get_server(server_id: str) -> dict[str, Any] | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
    return dict(row) if row else None


def create_server(name: str, url: str, timeout: int = 60) -> dict[str, Any]:
    conn = _get_conn()
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO mcp_servers (id, name, url, timeout, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (sid, name, url, timeout, now, now),
    )
    conn.commit()
    return get_server(sid)


def update_server(server_id: str, name: str | None = None, url: str | None = None, timeout: int | None = None) -> dict[str, Any] | None:
    conn = _get_conn()
    existing = get_server(server_id)
    if not existing:
        return None
    new_name = name if name is not None else existing["name"]
    new_url = url if url is not None else existing["url"]
    new_timeout = timeout if timeout is not None else existing["timeout"]
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE mcp_servers SET name=?, url=?, timeout=?, updated_at=? WHERE id=?",
        (new_name, new_url, new_timeout, now, server_id),
    )
    conn.commit()
    return get_server(server_id)


def delete_server(server_id: str) -> bool:
    conn = _get_conn()
    conn.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
    conn.execute("DELETE FROM mcp_servers WHERE id = ?", (server_id,))
    conn.commit()
    return conn.total_changes > 0


# ── Tools ──

def list_tools(server_id: str | None = None) -> list[dict[str, Any]]:
    conn = _get_conn()
    if server_id:
        rows = conn.execute("SELECT * FROM mcp_tools WHERE server_id = ? ORDER BY name", (server_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM mcp_tools ORDER BY server_id, name").fetchall()
    return [dict(r) for r in rows]


def upsert_tool(server_id: str, name: str, description: str | None, input_schema: dict | None) -> dict[str, Any]:
    conn = _get_conn()
    tid = str(uuid.uuid4())
    schema_str = json.dumps(input_schema) if input_schema else None
    conn.execute(
        """INSERT INTO mcp_tools (id, server_id, name, description, input_schema, enabled)
           VALUES (?, ?, ?, ?, ?, 1)
           ON CONFLICT(server_id, name) DO UPDATE SET description=excluded.description, input_schema=excluded.input_schema""",
        (tid, server_id, name, description, schema_str),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM mcp_tools WHERE server_id=? AND name=?", (server_id, name)).fetchone()
    return dict(row)


def delete_tools_by_server(server_id: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM mcp_tools WHERE server_id = ?", (server_id,))
    conn.commit()


def set_tool_enabled(tool_id: str, enabled: bool) -> dict[str, Any] | None:
    conn = _get_conn()
    conn.execute("UPDATE mcp_tools SET enabled=? WHERE id=?", (1 if enabled else 0, tool_id))
    conn.commit()
    row = conn.execute("SELECT * FROM mcp_tools WHERE id=?", (tool_id,)).fetchone()
    return dict(row) if row else None


def get_enabled_tools() -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT t.*, s.name as server_name, s.url as server_url "
        "FROM mcp_tools t JOIN mcp_servers s ON t.server_id = s.id "
        "WHERE t.enabled = 1 "
        "ORDER BY s.name, t.name"
    ).fetchall()
    return [dict(r) for r in rows}


def get_enabled_servers() -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT s.* FROM mcp_servers s JOIN mcp_tools t ON s.id = t.server_id WHERE t.enabled = 1"
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 3: Register plan in INDEX.md**

Add to `.sisyphus/plans/INDEX.md` active plans table:

```markdown
| [mcp-tool-integration.md](./mcp-tool-integration.md) | draft | P1 | feat/mcp-integration | 2026-06-01 | 2026-06-01 |
```

- [ ] **Step 4: Commit**

```bash
git add src/mcp/__init__.py src/mcp/db.py .sisyphus/plans/INDEX.md
git commit -m "feat: add MCP SQLite persistence layer"
```

---

### Task 2: MCP HTTP SSE client

**Files:**
- Create: `src/mcp/client.py`

- [ ] **Step 1: Write `src/mcp/client.py`**

Build the MCP client with:
- `connect(url, timeout)` — open SSE stream in background thread, negotiate endpoint
- `list_tools()` — send `tools/list` JSON-RPC, return tool definitions
- `call_tool(name, args)` — send `tools/call` JSON-RPC, return result
- `disconnect()` — close SSE thread and HTTP connection

```python
import json
import logging
import queue
import threading
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP protocol error."""


class MCPClient:
    """HTTP SSE MCP client.

    Opens a long-lived SSE connection for receiving server messages,
    and uses HTTP POST for sending client requests.
    """

    def __init__(self) -> None:
        self._base_url: str = ""
        self._post_url: str = ""
        self._http: httpx.Client | None = None
        self._sse_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._response_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._connected = False

    def connect(self, url: str, timeout: int = 60) -> None:
        """Establish SSE connection to MCP server.

        Args:
            url: Full SSE endpoint URL (e.g. http://host:port/sse).
            timeout: Connection and request timeout in seconds.

        Raises:
            MCPError: If connection fails or no endpoint event received.
        """
        self._base_url = url.rstrip("/")
        self._http = httpx.Client(timeout=httpx.Timeout(timeout))
        self._stop_event.clear()

        # Start SSE reader thread
        self._sse_thread = threading.Thread(
            target=self._sse_reader,
            name=f"mcp-sse-{id(self)}",
            daemon=True,
        )
        self._sse_thread.start()

        # Wait for endpoint event
        try:
            endpoint_event = self._response_queue.get(timeout=timeout)
        except queue.Empty:
            self.disconnect()
            raise MCPError(f"MCP server at {url} did not send endpoint event within {timeout}s") from None

        if "endpoint" not in endpoint_event:
            self.disconnect()
            raise MCPError(f"Expected endpoint event, got: {endpoint_event}")

        raw = endpoint_event["endpoint"]
        self._post_url = raw if raw.startswith("http") else self._base_url + raw
        self._connected = True
        logger.info("MCP connected: post_url=%s", self._post_url)

    def disconnect(self) -> None:
        """Close SSE connection and clean up."""
        self._connected = False
        self._stop_event.set()
        if self._http:
            self._http.close()
            self._http = None

    @property
    def connected(self) -> bool:
        return self._connected

    def list_tools(self) -> list[dict[str, Any]]:
        """Call tools/list and return tool definitions.

        Returns:
            List of tool dicts with keys: name, description, inputSchema.
        """
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """Call a tool on the MCP server.

        Args:
            name: Tool name.
            arguments: Tool arguments matching the inputSchema.

        Returns:
            Tool execution result (result.content list).
        """
        result = self._send_request("tools/call", {"name": name, "arguments": arguments})
        return result.get("content", [])

    # ── Internal ──

    def _sse_reader(self) -> None:
        """Background thread: read SSE event stream."""
        if not self._http:
            return
        try:
            with self._http.stream("GET", self._base_url) as response:
                response.raise_for_status()
                current_event = ""
                for line in response.iter_lines():
                    if self._stop_event.is_set():
                        break
                    line = line.strip()
                    if not line:
                        # Empty line = end of event
                        continue
                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                    elif line.startswith("data:"):
                        data_str = line[5:].strip()
                        if current_event == "endpoint":
                            self._response_queue.put({"endpoint": data_str})
                        elif current_event == "message":
                            try:
                                msg = json.loads(data_str)
                                self._response_queue.put(msg)
                            except json.JSONDecodeError:
                                logger.warning("SSE invalid JSON: %s", data_str[:200])
                        current_event = ""
                    elif line.startswith(":"):
                        # SSE comment/keepalive
                        pass
        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("SSE reader error: %s", exc)

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Send JSON-RPC request and wait for response."""
        if not self._http or not self._post_url:
            raise MCPError("Not connected")

        req_id = str(uuid.uuid4())
        body = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
        }
        if params:
            body["params"] = params

        response = self._http.post(self._post_url, json=body)
        response.raise_for_status()

        # JSON-RPC response may come in SSE stream or HTTP response body
        resp_data = response.json()
        if "error" in resp_data:
            raise MCPError(f"MCP {method} error: {resp_data['error']}")
        return resp_data.get("result", {})
```

- [ ] **Step 2: Commit**

```bash
git add src/mcp/client.py
git commit -m "feat: add MCP HTTP SSE client"
```

---

### Task 3: MCPTool adapter (MCP → BaseTool)

**Files:**
- Create: `src/mcp/adapter.py`

- [ ] **Step 1: Write `src/mcp/adapter.py`**

Wrap each MCP tool definition as a LangChain `BaseTool`. Dynamically create Pydantic model from JSON Schema `inputSchema`.

```python
import json
from typing import Any, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from src.mcp.client import MCPClient


def _json_schema_to_pydantic(name: str, schema: dict[str, Any] | None) -> Type[BaseModel]:
    """Convert JSON Schema to a Pydantic model.

    Handles basic JSON Schema types: string, number, integer, boolean, array, object.
    Falls back to empty model if schema is None or empty.
    """
    if not schema or "properties" not in schema:
        return create_model(f"{name}Args")

    fields: dict[str, Any] = {}
    required = set(schema.get("required", []))

    for prop_name, prop_schema in schema.get("properties", {}).items():
        json_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")

        # Map JSON Schema types to Python types
        type_map = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        py_type = type_map.get(json_type, str)

        # Handle optional fields
        if prop_name not in required:
            py_type = Optional[py_type]  # type: ignore
            default = None
        else:
            default = ...

        fields[prop_name] = (py_type, Field(default=default, description=description))

    return create_model(f"{name}Args", **fields)


class MCPTool(BaseTool):
    """LangChain BaseTool that delegates execution to a remote MCP server."""

    mcp_client: MCPClient
    mcp_tool_name: str
    mcp_tool_schema: dict[str, Any] = {}

    def _run(self, **kwargs: Any) -> Any:
        result = self.mcp_client.call_tool(self.mcp_tool_name, kwargs)
        # Extract text content from MCP result content list
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

    @classmethod
    def from_mcp_definition(cls, client: MCPClient, tool_def: dict[str, Any], server_name: str = "") -> "MCPTool":
        """Create MCPTool from a MCP tools/list entry."""
        name = tool_def["name"]
        description = tool_def.get("description", "")
        if server_name:
            description = f"[{server_name}] {description}"

        schema = tool_def.get("inputSchema", {})
        args_schema = _json_schema_to_pydantic(name, schema)

        return cls(
            name=name,
            description=description,
            args_schema=args_schema,
            mcp_client=client,
            mcp_tool_name=name,
            mcp_tool_schema=schema,
        )


def build_tools_for_server(server_config: dict[str, Any]) -> list[BaseTool]:
    """Connect to an MCP server and wrap all its tools as BaseTool instances.

    Args:
        server_config: Server config dict with keys: id, name, url, timeout.

    Returns:
        List of BaseTool instances. Empty if connection fails.
    """
    client = MCPClient()
    try:
        client.connect(server_config["url"], server_config.get("timeout", 60))
        tools_defs = client.list_tools()
        tools = []
        for td in tools_defs:
            tool = MCPTool.from_mcp_definition(client, td, server_config["name"])
            tools.append(tool)
        return tools
    except Exception as e:
        logger.warning("Failed to load tools from %s: %s", server_config["name"], e)
        return []
```

- [ ] **Step 2: Commit**

```bash
git add src/mcp/adapter.py
git commit -m "feat: add MCPTool BaseTool adapter"
```

---

### Task 4: FastAPI router for MCP management

**Files:**
- Create: `src/mcp/router.py`

- [ ] **Step 1: Write `src/mcp/router.py`**

8 endpoints for MCP server/tool management.

```python
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.mcp import db as mcp_db
from src.mcp.client import MCPClient, MCPError

router = APIRouter(prefix="/mcp", tags=["mcp"])


# ── Request/Response models ──

class ServerCreate(BaseModel):
    name: str
    url: str
    timeout: int = 60


class ServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    timeout: int | None = None


class ToolToggle(BaseModel):
    enabled: bool


# ── Server endpoints ──

@router.get("/servers")
def list_servers():
    return mcp_db.list_servers()


@router.post("/servers", status_code=201)
def create_server(body: ServerCreate):
    return mcp_db.create_server(body.name, body.url, body.timeout)


@router.put("/servers/{server_id}")
def update_server(server_id: str, body: ServerUpdate):
    result = mcp_db.update_server(server_id, body.name, body.url, body.timeout)
    if not result:
        raise HTTPException(404, f"Server {server_id} not found")
    return result


@router.delete("/servers/{server_id}")
def delete_server(server_id: str):
    if not mcp_db.get_server(server_id):
        raise HTTPException(404, f"Server {server_id} not found")
    mcp_db.delete_server(server_id)
    return {"ok": True}


@router.post("/servers/{server_id}/test")
def test_server(server_id: str):
    """Test connection: connect and call tools/list."""
    server = mcp_db.get_server(server_id)
    if not server:
        raise HTTPException(404, f"Server {server_id} not found")
    client = MCPClient()
    try:
        client.connect(server["url"], server.get("timeout", 60))
        tools = client.list_tools()
        client.disconnect()
        return {"ok": True, "tools_count": len(tools), "tools": [t["name"] for t in tools]}
    except (MCPError, Exception) as e:
        raise HTTPException(400, f"Connection failed: {e}")


@router.post("/servers/{server_id}/sync")
def sync_server_tools(server_id: str):
    """Fetch tools from server and upsert into DB."""
    server = mcp_db.get_server(server_id)
    if not server:
        raise HTTPException(404, f"Server {server_id} not found")
    client = MCPClient()
    try:
        client.connect(server["url"], server.get("timeout", 60))
        tools = client.list_tools()
        client.disconnect()
    except (MCPError, Exception) as e:
        raise HTTPException(400, f"Sync failed: {e}")

    synced = []
    for td in tools:
        tool = mcp_db.upsert_tool(
            server_id=server_id,
            name=td["name"],
            description=td.get("description"),
            input_schema=td.get("inputSchema"),
        )
        synced.append(tool)
    return {"ok": True, "tools_count": len(synced)}


# ── Tool endpoints ──

@router.get("/tools")
def list_tools(server_id: str | None = None):
    return mcp_db.list_tools(server_id)


@router.put("/tools/{tool_id}")
def toggle_tool(tool_id: str, body: ToolToggle):
    result = mcp_db.set_tool_enabled(tool_id, body.enabled)
    if not result:
        raise HTTPException(404, f"Tool {tool_id} not found")
    return result
```

- [ ] **Step 2: Commit**

```bash
git add src/mcp/router.py
git commit -m "feat: add MCP management API endpoints"
```

---

### Task 5: Integrate MCP tools into agent

**Files:**
- Modify: `src/agent/nodes.py`

- [ ] **Step 1: Modify `run_agent` in `src/agent/nodes.py`**

Add MCP tool loading before `create_deep_agent()` call. Keep route B unchanged.

Insert after `backend = LangSmithBackend(sb)`:

```python
        # ── MCP tool loading ──
        mcp_additional_tools: list[BaseTool] = []
        try:
            from src.mcp.db import get_enabled_servers
            from src.mcp.adapter import build_tools_for_server

            for server in get_enabled_servers():
                tools = build_tools_for_server(server)
                mcp_additional_tools.extend(tools)
                if tools:
                    names = [t.name for t in tools]
                    print(f"[MCP] Loaded {len(tools)} tools from {server['name']}: {names}")
        except Exception as e:
            print(f"[MCP] Failed to load MCP tools: {e}")
```

Then change `create_deep_agent(tools=mcp_additional_tools or None)`.

Add import at top of `nodes.py`:

```python
from langchain_core.tools import BaseTool
```

- [ ] **Step 2: Commit**

```bash
git add src/agent/nodes.py
git commit -m "feat: integrate MCP tools into run_agent node"
```

---

### Task 6: Register routes and MCP management page in API

**Files:**
- Modify: `api.py`

- [ ] **Step 1: Register MCP router in `api.py`**

Add after existing imports:

```python
from src.mcp.router import router as mcp_router
```

Add before `if __name__` or after other router registrations:

```python
app.include_router(mcp_router)
```

Also add a static file route or inline handler to serve `static/mcp.html` at `/mcp/`.

- [ ] **Step 2: Commit**

```bash
git add api.py
git commit -m "feat: register MCP API routes in FastAPI"
```

---

### Task 7: Web management UI

**Files:**
- Create: `static/mcp.html`
- Create: `static/mcp.js`

- [ ] **Step 1: Write `static/mcp.html`**

HTML page with:
- Server list table (name, URL, timeout, status, action buttons)
- Add/Edit server dialog (name, URL, timeout fields)
- Tool list table (server name, tool name, description, enabled/disabled toggle)
- Test connection and sync buttons per server

Style: matching existing `static/style.css` dark theme.

- [ ] **Step 2: Write `static/mcp.js`**

JavaScript for:
- Load servers on page load: `GET /mcp/servers`
- Load tools on page load: `GET /mcp/tools`
- Add server: `POST /mcp/servers`
- Edit server: `PUT /mcp/servers/{id}`
- Delete server: `DELETE /mcp/servers/{id}` (confirm dialog)
- Test connection: `POST /mcp/servers/{id}/test`
- Sync tools: `POST /mcp/servers/{id}/sync`
- Toggle tool: `PUT /mcp/tools/{id}` with `{enabled: true/false}`

- [ ] **Step 3: Commit**

```bash
git add static/mcp.html static/mcp.js
git commit -m "feat: add MCP management web UI"
```

---

### Task 8: Documentation

**Files:**
- Modify: `AGENTS.md`

- [ ] **Step 1: Update AGENTS.md**

Add MCP-related constraints and workflow notes to the code constraints section:

```markdown
## MCP 工具管理

- MCP server 配置通过 Web UI（`/mcp/`）管理，持久化在 `.sisyphus/mcp.db`
- 仅 HTTP SSE 传输模式，不支持 stdio（所有操作在沙箱内）
- 启用的工具对所有会话有效，通过 `create_deep_agent(tools=[...])` 注入
- 新增 MCP server 后需在 Web UI 点击"同步"工具列表
- 新增/修改依赖需检查 `pyproject.toml`
```

- [ ] **Step 2: Update plan INDEX.md status**

Change status from `draft` to `in_progress` (at execution time).

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: add MCP tool management notes to AGENTS.md"
```
