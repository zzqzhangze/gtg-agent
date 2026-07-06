import logging
from typing import Any, Optional, Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, create_model

from src.mcp.client import MCPClient

logger = logging.getLogger(__name__)

# 模块级连接缓存：同一进程内对同名 server 复用 MCPClient 实例
# key: (server_name, server_url) -> MCPClient
_CLIENT_CACHE: dict[tuple[str, str], MCPClient] = {}


def _json_schema_to_pydantic(name: str, schema: dict[str, Any] | None) -> Type[BaseModel]:
    if not schema or "properties" not in schema:
        return create_model(f"{name}Args")

    fields: dict[str, Any] = {}
    required = set(schema.get("required", []))

    for prop_name, prop_schema in schema.get("properties", {}).items():
        json_type = prop_schema.get("type", "string")
        description = prop_schema.get("description", "")

        type_map = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        py_type = type_map.get(json_type, str)

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
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)

    @classmethod
    def from_mcp_definition(cls, client: MCPClient, tool_def: dict[str, Any], server_name: str = "") -> "MCPTool":
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
    """Connect to MCP server and wrap all its tools as BaseTool instances.

    Uses a module-level connection cache (_CLIENT_CACHE) keyed by (name, url)
    so that the same server is not reconnected multiple times during a single
    agent invocation cycle.

    Returns empty list if connection fails (error logged, agent continues).
    """
    cache_key = (server_config["name"], server_config["url"])
    client = _CLIENT_CACHE.get(cache_key)
    if client is None:
        client = MCPClient()
        try:
            mode = server_config.get("transport_mode", "auto")
            client.connect(
                server_config["url"],
                server_config.get("timeout", 60),
                transport_mode=mode,
            )
        except Exception as e:
            logger.warning("Failed to load tools from %s: %s", server_config["name"], e)
            return []
        _CLIENT_CACHE[cache_key] = client

    try:
        tools_defs = client.list_tools()
        tools = []
        for td in tools_defs:
            tool = MCPTool.from_mcp_definition(client, td, server_config["name"])
            tools.append(tool)
        return tools
    except Exception as e:
        logger.warning("Failed to list tools from %s: %s", server_config["name"], e)
        return []


def clear_client_cache() -> None:
    """Disconnect and remove all cached MCP clients."""
    for key, client in list(_CLIENT_CACHE.items()):
        try:
            client.disconnect()
        except Exception:
            pass
    _CLIENT_CACHE.clear()
