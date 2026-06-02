from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.mcp import db as mcp_db
from src.mcp.client import MCPClient, MCPError

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ServerCreate(BaseModel):
    name: str
    url: str
    timeout: int = 60
    transport_mode: str = "auto"


class ServerUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    timeout: int | None = None
    transport_mode: str | None = None


class ToolToggle(BaseModel):
    enabled: bool


@router.get("/servers")
def list_servers():
    return mcp_db.list_servers()


@router.post("/servers", status_code=201)
def create_server(body: ServerCreate):
    return mcp_db.create_server(body.name, body.url, body.timeout, body.transport_mode)


@router.put("/servers/{server_id}")
def update_server(server_id: str, body: ServerUpdate):
    result = mcp_db.update_server(server_id, body.name, body.url, body.timeout, body.transport_mode)
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
    server = mcp_db.get_server(server_id)
    if not server:
        raise HTTPException(404, f"Server {server_id} not found")
    client = MCPClient()
    try:
        mode = server.get("transport_mode", "auto")
        client.connect(server["url"], server.get("timeout", 60), transport_mode=mode)
        tools = client.list_tools()
        client.disconnect()
        return {"ok": True, "tools_count": len(tools), "tools": [t["name"] for t in tools]}
    except (MCPError, Exception) as e:
        raise HTTPException(400, f"Connection failed: {e}")


@router.post("/servers/{server_id}/sync")
def sync_server_tools(server_id: str):
    server = mcp_db.get_server(server_id)
    if not server:
        raise HTTPException(404, f"Server {server_id} not found")
    client = MCPClient()
    try:
        mode = server.get("transport_mode", "auto")
        client.connect(server["url"], server.get("timeout", 60), transport_mode=mode)
        tools = client.list_tools()
        client.disconnect()
    except MCPError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"Sync failed: {e}") from e

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


@router.get("/tools")
def list_tools(server_id: str | None = None):
    return mcp_db.list_tools(server_id)


@router.put("/tools/{tool_id}")
def toggle_tool(tool_id: str, body: ToolToggle):
    result = mcp_db.set_tool_enabled(tool_id, body.enabled)
    if not result:
        raise HTTPException(404, f"Tool {tool_id} not found")
    return result
