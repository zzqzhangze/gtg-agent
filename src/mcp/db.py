import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import settings, data_path

DB_PATH = Path(data_path(settings.mcp_db))


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
            transport_mode TEXT DEFAULT 'auto',
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
    # 迁移：旧表没有 transport_mode 列
    try:
        conn.execute("ALTER TABLE mcp_servers ADD COLUMN transport_mode TEXT DEFAULT 'auto'")
    except sqlite3.OperationalError:
        pass  # 列已存在


# ── Servers ──

def list_servers() -> list[dict[str, Any]]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM mcp_servers ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def get_server(server_id: str) -> dict[str, Any] | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM mcp_servers WHERE id = ?", (server_id,)).fetchone()
    return dict(row) if row else None


def create_server(name: str, url: str, timeout: int = 60, transport_mode: str = "auto") -> dict[str, Any]:
    conn = _get_conn()
    sid = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    conn.execute(
        "INSERT INTO mcp_servers (id, name, url, timeout, transport_mode, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (sid, name, url, timeout, transport_mode, now, now),
    )
    conn.commit()
    result = get_server(sid)
    assert result is not None  # just inserted
    return result


def update_server(server_id: str, name: str | None = None, url: str | None = None, timeout: int | None = None, transport_mode: str | None = None) -> dict[str, Any] | None:
    conn = _get_conn()
    existing = get_server(server_id)
    if not existing:
        return None
    new_name = name if name is not None else existing["name"]
    new_url = url if url is not None else existing["url"]
    new_timeout = timeout if timeout is not None else existing["timeout"]
    new_transport = transport_mode if transport_mode is not None else existing.get("transport_mode", "auto")
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE mcp_servers SET name=?, url=?, timeout=?, transport_mode=?, updated_at=? WHERE id=?",
        (new_name, new_url, new_timeout, new_transport, now, server_id),
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
    query = """SELECT t.*, s.name AS server_name
               FROM mcp_tools t
               JOIN mcp_servers s ON t.server_id = s.id"""
    if server_id:
        rows = conn.execute(query + " WHERE t.server_id = ? ORDER BY t.name", (server_id,)).fetchall()
    else:
        rows = conn.execute(query + " ORDER BY s.name, t.name").fetchall()
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


def set_tool_enabled(tool_id: str, enabled: bool) -> dict[str, Any] | None:
    conn = _get_conn()
    conn.execute("UPDATE mcp_tools SET enabled=? WHERE id=?", (1 if enabled else 0, tool_id))
    conn.commit()
    row = conn.execute("SELECT * FROM mcp_tools WHERE id=?", (tool_id,)).fetchone()
    return dict(row) if row else None


def get_enabled_servers() -> list[dict[str, Any]]:
    """Return servers that have at least one enabled tool."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT s.* FROM mcp_servers s JOIN mcp_tools t ON s.id = t.server_id WHERE t.enabled = 1"
    ).fetchall()
    return [dict(r) for r in rows]
