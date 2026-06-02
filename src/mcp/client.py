import json
import logging
import os
import queue
import threading
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPError(Exception):
    """MCP protocol error."""


class MCPClient:
    """MCP HTTP 客户端 — 双模式传输.

    模式 1 · Streamable HTTP（直连）
      POST JSON-RPC 到同一 URL，通过 Mcp-Session-Id 头维持会话。
      第一次请求为 initialize，自动获得 session_id。

    模式 2 · SSE 传输（标准 MCP）
      GET → event:endpoint → POST 到 endpoint 指定的 URL。
      适用于所有标准 MCP SSE 服务端。

    自动检测，调用方无需感知。
    """

    def __init__(self) -> None:
        self._base_url: str = ""
        self._post_url: str = ""
        self._http: httpx.Client | None = None
        self._sse_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._response_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._connected = False
        self._transport_mode: str = ""   # "sse" | "streamable-http"
        self._session_id: str = ""       # streamable HTTP session

    # ── Public ──────────────────────────────────────────

    def connect(self, url: str, timeout: int = 60, transport_mode: str = "auto") -> None:
        """
        连接到 MCP 服务端。

        transport_mode:
          - "auto"           先试 streamable-http，失败后回退到 SSE
          - "streamable-http" 只用直连（跳过 SSE）
          - "sse"             只用 SSE（跳过直连）
        """
        self._base_url = url.rstrip("/")
        # 绕过系统代理（如 Clash / v2ray），MCP 服务器直连
        no_proxy = os.environ.get("NO_PROXY", "")
        os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1," + no_proxy
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        self._stop_event.clear()

        # 1) Streamable HTTP
        if transport_mode in ("auto", "streamable-http"):
            if self._try_streamable_http():
                self._transport_mode = "streamable-http"
                self._post_url = self._base_url
                self._connected = True
                logger.info("MCP connected (streamable HTTP): %s  session=%s",
                            self._base_url, self._session_id)
                return

        # 2) SSE（auto 时作为回退，sse 时作为唯一尝试）
        if transport_mode in ("auto", "sse"):
            if transport_mode == "sse":
                # 指定 SSE 模式时直接跳过 streamable-http，不视为失败
                pass
            self._start_sse()
            try:
                endpoint_event = self._response_queue.get(timeout=min(5, timeout))
            except queue.Empty:
                self.disconnect()
                raise MCPError(
                    f"Cannot connect to {url}: "
                    f"{'SSE timed out' if transport_mode == 'sse' else 'Streamable HTTP initialize failed and SSE timed out'}"
                ) from None

            if "endpoint" not in endpoint_event:
                self.disconnect()
                raise MCPError(f"Expected endpoint event, got: {endpoint_event}")

            raw = endpoint_event["endpoint"]
            self._post_url = raw if raw.startswith("http") else self._base_url + raw
            self._transport_mode = "sse"
            self._connected = True
            logger.info("MCP connected (SSE mode): post_url=%s", self._post_url)
            return

        # 3) 指定的模式在尝试后失败
        self.disconnect()
        raise MCPError(
            f"Cannot connect to {url}: transport_mode={transport_mode} failed"
        )

    def disconnect(self) -> None:
        self._connected = False
        self._stop_event.set()
        if self._http:
            self._http.close()
            self._http = None

    @property
    def connected(self) -> bool:
        return self._connected

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._send_request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        result = self._send_request("tools/call", {"name": name, "arguments": arguments})
        return result.get("content", [])

    # ── Transport: Streamable HTTP ──────────────────────

    def _try_streamable_http(self) -> bool:
        """POST initialize — 成功返回 True 并记录 _session_id."""
        if not self._http:
            return False
        init_body: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "my-deep-agent", "version": "1.0"},
            },
        }
        try:
            resp = self._http.post(self._base_url, json=init_body)
        except Exception as exc:
            logger.info("Streamable HTTP failed (connect): %s", exc)
            return False

        if resp.status_code >= 400:
            logger.info("Streamable HTTP rejected (%s)", resp.status_code)
            return False

        # 提取 session ID
        sid = resp.headers.get("mcp-session-id") or resp.headers.get("Mcp-Session-Id")
        if sid:
            self._session_id = sid
        # 验证响应是有效的 JSON-RPC
        try:
            data = resp.json()
        except Exception:
            logger.warning("Streamable HTTP response not JSON")
            return False

        if "error" in data:
            logger.info("Streamable HTTP initialize error: %s", data["error"])
            return False
        logger.info("Streamable HTTP handshake OK: %s", data.get("result", {}))
        return True

    # ── Transport: SSE ──────────────────────────────────

    def _start_sse(self) -> None:
        """启动 SSE reader 线程（仅 SSE 模式）。"""
        self._sse_thread = threading.Thread(
            target=self._sse_reader,
            name=f"mcp-sse-{id(self)}",
            daemon=True,
        )
        self._sse_thread.start()

    def _sse_reader(self) -> None:
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
                        pass
        except Exception as exc:
            if not self._stop_event.is_set():
                logger.error("SSE reader error: %s", exc)

    # ── Shared: send request ────────────────────────────

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._http or not self._post_url:
            raise MCPError("Not connected")

        req_id = str(uuid.uuid4())
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            body["params"] = params

        headers: dict[str, str] = {"Accept": "application/json"}
        if self._transport_mode == "streamable-http" and self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        response = self._http.post(self._post_url, json=body, headers=headers)
        response.raise_for_status()

        resp_data = response.json()
        if "error" in resp_data:
            raise MCPError(f"MCP {method} error: {resp_data['error']}")
        return resp_data.get("result", {})
