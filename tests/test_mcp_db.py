"""Tests for MCP database layer (src/mcp/db.py).

Uses an in-memory SQLite database by monkey-patching the DB path.
"""

import pytest
import sqlite3
from pathlib import Path
from unittest.mock import patch

import src.mcp.db as mcp_db


@pytest.fixture(autouse=True)
def in_memory_db(monkeypatch):
    """Replace DB_PATH with an in-memory SQLite database for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")

    # Create tables
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

    # Replace _get_conn to return our in-memory connection
    original_get_conn = mcp_db._get_conn

    def mock_get_conn():
        return conn

    monkeypatch.setattr(mcp_db, "_get_conn", mock_get_conn)
    yield conn
    conn.close()


class TestMCPServers:
    """CRUD operations for MCP servers."""

    def test_create_and_list(self):
        created = mcp_db.create_server("test-server", "http://localhost:9999")
        assert created["name"] == "test-server"
        assert created["url"] == "http://localhost:9999"

        servers = mcp_db.list_servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "test-server"

    def test_get_server(self):
        created = mcp_db.create_server("get-test", "http://get:8080")
        fetched = mcp_db.get_server(created["id"])
        assert fetched is not None
        assert fetched["name"] == "get-test"

    def test_get_nonexistent_returns_none(self):
        assert mcp_db.get_server("nonexistent-id") is None

    def test_update_server(self):
        created = mcp_db.create_server("old-name", "http://old:8080")
        updated = mcp_db.update_server(created["id"], name="new-name")
        assert updated is not None
        assert updated["name"] == "new-name"
        assert updated["url"] == "http://old:8080"  # unchanged

    def test_delete_server(self):
        created = mcp_db.create_server("delete-me", "http://del:8080")
        assert mcp_db.delete_server(created["id"]) is True
        assert mcp_db.get_server(created["id"]) is None
        assert len(mcp_db.list_servers()) == 0

    def test_delete_nonexistent_returns_false(self):
        assert mcp_db.delete_server("nonexistent") is False


class TestMCPTools:
    """Tool operations tied to servers."""

    def test_upsert_and_list(self):
        server = mcp_db.create_server("tool-server", "http://tools:8080")
        tool = mcp_db.upsert_tool(server["id"], "get_weather", "Get weather data", {"type": "object"})
        assert tool["name"] == "get_weather"
        assert tool["enabled"] == 1

        tools = mcp_db.list_tools()
        assert len(tools) == 1

    def test_upsert_twice_is_idempotent(self):
        server = mcp_db.create_server("idempotent", "http://idem:8080")
        mcp_db.upsert_tool(server["id"], "tool_a", "desc 1", None)
        mcp_db.upsert_tool(server["id"], "tool_a", "desc 2", None)
        tools = mcp_db.list_tools(server_id=server["id"])
        assert len(tools) == 1
        assert tools[0]["description"] == "desc 2"

    def test_set_tool_enabled(self):
        server = mcp_db.create_server("toggle", "http://toggle:8080")
        tool = mcp_db.upsert_tool(server["id"], "toggler", "toggle test", None)
        mcp_db.set_tool_enabled(tool["id"], enabled=False)
        updated = mcp_db.set_tool_enabled(tool["id"], enabled=True)
        assert updated["enabled"] == 1

    def test_get_enabled_servers(self):
        s1 = mcp_db.create_server("enabled-srv", "http://enabled:8080")
        s2 = mcp_db.create_server("disabled-srv", "http://disabled:8080")
        mcp_db.upsert_tool(s1["id"], "active_tool", "active", None)
        # s2 has no tools → not returned
        enabled = mcp_db.get_enabled_servers()
        ids = [s["id"] for s in enabled]
        assert s1["id"] in ids
        assert s2["id"] not in ids
