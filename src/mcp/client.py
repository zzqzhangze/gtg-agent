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
        self._base_url = url.rstrip("/")
        self._http = httpx.Client(timeout=httpx.Timeout(timeout))
        self._stop_event.clear()

        self._sse_thread = threading.Thread(
            target=self._sse_reader,
            name=f"mcp-sse-{id(self)}",
            daemon=True,
        )
        self._sse_thread.start()

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

    # ── Internal ──

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

    def _send_request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self._http or not self._post_url:
            raise MCPError("Not connected")

        req_id = str(uuid.uuid4())
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": req_id, "method": method}
        if params:
            body["params"] = params

        response = self._http.post(self._post_url, json=body)
        response.raise_for_status()

        resp_data = response.json()
        if "error" in resp_data:
            raise MCPError(f"MCP {method} error: {resp_data['error']}")
        return resp_data.get("result", {})
